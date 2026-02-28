# rootsearch

**Find the highest-leverage unsolved problems in science.**

`rootsearch` constructs a dependency graph of open scientific problems, capability gaps, and bottlenecks across all fields — then analyzes it to surface the "root problems" whose resolution would trigger the largest cascades of downstream progress.

---

## The Idea

Scientific breakthroughs are not uniformly distributed. They cluster around a small number of enabling capabilities — tools, methods, datasets, or resolved sub-problems that many downstream research programs depend on. Progress on these "root problems" unlocks disproportionate advances across fields.

The problem: this dependency structure is implicit. It lives in the "Future Work" sections of papers, in grant abstracts, in the stated prerequisites of research proposals — scattered across millions of documents, never assembled into a queryable whole.

`rootsearch` makes it explicit. It ingests scientific literature, patents, and grant data; extracts open problems and the dependency relationships between them; builds a directed graph; and runs graph analysis to rank problems by their cascade impact across fields.

The goal is to answer questions like:
- *What are the 10 problems that, if solved, would unblock the most other research?*
- *What does solving protein misfolding unlock across medicine, materials science, and AI?*
- *What single bottleneck do drug discovery and autonomous vehicles both depend on?*
- *Which cross-field problems would no single-discipline researcher ever find?*

---

## How It Works

### 1. The Graph

The graph consists of **nodes** (unsolved problems and unbuilt capabilities) and **directed edges** (dependency/enablement relationships).

**Node types:** Open Problem · Capability Gap · Data Gap · Infrastructure Gap · Theoretical Gap · Engineering Bottleneck

**Granularity levels:**
- L0 — Grand Challenge ("Achieve sustainable fusion energy")
- L1 — Domain Problem ("Develop plasma-facing materials for reactor conditions")
- L2 — Sub-problem ("Characterize helium bubble formation in tungsten at 1000°C")
- L3 — Task (for downstream agent decomposition)

**Edge types:** `ENABLES` · `PRODUCES_FOR` (shared blockers and historical precedence are derived analytically from graph structure rather than explicitly tagged)

Every node and edge carries a **confidence score**, **evidence quotes** traceable to source documents, and field tags in a two-level taxonomy (`domain.subdomain`).

### 2. Data Ingestion

The system is buildable on free/low-cost public data:

| Source | What it provides |
|--------|-----------------|
| **OpenAlex** | 240M+ papers, abstracts, topics — backbone of the corpus |
| **arXiv (LaTeX source)** | Full text for STEM; "Future Work" sections extracted via regex before LLM calls |
| **PubMed / PMC OA** | Biomedical abstracts + structured full-text XML for open access articles |
| **bioRxiv / medRxiv** | Frontier preprints with full text via free API |
| **Semantic Scholar** | Pre-computed SPECTER2 embeddings for deduplication (bulk download) |
| **Unpaywall** | Legal OA PDF links for ~50% of recent papers |
| **PatentsView + Lens.org** | US patents + patent-to-paper citation links for PRODUCES_FOR edges |
| **NSF Awards + NIH RePORTER** | Grant abstracts: structured problem statements with stated dependencies |
| **Curated lists** | NAE Grand Challenges, Science 125, Wikipedia unsolved problems, Convergent Research gap map |

**Key extraction strategy:** For arXiv papers, section headers (`\section{Future Work}`, `\section{Limitations}`, etc.) are extracted via regex before any LLM call. This reduces token volume by 80-90% while capturing the densest bottleneck signal in the literature.

**Estimated Phase 0 cost:** ~$175-560 total (data is free; cost is LLM API calls for extraction).

### 3. LLM Extraction

Each document goes through two structured extraction passes:

**Pass 1 — Node extraction:** Identify unsolved problems, capability gaps, data gaps, and bottlenecks. Classify type and granularity. Require an evidence quote.

**Pass 2 — Edge extraction:** Identify dependency relationships between extracted nodes. Flag cross-field references as stub nodes for resolution during graph construction.

### 4. Deduplication & Entity Resolution

The same problem appears across many sources under different names. Resolution pipeline:
1. Embed all node descriptions (SPECTER2 or sentence transformers)
2. Cluster by cosine similarity > 0.85
3. LLM disambiguation: merge, link as parent-child, or keep distinct
4. Cross-field stubs matched against nodes from other domains; unmatched stubs promoted to first-class nodes

### 5. Analysis: Finding Root Problems

Four metrics combined into a **Leverage Index**:

| Metric | What it measures | Weight |
|--------|-----------------|--------|
| **Cascade Score** | Total importance of reachable downstream nodes, discounted by edge strength — computed iteratively (reverse-direction PageRank) | 0.45 |
| **Cross-Field Leverage** | Number of distinct scientific domains reachable from this node | 0.30 |
| **Bottleneck Centrality** | How many ENABLES paths between other important nodes pass through this one | 0.25 |

Nodes with high scores on all three dimensions are the "root problems" — chokepoints where a breakthrough would cascade broadly and cross field boundaries.

### 6. Decomposability Assessment

For the top-ranked root problems, the system assesses suitability for parallel multi-agent work across four axes: subtask independence, evaluability, interface clarity, and recombinability. It then suggests an agent architecture (parallel search, divide by domain, divide by method, pipeline with branching, adversarial debate, or map-reduce) and a decomposition sketch.

---

## Implementation Status

> Phase 0 is actively being built. This section tracks what's done.

### ✅ Completed

**Library (`src/rootsearch/`)**

| Module | What it does | Status |
|--------|-------------|--------|
| `models.py` | Pydantic models: `Node`, `Edge`, `Paper`, `Grant`, `SourceRef` | ✅ |
| `ingest/openalex.py` | Cursor-paginated review + top-cited fetch via OpenAlex API | ✅ |
| `ingest/arxiv.py` | arXiv Atom API + per-paper LaTeX tarball downloader + regex section extractor | ✅ |
| `ingest/pubmed.py` | PubMed E-utilities abstract search + PMC OA JATS full-text XML parser | ✅ |
| `ingest/grants.py` | NSF Awards API + NIH RePORTER v2 grant abstract fetcher | ✅ |
| `extract/nodes.py` | Claude tool-use Pass 1 — structured node extraction from paper text | ✅ |
| `extract/edges.py` | Claude tool-use Pass 2 — dependency edge extraction + cross-field stub nodes | ✅ |
| `graph/dedup.py` | `sentence-transformers` embedding dedup + optional LLM disambiguation | ✅ |
| `graph/builder.py` | NetworkX DiGraph builder + `graph_stats()` + JSONL I/O | ✅ |
| `analysis/scoring.py` | Cascade score, cross-field leverage, bottleneck centrality, composite Leverage Index | ✅ |

**Prototype scripts (`proto/`)**

| Script | Purpose | Result |
|--------|---------|--------|
| `01_sample_openalex.py` | Validate topic IDs, fetch 40 papers/field | ✅ Works — 40 papers/field, 32–75% abstract coverage |
| `02_sample_arxiv.py` | Fetch arXiv papers + test LaTeX section extraction | ✅ Works — signal sections found in recent papers; old tarballs (pre-2010) fail gracefully |
| `03_sample_pubmed.py` | PubMed abstracts + PMC OA full-text XML | ✅ Works — 20/20 abstracts, 3/3 PMC full-text sections, **50% dependency-language hit rate** |
| `04_sample_grants.py` | NSF Awards + NIH RePORTER abstracts | ✅ Works — 80 grants, 100% abstracts, **55% "challenge" / 30% "to enable"** signal language |
| `05_llm_extract_sample.py` | Claude node + edge extraction on 3 sample papers | ⏳ Ready — needs `ANTHROPIC_API_KEY` |
| `06_mini_pipeline.py` | Full ingest → extract → dedup → graph → leaderboard | ✅ Ingest layer verified (68 papers, 0 errors); LLM layer ready — needs `ANTHROPIC_API_KEY` |

### 🐛 Bugs Found and Fixed During Proto Runs

| Bug | Fix | Commit |
|-----|-----|--------|
| `b"tar" in content_type` — bytes vs str comparison in arXiv tarball detection | Changed to `"tar"` (str literal) | `2dd9938` |
| PMC OA endpoint moved to new URL | Updated `PMC_OA_BASE` to `pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/` | `2dd9938` |
| PMC XML parser used `root.iter("sec")` which skips JATS namespace | Rewrote with `etree.QName().localname` iteration | `2dd9938` |
| `save_jsonl()` called `.model_dump_json()` on plain dicts | Accept both Pydantic models and dicts | `2dd9938` |
| NSF API uses `printFields`, not `fields`, for column selection | Renamed param | `c72d7c8` |

### ⏳ Next Steps

1. **Set `ANTHROPIC_API_KEY`** in `.env` (see `.env.example`) to unlock LLM extraction
2. Run `proto/05_llm_extract_sample.py` — validate node/edge quality on 6 papers
3. Run `proto/06_mini_pipeline.py` — full end-to-end with leaderboard
4. Tune OpenAlex topic IDs (current IDs return too-broad results; use `search_topics()` output to find better ones)
5. Expand arXiv LaTeX extraction to newer papers (recent arXiv IDs work; pre-2010 tarballs use legacy formats)

### Running the Prototypes

```bash
# Install dependencies
uv sync

# Copy and fill in env vars
cp .env.example .env
# edit .env — at minimum set ANTHROPIC_API_KEY

# Run protos in order
uv run python proto/01_sample_openalex.py   # OpenAlex API probe
uv run python proto/02_sample_arxiv.py      # arXiv + LaTeX extraction
uv run python proto/03_sample_pubmed.py     # PubMed + PMC full-text
uv run python proto/04_sample_grants.py     # NSF + NIH grants
uv run python proto/05_llm_extract_sample.py  # LLM node+edge extraction
uv run python proto/06_mini_pipeline.py        # Full mini pipeline + leaderboard

# Proto 06 can also run without LLM calls (ingest layer only):
uv run python proto/06_mini_pipeline.py --no-llm
```

---

## Validation

The primary validation approach is **retrodiction**: build the graph as it would have existed in 2010-2015, and ask whether the system would have ranked the prerequisites for AlphaFold, CRISPR, or mRNA vaccines as high-leverage. If yes, the system has demonstrated predictive signal before any new predictions are made.

Secondary validation: domain expert review of top-ranked nodes, coverage audits per field, and annual tracking of whether high-leverage-index nodes see breakthroughs over 5-year windows.

---

## Phased Rollout

| Phase | Scope | Timeline | Success Criterion |
|-------|-------|----------|------------------|
| **Phase 0** | 3 seed fields (Materials Science, AI/ML, Drug Discovery); review articles + curated lists only | 4-6 weeks | 7/10 top root problems judged genuinely high-leverage by domain experts |
| **Phase 1** | One field, full paper corpus; all edge types; decomposability scoring | 3 months | ≥3 novel/non-obvious root problems surfaced |
| **Phase 2** | 10-20 fields; cross-field edges; patents + grants | 6 months | Cross-field root problems identified that single-field analysis would miss |
| **Phase 3** | All major scientific domains; continuous ingestion; public API | 12+ months | System informs real research prioritization decisions |

**Phase 0 is buildable now** for ~$200-500 in LLM API costs using entirely free data sources.

---

## Phase 0 Architecture

Phase 0 runs as 7 parallel agent workstreams:

```
[Agent 1a/b/c: Data Ingestion] ──┐
[Agent 2: Seed Node Curation]  ──┤
                                  ▼
         [Agent 3: Materials Extraction] ──┐
         [Agent 4: AI/ML Extraction]     ──┤
         [Agent 5: Drug Disc. Extraction]──┤
                                           ▼
                    [Agent 6: Graph Construction & Dedup]
                                           ▼
                    [Agent 7: Analysis Engine & Explorer]
```

Agents communicate via shared filesystem (JSONL files). Maximum 4-way parallelism in Phase 1; sequential graph construction and analysis after.

---

## Documentation

- [`docs/scientific_dependency_graph_spec.md`](docs/scientific_dependency_graph_spec.md) — Full system specification: ontology, ingestion pipeline, graph analysis algorithms, validation approach, and phased rollout plan
- [`docs/data_sources_appendix.md`](docs/data_sources_appendix.md) — Detailed feasibility assessment of every data source: availability, cost, rate limits, and practical access strategies
- [`docs/phase0_agent_workstreams.md`](docs/phase0_agent_workstreams.md) — Phase 0 implementation spec: agent-by-agent breakdown with canonical schemas, extraction prompts, and acceptance criteria

---

## License

MIT
