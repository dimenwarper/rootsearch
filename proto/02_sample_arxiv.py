#!/usr/bin/env python3
"""Proto 02: Probe arXiv API and LaTeX section parser.

Fetches 10 papers per field from arXiv, downloads 3 LaTeX sources,
tests the section regex, prints extracted signal sections.
Saves to data/samples/arxiv_{field}.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from rootsearch.ingest.arxiv import (
    FIELD_CATEGORIES, fetch_papers, extract_latex_sections
)
from rootsearch.graph.builder import save_jsonl

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def sample_field_arxiv(field: str, n: int = 10, n_latex: int = 3):
    console.rule(f"[bold cyan]arXiv Field: {field}[/]")
    categories = FIELD_CATEGORIES.get(field, [])
    console.print(f"  Categories: {', '.join(categories)}")

    # Fetch papers via arXiv API
    console.print(f"Fetching {n} papers...")
    papers = fetch_papers(field, max_results=n)
    console.print(f"  Got {len(papers)} papers")

    if not papers:
        console.print("[red]No papers fetched — skipping.[/]")
        return []

    # Stats
    has_abstract = sum(1 for p in papers if p.abstract.strip())
    has_oa_url = sum(1 for p in papers if p.oa_url)

    table = Table(title=f"{field} arXiv — {len(papers)} papers")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Papers fetched", str(len(papers)))
    table.add_row("With abstract", f"{has_abstract} ({100*has_abstract//max(len(papers),1)}%)")
    table.add_row("With OA URL", f"{has_oa_url} ({100*has_oa_url//max(len(papers),1)}%)")
    console.print(table)

    # Print first 3 paper titles/abstracts
    console.print("\n[bold]Sample papers:[/]")
    for p in papers[:3]:
        console.print(f"\n  [yellow]{p.title[:80]}[/]")
        console.print(f"  id={p.id}  year={p.year}")
        if p.abstract:
            console.print(f"  {p.abstract[:200]}...")

    # Try LaTeX section extraction on first n_latex papers
    console.rule(f"[bold]LaTeX section extraction — {field}[/]")
    n_with_sections = 0
    for p in papers[:n_latex]:
        arxiv_id = p.id
        console.print(f"\n[cyan]Attempting LaTeX download for {arxiv_id}...[/]")
        try:
            sections = extract_latex_sections(arxiv_id)
            if sections:
                n_with_sections += 1
                console.print(f"  [green]Found {len(sections)} signal sections: {list(sections.keys())}[/]")
                for sec_title, sec_text in sections.items():
                    word_count = len(sec_text.split())
                    console.print(f"\n  [bold]Section: {sec_title}[/] ({word_count} words)")
                    # Print first 400 chars
                    preview = sec_text[:400].replace("\n", " ")
                    console.print(f"  {preview}...")
            else:
                console.print("  [yellow]No signal sections found in LaTeX source.[/]")
        except Exception as e:
            console.print(f"  [red]LaTeX download failed: {e}[/]")

    console.print(f"\n[dim]{n_with_sections}/{n_latex} papers had extractable signal sections[/]")

    # Save to JSONL
    out = SAMPLES_DIR / f"arxiv_{field}.jsonl"
    save_jsonl([p.model_dump() for p in papers], out)
    console.print(f"[dim]Saved {len(papers)} records → {out}[/]")

    return papers


def main():
    all_results = {}
    for field in ["materials_science", "ai_ml"]:
        papers = sample_field_arxiv(field, n=10, n_latex=3)
        all_results[field] = papers

    console.rule("[bold]Summary[/]")
    for field, papers in all_results.items():
        console.print(f"  {field:25s}  {len(papers):3d} papers")

    console.print("\n[bold]Key findings to check:[/]")
    console.print("  1. Do section titles match our SIGNAL_SECTIONS regex?")
    console.print("  2. Are section lengths reasonable (100-3000 words)?")
    console.print("  3. Does abstract text overlap with the arxiv search field?")


if __name__ == "__main__":
    main()
