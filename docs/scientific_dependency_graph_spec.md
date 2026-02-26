# System Specification: Scientific Progress Dependency Graph

**Version 0.1 — Working Draft**
**Purpose:** Systematically identify high-leverage "root problems" across all of science and engineering by constructing a dependency graph of open problems, bottlenecks, and enabling capabilities, then analyzing it for nodes whose resolution would trigger the largest cascades of downstream progress.

---

## 1. Conceptual Model

### 1.1 Core Thesis

Scientific progress is not uniform — it clusters around breakthroughs that unblock entire fields. These breakthroughs are often not the "biggest" questions (e.g., "what is consciousness?") but rather enabling capabilities: tools, datasets, methods, or resolved sub-problems that many downstream research programs depend on. By mapping these dependency relationships as a graph and analyzing its structure, we can identify the highest-leverage intervention points — problems where progress yields disproportionate downstream benefit.

### 1.2 Analogy: The "Tech Tree" of Science

Just as a strategy game's technology tree encodes which capabilities unlock which others, science has an implicit (and partially discoverable) dependency structure. This system makes that structure explicit, queryable, and analyzable.

### 1.3 What This System Is Not

This is **not** a citation graph, co-authorship network, or knowledge graph of facts. It is a graph of **unsolved problems and unbuilt capabilities**, connected by **dependency and enablement relationships**. The nodes are gaps in knowledge or infrastructure; the edges encode how filling one gap would affect others.

---

## 2. Ontology

### 2.1 Node Types

Every node in the graph represents something that does not yet exist or is not yet resolved. Nodes have a **type**, a **granularity level**, and a set of metadata attributes.

#### Node Type Taxonomy

| Type | Definition | Example |
|------|-----------|---------|
| **Open Problem** | A well-defined question without a known answer | "What is the mechanism of high-Tc superconductivity?" |
| **Capability Gap** | A tool, method, or technique that does not yet exist but would enable research | "Whole-brain connectome mapping at synaptic resolution in humans" |
| **Data Gap** | A dataset that does not exist but is needed by multiple research programs | "Comprehensive atlas of all human cell types across developmental stages" |
| **Infrastructure Gap** | Shared resources or platforms that many groups need | "Open-access petascale simulation platform for molecular dynamics" |
| **Theoretical Gap** | A missing framework or model needed to unify or extend understanding | "Unified theory of turbulence across flow regimes" |
| **Engineering Bottleneck** | A practical constraint blocking deployment of known science | "Economically viable direct air capture at <$100/ton CO₂" |

#### Granularity Levels

Nodes exist at multiple resolutions. The system maintains a **hierarchical decomposition** where coarse nodes can be expanded into finer sub-problems:

| Level | Scope | Example |
|-------|-------|---------|
| **L0 — Grand Challenge** | Civilizational-scale goal | "Achieve sustainable fusion energy" |
| **L1 — Domain Problem** | A major open question within a field | "Develop plasma-facing materials that survive reactor conditions" |
| **L2 — Sub-problem** | A specific, attackable research question | "Characterize helium bubble formation in tungsten under neutron irradiation at 1000°C" |
| **L3 — Task** | A concrete experiment, simulation, or engineering task | "Run DFT calculations of helium interstitial energetics in BCC tungsten grain boundaries" |

The system primarily operates at **L1 and L2**. L0 provides organizational context; L3 is relevant only for downstream task decomposition by multi-agent systems.

#### Node Attributes

```yaml
node:
  id: string                    # Unique identifier (UUID)
  type: enum[NodeType]          # From taxonomy above
  granularity: enum[L0..L3]     # Hierarchical level
  title: string                 # Human-readable name
  description: string           # Detailed description of the problem/gap
  fields: list[string]          # Scientific domains this touches (can be multiple)
  status: enum                  # open | partially_resolved | resolved | obsolete
  confidence: float[0..1]       # Confidence that this node is correctly specified
  sources: list[SourceRef]      # Where this node was extracted from
  parent: optional[NodeID]      # Coarser-grained parent node (L0 ← L1 ← L2 ← L3)
  children: list[NodeID]        # Finer-grained sub-problems
  created_at: timestamp
  last_validated: timestamp     # Last time a human or automated check confirmed status
```

### 2.2 Edge Types

Edges encode relationships between nodes. They are **directed** and **typed**, with the edge direction indicating the flow of enablement (from blocker to blocked, or from enabler to enabled).

#### Edge Type Taxonomy (Priority-Ordered)

| Priority | Type | Semantics | Direction | Example |
|----------|------|-----------|-----------|---------|
| 1 | **ENABLES** | Solving A would directly enable progress on B | A → B | "Accurate protein structure prediction ENABLES rational drug design" |
| 2 | **SHARED_BLOCKER** | A and B are both blocked by a common node C | C → A, C → B | "Lack of interpretable AI BLOCKS both clinical diagnosis AND autonomous vehicles" |
| 3 | **PRODUCES_FOR** | A produces a tool, dataset, or capability that B requires as input | A → B | "Single-cell RNA sequencing at scale PRODUCES_FOR cell atlas construction" |
| 4 | **PRECEDED_BY** | Historically, progress on A has been prerequisite to progress on B | A → B | "Transistor miniaturization PRECEDED_BY advances in photolithography" |

#### Edge Attributes

```yaml
edge:
  id: string
  type: enum[EdgeType]          # From taxonomy above
  source_node: NodeID           # The enabler / blocker / producer
  target_node: NodeID           # The enabled / blocked / consumer
  strength: float[0..1]         # How critical is this dependency? (1 = hard block, 0.1 = nice-to-have)
  confidence: float[0..1]       # How confident are we this edge exists?
  evidence: list[EvidenceRef]   # Supporting references
  mechanism: string             # Brief explanation of WHY this dependency holds
  created_at: timestamp
  extraction_method: enum       # llm_extracted | expert_curated | citation_inferred | pattern_matched
```

### 2.3 Cross-Cutting Annotations

Nodes and edges can carry additional structured annotations:

- **Field tags:** hierarchical taxonomy of scientific domains (e.g., `physics > condensed_matter > superconductivity`)
- **Decomposability score:** estimated suitability for parallel multi-agent work (see Section 6)
- **Temporal markers:** estimated time horizon (near-term < 5yr, medium 5-15yr, long-term > 15yr)
- **Resource class:** what class of resource is primarily needed (compute, wet-lab, theory, data, funding, policy)

---

## 3. Data Ingestion Pipeline

The system ingests heterogeneous sources and extracts candidate nodes and edges.

### 3.1 Source Types and Priorities

| Source | What We Extract | Ingestion Method |
|--------|----------------|-----------------|
| **Scientific papers** (arXiv, PubMed, Semantic Scholar) | Open problems from "Limitations" & "Future Work" sections; dependency claims from introductions; capability references from methods | Bulk API access → section extraction → LLM-based structured extraction |
| **Review articles and survey papers** | High-quality summaries of open problems per field; explicit roadmaps and dependency claims | Targeted retrieval → full-text extraction |
| **Expert-curated lists** (NAE Grand Challenges, FRO gap maps, Science 125, Hilbert-style lists) | Pre-identified high-leverage problems with some dependency structure | Structured parsing of known sources; periodically updated |
| **Patent filings** (USPTO, EPO, WIPO) | Claims about what prior problems a patent solves; references to enabling technologies | Patent API → claim parsing → dependency extraction |
| **Grant proposals and funded project databases** (NSF Awards, NIH Reporter, ERC) | What problems researchers propose to solve; what they cite as prerequisites; what tools they say they need | Award abstracts → LLM extraction of stated dependencies |

### 3.2 Extraction Pipeline Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌─────────────┐
│   Sources    │────▶│   Retrieval  │────▶│  Extraction   │────▶│  Candidate  │
│  (APIs, DBs) │     │  & Filtering │     │  (LLM-based)  │     │   Store     │
└─────────────┘     └──────────────┘     └───────────────┘     └──────┬──────┘
                                                                      │
                                                                      ▼
                                          ┌───────────────┐     ┌─────────────┐
                                          │   Resolution  │◀────│  Dedup &    │
                                          │   & Merging   │     │  Alignment  │
                                          └───────┬───────┘     └─────────────┘
                                                  │
                                                  ▼
                                          ┌───────────────┐
                                          │  Graph Store  │
                                          └───────────────┘
```

### 3.3 Extraction Prompts (LLM-Based)

The core extraction step uses large language models with structured output. For each document, the system runs two extraction passes:

**Pass 1 — Node Extraction:**

```
Given the following scientific text, extract all UNSOLVED PROBLEMS,
CAPABILITY GAPS, DATA GAPS, or BOTTLENECKS mentioned or implied.

For each, provide:
- title: concise name
- type: open_problem | capability_gap | data_gap | infrastructure_gap |
        theoretical_gap | engineering_bottleneck
- description: 2-3 sentence explanation
- granularity: L0 | L1 | L2 | L3
- fields: list of scientific domains
- evidence_quote: the passage that supports this extraction
- confidence: 0.0 to 1.0

Output as JSON array. Only include items that are genuinely UNSOLVED or UNBUILT.
Do not include things the paper itself resolves.
```

**Pass 2 — Edge Extraction:**

```
Given the following scientific text and the list of extracted nodes,
identify DEPENDENCY RELATIONSHIPS between problems/gaps.

For each relationship, provide:
- source_node: which node enables/blocks/produces
- target_node: which node is enabled/blocked/consuming
- type: ENABLES | SHARED_BLOCKER | PRODUCES_FOR | PRECEDED_BY
- strength: 0.0 to 1.0 (1.0 = hard prerequisite)
- mechanism: why this dependency holds
- evidence_quote: supporting passage
- confidence: 0.0 to 1.0

Also identify edges to nodes NOT in the current list (cross-document
dependencies). For these, describe the external node well enough to
match against existing graph nodes or create new ones.
```

### 3.4 Deduplication and Entity Resolution

A critical challenge: the same problem is described differently across sources. "Room-temperature superconductivity," "ambient-condition superconducting materials," and "high-Tc superconductor discovery" are all the same node.

**Resolution strategy:**

1. **Embedding-based clustering:** Embed all candidate node titles + descriptions. Cluster with a similarity threshold. Flag clusters for merging.
2. **LLM-based disambiguation:** For each cluster, ask an LLM: "Are these the same problem? If so, produce a canonical title and merged description. If they are related but distinct, explain the difference."
3. **Hierarchical linking:** If two nodes are at different granularity levels, link them as parent-child rather than merging.
4. **Ongoing resolution:** As new candidates arrive, compare against the existing graph using the same embedding + LLM pipeline.

---

## 4. Graph Construction and Maintenance

### 4.1 Graph Storage

The graph is stored in a property graph database (e.g., Neo4j or TigerGraph) that supports:

- Typed, directed edges with properties
- Efficient traversal queries (multi-hop path finding)
- Full-text and vector search on node attributes
- Temporal versioning (the graph evolves as problems are solved or new ones emerge)

### 4.2 Graph Quality Maintenance

| Process | Frequency | Method |
|---------|-----------|--------|
| **Staleness check** | Monthly | For each node, search recent literature for evidence the problem has been solved or the status has changed |
| **Edge validation** | Quarterly | Sample edges and verify with LLM re-evaluation against recent papers |
| **Orphan detection** | Continuous | Flag nodes with no inbound or outbound edges for review |
| **Confidence decay** | Continuous | Nodes/edges not re-confirmed by new evidence decay in confidence over time |
| **Expert review** | As available | Domain experts validate high-centrality nodes and their edges |

### 4.3 Multi-Resolution Navigation

The graph supports zooming in and out:

```
[L0] Achieve sustainable fusion energy
  ├── [L1] Develop plasma-facing materials that survive reactor conditions
  │     ├── [L2] Characterize helium bubble formation in tungsten
  │     ├── [L2] Design self-healing alloys for first-wall applications
  │     └── [L2] Model neutron damage accumulation over reactor lifetime
  ├── [L1] Achieve stable plasma confinement >10x energy breakeven
  │     ├── [L2] Solve edge-localized mode (ELM) suppression
  │     └── [L2] Develop real-time plasma control with ML
  └── [L1] Design tritium breeding blankets with sufficient yield
        └── [L2] Validate lithium-lead eutectic flow under magnetic fields
```

Edges can connect nodes at different levels. An L2 capability gap in materials science can ENABLE an L1 problem in energy. The analysis algorithms (Section 5) operate across levels.

---

## 5. Graph Analysis: Finding High-Leverage Root Problems

### 5.1 Core Metrics

#### 5.1.1 Cascade Score

The most important metric. For each node N, the **cascade score** estimates how many downstream problems would become tractable (or significantly easier) if N were resolved.

```
cascade_score(N) = Σ over all reachable nodes R from N:
    edge_strength(path(N → R)) × importance_weight(R)
```

Where:
- `edge_strength(path)` is the product of edge strengths along the max-product path from N to R (representing compounding probability of enablement)
- `importance_weight(R)` is a function of R's own cascade score and field-breadth (how many distinct fields R touches)

This is computed iteratively (similar to PageRank) until convergence.

#### 5.1.2 Cross-Field Leverage

Measures how many distinct scientific domains a node's resolution would impact:

```
cross_field_leverage(N) = |unique_fields(reachable_set(N))|
```

A node that unblocks problems in materials science, medicine, AND energy is more leveraged than one that only affects condensed matter physics, even if the total downstream count is similar.

#### 5.1.3 Bottleneck Centrality

Adapted betweenness centrality: how many ENABLES paths between other important nodes pass through N?

```
bottleneck_centrality(N) = Σ over all pairs (S, T) where S ≠ T ≠ N:
    (number of shortest ENABLES paths from S to T through N) /
    (total shortest ENABLES paths from S to T)
```

High bottleneck centrality means N is a chokepoint: many lines of progress converge on it.

#### 5.1.4 Shared Blocker Degree

Simply: how many other nodes have a SHARED_BLOCKER edge pointing to N? A node that blocks 20 different research programs across 5 fields is a high-value target regardless of its cascade depth.

### 5.2 Composite Leverage Index

The final ranking combines these metrics into a single score:

```
leverage_index(N) = w1 × normalized(cascade_score(N))
                  + w2 × normalized(cross_field_leverage(N))
                  + w3 × normalized(bottleneck_centrality(N))
                  + w4 × normalized(shared_blocker_degree(N))
```

Default weights: w1=0.4, w2=0.25, w3=0.2, w4=0.15. These are tunable and should be calibrated against expert judgment.

### 5.3 Analysis Queries

The system should support the following query types:

| Query | Description |
|-------|-------------|
| **"Top N root problems"** | Return nodes with highest leverage index across all fields |
| **"Root problems for field X"** | Return highest-leverage nodes whose reachable set includes nodes in field X |
| **"What does solving X unlock?"** | Return the reachable set from node X, ordered by importance |
| **"What blocks X?"** | Return all nodes with ENABLES or PRODUCES_FOR edges pointing into X |
| **"Common ancestors of X and Y"** | Find shared upstream blockers of two apparently unrelated problems |
| **"Decomposable root problems"** | Top-leverage nodes filtered by multi-agent decomposability (Section 6) |
| **"Emerging bottlenecks"** | Nodes whose shared_blocker_degree has increased rapidly (new papers citing them as blockers) |

---

## 6. Multi-Agent Decomposability Analysis

Once root problems are identified, assess their suitability for parallel multi-agent work.

### 6.1 Decomposability Criteria

For each candidate root problem, score along four axes:

| Axis | Question | Score Guide |
|------|----------|------------|
| **Subtask Independence** | Can sub-problems be worked on without constant coordination? | High: agents can work for days without sync. Low: every step depends on others. |
| **Evaluability** | Can each agent assess its own progress objectively? | High: clear metrics or simulation feedback. Low: requires expert judgment at every step. |
| **Interface Clarity** | Are the inputs/outputs between subtasks well-defined? | High: standard data formats, APIs, schemas. Low: tacit knowledge, fuzzy handoffs. |
| **Recombinability** | Is there a known method for merging parallel results? | High: natural aggregation (e.g., ensemble, union, optimization). Low: requires creative synthesis. |

```yaml
decomposability:
  subtask_independence: float[0..1]
  evaluability: float[0..1]
  interface_clarity: float[0..1]
  recombinability: float[0..1]
  composite_score: float[0..1]   # Weighted average
  suggested_architecture: enum   # See 6.2
  suggested_agent_count: int
  decomposition_sketch: string   # Brief description of how to split the work
```

### 6.2 Agent Architecture Patterns

Based on the decomposability profile, the system suggests an architecture:

| Pattern | When to Use | Example |
|---------|------------|---------|
| **Parallel Search** | Large search space, independent evaluation | Materials screening: each agent explores a region of composition space |
| **Divide by Domain** | Problem spans multiple fields, each needs depth | Climate modeling: atmosphere agent, ocean agent, economy agent |
| **Divide by Method** | Single problem, multiple analytical approaches | Protein function prediction: sequence-based agent, structure-based agent, evolution-based agent |
| **Pipeline with Branching** | Sequential stages, but each stage can branch | Drug discovery: target ID → lead generation (branch) → optimization (branch) → ADMET filtering |
| **Adversarial/Debate** | Problem benefits from critique and red-teaming | Theoretical physics: one agent proposes models, another finds counterexamples |
| **MapReduce** | Embarrassingly parallel data processing + synthesis | Literature mining: each agent processes a corpus, results merged into unified summary |

---

## 7. System Architecture

### 7.1 High-Level Components

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│   Graph Explorer │ Query Interface │ Dashboard │ Expert Review   │
└────────┬─────────────────┬──────────────────┬───────────────────┘
         │                 │                  │
    ┌────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
    │ Analysis │    │   Query     │    │  Curation   │
    │  Engine  │    │   Engine    │    │   Portal    │
    └────┬─────┘    └──────┬──────┘    └──────┬──────┘
         │                 │                  │
    ┌────▼─────────────────▼──────────────────▼──────┐
    │                 GRAPH STORE                     │
    │        (Property Graph + Vector Index)          │
    └────────────────────┬───────────────────────────┘
                         │
    ┌────────────────────▼───────────────────────────┐
    │              INGESTION PIPELINE                 │
    │  Retrieval → Extraction → Dedup → Integration  │
    └────────────────────┬───────────────────────────┘
                         │
    ┌────────────────────▼───────────────────────────┐
    │               DATA SOURCES                     │
    │  Papers │ Patents │ Grants │ Curated Lists     │
    └────────────────────────────────────────────────┘
```

### 7.2 Technology Stack (Recommended)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Graph database | Neo4j or Apache AGE (Postgres extension) | Mature property graph with Cypher queries; AGE if you want Postgres ecosystem |
| Vector store | Integrated (Neo4j vector index) or Pinecone/Weaviate | For embedding-based dedup and similarity search |
| LLM extraction | Claude API (Sonnet for bulk extraction, Opus for complex disambiguation) | Structured output, long context for full papers |
| Orchestration | Temporal or Prefect | Reliable workflow orchestration for ingestion pipelines |
| Paper API | Semantic Scholar API + arXiv API | Best coverage and structured metadata |
| Patent API | USPTO PatentsView + Lens.org | Open access to patent claims and citations |
| Grant API | NSF Award Search API + NIH Reporter API | Structured award abstracts with stated goals |
| Frontend | React + D3.js or Cytoscape.js | Interactive graph visualization with zoom/filter |
| Compute | Cloud GPU for embedding generation; CPU for graph algorithms | Embedding is the main GPU bottleneck |

### 7.3 Scale Estimates

| Dimension | Estimated Scale |
|-----------|----------------|
| Nodes (initial build from top-100 fields) | 50,000 – 200,000 |
| Edges | 200,000 – 1,000,000 |
| Papers processed (initial corpus) | 5M – 20M abstracts; 500K – 2M full-text |
| LLM calls (initial extraction) | ~2M (at abstract level); ~500K (full-text passes) |
| Embedding operations | ~10M (for dedup and similarity) |
| Storage | ~50 GB graph + ~500 GB embeddings + ~2 TB raw source cache |

---

## 8. Validation and Evaluation

### 8.1 How Do We Know the Graph Is Correct?

| Validation Method | What It Tests |
|-------------------|--------------|
| **Expert spot-checks** | Sample 100 nodes per field; ask domain experts to rate correctness of node description, type, and status |
| **Edge plausibility scoring** | Sample 500 edges; ask experts: "Does solving A actually help with B?" |
| **Retrodiction test** | Take historical breakthroughs (e.g., CRISPR, AlphaFold). Build the graph as it would have existed 10 years prior. Does the system correctly identify the pre-breakthrough node as high-leverage? |
| **Prediction tracking** | Log the system's top-50 root problems annually. Track which ones see breakthroughs over the next 5 years. Does high leverage index predict actual cascade effects? |
| **Coverage audit** | For each major field, ask: are the known open problems represented? Are there obvious gaps? |

### 8.2 Failure Modes to Monitor

| Failure Mode | Symptom | Mitigation |
|-------------|---------|------------|
| **Popularity bias** | Well-studied problems dominate rankings regardless of true leverage | Weight by structural position, not citation count |
| **Extraction hallucination** | LLM invents problems not in the source text | Require evidence_quote; validate against source |
| **Stale nodes** | Solved problems remain in graph as open | Monthly staleness checks with literature search |
| **Granularity inconsistency** | Mixing L0 and L2 nodes in the same analysis | Enforce level-aware metrics; separate analyses per level |
| **Field coverage bias** | Biomedical papers dominate because PubMed is larger | Normalize metrics per field; ensure balanced ingestion |
| **Edge over-inference** | Too many weak edges dilute the signal | Threshold on confidence × strength; prune edges below threshold |

---

## 9. Phased Rollout Plan

### Phase 0 — Proof of Concept (4-6 weeks)

- Select 3 fields as seeds (suggestion: materials science, neuroscience, energy storage)
- Ingest review articles and curated problem lists only (not full paper corpus)
- Extract ~500 nodes and ~2,000 edges
- Implement cascade score and basic visualization
- Validate with 5-10 domain experts
- **Success criterion:** Experts agree that 7/10 of the top-ranked root problems are genuinely high-leverage

### Phase 1 — Single-Domain Deep Build (3 months)

- Expand one seed field to full paper corpus ingestion
- Build complete multi-resolution graph for that field
- Implement all four edge types and full analysis suite
- Add decomposability scoring
- Build expert review portal
- **Success criterion:** The system surfaces at least 3 root problems that domain experts find novel or non-obvious

### Phase 2 — Cross-Domain Expansion (6 months)

- Extend to 10-20 fields
- Focus on cross-field edges (the highest-value additions)
- Implement patent and grant ingestion
- Add temporal tracking (emerging bottlenecks)
- **Success criterion:** System identifies cross-field root problems (problem in field A that blocks field B) that no single-field analysis would surface

### Phase 3 — Full-Scale Operation (12+ months)

- Continuous ingestion across all major scientific domains
- Automated staleness detection and graph maintenance
- Public-facing explorer interface
- Integration with multi-agent task decomposition systems
- API for downstream consumers (FROs, funding agencies, research groups)
- **Success criterion:** External users report that the system informed real research prioritization decisions

---

## 10. Open Design Questions

The following decisions are deferred and should be resolved during Phase 0:

1. **Node identity:** When is a problem "the same" across two sources? What similarity threshold for merging? This needs empirical tuning.

2. **Edge directionality for SHARED_BLOCKER:** Currently modeled as C → A and C → B (blocker points to blocked). But should we also add an undirected "co-blocked" edge between A and B for analysis purposes?

3. **Handling negative dependencies:** Some breakthroughs *close* avenues rather than opening them. (e.g., proving a no-go theorem eliminates a line of research.) How should these be represented?

4. **Confidence propagation:** If a high-confidence node has an edge to a low-confidence node, how does that affect analysis? Should we propagate confidence through the graph?

5. **Human-in-the-loop vs. fully automated:** How much expert curation is needed to keep the graph useful? Can we identify the minimum viable human input?

6. **Intellectual property and sensitivity:** Grant proposals may contain pre-publication ideas. Patent filings have legal implications. What are the ethical boundaries of ingesting and exposing this data?

7. **Integration with existing systems:** Should this interoperate with Convergent Research's gap map, OpenAlex, or other scientific knowledge infrastructure?
