# Phase 0 Implementation Spec: Agent Workstream Decomposition

**Parent Document:** Scientific Progress Dependency Graph — System Specification v0.1
**Scope:** Proof-of-concept build for 3 seed fields: Materials Science / Energy Storage, AI/ML Foundations, Drug Discovery / Biomedicine
**Target Output:** A working dependency graph with ~500-2000 nodes, ~2000-8000 edges, cascade scoring, and a queryable interface
**Estimated Total Effort:** 4-6 weeks across 7 parallel agent workstreams

---

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │      AGENT 7: Integration &      │
                    │      Analysis Engine              │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │        AGENT 6: Graph            │
                    │        Construction & Dedup       │
                    └──┬──────────┬──────────┬────────┘
                       │          │          │
              ┌────────▼──┐ ┌────▼─────┐ ┌──▼────────┐
              │ AGENT 3:  │ │ AGENT 4: │ │ AGENT 5:  │
              │ Materials │ │ AI/ML    │ │ Drug Disc. │
              │ Extractor │ │ Extractor│ │ Extractor  │
              └────────┬──┘ └────┬─────┘ └──┬────────┘
                       │         │           │
              ┌────────▼──┐ ┌────▼─────┐ ┌──▼────────┐
              │ AGENT 1a: │ │ AGENT 1b:│ │ AGENT 1c: │
              │ Materials │ │ AI/ML    │ │ Drug Disc. │
              │ Ingestion │ │ Ingestion│ │ Ingestion  │
              └───────────┘ └──────────┘ └───────────┘
                       │         │           │
              ┌────────▼─────────▼───────────▼────────┐
              │       AGENT 2: Seed Node Curator       │
              └────────────────────────────────────────┘
```

---

## Shared Conventions (All Agents Must Follow)

### File Formats

All inter-agent data exchange uses newline-delimited JSON (JSONL). One record per line. UTF-8 encoded.

### Node Schema (Canonical)

Every agent that produces nodes MUST output this exact schema:

```json
{
  "node_id": "temp_<agent>_<sequential_int>",
  "type": "open_problem | capability_gap | data_gap | infrastructure_gap | theoretical_gap | engineering_bottleneck",
  "granularity": "L0 | L1 | L2 | L3",
  "title": "string, max 200 chars",
  "description": "string, 2-5 sentences",
  "fields": ["materials_science", "energy_storage"],
  "status": "open | partially_resolved",
  "confidence": 0.0-1.0,
  "sources": [
    {
      "source_type": "paper | patent | grant | curated_list",
      "source_id": "DOI or OpenAlex ID or patent number or URL",
      "evidence_quote": "exact quote supporting this extraction, max 500 chars"
    }
  ],
  "extraction_method": "llm_extracted | expert_curated | pattern_matched",
  "suggested_parent": "string description of likely parent node if granularity is L2+, or null"
}
```

### Edge Schema (Canonical)

```json
{
  "edge_id": "temp_<agent>_<sequential_int>",
  "type": "ENABLES | PRODUCES_FOR",
  "source_node_id": "node_id of the enabler/producer",
  "target_node_id": "node_id of the enabled/consumer",
  "strength": 0.0-1.0,
  "confidence": 0.0-1.0,
  "mechanism": "1-2 sentence explanation of why this dependency holds",
  "evidence": [
    {
      "source_type": "paper | patent | grant | curated_list",
      "source_id": "DOI or ID",
      "evidence_quote": "max 500 chars"
    }
  ],
  "extraction_method": "llm_extracted | expert_curated | citation_inferred"
}
```

Note: Only ENABLES and PRODUCES_FOR are used as primary edge types. Shared blockers are identified analytically (high out-degree nodes in the ENABLES graph) rather than tagged explicitly. Historical PRECEDED_BY relationships are captured as an optional `historically_preceded: bool` annotation on ENABLES edges rather than a separate edge type.

### Cross-Agent References

When an extraction agent discovers an edge pointing to a node it believes exists but hasn't extracted itself (e.g., a materials science paper references an AI/ML capability gap), it should:

1. Create a **stub node** with `confidence: 0.5` and `extraction_method: "llm_extracted"`
2. Tag it with `"cross_field_ref": true`
3. Agent 6 (Graph Construction) will resolve these stubs against nodes from other agents

### Field Taxonomy

Use a two-level dot notation for consistency: `{domain}.{subdomain}`. Nodes can have multiple tags.

```
materials_science.general, materials_science.energy_storage,
materials_science.batteries, materials_science.solar_cells,
materials_science.catalysis, materials_science.superconductivity,
materials_science.polymers, materials_science.metallurgy,
materials_science.nanomaterials,

ai_ml.general, ai_ml.deep_learning, ai_ml.reinforcement_learning,
ai_ml.nlp, ai_ml.computer_vision, ai_ml.optimization,
ai_ml.interpretability, ai_ml.generalization, ai_ml.robotics,
ai_ml.safety_alignment, ai_ml.efficiency,

drug_discovery.general, drug_discovery.small_molecule,
drug_discovery.biologics, drug_discovery.genomics,
drug_discovery.proteomics, drug_discovery.clinical_trials,
drug_discovery.molecular_biology, drug_discovery.immunology,
drug_discovery.neuropharmacology, drug_discovery.bioinformatics,

quantum_computing.general, quantum_computing.hardware,
quantum_computing.algorithms,

cross_domain
```

---

## AGENT 1 (a/b/c): Data Ingestion Pipeline

### Mission
Retrieve and stage raw data from all sources so that extraction agents (3, 4, 5) have clean, accessible input. Runs as three separate agents (one per field) for independence and parallelism.

### Inputs
- API credentials (OpenAlex key, Semantic Scholar bulk dataset, NCBI API key)
- Field-specific query definitions (provided below)

### Outputs
For each field, produce:
- `{field}_papers.jsonl` — paper metadata with abstracts
- `{field}_reviews.jsonl` — subset filtered to review articles and surveys
- `{field}_grants.jsonl` — relevant grant abstracts
- `{field}_patents.jsonl` — relevant patent records (materials science only for Phase 0)
- `{field}_embeddings.jsonl` — Semantic Scholar SPECTER2 embeddings for all papers (for Agent 6)

### Field-Specific Queries

#### Materials Science / Energy Storage

```python
# OpenAlex: review articles in materials/energy
# Note: combine filters with comma in a single "filter" param
params_reviews = {
    "filter": "topics.id:T10134|T10256|T10891|T11327,type:review",
    # Verify topic IDs against OpenAlex Topics API before use
    "sort": "cited_by_count:desc",
    "per_page": 200,
    "mailto": "your@email.com"  # required for polite pool (10 req/sec)
}
params_top_cited = {
    "filter": "topics.id:T10134|T10256|T10891|T11327,cited_by_count:>50",
    "sort": "cited_by_count:desc",
    "per_page": 200,
    "mailto": "your@email.com"
}

# arXiv categories: cond-mat.mtrl-sci, physics.chem-ph
# NSF program codes: DMR (Division of Materials Research), CBET (energy)
# PatentsView: CPC codes H01M (batteries), H01L31 (solar), B01J (catalysis)
```

**Target volume:** ~3,000 papers (500 reviews + 2,500 top-cited), ~500 grants, ~1,000 patents

#### AI/ML Foundations

```python
params_reviews = {
    "filter": "topics.id:T10077|T10210|T10563,type:review",
    # Verify topic IDs against OpenAlex Topics API before use
    "sort": "cited_by_count:desc",
    "per_page": 200,
    "mailto": "your@email.com"
}

# arXiv categories: cs.LG, cs.AI, cs.CL, cs.CV, stat.ML
# NSF program codes: IIS (Intelligent Information Systems), CCF
# Prioritize papers with "open problem", "survey", or "challenges" in title
```

**Target volume:** ~3,000 papers (500 reviews + 2,500 top-cited), ~500 grants

#### Drug Discovery / Biomedicine

```python
# PubMed: review articles in drug discovery
pubmed_query = (
    "(drug discovery[MeSH] OR pharmacology[MeSH] OR drug design[MeSH]) "
    "AND review[pt] AND 2020:2025[dp]"
)

# bioRxiv/medRxiv: preprints via api.biorxiv.org (full text freely available)
# PMC OA: full-text articles mentioning "unmet need" or "remains challenging"
# NIH RePORTER: active R01 grants — use project abstracts (not specific aims)
# OpenAlex topics: drug discovery, pharmacology, molecular docking
```

**Target volume:** ~3,000 papers (500 reviews + 2,500 top-cited), ~1,000 grants

### Implementation Notes

1. **Use OpenAlex as backbone** — 10 req/sec with polite pool, no cap. Add `mailto=` to all requests.
2. **Supplement with field-specific sources:** arXiv full-text for AI/ML and materials; PubMed/PMC + bioRxiv/medRxiv for drug discovery; PatentsView for materials.
3. **For arXiv papers:** use LaTeX source to extract "Future Work," "Limitations," "Open Problems" sections via regex *before* LLM calls — this is the highest-leverage cost reduction in the pipeline.
4. **Fetch Semantic Scholar embeddings** via bulk dataset download (not API). The 768-dim SPECTER2 vectors go to Agent 6 for dedup.
5. **For review articles, attempt full-text retrieval** via Unpaywall (`api.unpaywall.org`) or direct OA links from OpenAlex. Reviews have the richest problem descriptions.
6. **Store all raw responses** for auditability. The extraction agents should be able to trace any node back to its source text.

### Acceptance Criteria
- [ ] Each field has ≥2,500 papers with abstracts in JSONL format
- [ ] Each field has ≥200 review articles identified
- [ ] Each field has ≥100 grant abstracts
- [ ] Materials science has ≥500 patent records with claims text
- [ ] SPECTER2 embeddings retrieved for ≥80% of papers
- [ ] All output files validate against the schemas above
- [ ] A `data_manifest.json` file lists all output files with record counts

---

## AGENT 2: Seed Node Curator

### Mission
Parse curated problem lists and expert-identified challenges into high-confidence seed nodes that anchor the graph. These are the "known knowns" — problems the community already recognizes.

### Runs In Parallel With
Agent 1 (no dependency)

### Inputs
Manually retrieved source documents (URLs and/or downloaded files):

#### Materials Science / Energy Storage
- NAE Grand Challenge: "Make Solar Energy Economical"
- NAE Grand Challenge: "Provide Energy from Fusion"
- DOE Basic Energy Sciences reports on priority research directions
- Wikipedia: "List of unsolved problems in physics" (condensed matter section) — fetch via MediaWiki API
- Battery500 Consortium goals and roadmap

#### AI/ML Foundations
- NSF AI Research Institutes published research agendas
- "Concrete Problems in AI Safety" (Amodei et al., 2016)
- "Unsolved Problems in ML Safety" (Hendrycks et al., 2022)
- Wikipedia: "List of unsolved problems in computer science" (AI section) — fetch via MediaWiki API
- NeurIPS/ICML "open problems" workshops proceedings

#### Drug Discovery / Biomedicine
- Science 125 Questions (biomedical subset)
- NIH BRAIN Initiative goals
- WHO priority pathogen list (for antibiotic resistance)
- Gates Foundation Grand Challenges in Global Health
- FDA Critical Path Initiative

### Outputs
- `seed_nodes.jsonl` — high-confidence (≥0.8) nodes extracted from curated lists
- `seed_edges.jsonl` — any explicit dependency relationships stated in the source materials
- `seed_hierarchy.jsonl` — parent-child relationships (L0 → L1 → L2 decompositions stated in the sources)

### Extraction Approach

For each curated source, use an LLM with this prompt template:

```
You are analyzing a curated list of scientific/engineering challenges.
For each challenge or open problem mentioned, extract:

1. A node following the canonical schema (see below)
2. Any DEPENDENCY RELATIONSHIPS explicitly stated or strongly implied
3. Any HIERARCHICAL RELATIONSHIPS (this challenge contains these sub-challenges)

Rules:
- Set confidence to 0.9 for explicitly named challenges, 0.7 for implied ones
- Set granularity to L0 for civilization-scale goals, L1 for field-level problems, L2 for specific sub-problems
- Use the canonical field tags (dot notation: domain.subdomain)
- Include the exact source quote that supports each extraction

[CANONICAL SCHEMAS HERE]

Source document:
{document_text}
```

### Acceptance Criteria
- [ ] ≥50 seed nodes per field (150+ total)
- [ ] ≥30 seed edges total
- [ ] ≥20 hierarchical parent-child links
- [ ] All nodes have confidence ≥ 0.7
- [ ] All nodes have at least one source reference with evidence quote
- [ ] Covers at least 3 distinct sub-domains within each field

---

## AGENT 3: Materials Science Extraction Agent

### Mission
Process materials science / energy storage papers, grants, and patents to extract open problems, capability gaps, and dependency relationships.

### Depends On
Agent 1a (needs `materials_papers.jsonl`, `materials_reviews.jsonl`, `materials_grants.jsonl`, `materials_patents.jsonl`)

### Outputs
- `materials_nodes.jsonl`
- `materials_edges.jsonl`

### Extraction Pipeline

#### Step 1: Review Article Extraction (highest priority)

Reviews are the richest source. Process all ~500 review articles with this two-pass approach:

**Pass 1 — Node Extraction Prompt:**

```
You are a materials science research analyst. Read the following
review article abstract (and full text if available).

Extract ALL unsolved problems, capability gaps, missing tools/methods,
missing datasets, and engineering bottlenecks mentioned or implied.

Focus especially on:
- Statements like "remains poorly understood", "a key challenge is",
  "further work is needed", "currently limited by"
- Mentions of tools, instruments, or computational methods that
  don't yet exist but would enable progress
- Gaps between lab-scale demonstrations and practical deployment
- Materials properties that need improvement (energy density,
  cycle life, stability, cost, etc.)

For each extraction, output a node following this schema:
{CANONICAL_NODE_SCHEMA}

Important:
- Only extract things that are UNSOLVED or UNBUILT as of the paper's date
- Assign granularity carefully: L0 = civilizational goal, L1 = field-level
  problem, L2 = specific attackable research question
- Tag with all relevant field tags (dot notation: domain.subdomain)
- Set confidence based on how explicitly the problem is stated
  (explicit mention = 0.9, implied = 0.6)
```

**Pass 2 — Edge Extraction Prompt:**

```
You are a materials science research analyst. Given the following
paper and the list of nodes already extracted from it, identify
DEPENDENCY RELATIONSHIPS.

Types of relationships to look for:
1. ENABLES: "Solving X would directly allow progress on Y"
   Example: "Accurate prediction of electrolyte decomposition
   pathways [X] would enable rational electrolyte design [Y]"

2. PRODUCES_FOR: "X produces a tool/dataset/method that Y needs"
   Example: "High-throughput DFT screening [X] produces candidate
   lists that experimental validation [Y] requires"

Also identify edges to problems OUTSIDE materials science
(cross-domain). For these, create stub nodes with cross_field_ref=true
and confidence=0.5.

Output edges following this schema:
{CANONICAL_EDGE_SCHEMA}
```

#### Step 2: Top-Cited Paper Extraction

Process the ~2,500 top-cited papers using the same prompts but with abstracts only (faster, lower cost). Prioritize papers with ≥100 citations.

#### Step 3: Grant Abstract Extraction

NSF/DOE grants are particularly rich in materials science. Use a modified prompt:

```
You are analyzing an NSF/DOE grant abstract in materials science.
Grant abstracts describe what researchers PLAN to do and what
they need. Extract:

1. The PROBLEM the grant proposes to solve (this is a node)
2. Any PREREQUISITES or CAPABILITIES the grant says are needed
   but don't yet exist (these are also nodes)
3. The DEPENDENCY between them (if the grant says "we need X to do Y",
   that's an ENABLES edge from X to Y)

Note: The fact that a grant was funded means the community considers
the problem important. Set confidence to 0.8 for explicitly stated
problems in funded grants.
```

#### Step 4: Patent Extraction

For materials science patents, extract differently — patents describe *solutions*, so we look for:

```
Analyze this patent's claims and description. Extract:

1. What PROBLEM does this patent solve? (This may be a partially_resolved node)
2. What PRIOR PROBLEMS had to be solved first for this patent to be possible?
   (These are ENABLES edges pointing INTO the solved problem)
3. What LIMITATIONS does the patent acknowledge?
   (These are still-open problems — new nodes)
4. What does the patent cite from scholarly literature?
   (These citations suggest PRODUCES_FOR edges from papers to the patent's domain)
```

### Domain-Specific Extraction Guidance

Materials science has particular patterns to watch for:

- **Scale-up gaps:** "Works at lab scale but not at industrial scale" → engineering_bottleneck
- **Characterization gaps:** "We can't measure X at the relevant conditions" → capability_gap
- **Computational gaps:** "DFT can't handle systems this large" → capability_gap
- **Stability/durability gaps:** "Promising material but degrades rapidly" → open_problem
- **Cost gaps:** "Technically feasible but economically prohibitive" → engineering_bottleneck
- **Multi-property trade-offs:** "Improving X always worsens Y" → theoretical_gap (need better understanding of the trade-off)

### Acceptance Criteria
- [ ] ≥200 nodes extracted with confidence ≥ 0.5
- [ ] ≥500 edges extracted
- [ ] ≥3 node types represented
- [ ] ≥20 cross-field stub nodes created
- [ ] ≥50 nodes extracted from patents
- [ ] All outputs validate against canonical schemas
- [ ] A `materials_extraction_report.md` summarizing statistics and quality observations

---

## AGENT 4: AI/ML Foundations Extraction Agent

### Mission
Same as Agent 3 but for AI/ML.

### Depends On
Agent 1b (needs `aiml_papers.jsonl`, `aiml_reviews.jsonl`, `aiml_grants.jsonl`)

### Outputs
- `aiml_nodes.jsonl`
- `aiml_edges.jsonl`

### Extraction Pipeline
Same two-pass approach as Agent 3, with these domain-specific modifications:

#### Domain-Specific Prompt Additions

```
AI/ML has particular patterns to watch for:

- **Scalability walls:** "Method works on toy problems but fails at scale" → engineering_bottleneck
- **Benchmark saturation:** "We've plateaued on benchmark X, suggesting the
  underlying approach has limits" → theoretical_gap
- **Generalization failures:** "Trains well but doesn't transfer to new domains" → open_problem
- **Interpretability gaps:** "Model works but we can't explain why" → capability_gap
- **Data requirements:** "Needs 10x more labeled data than is available" → data_gap
- **Compute requirements:** "Requires resources only available to large labs" → infrastructure_gap
- **Safety/alignment problems:** "Model optimizes the wrong objective" → open_problem
- **Evaluation gaps:** "We don't have good metrics for X" → capability_gap
- **Theory-practice gaps:** "Theoretically optimal but impractical" → theoretical_gap
```

#### AI/ML-Specific Source: arXiv "Open Problems" Papers

arXiv has a rich tradition of "open problems in X" papers. Specifically search for and prioritize:
- Papers with "open problem" in the title
- Papers with "survey" or "challenges" in the title within cs.LG, cs.AI, cs.CL, cs.CV
- The "Limitations" sections of highly-cited method papers (these often contain the most honest assessments of what doesn't work)

#### Cross-Domain Edges

AI/ML is an enabler for almost everything. Watch specifically for:
- AI methods that could accelerate materials discovery → ENABLES edges to materials science nodes
- ML for drug discovery (molecular property prediction, protein folding) → ENABLES edges to drug discovery nodes
- Computational bottlenecks in AI that materials breakthroughs could solve (better chips, energy efficiency) → reverse ENABLES edges

### Acceptance Criteria
- [ ] ≥200 nodes extracted
- [ ] ≥500 edges extracted
- [ ] ≥30 cross-field stub nodes (AI/ML should have the most cross-domain connections)
- [ ] Coverage across at least: deep learning theory, RL, NLP, CV, safety/alignment, efficiency
- [ ] All outputs validate against canonical schemas

---

## AGENT 5: Drug Discovery / Biomedicine Extraction Agent

### Mission
Same as Agents 3-4 but for drug discovery and biomedicine.

### Depends On
Agent 1c (needs `drugdisc_papers.jsonl`, `drugdisc_reviews.jsonl`, `drugdisc_grants.jsonl`)

### Outputs
- `drugdisc_nodes.jsonl`
- `drugdisc_edges.jsonl`

### Extraction Pipeline
Same two-pass approach, with domain-specific modifications:

#### Domain-Specific Prompt Additions

```
Drug discovery / biomedicine has particular patterns:

- **Target validation gaps:** "We don't know if target X is truly causative" → open_problem
- **Translational failures:** "Works in mice but not in humans" → engineering_bottleneck
- **Assay limitations:** "Current assays can't measure X in physiological conditions" → capability_gap
- **Resistance mechanisms:** "Pathogens/cancer cells evolve resistance to X" → open_problem
- **Delivery challenges:** "Drug works in vitro but can't reach the target in vivo" → engineering_bottleneck
- **Biomarker gaps:** "We can't identify which patients will respond" → data_gap or capability_gap
- **Model organism limitations:** "No good animal model exists for disease X" → infrastructure_gap
- **Multi-target complexity:** "Disease involves multiple pathways we can't modulate simultaneously" → theoretical_gap
- **Clinical trial design:** "We can't efficiently test combinations" → capability_gap
- **Toxicity prediction:** "Can't predict off-target effects early enough" → capability_gap
```

#### Drug Discovery-Specific Sources

- **NIH RePORTER grants:** Project abstracts explicitly list problems being attacked and capabilities needed. Use the modified grant prompt.
- **bioRxiv/medRxiv:** Full text freely available via API — high priority for emerging bottleneck detection.
- **PMC Open Access full text:** For reviews in drug discovery, attempt full-text extraction from PMC OA subset. Look for "Challenges and Future Directions" sections.
- **WHO/FDA priority lists:** These define which disease areas are most in need of new treatments (useful for importance weighting).

#### Cross-Domain Edges

Drug discovery depends heavily on:
- AI/ML capabilities (molecular property prediction, virtual screening, clinical trial optimization)
- Materials science (drug delivery vehicles, biosensors, implantable devices)
- Watch for these dependencies and create cross-field stub nodes

### Acceptance Criteria
- [ ] ≥200 nodes extracted
- [ ] ≥500 edges extracted
- [ ] ≥20 cross-field stub nodes
- [ ] Coverage across: small molecule, biologics, genomics/precision medicine, infectious disease, oncology, neurodegeneration
- [ ] All outputs validate against canonical schemas

---

## AGENT 6: Graph Construction & Entity Resolution

### Mission
Merge outputs from Agents 2-5 into a single, deduplicated graph. Resolve cross-field stubs. Build the final graph store.

### Depends On
All of Agents 2, 3, 4, 5 (waits for all outputs)

### Inputs
- `seed_nodes.jsonl`, `seed_edges.jsonl`, `seed_hierarchy.jsonl` (from Agent 2)
- `materials_nodes.jsonl`, `materials_edges.jsonl` (from Agent 3)
- `aiml_nodes.jsonl`, `aiml_edges.jsonl` (from Agent 4)
- `drugdisc_nodes.jsonl`, `drugdisc_edges.jsonl` (from Agent 5)
- `{field}_embeddings.jsonl` (from Agent 1)

### Outputs
- `final_graph_nodes.jsonl` — deduplicated, merged nodes with permanent IDs
- `final_graph_edges.jsonl` — deduplicated, merged edges with permanent IDs
- `merge_log.jsonl` — record of every merge decision for auditability
- `graph_stats.json` — node/edge counts, field distributions, quality metrics, orphan node list
- Neo4j import scripts or direct database load

### Pipeline

#### Step 1: Intra-Field Dedup

For each field separately:

1. Compute pairwise cosine similarity between all node title+description embeddings (use SPECTER2 from Agent 1 if available, otherwise generate with a sentence transformer)
2. Cluster nodes with cosine similarity > 0.85
3. For each cluster, send to LLM for disambiguation:

```
These nodes were extracted from different sources but may describe
the same problem. For each cluster, decide:

A) MERGE: They are the same problem. Produce a single canonical node
   with the best title, merged description, union of sources, and
   max confidence.
B) HIERARCHY: They are related but at different granularity levels.
   Produce a parent-child link.
C) DISTINCT: They are genuinely different despite surface similarity.
   Keep them separate.

Cluster:
{nodes_in_cluster}
```

4. Log every decision in `merge_log.jsonl`

#### Step 2: Cross-Field Stub Resolution

1. Collect all nodes with `cross_field_ref: true`
2. For each stub, search for matching non-stub nodes across all fields using embedding similarity
3. Resolution rules:
   - **Single clear match** (similarity > 0.85, next-highest < 0.75): replace stub with edge to existing node
   - **Multiple close matches** (top-2 both > 0.75): flag for human review — do not silently pick one
   - **No match found** (all < 0.80): promote stub to a real node (represents a gap not captured by any field's extraction)
4. Log all decisions in `merge_log.jsonl`

#### Step 3: Seed Node Integration

1. For each seed node (from Agent 2), find matching extracted nodes (from Agents 3-5)
2. Merge matched pairs: keep the seed node's metadata but absorb the extracted node's additional sources and edges
3. Unmatched seed nodes remain as high-confidence anchors
4. Unmatched extracted nodes remain as discoveries the automated pipeline found beyond the curated lists

#### Step 4: Edge Dedup and Validation

1. Remove exact duplicate edges (same source_node + target_node + type)
2. For near-duplicate edges (same node pair, different type), keep both but flag for review
3. Remove self-loops
4. Remove edges where confidence × strength < 0.15

#### Step 5: Assign Permanent IDs and Build Graph

1. Replace all `temp_*` node IDs with permanent UUIDs
2. Update all edge references
3. Compute basic graph statistics including orphan node count
4. Export in formats suitable for Agent 7:
   - JSONL for programmatic access
   - Neo4j Cypher import script (or CSV import files)
   - NetworkX-compatible edge list for analysis

### Acceptance Criteria
- [ ] ≥400 unique nodes after dedup (targeting ~30-50% reduction from raw extractions)
- [ ] ≥1,500 unique edges after dedup
- [ ] Orphan nodes (no edges) flagged in `graph_stats.json`; ≤15% of total nodes
- [ ] ≥50 cross-field edges connecting nodes in different domains
- [ ] All stub nodes resolved or promoted; multi-match stubs flagged for review
- [ ] Merge log complete and auditable
- [ ] Graph loadable into Neo4j (or NetworkX as fallback)

---

## AGENT 7: Analysis Engine & Interface

### Mission
Implement the cascade scoring algorithms, build query capabilities, and create a basic visualization interface.

### Depends On
Agent 6 (needs the final graph)

### Outputs
- `analysis_engine.py` — Python module implementing all scoring algorithms
- `scored_nodes.jsonl` — all nodes with computed leverage scores
- `top_root_problems.md` — ranked list of top 50 root problems with explanations
- `decomposability_assessments.jsonl` — multi-agent decomposability scores for top 50
- `explorer.py` — interactive graph visualization (Streamlit + Plotly/PyVis with filtering)

### Implementation

#### Component 1: Cascade Score

```python
def compute_cascade_scores(graph, max_iterations=100, damping=0.85, tolerance=1e-6):
    """
    Iterative cascade propagation over ENABLES and PRODUCES_FOR edges.

    A node's leverage = the total importance of what it enables,
    discounted by edge strength and confidence. Propagates importance
    from downstream nodes back to upstream enablers.

    importance[N] starts at 1.0 for all nodes and grows based on
    what N enables — nodes that enable high-importance nodes
    accumulate high scores iteratively.
    """
    importance = {n: 1.0 for n in graph.nodes}
    scores = {n: 0.0 for n in graph.nodes}

    for _ in range(max_iterations):
        new_scores = {}
        for node in graph.nodes:
            outbound = [
                (target, data)
                for _, target, data in graph.out_edges(node, data=True)
                if data['type'] in ('ENABLES', 'PRODUCES_FOR')
            ]
            new_scores[node] = sum(
                d['strength'] * d['confidence'] * importance[target]
                for target, d in outbound
            )
        # Update importance: base 1.0 + damped cascade contribution
        importance = {n: 1.0 + damping * new_scores[n] for n in graph.nodes}
        if max(abs(new_scores[n] - scores[n]) for n in graph.nodes) < tolerance:
            break
        scores = new_scores

    return scores
```

Key design decisions:
- Use only ENABLES and PRODUCES_FOR edges for cascade propagation
- Weight edges by `strength * confidence`
- Damping factor prevents infinite accumulation in cycles
- Iterate until convergence or max_iterations
- Normalize scores to [0, 1] range for composite index

#### Component 2: Cross-Field Leverage

```python
def compute_cross_field_leverage(graph, node_id):
    """
    BFS/DFS from node_id following outbound ENABLES/PRODUCES_FOR edges.
    Count unique top-level domain tags in the reachable set.
    Weight by depth (closer = more valuable).
    """
    pass
```

#### Component 3: Bottleneck Centrality

```python
def compute_bottleneck_centrality(graph):
    """
    Betweenness centrality computed only over ENABLES edges.
    Use networkx.betweenness_centrality with weight=1/(strength*confidence).
    """
    pass
```

#### Component 4: Composite Leverage Index

```python
def compute_leverage_index(graph, weights=None):
    """
    Combine cascade score, cross-field leverage, and bottleneck centrality.
    Default weights: cascade=0.45, cross_field=0.30, bottleneck=0.25
    (shared_blocker_degree removed as it's now derived analytically)

    Returns sorted list of (node_id, leverage_score, component_scores).
    """
    pass
```

#### Component 5: Decomposability Assessment

For the top 50 nodes by leverage index, assess multi-agent decomposability:

```
Given this high-leverage scientific problem:
Title: {title}
Description: {description}
Downstream problems it enables: {list of enabled nodes}

Score it on four axes (0.0 to 1.0):

1. SUBTASK INDEPENDENCE: Can this problem be split into parts
   that can be worked on without constant coordination?

2. EVALUABILITY: Can progress on each subtask be objectively measured?
   (simulation feedback, benchmark scores, experimental results)

3. INTERFACE CLARITY: Are the inputs/outputs between subtasks well-defined?
   (standard data formats, clear specifications)

4. RECOMBINABILITY: Is there a known method for merging parallel results?
   (ensemble methods, parameter sweeps, systematic reviews)

Also suggest:
- A decomposition sketch: how would you split this into 3-10 parallel tasks?
- An agent architecture pattern: parallel_search | divide_by_domain |
  divide_by_method | pipeline_with_branching | adversarial_debate | map_reduce
- Estimated number of agents needed
```

#### Component 6: Visualization

Build a Streamlit app with Plotly for interactive filtering (avoid rendering the full graph at once — use filtered subgraphs for performance at 400-2000 nodes).

Required features:
- **Graph view:** Nodes colored by field, sized by leverage score. Filter by field, node type, min leverage. Zoom/pan.
- **Node detail panel:** Click a node to see its description, scores, sources, and edges.
- **Top problems table:** Sortable table of top 50 root problems with all scores.
- **Query box:** Basic queries: "what does solving X unlock?", "what blocks X?", "top problems in field Y"
- **Decomposition view:** For any top-50 node, show the decomposability assessment and suggested agent architecture.

### Acceptance Criteria
- [ ] All scoring algorithms implemented and producing non-degenerate results
- [ ] Composite leverage index computed for all nodes
- [ ] Top 50 root problems identified and listed with explanations
- [ ] Decomposability assessed for top 50
- [ ] At least 3 of the top 50 are cross-domain problems
- [ ] Visualization functional and demonstrates the graph's structure
- [ ] `validation_report.md` documenting:
  - Top 10 results with assessment of plausibility
  - Field distribution of top 50 (flag if >60% from one domain — coverage bias)
  - Average confidence of top 50 nodes (flag if <0.6)
  - Count of top 50 that are seed nodes vs. LLM-extracted (validates pipeline adds value)
  - Count of top 50 with cross-field edges

---

## Coordination & Sequencing

### Dependency Graph (of the build itself!)

```
Week 1-2:  [Agent 1a: Materials Ingestion] ─────────────────┐
           [Agent 1b: AI/ML Ingestion]     ─────────────────┤
           [Agent 1c: Drug Disc. Ingestion] ─────────────────┤
           [Agent 2: Seed Curation]  (parallel) ─────────────┤
                                                             │
Week 2-3:  [Agent 3: Materials Extraction] ──────┐          │
           [Agent 4: AI/ML Extraction]     ──────┤ (after 1a/1b/1c)
           [Agent 5: Drug Discovery Extraction] ──┤          │
                                                  │          │
Week 3-4:  [Agent 6: Graph Construction] ─────── (after 2,3,4,5)
                                                             │
Week 4-5:  [Agent 7: Analysis & Interface] ────── (after 6) │
                                                             │
Week 5-6:  Validation, iteration, documentation ─────────────┘
```

### Parallelism Summary

| Phase | Agents Running | Parallelism |
|-------|---------------|-------------|
| 1 | Agents 1a, 1b, 1c + Agent 2 | 4-way parallel |
| 2 | Agents 3, 4, 5 | 3-way parallel |
| 3 | Agent 6 | Sequential (needs all inputs) |
| 4 | Agent 7 | Sequential (needs graph) |

### Communication Protocol

Agents communicate via shared filesystem only. No real-time messaging needed.

- All outputs go to `output/{agent_name}/` directories
- Each agent writes a `status.json` with: `{"status": "running|complete|failed", "progress": 0.0-1.0, "errors": []}`
- Agent 6 polls for all upstream agents to reach `"complete"` before starting
- Agent 7 polls for Agent 6 to complete

### Error Handling

- If an ingestion agent fails to retrieve data for one source, extraction agents run on whatever data was retrieved
- If an extraction agent fails partway through, it saves partial results — Agent 6 works with incomplete data
- Agent 6 logs and skips (does not crash on) malformed nodes/edges from upstream agents

---

## Success Criteria for Phase 0

The Phase 0 build succeeds if:

1. **Coverage:** The graph contains ≥400 unique nodes across all 3 fields
2. **Connectivity:** ≥50 cross-field edges exist
3. **Signal quality:** When shown the top 10 root problems to a domain expert, ≥7 are judged as "genuinely high-leverage" (not just well-known or obvious)
4. **Novelty:** At least 2 of the top 10 are problems that a typical researcher in one field would NOT have identified without the cross-field analysis
5. **Decomposability:** At least 5 of the top 20 score ≥0.6 on composite decomposability, suggesting they're viable targets for multi-agent work
6. **Reproducibility:** The entire pipeline can be re-run from scratch and produce substantially similar results

---

## Appendix: Estimated Costs

| Item | Estimated Cost |
|------|---------------|
| OpenAlex API | $0 (within free tier, no cap with polite pool) |
| Semantic Scholar bulk dataset | $0 (free download) |
| arXiv metadata | $0 (OAI-PMH) |
| arXiv LaTeX S3 (targeted subset) | ~$20 (partial download for one domain) |
| PubMed/PMC | $0 (free) |
| bioRxiv/medRxiv | $0 (free API) |
| PatentsView | $0 (free download) |
| NSF Awards API | $0 (free) |
| NIH RePORTER | $0 (free) |
| LLM API — abstract extraction (~10K papers × 2 passes) | ~$100-300 (Claude Sonnet) |
| LLM API — targeted full-text sections (~2K sections) | ~$50-150 additional |
| LLM API — dedup (~5K comparisons) | ~$20-50 |
| LLM API — decomposability (50 assessments) | ~$5-10 |
| Compute (embeddings, graph algorithms) | ~$0-50 (local or small cloud instance) |
| **Total estimated Phase 0 cost** | **~$175-560** |
