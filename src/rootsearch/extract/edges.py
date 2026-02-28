"""Pass 2: LLM-based edge extraction using Claude tool-use for structured output."""

from __future__ import annotations

import os

import anthropic
from rich.console import Console

from rootsearch.models import Edge, EvidenceRef, Node

console = Console()

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


EDGE_TOOL = {
    "name": "extract_edges",
    "description": "Extract dependency relationships between scientific problems and capability gaps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["source_title", "target_title", "type",
                                 "strength", "confidence", "mechanism", "evidence_quote"],
                    "properties": {
                        "source_title": {
                            "type": "string",
                            "description": "Title of the enabling/producing node",
                        },
                        "target_title": {
                            "type": "string",
                            "description": "Title of the enabled/consuming node",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["ENABLES", "PRODUCES_FOR"],
                        },
                        "strength": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "1.0 = hard prerequisite, 0.1 = nice-to-have",
                        },
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "mechanism": {
                            "type": "string",
                            "description": "1-2 sentence explanation of why this dependency holds",
                        },
                        "evidence_quote": {"type": "string", "maxLength": 500},
                        "source_is_new": {
                            "type": "boolean",
                            "description": "True if source node is not in the provided node list (cross-field ref)",
                        },
                        "target_is_new": {
                            "type": "boolean",
                            "description": "True if target node is not in the provided node list (cross-field ref)",
                        },
                    },
                },
            }
        },
        "required": ["edges"],
    },
}

SYSTEM_PROMPT = """You are a scientific research analyst identifying dependency relationships between unsolved problems and capability gaps.

You look for two types of relationships:
- ENABLES: Solving/building A would directly allow progress on B. A → B.
  Example: "Accurate protein structure prediction ENABLES rational drug design"
- PRODUCES_FOR: A produces a tool, dataset, or method that B requires as input. A → B.
  Example: "High-throughput DFT screening PRODUCES_FOR experimental materials validation"

Strength guide:
- 1.0: hard prerequisite (B literally cannot proceed without A)
- 0.7: strong enablement (B would be much easier/faster with A)
- 0.4: moderate enablement (A would help B but isn't essential)
- 0.1: weak or speculative connection

Also identify edges to nodes NOT in the provided list (cross-field references).
Mark these with source_is_new=true or target_is_new=true.
Use titles that are specific enough to match against or create new nodes.

Only extract relationships that are explicitly stated or strongly implied in the text."""


def extract_edges_from_text(
    text: str,
    nodes: list[Node],
    source_id: str,
    source_type: str = "paper",
    model: str = "claude-haiku-4-5",
) -> tuple[list[Edge], list[Node]]:
    """
    Run Pass 2 edge extraction on a piece of text given the already-extracted nodes.

    Returns:
        (edges, new_stub_nodes) where new_stub_nodes are cross-field references
        discovered but not in the original node list.
    """
    if not text.strip() or not nodes:
        return [], []

    text = text[:4000]

    node_list = "\n".join(
        f"- [{n.node_id}] {n.title} ({n.type})" for n in nodes
    )

    prompt = f"""Given the following scientific text and the list of already-extracted problem nodes,
identify DEPENDENCY RELATIONSHIPS between them.

Extracted nodes:
{node_list}

Text:
\"\"\"
{text}
\"\"\"

Use the extract_edges tool. Reference nodes by their exact titles.
If you find an edge to/from a node NOT in the list, set source_is_new or target_is_new to true."""

    try:
        response = _client().messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[EDGE_TOOL],
            tool_choice={"type": "tool", "name": "extract_edges"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        console.print(f"[red]Claude API error (edges): {e}[/]")
        return [], []

    raw_edges: list[dict] = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_edges":
            raw_edges = block.input.get("edges", [])
            break

    # Build title→node_id lookup
    title_to_id: dict[str, str] = {n.title.lower(): n.node_id for n in nodes}

    edges: list[Edge] = []
    stub_nodes: list[Node] = []

    for raw in raw_edges:
        try:
            src_title = raw["source_title"]
            tgt_title = raw["target_title"]

            src_is_new = raw.get("source_is_new", False)
            tgt_is_new = raw.get("target_is_new", False)

            # Resolve or create source node
            src_id = title_to_id.get(src_title.lower())
            if src_id is None:
                stub = _make_stub(src_title, is_new=src_is_new)
                stub_nodes.append(stub)
                src_id = stub.node_id
                title_to_id[src_title.lower()] = src_id

            # Resolve or create target node
            tgt_id = title_to_id.get(tgt_title.lower())
            if tgt_id is None:
                stub = _make_stub(tgt_title, is_new=tgt_is_new)
                stub_nodes.append(stub)
                tgt_id = stub.node_id
                title_to_id[tgt_title.lower()] = tgt_id

            if src_id == tgt_id:
                continue  # skip self-loops

            edge = Edge(
                type=raw["type"],
                source_node_id=src_id,
                target_node_id=tgt_id,
                strength=float(raw.get("strength", 0.5)),
                confidence=float(raw.get("confidence", 0.7)),
                mechanism=raw.get("mechanism", ""),
                evidence=[EvidenceRef(
                    source_type=source_type,
                    source_id=source_id,
                    evidence_quote=(raw.get("evidence_quote") or "")[:500],
                )],
                extraction_method="llm_extracted",
            )
            edges.append(edge)
        except Exception as e:
            console.print(f"[yellow]Edge schema error: {e}[/]")
            continue

    return edges, stub_nodes


def _make_stub(title: str, is_new: bool = True) -> Node:
    """Create a low-confidence stub node for a cross-field reference."""
    from rootsearch.models import Node
    return Node(
        type="capability_gap",          # default; Agent 6 will refine
        granularity="L1",
        title=title[:200],
        description=f"Stub node: cross-field reference to '{title}'. To be resolved by graph construction.",
        confidence=0.5,
        extraction_method="llm_extracted",
        cross_field_ref=is_new,
    )
