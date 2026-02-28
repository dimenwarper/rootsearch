"""arXiv ingestion client + LaTeX section extractor.

Fetches paper metadata via the arXiv API.
For individual papers, downloads the LaTeX source tarball and extracts
high-signal sections (Future Work, Limitations, Open Problems, etc.)
via regex — before any LLM call, reducing token cost by ~80%.
"""

from __future__ import annotations

import io
import re
import tarfile
import time
from pathlib import Path

import httpx
from rich.console import Console

from rootsearch.models import Paper

console = Console()

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_SRC  = "https://arxiv.org/src"

# arXiv categories per seed field
FIELD_CATEGORIES: dict[str, list[str]] = {
    "materials_science": ["cond-mat.mtrl-sci", "cond-mat.supr-con", "physics.chem-ph"],
    "ai_ml":             ["cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML"],
    "drug_discovery":    ["q-bio.BM", "q-bio.QM", "cs.LG"],  # overlaps with AI/ML intentionally
}

# Section headings that contain dense bottleneck/dependency signal
SIGNAL_SECTIONS = re.compile(
    r"\\section\*?\{([^}]*(?:future work|open problem|limitation|challenge|"
    r"conclusion|discussion|outlook|unsolved|direction)[^}]*)\}",
    re.IGNORECASE,
)

# Split on any \section to delimit content
SECTION_SPLIT = re.compile(r"(\\(?:sub)*section\*?\{[^}]*\})", re.IGNORECASE)


def _parse_atom_entry(entry_xml: str) -> dict:
    """Extract fields from a single Atom entry string."""
    def _tag(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", entry_xml, re.DOTALL)
        return m.group(1).strip() if m else ""

    arxiv_id = re.search(r"<id>.*?abs/([^<\s]+)</id>", entry_xml)
    return {
        "id": arxiv_id.group(1) if arxiv_id else "",
        "title": re.sub(r"\s+", " ", _tag("title")),
        "abstract": re.sub(r"\s+", " ", _tag("summary")),
        "published": _tag("published")[:4],  # year only
    }


def fetch_papers(
    field: str,
    max_results: int = 20,
    search_query: str = "",
    *,
    delay: float = 3.5,   # arXiv asks for 3s between requests
) -> list[Paper]:
    """Fetch recent papers for a field via the arXiv Atom API."""
    cats = FIELD_CATEGORIES.get(field, [])
    if not cats:
        return []

    cat_query = " OR ".join(f"cat:{c}" for c in cats)
    query = f"({cat_query})"
    if search_query:
        query = f"({search_query}) AND {query}"

    papers: list[Paper] = []
    start = 0
    batch = 25

    with httpx.Client() as client:
        while len(papers) < max_results:
            fetch_n = min(batch, max_results - len(papers))
            try:
                r = client.get(ARXIV_API, params={
                    "search_query": query,
                    "start": start,
                    "max_results": fetch_n,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                }, timeout=30)
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                console.print(f"[red]arXiv API error: {e.response.status_code}[/]")
                break

            entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.DOTALL)
            if not entries:
                break

            for entry_xml in entries:
                parsed = _parse_atom_entry(entry_xml)
                if parsed["id"]:
                    papers.append(Paper(
                        id=f"arxiv:{parsed['id']}",
                        title=parsed["title"],
                        abstract=parsed["abstract"],
                        year=int(parsed["published"]) if parsed["published"].isdigit() else None,
                        source="arxiv",
                    ))

            start += fetch_n
            if len(entries) < fetch_n:
                break
            time.sleep(delay)

    return papers[:max_results]


def extract_latex_sections(arxiv_id: str) -> dict[str, str]:
    """
    Download the LaTeX source for a single arXiv paper and extract
    high-signal sections (Future Work, Limitations, etc.) via regex.

    Returns a dict mapping section_title → section_text.
    Empty dict if source unavailable or not LaTeX.
    """
    # Strip version suffix if present (e.g. "2301.00001v2" → "2301.00001")
    clean_id = re.sub(r"v\d+$", "", arxiv_id.replace("arxiv:", ""))
    url = f"{ARXIV_SRC}/{clean_id}"

    try:
        with httpx.Client(follow_redirects=True) as client:
            r = client.get(url, timeout=30)
            if r.status_code != 200:
                console.print(f"[yellow]arXiv src {clean_id}: HTTP {r.status_code}[/]")
                return {}
            content_type = r.headers.get("content-type", "")
            content = r.content
    except Exception as e:
        console.print(f"[yellow]arXiv src {clean_id}: {e}[/]")
        return {}

    # Try to extract .tex from tarball
    tex_source = ""
    if "tar" in content_type.lower() or content[:2] == b"\x1f\x8b" or content[:5] == b"PK\x03\x04":
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                # Find the main .tex file (largest one, or the one with \documentclass)
                tex_members = [m for m in tar.getmembers() if m.name.endswith(".tex")]
                best = None
                for m in tex_members:
                    f = tar.extractfile(m)
                    if f:
                        text = f.read().decode("utf-8", errors="replace")
                        if r"\documentclass" in text or (best is None):
                            if best is None or len(text) > len(tex_source):
                                tex_source = text
                                best = m
        except Exception as e:
            console.print(f"[yellow]arXiv tar {clean_id}: {e}[/]")
            return {}
    else:
        # Might be a raw .tex file
        try:
            tex_source = content.decode("utf-8", errors="replace")
        except Exception:
            return {}

    if not tex_source:
        return {}

    return _extract_signal_sections(tex_source)


def _extract_signal_sections(tex: str) -> dict[str, str]:
    """Split a LaTeX document into sections and return the high-signal ones."""
    # Split on section commands, keeping the delimiters
    parts = SECTION_SPLIT.split(tex)

    sections: dict[str, str] = {}
    current_title = ""
    for part in parts:
        if SECTION_SPLIT.match(part):
            # Extract the title from the section command
            m = re.search(r"\{([^}]+)\}", part)
            current_title = m.group(1).strip() if m else part
        else:
            if current_title and SIGNAL_SECTIONS.search(f"\\section{{{current_title}}}"):
                # Strip LaTeX commands, keep readable text
                text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", part)
                text = re.sub(r"\\[a-zA-Z]+", " ", text)
                text = re.sub(r"[{}]", "", text)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 100:
                    sections[current_title] = text

    return sections
