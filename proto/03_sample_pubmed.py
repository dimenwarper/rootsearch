#!/usr/bin/env python3
"""Proto 03: Probe PubMed E-utilities and PMC OA full-text XML.

Fetches 20 drug discovery review abstracts via NCBI E-utilities,
then fetches 3 PMC OA full-text XMLs and extracts signal sections.
Saves to data/samples/pubmed_drug_discovery.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rich.console import Console
from rich.table import Table

from rootsearch.ingest.pubmed import (
    search_pubmed, fetch_abstracts, fetch_drug_discovery_reviews,
    fetch_pmc_fulltext_sections
)
from rootsearch.graph.builder import save_jsonl

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def sample_pubmed_abstracts(n: int = 20):
    console.rule("[bold cyan]PubMed: Drug Discovery Reviews[/]")

    console.print(f"Fetching {n} drug discovery reviews...")
    papers = fetch_drug_discovery_reviews(max_results=n)
    console.print(f"  Got {len(papers)} papers")

    if not papers:
        console.print("[red]No papers — PubMed may require NCBI_API_KEY or rate limiting.[/]")
        return []

    # Stats
    has_abstract = sum(1 for p in papers if p.abstract.strip())

    table = Table(title=f"PubMed drug discovery — {len(papers)} papers")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Papers fetched", str(len(papers)))
    table.add_row("With abstract", f"{has_abstract} ({100*has_abstract//max(len(papers),1)}%)")
    console.print(table)

    # Print sample abstracts
    console.print("\n[bold]Sample abstracts:[/]")
    for p in papers[:3]:
        console.print(f"\n  [yellow]{p.title[:80]}[/]")
        console.print(f"  PMID={p.id}  year={p.year}")
        if p.abstract:
            console.print(f"  {p.abstract[:300]}...")
        else:
            console.print("  [red](no abstract)[/]")

    # Extract PMIDs that could be PMC IDs (some papers have OA full text)
    console.print("\n[bold]Checking for OA URLs...[/]")
    oa_papers = [p for p in papers if p.oa_url]
    console.print(f"  {len(oa_papers)} papers with OA URL")
    for p in oa_papers[:3]:
        console.print(f"  {p.id}: {p.oa_url}")

    # Save
    out = SAMPLES_DIR / "pubmed_drug_discovery.jsonl"
    save_jsonl([p.model_dump() for p in papers], out)
    console.print(f"\n[dim]Saved {len(papers)} records → {out}[/]")

    return papers


def sample_pmc_fulltext(n_papers: int = 3):
    console.rule("[bold cyan]PMC OA Full-text XML[/]")

    # Try a few known PMC IDs for drug discovery reviews
    # These are open access review articles on drug discovery
    test_pmc_ids = [
        "PMC7914182",   # drug discovery review
        "PMC8236509",   # AI in drug discovery
        "PMC9478741",   # target identification
    ]

    success_count = 0
    for pmc_id in test_pmc_ids[:n_papers]:
        console.print(f"\n[cyan]Fetching PMC full text: {pmc_id}[/]")
        try:
            sections = fetch_pmc_fulltext_sections(pmc_id)
            if sections:
                success_count += 1
                console.print(f"  [green]Got {len(sections)} sections: {list(sections.keys())}[/]")
                for sec_name, sec_text in sections.items():
                    word_count = len(sec_text.split())
                    console.print(f"\n  [bold]Section: {sec_name}[/] ({word_count} words)")
                    preview = sec_text[:400].replace("\n", " ")
                    console.print(f"  {preview}...")
            else:
                console.print("  [yellow]No signal sections found.[/]")
        except Exception as e:
            console.print(f"  [red]PMC fetch failed: {e}[/]")

    console.print(f"\n[dim]{success_count}/{n_papers} PMC articles had extractable signal sections[/]")


def main():
    papers = sample_pubmed_abstracts(n=20)
    sample_pmc_fulltext(n_papers=3)

    console.rule("[bold]Key findings to check[/]")
    console.print("  1. How many PubMed abstracts mention dependency language ('requires', 'bottleneck', 'lacking')?")
    console.print("  2. Do PMC XML section names match 'conclusions', 'future', 'discussion'?")
    console.print("  3. Does NCBI rate limiting kick in (need NCBI_API_KEY)?")

    # Quick dependency-language scan on abstracts
    if papers:
        dep_words = ["requires", "bottleneck", "lack", "challenge", "missing",
                     "needed", "limited by", "unable to", "open question"]
        hits = 0
        for p in papers:
            if any(w in p.abstract.lower() for w in dep_words):
                hits += 1
        console.print(f"\n  Dependency language in abstracts: {hits}/{len(papers)} ({100*hits//max(len(papers),1)}%)")


if __name__ == "__main__":
    main()
