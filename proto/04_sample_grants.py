#!/usr/bin/env python3
"""Proto 04: Probe NSF Awards API and NIH RePORTER.

Fetches 20 grants per agency per field, prints abstract patterns,
looks for dependency language. Saves to data/samples/grants_{field}.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rich.console import Console
from rich.table import Table

from rootsearch.ingest.grants import (
    fetch_nsf_grants, fetch_nih_grants, NSF_PROGRAMS, NIH_TERMS
)
from rootsearch.graph.builder import save_jsonl

console = Console()
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


# Words that signal explicit dependency / gap language in grant abstracts
DEPENDENCY_SIGNALS = [
    "requires", "bottleneck", "lack of", "lacking", "challenge",
    "missing", "needed", "limited by", "unable to", "open question",
    "no existing", "absence of", "developing a", "current methods fail",
    "barrier", "gap", "insufficient", "fundamental challenge",
    "critical need", "to address", "to overcome", "to enable",
]


def scan_for_dependency_language(abstracts: list[str]) -> dict:
    """Count dependency signal words across a list of abstracts."""
    counts = {w: 0 for w in DEPENDENCY_SIGNALS}
    for abstract in abstracts:
        low = abstract.lower()
        for signal in DEPENDENCY_SIGNALS:
            if signal in low:
                counts[signal] += 1
    return {k: v for k, v in sorted(counts.items(), key=lambda x: -x[1]) if v > 0}


def sample_nsf_grants(field: str, n: int = 20):
    console.rule(f"[bold cyan]NSF Grants: {field}[/]")
    programs = NSF_PROGRAMS.get(field, [])
    console.print(f"  Program codes: {', '.join(programs)}")

    grants = fetch_nsf_grants(field, max_results=n)
    console.print(f"  Got {len(grants)} NSF grants")

    if not grants:
        console.print("[yellow]No NSF grants — API may be unavailable.[/]")
        return []

    # Stats
    has_abstract = sum(1 for g in grants if g.abstract.strip())
    avg_len = sum(len(g.abstract.split()) for g in grants) // max(len(grants), 1)

    table = Table(title=f"NSF {field} — {len(grants)} grants")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Grants fetched", str(len(grants)))
    table.add_row("With abstract", f"{has_abstract} ({100*has_abstract//max(len(grants),1)}%)")
    table.add_row("Avg abstract length (words)", str(avg_len))
    console.print(table)

    # Print 2 sample abstracts
    console.print("\n[bold]Sample NSF abstracts:[/]")
    for g in grants[:2]:
        console.print(f"\n  [yellow]{g.title[:80]}[/]")
        console.print(f"  id={g.id}  year={g.year}  amount=${g.amount:,.0f}" if g.amount else f"  id={g.id}  year={g.year}")
        console.print(f"  {g.abstract[:300]}...")

    # Dependency language scan
    abstracts = [g.abstract for g in grants if g.abstract]
    dep_counts = scan_for_dependency_language(abstracts)
    if dep_counts:
        console.print(f"\n[bold]Dependency signal words (out of {len(abstracts)} abstracts):[/]")
        for word, count in list(dep_counts.items())[:10]:
            pct = 100 * count // max(len(abstracts), 1)
            console.print(f"  {word!r:40s}  {count:3d} ({pct}%)")

    return grants


def sample_nih_grants(field: str, n: int = 20):
    console.rule(f"[bold cyan]NIH Grants: {field}[/]")
    terms = NIH_TERMS.get(field, [])
    console.print(f"  Search terms: {', '.join(terms)}")

    grants = fetch_nih_grants(field, max_results=n)
    console.print(f"  Got {len(grants)} NIH grants")

    if not grants:
        console.print("[yellow]No NIH grants — API may be unavailable.[/]")
        return []

    # Stats
    has_abstract = sum(1 for g in grants if g.abstract.strip())
    avg_len = sum(len(g.abstract.split()) for g in grants) // max(len(grants), 1)

    table = Table(title=f"NIH {field} — {len(grants)} grants")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Grants fetched", str(len(grants)))
    table.add_row("With abstract", f"{has_abstract} ({100*has_abstract//max(len(grants),1)}%)")
    table.add_row("Avg abstract length (words)", str(avg_len))
    console.print(table)

    # Print 2 sample abstracts
    console.print("\n[bold]Sample NIH abstracts:[/]")
    for g in grants[:2]:
        console.print(f"\n  [yellow]{g.title[:80]}[/]")
        console.print(f"  id={g.id}  year={g.year}")
        console.print(f"  {g.abstract[:300]}...")

    # Dependency language scan
    abstracts = [g.abstract for g in grants if g.abstract]
    dep_counts = scan_for_dependency_language(abstracts)
    if dep_counts:
        console.print(f"\n[bold]Dependency signal words (out of {len(abstracts)} abstracts):[/]")
        for word, count in list(dep_counts.items())[:10]:
            pct = 100 * count // max(len(abstracts), 1)
            console.print(f"  {word!r:40s}  {count:3d} ({pct}%)")

    return grants


def main():
    all_grants = {}

    # NSF: materials + AI
    for field in ["materials_science", "ai_ml"]:
        nsf = sample_nsf_grants(field, n=20)
        all_grants[f"nsf_{field}"] = nsf
        if nsf:
            out = SAMPLES_DIR / f"grants_nsf_{field}.jsonl"
            save_jsonl([g.model_dump() for g in nsf], out)
            console.print(f"[dim]Saved {len(nsf)} records → {out}[/]")

    # NIH: drug discovery + AI
    for field in ["drug_discovery", "ai_ml"]:
        nih = sample_nih_grants(field, n=20)
        all_grants[f"nih_{field}"] = nih
        if nih:
            out = SAMPLES_DIR / f"grants_nih_{field}.jsonl"
            save_jsonl([g.model_dump() for g in nih], out)
            console.print(f"[dim]Saved {len(nih)} records → {out}[/]")

    console.rule("[bold]Summary[/]")
    for source, grants in all_grants.items():
        console.print(f"  {source:30s}  {len(grants):3d} grants")

    console.rule("[bold]Key findings to check[/]")
    console.print("  1. Are grant abstracts more explicit about gaps than paper abstracts?")
    console.print("  2. Do NSF/NIH abstracts use future tense ('will develop', 'to create')?")
    console.print("  3. What fraction of grants name a specific bottleneck?")


if __name__ == "__main__":
    main()
