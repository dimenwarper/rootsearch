"""Build a NetworkX directed graph from Node and Edge lists."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from rich.console import Console

from rootsearch.models import Edge, Node

console = Console()


def build_graph(nodes: list[Node], edges: list[Edge]) -> nx.DiGraph:
    """
    Construct a NetworkX DiGraph from canonical Node and Edge objects.

    Node attributes stored: type, granularity, title, description,
    fields, confidence, status, extraction_method.

    Edge attributes stored: type, strength, confidence, mechanism.
    """
    G = nx.DiGraph()

    for node in nodes:
        G.add_node(
            node.node_id,
            title=node.title,
            type=node.type,
            granularity=node.granularity,
            description=node.description,
            fields=node.fields,
            confidence=node.confidence,
            status=node.status,
            extraction_method=node.extraction_method,
            cross_field_ref=node.cross_field_ref,
        )

    for edge in edges:
        # Skip edges referencing unknown nodes
        if edge.source_node_id not in G or edge.target_node_id not in G:
            continue
        if edge.source_node_id == edge.target_node_id:
            continue
        G.add_edge(
            edge.source_node_id,
            edge.target_node_id,
            edge_id=edge.edge_id,
            type=edge.type,
            strength=edge.strength,
            confidence=edge.confidence,
            mechanism=edge.mechanism,
            extraction_method=edge.extraction_method,
        )

    return G


def graph_stats(G: nx.DiGraph) -> dict:
    """Return a summary stats dict for a graph."""
    node_types: dict[str, int] = {}
    field_counts: dict[str, int] = {}
    orphans = 0

    for nid, data in G.nodes(data=True):
        nt = data.get("type", "unknown")
        node_types[nt] = node_types.get(nt, 0) + 1
        for f in data.get("fields", []):
            domain = f.split(".")[0]
            field_counts[domain] = field_counts.get(domain, 0) + 1
        if G.degree(nid) == 0:
            orphans += 1

    edge_types: dict[str, int] = {}
    cross_field_edges = 0
    for u, v, data in G.edges(data=True):
        et = data.get("type", "unknown")
        edge_types[et] = edge_types.get(et, 0) + 1
        u_fields = {f.split(".")[0] for f in G.nodes[u].get("fields", [])}
        v_fields = {f.split(".")[0] for f in G.nodes[v].get("fields", [])}
        if u_fields and v_fields and not u_fields.intersection(v_fields):
            cross_field_edges += 1

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "orphan_nodes": orphans,
        "orphan_pct": round(orphans / max(G.number_of_nodes(), 1) * 100, 1),
        "cross_field_edges": cross_field_edges,
        "node_types": dict(sorted(node_types.items(), key=lambda x: -x[1])),
        "edge_types": edge_types,
        "field_distribution": dict(sorted(field_counts.items(), key=lambda x: -x[1])),
    }


def save_jsonl(items: list, path: Path) -> None:
    """Save a list of Pydantic models or plain dicts to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for item in items:
            if hasattr(item, "model_dump_json"):
                f.write(item.model_dump_json() + "\n")
            else:
                f.write(json.dumps(item) + "\n")
    console.print(f"[dim]Saved {len(items)} records → {path}[/]")


def load_nodes_jsonl(path: Path) -> list[Node]:
    nodes = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    nodes.append(Node.model_validate_json(line))
                except Exception as e:
                    console.print(f"[yellow]Node parse error: {e}[/]")
    return nodes


def load_edges_jsonl(path: Path) -> list[Edge]:
    edges = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    edges.append(Edge.model_validate_json(line))
                except Exception as e:
                    console.print(f"[yellow]Edge parse error: {e}[/]")
    return edges
