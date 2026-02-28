"""NSF Awards API + NIH RePORTER ingestion client."""

from __future__ import annotations

import time

import httpx
from rich.console import Console

from rootsearch.models import Grant

console = Console()

NSF_BASE = "https://api.nsf.gov/services/v1/awards.json"
NIH_BASE = "https://api.reporter.nih.gov/v2/projects/search"


# ── NSF ──────────────────────────────────────────────────

NSF_PROGRAMS: dict[str, list[str]] = {
    "materials_science": ["DMR", "CMMI", "CBET"],   # Division of Materials Research, etc.
    "ai_ml":             ["IIS", "CCF", "OAC"],
    "drug_discovery":    ["MCB", "DBI", "CHEM"],
}


def fetch_nsf_grants(field: str, max_results: int = 20, *, delay: float = 1.0) -> list[Grant]:
    """Fetch NSF award abstracts for a given seed field."""
    program_codes = NSF_PROGRAMS.get(field, [])
    grants: list[Grant] = []

    with httpx.Client() as client:
        for code in program_codes:
            if len(grants) >= max_results:
                break
            try:
                r = client.get(NSF_BASE, params={
                    "fundProgramName": code,
                    "dateStart": "01/01/2022",
                    "dateEnd": "12/31/2024",
                    "printFields": "id,title,abstractText,agency,fundsObligatedAmt,date",
                    "offset": 1,
                    "rpp": min(20, max_results - len(grants)),
                }, timeout=20)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                console.print(f"[yellow]NSF API ({code}): {e}[/]")
                continue

            awards = (data.get("response") or {}).get("award") or []
            for aw in awards:
                abstract = (aw.get("abstractText") or "").strip()
                if not abstract:
                    continue
                grants.append(Grant(
                    id=str(aw.get("id", "")),
                    title=aw.get("title", ""),
                    abstract=abstract,
                    agency="NSF",
                    year=_parse_nsf_year(aw.get("date", "")),
                    amount=_safe_float(aw.get("fundsObligatedAmt")),
                    source="nsf",
                ))

            time.sleep(delay)

    return grants[:max_results]


def _parse_nsf_year(date_str: str) -> int | None:
    if not date_str:
        return None
    parts = date_str.split("/")
    try:
        return int(parts[-1]) if len(parts) >= 3 else None
    except ValueError:
        return None


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── NIH ──────────────────────────────────────────────────

NIH_TERMS: dict[str, list[str]] = {
    "drug_discovery":    ["drug discovery", "drug design", "pharmacology"],
    "ai_ml":             ["machine learning", "artificial intelligence", "deep learning"],
    "materials_science": ["materials science", "energy storage", "superconductor"],
}


def fetch_nih_grants(field: str, max_results: int = 20, *, delay: float = 1.0) -> list[Grant]:
    """Fetch NIH RePorter project abstracts for a given seed field."""
    terms = NIH_TERMS.get(field, [])
    grants: list[Grant] = []

    with httpx.Client() as client:
        for term in terms:
            if len(grants) >= max_results:
                break
            payload = {
                "criteria": {
                    "advanced_text_search": {
                        "operator": "and",
                        "search_field": "all",
                        "search_text": term,
                    },
                    "fiscal_years": [2022, 2023, 2024],
                    "activity_codes": ["R01", "R21", "U01"],
                },
                "offset": 0,
                "limit": min(15, max_results - len(grants)),
                "fields": ["project_num", "project_title", "abstract_text",
                           "agency_ic_admin", "fiscal_year", "award_amount"],
            }
            try:
                r = client.post(NIH_BASE, json=payload, timeout=20)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                console.print(f"[yellow]NIH API ({term}): {e}[/]")
                continue

            for proj in (data.get("results") or []):
                abstract = (proj.get("abstract_text") or "").strip()
                if not abstract:
                    continue
                grants.append(Grant(
                    id=proj.get("project_num", ""),
                    title=proj.get("project_title", ""),
                    abstract=abstract,
                    agency="NIH",
                    year=proj.get("fiscal_year"),
                    amount=_safe_float(proj.get("award_amount")),
                    source="nih",
                ))

            time.sleep(delay)

    return grants[:max_results]
