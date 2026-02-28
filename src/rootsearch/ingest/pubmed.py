"""PubMed / PMC ingestion client.

Uses NCBI E-utilities for PubMed abstract search.
Uses PMC OA API for full-text XML retrieval (open access subset only).
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from lxml import etree
from rich.console import Console

from rootsearch.models import Paper

console = Console()

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_OA_BASE = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"

# High-signal section types in PMC XML
PMC_SIGNAL_SECTIONS = {
    "conclusions", "conclusion", "discussion", "future", "limitations",
    "challenges", "outlook", "open problems", "future directions",
}


def _api_key_param() -> dict[str, str]:
    key = os.getenv("NCBI_API_KEY", "")
    return {"api_key": key} if key else {}


def search_pubmed(query: str, max_results: int = 20, *, delay: float = 0.4) -> list[str]:
    """Search PubMed and return a list of PMIDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "usehistory": "n",
        **_api_key_param(),
    }
    with httpx.Client() as client:
        try:
            r = client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            return data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            console.print(f"[red]PubMed search error: {e}[/]")
            return []


def fetch_abstracts(pmids: list[str], *, delay: float = 0.4) -> list[Paper]:
    """Fetch abstracts for a list of PMIDs via efetch."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
        **_api_key_param(),
    }

    with httpx.Client() as client:
        try:
            r = client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=30)
            r.raise_for_status()
            xml_text = r.text
        except Exception as e:
            console.print(f"[red]PubMed fetch error: {e}[/]")
            return []

    time.sleep(delay)
    return _parse_pubmed_xml(xml_text)


def _parse_pubmed_xml(xml_text: str) -> list[Paper]:
    """Parse PubMed efetch XML into Paper records."""
    try:
        root = etree.fromstring(xml_text.encode())
    except Exception as e:
        console.print(f"[red]PubMed XML parse error: {e}[/]")
        return []

    papers: list[Paper] = []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            title_el = article.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            # Abstract may have multiple AbstractText elements (structured abstract)
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join(
                ("".join(el.itertext())).strip()
                for el in abstract_parts
            )

            year_el = article.find(".//PubDate/Year")
            year = int(year_el.text) if year_el is not None and year_el.text else None

            pub_type_els = article.findall(".//PublicationType")
            is_review = any(
                "review" in (el.text or "").lower()
                for el in pub_type_els
            )

            mesh_els = article.findall(".//MeshHeading/DescriptorName")
            fields = [el.text for el in mesh_els if el.text]

            doi_el = article.find(".//ArticleId[@IdType='doi']")
            doi = doi_el.text if doi_el is not None else None

            papers.append(Paper(
                id=f"pmid:{pmid}",
                title=title,
                abstract=abstract,
                doi=doi,
                year=year,
                fields=fields[:10],
                is_review=is_review,
                source="pubmed",
            ))
        except Exception as e:
            console.print(f"[yellow]Skipping article: {e}[/]")
            continue

    return papers


def fetch_drug_discovery_reviews(max_results: int = 20) -> list[Paper]:
    """Convenience: fetch drug discovery review articles."""
    query = (
        "(drug discovery[MeSH] OR drug design[MeSH] OR pharmacology[MeSH] "
        "OR molecular docking[MeSH] OR drug resistance[MeSH]) "
        "AND (review[pt]) AND (2018:2025[dp])"
    )
    pmids = search_pubmed(query, max_results=max_results)
    if not pmids:
        console.print("[yellow]No PMIDs returned — trying simpler query[/]")
        pmids = search_pubmed(
            "drug discovery review[pt] 2020:2025[dp]",
            max_results=max_results,
        )
    return fetch_abstracts(pmids)


def fetch_pmc_fulltext_sections(pmc_id: str) -> dict[str, str]:
    """
    Fetch full-text XML from PMC OA and extract high-signal sections.
    pmc_id should be like "PMC1234567".
    Returns dict of section_title → section_text.
    """
    params = {
        "verb": "GetRecord",
        "identifier": f"oai:pubmedcentral.nih.gov:{pmc_id.replace('PMC', '')}",
        "metadataPrefix": "pmc",
    }

    with httpx.Client() as client:
        try:
            r = client.get(PMC_OA_BASE, params=params, timeout=30)
            r.raise_for_status()
        except Exception as e:
            console.print(f"[yellow]PMC OA {pmc_id}: {e}[/]")
            return {}

    return _parse_pmc_xml_sections(r.text)


def _parse_pmc_xml_sections(xml_text: str) -> dict[str, str]:
    """Extract high-signal section text from PMC OAI-PMH XML."""
    try:
        root = etree.fromstring(xml_text.encode())
    except Exception as e:
        console.print(f"[red]PMC XML parse error: {e}[/]")
        return {}

    sections: dict[str, str] = {}
    # PMC XML uses <sec sec-type="..."> or <sec><title>...</title> patterns
    for sec in root.iter("sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title = ("".join(title_el.itertext())).strip().lower() if title_el is not None else sec_type

        is_signal = (
            any(kw in title for kw in PMC_SIGNAL_SECTIONS) or
            any(kw in sec_type for kw in PMC_SIGNAL_SECTIONS)
        )
        if not is_signal:
            continue

        # Extract all text from this section
        text = " ".join("".join(el.itertext()).strip() for el in sec.iter("p"))
        text = " ".join(text.split())  # normalize whitespace
        if len(text) > 100:
            sections[title or sec_type] = text

    return sections
