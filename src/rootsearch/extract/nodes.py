"""Pass 1: LLM-based node extraction using Claude tool-use for structured output."""

from __future__ import annotations

import json
import os

import anthropic
from rich.console import Console

from rootsearch.models import Node, SourceRef

console = Console()

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


# ── Tool schema for structured node extraction ────────────

NODE_TOOL = {
    "name": "extract_nodes",
    "description": "Extract unsolved scientific problems, capability gaps, and bottlenecks from text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["title", "type", "granularity", "description",
                                 "fields", "confidence", "evidence_quote"],
                    "properties": {
                        "title": {"type": "string", "maxLength": 200},
                        "type": {
                            "type": "string",
                            "enum": ["open_problem", "capability_gap", "data_gap",
                                     "infrastructure_gap", "theoretical_gap",
                                     "engineering_bottleneck"],
                        },
                        "granularity": {
                            "type": "string",
                            "enum": ["L0", "L1", "L2", "L3"],
                        },
                        "description": {"type": "string"},
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "evidence_quote": {"type": "string", "maxLength": 500},
                        "suggested_parent": {"type": "string"},
                    },
                },
            }
        },
        "required": ["nodes"],
    },
}

SYSTEM_PROMPT = """You are a scientific research analyst identifying unsolved problems and capability gaps in scientific literature.

You extract structured information about what is NOT yet solved, NOT yet built, or NOT yet understood.
Focus on gaps, bottlenecks, and missing capabilities — not on what the paper itself achieves.

Node types:
- open_problem: A well-defined question without a known answer
- capability_gap: A tool, method, or technique that doesn't exist yet but would enable research
- data_gap: A dataset that doesn't exist but is needed by multiple research programs
- infrastructure_gap: Shared resources or platforms that many groups need
- theoretical_gap: A missing framework or model needed to unify or extend understanding
- engineering_bottleneck: A practical constraint blocking deployment of known science

Granularity:
- L0: Civilizational-scale goal ("achieve sustainable fusion energy")
- L1: Major open question within a field ("develop radiation-tolerant materials for fusion reactors")
- L2: Specific, attackable research question ("characterize helium bubble formation in tungsten at 1000°C")
- L3: Concrete experiment or task (rare — mostly L1 and L2)

Field tags use dot notation: domain.subdomain (e.g. "materials_science.batteries", "ai_ml.interpretability")

Set confidence:
- 0.9: explicitly stated as an open problem/gap
- 0.7: clearly implied as unsolved
- 0.5: inferred from context

Only extract things that are UNSOLVED or UNBUILT. Do not extract things the paper itself resolves."""


def extract_nodes_from_text(
    text: str,
    source_id: str,
    source_type: str = "paper",
    model: str = "claude-haiku-4-5",
) -> list[Node]:
    """
    Run Pass 1 node extraction on a piece of scientific text.
    Returns a list of Node objects validated against the canonical schema.
    """
    if not text.strip():
        return []

    # Truncate to avoid huge context windows
    text = text[:6000]

    prompt = f"""Extract all unsolved problems, capability gaps, data gaps, and bottlenecks from the following scientific text.

Text:
\"\"\"
{text}
\"\"\"

Use the extract_nodes tool to return structured results."""

    try:
        response = _client().messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[NODE_TOOL],
            tool_choice={"type": "tool", "name": "extract_nodes"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        console.print(f"[red]Claude API error (nodes): {e}[/]")
        return []

    # Extract tool result
    raw_nodes: list[dict] = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_nodes":
            raw_nodes = block.input.get("nodes", [])
            break

    nodes: list[Node] = []
    for raw in raw_nodes:
        try:
            node = Node(
                type=raw["type"],
                granularity=raw["granularity"],
                title=raw["title"],
                description=raw["description"],
                fields=raw.get("fields", []),
                confidence=float(raw.get("confidence", 0.7)),
                sources=[SourceRef(
                    source_type=source_type,
                    source_id=source_id,
                    evidence_quote=(raw.get("evidence_quote") or "")[:500],
                )],
                extraction_method="llm_extracted",
                suggested_parent=raw.get("suggested_parent"),
            )
            nodes.append(node)
        except Exception as e:
            console.print(f"[yellow]Node schema error: {e} | raw={raw.get('title', '?')}[/]")
            continue

    return nodes


def extract_nodes_from_paper(paper, model: str = "claude-haiku-4-5") -> list[Node]:
    """Convenience wrapper: extract nodes from a Paper object."""
    text = paper.abstract
    if not text:
        return []
    source_id = paper.doi or paper.id
    return extract_nodes_from_text(text, source_id=source_id, model=model)


def extract_nodes_from_section(
    section_text: str,
    section_title: str,
    arxiv_id: str,
    model: str = "claude-haiku-4-5",
) -> list[Node]:
    """Extract nodes from a single LaTeX section (Future Work, Limitations, etc.)."""
    text = f"[Section: {section_title}]\n\n{section_text}"
    return extract_nodes_from_text(text, source_id=arxiv_id, model=model)
