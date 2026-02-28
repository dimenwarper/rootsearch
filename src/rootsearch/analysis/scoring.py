"""Cascade scoring and leverage index computation.

cascade_score:       iterative propagation — importance flows outward from enablers
cross_field_leverage: BFS reachability across field domains
bottleneck_centrality: betweenness centrality over ENABLES edges only
leverage_index:      weighted composite of all three
"""

from __future__ import annotations

import networkx as nx
from rich.console import Console

console = Console()


# ── Helpers ──────────────────────────────────────────────

def _enables_subgraph(G: nx.DiGraph) -> nx.DiGraph:
    """Return a subgraph containing only ENABLES and PRODUCES_FOR edges."""
    edges = [
        (u, v, d) for u, v, d in G.edges(data=True)
        if d.get("type") in ("ENABLES", "PRODUCES_FOR")
    ]
    sub = nx.DiGraph()
    sub.add_nodes_from(G.nodes(data=True))
    for u, v, d in edges:
        sub.add_edge(u, v, **d)
    return sub


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a score dict to [0, 1]."""
    if not scores:
        return scores
    lo = min(scores.values())
    hi = max(scores.values())
    if hi == lo:
        return {k: 0.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


# ── Cascade score ─────────────────────────────────────────

def compute_cascade_scores(
    G: nx.DiGraph,
    max_iterations: int = 100,
    damping: float = 0.85,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """
    Iterative cascade propagation over ENABLES and PRODUCES_FOR edges.

    Each node's importance starts at 1.0 and grows based on what it enables.
    Nodes that enable high-importance nodes accumulate high scores.
    Damping prevents infinite accumulation in cycles.

    Returns: node_id → cascade_score (unnormalized)
    """
    sub = _enables_subgraph(G)
    nodes = list(sub.nodes())

    importance: dict[str, float] = {n: 1.0 for n in nodes}
    scores: dict[str, float] = {n: 0.0 for n in nodes}

    for iteration in range(max_iterations):
        new_scores: dict[str, float] = {}
        for node in nodes:
            outbound = list(sub.out_edges(node, data=True))
            new_scores[node] = sum(
                d.get("strength", 0.5) * d.get("confidence", 0.7) * importance[target]
                for _, target, d in outbound
            )

        # Update importance: base 1.0 + damped cascade contribution
        importance = {n: 1.0 + damping * new_scores[n] for n in nodes}

        # Check convergence
        delta = max(abs(new_scores[n] - scores[n]) for n in nodes)
        scores = new_scores
        if delta < tolerance:
            console.print(f"[dim]Cascade scores converged after {iteration + 1} iterations[/]")
            break

    return scores


# ── Cross-field leverage ──────────────────────────────────

def compute_cross_field_leverage(G: nx.DiGraph) -> dict[str, float]:
    """
    BFS from each node over ENABLES/PRODUCES_FOR edges.
    Score = number of unique top-level domains reachable,
    weighted by depth (closer nodes count more).

    Returns: node_id → cross_field_leverage_score
    """
    sub = _enables_subgraph(G)
    scores: dict[str, float] = {}

    for start in sub.nodes():
        start_domains = {
            f.split(".")[0]
            for f in (sub.nodes[start].get("fields") or [])
        }
        reachable_domains: dict[str, float] = {}  # domain → max weight seen

        # BFS with depth tracking
        queue = [(start, 1.0)]  # (node, weight)
        visited = {start}

        while queue:
            node, weight = queue.pop(0)
            for _, neighbor, edata in sub.out_edges(node, data=True):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                edge_weight = weight * edata.get("strength", 0.5) * edata.get("confidence", 0.7)
                for f in (sub.nodes[neighbor].get("fields") or []):
                    domain = f.split(".")[0]
                    if domain not in start_domains:  # only count cross-field domains
                        reachable_domains[domain] = max(
                            reachable_domains.get(domain, 0.0), edge_weight
                        )
                queue.append((neighbor, edge_weight))

        scores[start] = sum(reachable_domains.values())

    return scores


# ── Bottleneck centrality ─────────────────────────────────

def compute_bottleneck_centrality(G: nx.DiGraph) -> dict[str, float]:
    """
    Betweenness centrality computed only over ENABLES/PRODUCES_FOR edges.
    Uses inverse of edge weight (strength * confidence) so stronger edges
    are preferred paths — nodes on many strong paths score higher.

    Returns: node_id → betweenness_centrality_score
    """
    sub = _enables_subgraph(G)

    if sub.number_of_edges() == 0:
        return {n: 0.0 for n in sub.nodes()}

    # Add weight attribute for betweenness (inverse of strength*conf so strong paths are short)
    for u, v, d in sub.edges(data=True):
        w = d.get("strength", 0.5) * d.get("confidence", 0.7)
        sub[u][v]["btwn_weight"] = 1.0 / max(w, 1e-6)

    try:
        centrality = nx.betweenness_centrality(
            sub, weight="btwn_weight", normalized=True
        )
    except Exception as e:
        console.print(f"[yellow]Betweenness centrality error: {e}[/]")
        centrality = {n: 0.0 for n in sub.nodes()}

    return centrality


# ── Composite leverage index ──────────────────────────────

def compute_leverage_index(
    G: nx.DiGraph,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float, dict[str, float]]]:
    """
    Compute the composite leverage index for all nodes.

    Default weights: cascade=0.45, cross_field=0.30, bottleneck=0.25

    Returns: sorted list of (node_id, leverage_score, component_scores)
             highest leverage first.
    """
    w = weights or {"cascade": 0.45, "cross_field": 0.30, "bottleneck": 0.25}

    console.print("[bold]Computing cascade scores...[/]")
    cascade = compute_cascade_scores(G)

    console.print("[bold]Computing cross-field leverage...[/]")
    cross_field = compute_cross_field_leverage(G)

    console.print("[bold]Computing bottleneck centrality...[/]")
    bottleneck = compute_bottleneck_centrality(G)

    # Normalize each metric to [0, 1]
    cascade_n    = _normalize(cascade)
    cross_field_n = _normalize(cross_field)
    bottleneck_n  = _normalize(bottleneck)

    results: list[tuple[str, float, dict[str, float]]] = []
    for node_id in G.nodes():
        c  = cascade_n.get(node_id, 0.0)
        cf = cross_field_n.get(node_id, 0.0)
        bt = bottleneck_n.get(node_id, 0.0)
        score = (
            w["cascade"]     * c +
            w["cross_field"] * cf +
            w["bottleneck"]  * bt
        )
        results.append((node_id, score, {
            "cascade": c,
            "cross_field": cf,
            "bottleneck": bt,
        }))

    results.sort(key=lambda x: -x[1])
    return results
