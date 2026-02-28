#!/usr/bin/env python3
"""Proto 05: Test LLM node + edge extraction on a small sample.

Loads saved OpenAlex samples (from proto 01), picks 3 papers,
runs Pass 1 (node extraction) and Pass 2 (edge extraction) via Claude.
Prints extracted nodes and edges as Rich tables.
Saves to data/samples/extracted_nodes.jsonl + extracted_edges.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rich.console import Console
from rich.table import Table

from rootsearch.models import Paper
from rootsearch.extract.nodes import extract_nodes_from_paper
from rootsearch.extract.edges import extract_edges_from_text
from rootsearch.graph.builder import save_jsonl

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# Node type → color
NODE_COLORS = {
    "open_problem": "yellow",
    "capability_gap": "cyan",
    "data_gap": "magenta",
    "infrastructure_gap": "red",
    "theoretical_gap": "blue",
    "engineering_bottleneck": "orange3",
}

EDGE_COLORS = {
    "ENABLES": "green",
    "PRODUCES_FOR": "cyan",
}


def load_sample_papers(field: str, n: int = 3) -> list[Paper]:
    """Load papers from a saved JSONL sample file."""
    path = SAMPLES_DIR / f"openalex_{field}.jsonl"
    if not path.exists():
        console.print(f"[red]No sample file {path} — run proto 01 first.[/]")
        return []
    papers = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            papers.append(Paper(**data))
    return papers[:n]


def print_nodes_table(nodes, title: str):
    if not nodes:
        console.print(f"[yellow]No nodes extracted for: {title}[/]")
        return
    table = Table(title=title, show_lines=True)
    table.add_column("Type", width=20)
    table.add_column("L", width=3, justify="center")
    table.add_column("Title", width=40)
    table.add_column("Conf", width=6, justify="right")
    table.add_column("Fields", width=20)
    for n in nodes:
        color = NODE_COLORS.get(n.type, "white")
        table.add_row(
            f"[{color}]{n.type}[/]",
            str(n.granularity),
            n.title[:38] if n.title else "—",
            f"{n.confidence:.2f}",
            ", ".join(n.fields[:2]) if n.fields else "—",
        )
    console.print(table)


def print_edges_table(edges, nodes_by_id, title: str):
    if not edges:
        console.print(f"[yellow]No edges extracted for: {title}[/]")
        return
    table = Table(title=title, show_lines=True)
    table.add_column("Type", width=14)
    table.add_column("Source", width=35)
    table.add_column("Target", width=35)
    table.add_column("Str", width=5, justify="right")
    table.add_column("Conf", width=5, justify="right")
    for e in edges:
        color = EDGE_COLORS.get(e.type, "white")
        src_title = nodes_by_id.get(e.source_node_id, {}).get("title", e.source_node_id)[:33]
        tgt_title = nodes_by_id.get(e.target_node_id, {}).get("title", e.target_node_id)[:33]
        table.add_row(
            f"[{color}]{e.type}[/]",
            src_title,
            tgt_title,
            f"{e.strength:.2f}",
            f"{e.confidence:.2f}",
        )
    console.print(table)


def run_extraction_for_field(field: str, n_papers: int = 3):
    console.rule(f"[bold cyan]LLM Extraction: {field}[/]")

    papers = load_sample_papers(field, n=n_papers)
    if not papers:
        return [], []

    all_nodes = []
    all_edges = []

    for i, paper in enumerate(papers):
        console.print(f"\n[bold]Paper {i+1}/{len(papers)}:[/] {paper.title[:70]}...")
        console.print(f"  Abstract: {len(paper.abstract.split())} words")

        # Pass 1: node extraction
        try:
            nodes = extract_nodes_from_paper(paper)
            console.print(f"  [green]Pass 1 extracted {len(nodes)} nodes[/]")
            print_nodes_table(nodes, f"Nodes from: {paper.title[:50]}")
            all_nodes.extend(nodes)
        except Exception as e:
            console.print(f"  [red]Pass 1 failed: {e}[/]")
            nodes = []

        # Pass 2: edge extraction (needs node context)
        if nodes:
            # Build context text from abstract + node summaries
            context_text = (
                f"Paper: {paper.title}\n\n"
                f"Abstract: {paper.abstract}\n\n"
                f"Identified problems/gaps:\n" +
                "\n".join(f"- [{n.type}] {n.title}: {n.description[:100]}" for n in nodes)
            )
            try:
                edges, stub_nodes = extract_edges_from_text(
                    context_text,
                    nodes,
                    source_id=paper.id,
                    source_type="paper"
                )
                console.print(f"  [green]Pass 2 extracted {len(edges)} edges, {len(stub_nodes)} cross-field stubs[/]")
                nodes_by_id = {n.node_id: {"title": n.title} for n in nodes + stub_nodes}
                print_edges_table(edges, nodes_by_id, f"Edges from: {paper.title[:50]}")
                all_edges.extend(edges)
                all_nodes.extend(stub_nodes)
            except Exception as e:
                console.print(f"  [red]Pass 2 failed: {e}[/]")

    return all_nodes, all_edges


def main():
    all_nodes = []
    all_edges = []

    for field in ["materials_science", "drug_discovery"]:
        nodes, edges = run_extraction_for_field(field, n_papers=3)
        all_nodes.extend(nodes)
        all_edges.extend(edges)

    # Summary
    console.rule("[bold]Extraction Summary[/]")
    type_counts = {}
    for n in all_nodes:
        type_counts[n.type] = type_counts.get(n.type, 0) + 1

    table = Table(title="Extracted Nodes by Type")
    table.add_column("Node Type")
    table.add_column("Count", justify="right")
    for ntype, count in sorted(type_counts.items()):
        color = NODE_COLORS.get(ntype, "white")
        table.add_row(f"[{color}]{ntype}[/]", str(count))
    table.add_row("[bold]TOTAL[/]", f"[bold]{len(all_nodes)}[/]")
    console.print(table)

    edge_types = {}
    for e in all_edges:
        edge_types[e.type] = edge_types.get(e.type, 0) + 1
    console.print(f"\nEdge types: {edge_types}")
    console.print(f"Total edges: {len(all_edges)}")

    # Save
    if all_nodes:
        out_nodes = SAMPLES_DIR / "extracted_nodes.jsonl"
        save_jsonl([n.model_dump() for n in all_nodes], out_nodes)
        console.print(f"\n[dim]Saved {len(all_nodes)} nodes → {out_nodes}[/]")

    if all_edges:
        out_edges = SAMPLES_DIR / "extracted_edges.jsonl"
        save_jsonl([e.model_dump() for e in all_edges], out_edges)
        console.print(f"[dim]Saved {len(all_edges)} edges → {out_edges}[/]")

    console.rule("[bold]Key findings to check[/]")
    console.print("  1. Are extracted node types well-distributed or skewed?")
    console.print("  2. Do edge strengths correlate with the mechanism descriptions?")
    console.print("  3. How many cross-field stub nodes were created?")
    console.print("  4. Token cost per paper? (check Anthropic dashboard)")


if __name__ == "__main__":
    main()
