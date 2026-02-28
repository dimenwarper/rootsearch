"""Embedding-based deduplication and entity resolution for nodes.

Uses sentence-transformers (all-MiniLM-L6-v2, ~80MB) for local embeddings.
No bulk downloads required — the model is fetched once and cached by HuggingFace.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import numpy as np
from rich.console import Console

from rootsearch.models import Node

if TYPE_CHECKING:
    pass

console = Console()

_EMBED_MODEL = None


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer
        console.print("[dim]Loading sentence-transformers model (first run downloads ~80MB)...[/]")
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL


def embed_nodes(nodes: list[Node]) -> np.ndarray:
    """Embed node titles + descriptions. Returns (N, dim) float32 array."""
    model = _get_embed_model()
    texts = [f"{n.title}. {n.description}" for n in nodes]
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)
    return np.array(embeddings, dtype=np.float32)


def cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity. Returns (N, N) float32 array."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    normed = embeddings / norms
    return normed @ normed.T


def find_duplicate_clusters(
    nodes: list[Node],
    embeddings: np.ndarray | None = None,
    threshold: float = 0.85,
) -> list[list[int]]:
    """
    Find clusters of potentially duplicate nodes using cosine similarity.
    Returns a list of clusters, each cluster is a list of node indices.
    Nodes not in any cluster (no duplicates) are not returned.
    """
    if embeddings is None:
        embeddings = embed_nodes(nodes)

    sim = cosine_similarity_matrix(embeddings)
    n = len(nodes)
    visited = set()
    clusters: list[list[int]] = []

    for i in range(n):
        if i in visited:
            continue
        # Find all nodes similar to i
        similar = [j for j in range(n) if j != i and sim[i, j] >= threshold]
        if similar:
            cluster = [i] + similar
            for idx in cluster:
                visited.add(idx)
            clusters.append(cluster)

    return clusters


def simple_merge(nodes_in_cluster: list[Node]) -> Node:
    """
    Merge a cluster of duplicate nodes into one canonical node without an LLM call.
    Takes the node with the highest confidence as the base; merges sources.
    Used as a fast fallback when no LLM is available.
    """
    base = max(nodes_in_cluster, key=lambda n: n.confidence)
    merged = base.model_copy()

    # Merge sources from all cluster members
    seen_source_ids = {s.source_id for s in merged.sources}
    for node in nodes_in_cluster:
        if node.node_id == base.node_id:
            continue
        for src in node.sources:
            if src.source_id not in seen_source_ids:
                merged.sources.append(src)
                seen_source_ids.add(src.source_id)

    # Use max confidence
    merged.confidence = max(n.confidence for n in nodes_in_cluster)

    return merged


def llm_disambiguate_cluster(
    nodes_in_cluster: list[Node],
    model: str = "claude-haiku-4-5",
) -> tuple[str, list[Node]]:
    """
    Use Claude to decide: MERGE, HIERARCHY, or DISTINCT for a cluster of similar nodes.

    Returns:
        (decision, resolved_nodes) where decision is one of "MERGE", "HIERARCHY", "DISTINCT"
        and resolved_nodes is the resulting list of nodes after the decision.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    cluster_text = "\n\n".join(
        f"Node {i+1}:\n  Title: {n.title}\n  Type: {n.type}\n  "
        f"Granularity: {n.granularity}\n  Description: {n.description}"
        for i, n in enumerate(nodes_in_cluster)
    )

    prompt = f"""These nodes were extracted from different sources and may describe the same scientific problem.

{cluster_text}

Decide ONE of:
A) MERGE — they are the same problem. Produce a single canonical title and merged description.
B) HIERARCHY — they are related but at different granularity levels. State which is parent and which is child.
C) DISTINCT — they are genuinely different despite surface similarity. Explain briefly.

Respond in JSON: {{"decision": "MERGE"|"HIERARCHY"|"DISTINCT", "canonical_title": "...", "canonical_description": "...", "reason": "..."}}"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.content[0].text.strip()
        # Extract JSON even if there's surrounding text
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return "DISTINCT", nodes_in_cluster
        result = json.loads(m.group())
        decision = result.get("decision", "DISTINCT").upper()

        if decision == "MERGE":
            merged = simple_merge(nodes_in_cluster)
            merged.title = result.get("canonical_title", merged.title)[:200]
            merged.description = result.get("canonical_description", merged.description)
            return "MERGE", [merged]

        elif decision == "HIERARCHY" and len(nodes_in_cluster) >= 2:
            # Keep all nodes but set parent-child links (simplified: first=parent, rest=children)
            parent = nodes_in_cluster[0]
            for child in nodes_in_cluster[1:]:
                child_copy = child.model_copy()
                child_copy.parent_id = parent.node_id
                parent.children_ids.append(child_copy.node_id)
            return "HIERARCHY", nodes_in_cluster

        else:
            return "DISTINCT", nodes_in_cluster

    except Exception as e:
        console.print(f"[yellow]LLM disambiguate error: {e} — defaulting to DISTINCT[/]")
        return "DISTINCT", nodes_in_cluster


def dedup_nodes(
    nodes: list[Node],
    threshold: float = 0.85,
    use_llm: bool = False,
    model: str = "claude-haiku-4-5",
) -> list[Node]:
    """
    Full dedup pipeline: embed → cluster → merge/resolve.
    If use_llm=False, uses simple_merge (fast, no API cost).
    """
    if len(nodes) < 2:
        return nodes

    console.print(f"[dim]Deduplicating {len(nodes)} nodes (threshold={threshold})...[/]")
    embeddings = embed_nodes(nodes)
    clusters = find_duplicate_clusters(nodes, embeddings, threshold)

    if not clusters:
        console.print(f"[dim]No duplicates found.[/]")
        return nodes

    console.print(f"[dim]Found {len(clusters)} duplicate clusters.[/]")

    # Index of nodes to keep/replace
    cluster_indices: set[int] = {i for cluster in clusters for i in cluster}
    result: list[Node] = [n for i, n in enumerate(nodes) if i not in cluster_indices]

    for cluster in clusters:
        cluster_nodes = [nodes[i] for i in cluster]
        if use_llm:
            _, resolved = llm_disambiguate_cluster(cluster_nodes, model=model)
            result.extend(resolved)
        else:
            result.append(simple_merge(cluster_nodes))

    console.print(f"[dim]After dedup: {len(result)} nodes (removed {len(nodes) - len(result)})[/]")
    return result
