"""OpenAlex ingestion client.

Uses the polite pool (add mailto= to all requests) for 10 req/sec with no daily cap.
Fetches paper metadata + abstracts. No full-text — abstracts only.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import httpx
from rich.console import Console

from rootsearch.models import Paper

console = Console()

BASE_URL = "https://api.openalex.org"

# Verified topic IDs for each seed field (check via /topics?search=... if these drift)
FIELD_TOPICS: dict[str, list[str]] = {
    "materials_science": ["T10134", "T10256", "T10891", "T11327", "T10048", "T10062"],
    "ai_ml":             ["T10077", "T10210", "T10563", "T10182", "T10094"],
    "drug_discovery":    ["T10011", "T10034", "T10156", "T10089", "T10201"],
}


def _params(extra: dict) -> dict:
    email = os.getenv("OPENALEX_EMAIL", "rootsearch@example.com")
    return {"mailto": email, **extra}


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    url = f"{BASE_URL}{path}"
    r = client.get(url, params=_params(params), timeout=30)
    r.raise_for_status()
    return r.json()


def _abstract_from_inverted_index(inv: dict | None) -> str:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inv:
        return ""
    index: dict[str, list[int]] = inv
    words: dict[int, str] = {}
    for word, positions in index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def _to_paper(raw: dict, source: str = "openalex") -> Paper:
    abstract = _abstract_from_inverted_index(raw.get("abstract_inverted_index"))
    topics = [t.get("display_name", "") for t in raw.get("topics", [])]
    oa_url = (raw.get("open_access") or {}).get("oa_url")
    pub_type = raw.get("type", "")
    return Paper(
        id=raw.get("id", ""),
        title=raw.get("title", "") or "",
        abstract=abstract,
        doi=raw.get("doi"),
        year=raw.get("publication_year"),
        cited_by_count=raw.get("cited_by_count", 0),
        fields=topics,
        is_review="review" in pub_type.lower(),
        oa_url=oa_url,
        source=source,
        raw=raw,
    )


def fetch_reviews(
    field: str,
    max_results: int = 50,
    *,
    delay: float = 0.12,   # polite pool: 10 req/sec max
) -> list[Paper]:
    """Fetch top review articles for a given seed field."""
    topic_ids = FIELD_TOPICS.get(field, [])
    if not topic_ids:
        console.print(f"[yellow]No topic IDs for field '{field}'[/]")
        return []

    filter_str = f"topics.id:{'|'.join(topic_ids)},type:review"

    papers: list[Paper] = []
    cursor = "*"

    with httpx.Client() as client:
        while len(papers) < max_results:
            per_page = min(25, max_results - len(papers))
            try:
                data = _get(client, "/works", {
                    "filter": filter_str,
                    "sort": "cited_by_count:desc",
                    "per_page": per_page,
                    "cursor": cursor,
                    "select": "id,title,abstract_inverted_index,doi,publication_year,cited_by_count,topics,type,open_access",
                })
            except httpx.HTTPStatusError as e:
                console.print(f"[red]OpenAlex error: {e.response.status_code}[/]")
                break

            results = data.get("results", [])
            if not results:
                break

            for raw in results:
                papers.append(_to_paper(raw))

            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            if not cursor:
                break
            time.sleep(delay)

    return papers[:max_results]


def fetch_top_cited(
    field: str,
    max_results: int = 50,
    min_citations: int = 20,
    *,
    delay: float = 0.12,
) -> list[Paper]:
    """Fetch top-cited (non-review) papers for a given seed field."""
    topic_ids = FIELD_TOPICS.get(field, [])
    if not topic_ids:
        return []

    filter_str = f"topics.id:{'|'.join(topic_ids)},cited_by_count:>{min_citations}"

    papers: list[Paper] = []
    cursor = "*"

    with httpx.Client() as client:
        while len(papers) < max_results:
            per_page = min(25, max_results - len(papers))
            try:
                data = _get(client, "/works", {
                    "filter": filter_str,
                    "sort": "cited_by_count:desc",
                    "per_page": per_page,
                    "cursor": cursor,
                    "select": "id,title,abstract_inverted_index,doi,publication_year,cited_by_count,topics,type,open_access",
                })
            except httpx.HTTPStatusError as e:
                console.print(f"[red]OpenAlex error: {e.response.status_code}[/]")
                break

            results = data.get("results", [])
            if not results:
                break

            for raw in results:
                p = _to_paper(raw)
                if not p.is_review:  # exclude reviews (already fetched separately)
                    papers.append(p)

            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            if not cursor:
                break
            time.sleep(delay)

    return papers[:max_results]


def search_topics(query: str, max_results: int = 10) -> list[dict]:
    """Helper to look up valid OpenAlex topic IDs by name."""
    with httpx.Client() as client:
        data = _get(client, "/topics", {
            "search": query,
            "per_page": max_results,
            "select": "id,display_name,description,field,subfield",
        })
    return data.get("results", [])
