"""Canonical data models for rootsearch nodes, edges, and sources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Source reference ──────────────────────────────────────

class SourceRef(BaseModel):
    source_type: Literal["paper", "patent", "grant", "curated_list"]
    source_id: str                   # DOI, OpenAlex ID, patent number, URL
    evidence_quote: str = ""         # exact supporting passage, max 500 chars


# ── Node ─────────────────────────────────────────────────

NodeType = Literal[
    "open_problem",
    "capability_gap",
    "data_gap",
    "infrastructure_gap",
    "theoretical_gap",
    "engineering_bottleneck",
]

Granularity = Literal["L0", "L1", "L2", "L3"]

NodeStatus = Literal["open", "partially_resolved", "resolved", "obsolete"]

ExtractionMethod = Literal["llm_extracted", "expert_curated", "pattern_matched", "citation_inferred"]


class Node(BaseModel):
    node_id: str = Field(default_factory=lambda: f"temp_{_new_id()[:8]}")
    type: NodeType
    granularity: Granularity
    title: str                       # max 200 chars
    description: str                 # 2-5 sentences
    fields: list[str] = Field(default_factory=list)   # e.g. ["ai_ml.deep_learning"]
    status: NodeStatus = "open"
    confidence: float = 0.7          # 0.0–1.0
    sources: list[SourceRef] = Field(default_factory=list)
    extraction_method: ExtractionMethod = "llm_extracted"
    suggested_parent: str | None = None
    cross_field_ref: bool = False    # True for stub nodes pointing outside the field

    # Graph navigation (populated by Agent 6)
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_validated: datetime | None = None

    def model_post_init(self, __context) -> None:
        if len(self.title) > 200:
            self.title = self.title[:197] + "..."

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ── Edge ─────────────────────────────────────────────────

EdgeType = Literal["ENABLES", "PRODUCES_FOR"]


class EvidenceRef(BaseModel):
    source_type: Literal["paper", "patent", "grant", "curated_list"]
    source_id: str
    evidence_quote: str = ""


class Edge(BaseModel):
    edge_id: str = Field(default_factory=lambda: f"temp_{_new_id()[:8]}")
    type: EdgeType
    source_node_id: str              # the enabler / producer
    target_node_id: str              # the enabled / consumer
    strength: float = 0.5            # 0.0–1.0  (1.0 = hard prerequisite)
    confidence: float = 0.7          # 0.0–1.0
    mechanism: str = ""              # 1-2 sentence explanation
    evidence: list[EvidenceRef] = Field(default_factory=list)
    extraction_method: ExtractionMethod = "llm_extracted"
    historically_preceded: bool = False   # annotation for historical ordering

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ── Lightweight paper record (from ingestion) ─────────────

class Paper(BaseModel):
    """Minimal paper record as ingested from APIs."""
    id: str                          # OpenAlex ID, arXiv ID, or PMID
    title: str
    abstract: str = ""
    doi: str | None = None
    year: int | None = None
    cited_by_count: int = 0
    fields: list[str] = Field(default_factory=list)
    is_review: bool = False
    oa_url: str | None = None
    source: str = ""                 # "openalex" | "arxiv" | "pubmed"
    raw: dict = Field(default_factory=dict, exclude=True)   # original API response


class Grant(BaseModel):
    """Minimal grant record from NSF / NIH."""
    id: str
    title: str
    abstract: str = ""
    agency: str = ""                 # "NSF" | "NIH"
    year: int | None = None
    amount: float | None = None
    source: str = ""
