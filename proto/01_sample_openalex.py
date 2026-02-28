#!/usr/bin/env python3
"""Proto 01: Probe OpenAlex API.

Fetches 20 review papers per seed field, prints schema, validates topic IDs,
checks abstract availability.  Saves to data/samples/openalex_{field}.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import httpx
from rich.console import Console
from rich.table import Table

from rootsearch.ingest.openalex import (
    FIELD_TOPICS, fetch_reviews, fetch_top_cited, search_topics
)
from rootsearch.graph.builder import save_jsonl

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def validate_topic_ids():
    """Check that our hardcoded topic IDs are real OpenAlex topics."""
    console.rule("[bold]Validating topic IDs[/]")
    for field, ids in FIELD_TOPICS.items():
        console.print(f"\n[cyan]{field}[/]")
        # Search for topics by name to verify
        sample_searches = {
            "materials_science": "materials science",
            "ai_ml": "machine learning",
            "drug_discovery": "drug discovery",
        }
        results = search_topics(sample_searches.get(field, field), max_results=5)
        for r in results:
            console.print(f"  {r.get('id','?').split('/')[-1]}  {r.get('display_name','?')}")


def sample_field(field: str, n: int = 20):
    console.rule(f"[bold cyan]Field: {field}[/]")

    # Fetch reviews
    console.print(f"Fetching up to {n} review papers...")
    reviews = fetch_reviews(field, max_results=n)
    console.print(f"  Got {len(reviews)} reviews")

    # Fetch top-cited
    console.print(f"Fetching up to {n} top-cited papers...")
    top = fetch_top_cited(field, max_results=n)
    console.print(f"  Got {len(top)} top-cited")

    all_papers = reviews + top

    # Stats
    has_abstract = sum(1 for p in all_papers if p.abstract.strip())
    has_oa_url   = sum(1 for p in all_papers if p.oa_url)

    table = Table(title=f"{field} — sample stats")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total papers", str(len(all_papers)))
    table.add_row("With abstract", f"{has_abstract} ({100*has_abstract//max(len(all_papers),1)}%)")
    table.add_row("With OA URL",   f"{has_oa_url}   ({100*has_oa_url//max(len(all_papers),1)}%)")
    table.add_row("Reviews",       str(len(reviews)))
    console.print(table)

    # Print 3 sample abstracts
    console.print("\n[bold]Sample abstracts:[/]")
    for p in all_papers[:3]:
        console.print(f"\n  [yellow]{p.title[:80]}[/]")
        console.print(f"  year={p.year}  citations={p.cited_by_count}  review={p.is_review}")
        if p.abstract:
            console.print(f"  {p.abstract[:300]}...")
        else:
            console.print("  [red](no abstract)[/]")

    # Save to JSONL
    out = SAMPLES_DIR / f"openalex_{field}.jsonl"
    with open(out, "w") as f:
        for p in all_papers:
            f.write(p.model_dump_json() + "\n")
    console.print(f"\n[dim]Saved {len(all_papers)} records → {out}[/]")

    return all_papers


def main():
    validate_topic_ids()

    all_results = {}
    for field in ["materials_science", "ai_ml", "drug_discovery"]:
        papers = sample_field(field, n=20)
        all_results[field] = papers

    console.rule("[bold]Summary[/]")
    for field, papers in all_results.items():
        total   = len(papers)
        w_abs   = sum(1 for p in papers if p.abstract.strip())
        console.print(f"  {field:25s}  {total:3d} papers  {w_abs:3d} with abstract")


if __name__ == "__main__":
    main()
