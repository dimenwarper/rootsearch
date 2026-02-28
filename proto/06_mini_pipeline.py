#!/usr/bin/env python3
"""Proto 06: Mini end-to-end pipeline.

Runs the full Phase 0 pipeline on a tiny dataset:
  - OpenAlex: 10 papers per field (3 fields)
  - arXiv: 5 papers per field with LaTeX extraction (2 fields)
  - Node extraction via Claude
  - Dedup via embeddings (+ optional LLM)
  - Graph build
  - Cascade + cross-field + bottleneck scoring
  - Rich leaderboard of top leverage nodes

Usage:
  python proto/06_mini_pipeline.py [--no-llm]  # skip LLM calls for pure API testing
  python proto/06_mini_pipeline.py              # full run
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from rootsearch.models import Paper, Node, Edge
from rootsearch.ingest.openalex import fetch_reviews, fetch_top_cited
from rootsearch.ingest.arxiv import fetch_papers, extract_latex_sections
from rootsearch.extract.nodes import extract_nodes_from_paper, extract_nodes_from_section
from rootsearch.extract.edges import extract_edges_from_text
from rootsearch.graph.dedup import dedup_nodes
from rootsearch.graph.builder import build_graph, graph_stats, save_jsonl, load_nodes_jsonl, load_edges_jsonl
from rootsearch.analysis.scoring import compute_leverage_index

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

PIPELINE_FIELDS = ["materials_science", "drug_discovery", "ai_ml"]
ARXIV_FIELDS = ["materials_science", "ai_ml"]

NODE_COLORS = {
    "open_problem": "yellow",
    "capability_gap": "cyan",
    "data_gap": "magenta",
    "infrastructure_gap": "red",
    "theoretical_gap": "blue",
    "engineering_bottleneck": "orange3",
}


# ─── Step 1: Ingest ──────────────────────────────────────────────────────────

def ingest_papers(use_cache: bool = True) -> list[Paper]:
    """Fetch or load papers from OpenAlex and arXiv."""
    cache_path = SAMPLES_DIR / "pipeline_papers.jsonl"
    if use_cache and cache_path.exists():
        console.print(f"[dim]Loading cached papers from {cache_path}[/]")
        papers = []
        with open(cache_path) as f:
            for line in f:
                papers.append(Paper(**json.loads(line)))
        console.print(f"  Loaded {len(papers)} papers from cache")
        return papers

    papers = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        # OpenAlex
        for field in PIPELINE_FIELDS:
            task = progress.add_task(f"OpenAlex: {field} reviews...", total=None)
            try:
                reviews = fetch_reviews(field, max_results=10)
                papers.extend(reviews)
                progress.update(task, description=f"OpenAlex {field}: {len(reviews)} reviews ✓")
            except Exception as e:
                progress.update(task, description=f"OpenAlex {field}: FAILED ({e})")
            time.sleep(0.3)

            task2 = progress.add_task(f"OpenAlex: {field} top-cited...", total=None)
            try:
                top = fetch_top_cited(field, max_results=10)
                papers.extend(top)
                progress.update(task2, description=f"OpenAlex {field} top-cited: {len(top)} ✓")
            except Exception as e:
                progress.update(task2, description=f"OpenAlex {field} top-cited: FAILED ({e})")
            time.sleep(0.3)

        # arXiv
        for field in ARXIV_FIELDS:
            task = progress.add_task(f"arXiv: {field}...", total=None)
            try:
                arxiv_papers = fetch_papers(field, max_results=5)
                papers.extend(arxiv_papers)
                progress.update(task, description=f"arXiv {field}: {len(arxiv_papers)} ✓")
            except Exception as e:
                progress.update(task, description=f"arXiv {field}: FAILED ({e})")
            time.sleep(0.5)

    # Deduplicate by title (rough)
    seen_titles = set()
    unique = []
    for p in papers:
        key = p.title.lower().strip()[:60]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(p)
    console.print(f"\n[bold]Ingest complete:[/] {len(papers)} total → {len(unique)} unique papers")

    save_jsonl([p.model_dump() for p in unique], cache_path)
    console.print(f"[dim]Cached to {cache_path}[/]")
    return unique


# ─── Step 2: LaTeX section extraction (arXiv papers only) ────────────────────

def extract_arxiv_sections(papers: list[Paper], n_max: int = 5) -> dict[str, dict]:
    """Try LaTeX section extraction for arXiv papers. Returns {arxiv_id: sections}."""
    arxiv_papers = [p for p in papers if p.source == "arxiv"][:n_max]
    results = {}

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for p in arxiv_papers:
            task = progress.add_task(f"LaTeX: {p.id}...", total=None)
            try:
                sections = extract_latex_sections(p.id)
                if sections:
                    results[p.id] = sections
                    progress.update(task, description=f"LaTeX {p.id}: {len(sections)} sections ✓")
                else:
                    progress.update(task, description=f"LaTeX {p.id}: no signal sections")
            except Exception as e:
                progress.update(task, description=f"LaTeX {p.id}: FAILED ({e})")
            time.sleep(1.0)

    console.print(f"\n[bold]LaTeX extraction:[/] {len(results)}/{len(arxiv_papers)} papers had signal sections")
    return results


# ─── Step 3: LLM extraction ──────────────────────────────────────────────────

def extract_all_nodes(
    papers: list[Paper],
    latex_sections: dict[str, dict],
    n_papers: int = 9,
    skip_llm: bool = False,
) -> tuple[list[Node], list[Edge]]:
    """Run Pass 1 + Pass 2 on papers. Returns (nodes, edges)."""
    if skip_llm:
        console.print("[yellow]--no-llm: skipping LLM extraction[/]")
        return [], []

    all_nodes: list[Node] = []
    all_edges: list[Edge] = []

    # Select diverse papers: 3 per field
    by_field: dict[str, list[Paper]] = {}
    for p in papers:
        for f in (p.fields or ["unknown"]):
            by_field.setdefault(f, []).append(p)

    selected: list[Paper] = []
    seen_ids = set()
    for f in PIPELINE_FIELDS:
        for p in by_field.get(f, [])[:3]:
            if p.id not in seen_ids:
                selected.append(p)
                seen_ids.add(p.id)
    # Fill up to n_papers
    for p in papers:
        if len(selected) >= n_papers:
            break
        if p.id not in seen_ids:
            selected.append(p)
            seen_ids.add(p.id)

    console.print(f"\n[bold]LLM extraction on {len(selected)} papers...[/]")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for i, paper in enumerate(selected):
            task = progress.add_task(f"[{i+1}/{len(selected)}] {paper.title[:45]}...", total=None)
            try:
                # Pass 1: nodes from abstract
                nodes = extract_nodes_from_paper(paper)

                # Also extract from LaTeX sections if available
                if paper.id in latex_sections:
                    for sec_title, sec_text in latex_sections[paper.id].items():
                        sec_nodes = extract_nodes_from_section(sec_text, sec_title, paper.id)
                        nodes.extend(sec_nodes)

                # Pass 2: edges
                if nodes:
                    context = (
                        f"Paper: {paper.title}\nAbstract: {paper.abstract}\n\n"
                        "Identified nodes:\n" +
                        "\n".join(f"- [{n.type}] {n.title}" for n in nodes)
                    )
                    edges, stubs = extract_edges_from_text(context, nodes, paper.id, "paper")
                    all_edges.extend(edges)
                    all_nodes.extend(stubs)

                all_nodes.extend(nodes)
                progress.update(task, description=f"[{i+1}/{len(selected)}] ✓ {len(nodes)} nodes, {len(edges) if nodes else 0} edges")
            except Exception as e:
                progress.update(task, description=f"[{i+1}/{len(selected)}] FAILED: {e}")

            time.sleep(0.5)

    console.print(f"\n[bold]Extraction complete:[/] {len(all_nodes)} nodes, {len(all_edges)} edges (before dedup)")
    return all_nodes, all_edges


# ─── Step 4: Dedup ───────────────────────────────────────────────────────────

def deduplicate(nodes: list[Node]) -> list[Node]:
    if not nodes:
        console.print("[yellow]No nodes to dedup.[/]")
        return []

    console.print(f"\n[bold]Deduplication:[/] {len(nodes)} nodes → embedding...")
    try:
        merged = dedup_nodes(nodes, threshold=0.85, use_llm=False)
        console.print(f"  {len(nodes)} → {len(merged)} nodes ({len(nodes)-len(merged)} merged)")
        return merged
    except Exception as e:
        console.print(f"[red]Dedup failed: {e}[/]")
        return nodes


# ─── Step 5: Graph build + scoring ───────────────────────────────────────────

def build_and_score(nodes: list[Node], edges: list[Edge]):
    if not nodes:
        console.print("[yellow]No nodes to build graph.[/]")
        return None, []

    console.print(f"\n[bold]Building graph:[/] {len(nodes)} nodes, {len(edges)} edges")
    G = build_graph(nodes, edges)
    stats = graph_stats(G)

    # Print graph stats
    table = Table(title="Graph Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for k, v in stats.items():
        table.add_row(str(k), str(v))
    console.print(table)

    # Scoring
    console.print("\n[bold]Computing leverage scores...[/]")
    try:
        ranked = compute_leverage_index(G)
    except Exception as e:
        console.print(f"[red]Scoring failed: {e}[/]")
        return G, []

    return G, ranked


# ─── Step 6: Leaderboard ─────────────────────────────────────────────────────

def print_leaderboard(G, ranked: list, top_n: int = 15):
    if not ranked:
        console.print("[yellow]No scores to display.[/]")
        return

    table = Table(
        title=f"🏆 Top-{top_n} High-Leverage Nodes",
        show_lines=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Type", width=18)
    table.add_column("Title", width=42)
    table.add_column("Fields", width=18)
    table.add_column("Leverage", width=9, justify="right")
    table.add_column("Cascade", width=8, justify="right")
    table.add_column("CrossF", width=7, justify="right")
    table.add_column("Btw", width=7, justify="right")

    for rank, (node_id, score, components) in enumerate(ranked[:top_n], 1):
        data = G.nodes.get(node_id, {})
        ntype = data.get("type", "?")
        title = data.get("title", node_id)[:40]
        fields = ", ".join((data.get("fields") or [])[:2])
        color = NODE_COLORS.get(ntype, "white")
        table.add_row(
            str(rank),
            f"[{color}]{ntype}[/]",
            title,
            fields,
            f"[bold]{score:.4f}[/]",
            f"{components.get('cascade', 0):.4f}",
            f"{components.get('cross_field', 0):.4f}",
            f"{components.get('bottleneck', 0):.4f}",
        )

    console.print(table)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="rootsearch mini pipeline")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM calls (API testing only)")
    parser.add_argument("--no-cache", action="store_true", help="Re-fetch all data (ignore cache)")
    parser.add_argument("--n-papers", type=int, default=9, help="Number of papers to extract from (default 9)")
    args = parser.parse_args()

    console.print(Panel(
        "[bold]rootsearch[/] — Phase 0 Mini Pipeline\n"
        f"Fields: {', '.join(PIPELINE_FIELDS)}\n"
        f"LLM extraction: {'[red]DISABLED[/]' if args.no_llm else '[green]ENABLED[/]'}\n"
        f"Papers to extract: {args.n_papers}",
        title="Pipeline Config",
        border_style="blue"
    ))

    # 1. Ingest
    console.rule("[bold]Step 1: Ingest[/]")
    papers = ingest_papers(use_cache=not args.no_cache)

    # 2. LaTeX sections
    console.rule("[bold]Step 2: LaTeX Section Extraction[/]")
    latex_sections = extract_arxiv_sections(papers, n_max=5)

    # 3. LLM extraction
    console.rule("[bold]Step 3: LLM Node + Edge Extraction[/]")
    nodes, edges = extract_all_nodes(papers, latex_sections, n_papers=args.n_papers, skip_llm=args.no_llm)

    # Save raw extraction
    if nodes:
        save_jsonl([n.model_dump() for n in nodes], SAMPLES_DIR / "pipeline_nodes_raw.jsonl")
    if edges:
        save_jsonl([e.model_dump() for e in edges], SAMPLES_DIR / "pipeline_edges_raw.jsonl")

    # 4. Dedup
    console.rule("[bold]Step 4: Deduplication[/]")
    nodes = deduplicate(nodes)

    if nodes:
        save_jsonl([n.model_dump() for n in nodes], SAMPLES_DIR / "pipeline_nodes_deduped.jsonl")

    # 5. Graph + scoring
    console.rule("[bold]Step 5: Graph Build + Scoring[/]")
    G, ranked = build_and_score(nodes, edges)

    if ranked:
        save_jsonl(
            [{"node_id": nid, "leverage": s, "components": c} for nid, s, c in ranked],
            SAMPLES_DIR / "pipeline_scores.jsonl"
        )

    # 6. Leaderboard
    console.rule("[bold]Step 6: Leaderboard[/]")
    if G is not None and ranked:
        print_leaderboard(G, ranked, top_n=15)
    else:
        console.print("[yellow]No graph to display. Try running with LLM extraction enabled.[/]")
        console.print("[dim]Run without --no-llm and ensure ANTHROPIC_API_KEY is set.[/]")

    console.rule("[bold]Pipeline Complete[/]")
    console.print(f"  Papers ingested:   {len(papers)}")
    console.print(f"  LaTeX extractions: {len(latex_sections)}")
    console.print(f"  Nodes extracted:   {len(nodes)}")
    console.print(f"  Edges extracted:   {len(edges)}")
    console.print(f"  Top leverage node: {ranked[0][0] if ranked else 'N/A'}")
    console.print(f"\n  Data saved to: {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
