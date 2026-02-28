# Phase 0 Implementation Plan

## Core Approach

Before building the full pipeline, run 6 small prototype scripts in sequence. Each probes one data source, downloads a tiny sample, and prints the structure. By proto 06 we have a working end-to-end mini-pipeline on ~150 papers that validates everything fits together — cheaply and without eating disk space.

---

## Constraints

- **No bulk downloads** — no arXiv S3 (~9TB), no Semantic Scholar bulk dump (hundreds of GB), no PatentsView full dump
- **Embeddings computed locally** with `sentence-transformers` `all-MiniLM-L6-v2` (~80MB model)
- **NetworkX** instead of Neo4j — zero server, zero disk overhead for Phase 0
- **Sample data** kept in `data/samples/` (gitignored) — target <50MB total

---

## Project Structure

```
rootsearch/
├── pyproject.toml
├── .env.example                     # ANTHROPIC_API_KEY, NCBI_API_KEY
├── .gitignore                       # ignore data/, .env
├── src/
│   └── rootsearch/
│       ├── __init__.py
│       ├── models.py                # Pydantic: Node, Edge, Source, EvidenceRef
│       ├── ingest/
│       │   ├── openalex.py          # OpenAlex client (polite pool, 10 req/sec)
│       │   ├── arxiv.py             # arXiv API + LaTeX section regex parser
│       │   ├── pubmed.py            # PubMed E-utilities + PMC OA XML client
│       │   └── grants.py            # NSF Awards API + NIH RePORTER API
│       ├── extract/
│       │   ├── nodes.py             # Pass 1: Claude → canonical Node schema
│       │   └── edges.py             # Pass 2: Claude → canonical Edge schema
│       ├── graph/
│       │   ├── dedup.py             # cosine sim clustering + LLM merge
│       │   └── builder.py           # NetworkX graph from JSONL
│       └── analysis/
│           └── scoring.py           # cascade score, cross-field leverage, bottleneck centrality
├── proto/
│   ├── 01_sample_openalex.py        # 50 review papers/field → explore schema
│   ├── 02_sample_arxiv.py           # 10 papers, 3 LaTeX tarballs → test section regex
│   ├── 03_sample_pubmed.py          # 20 papers + 3 PMC OA XMLs → explore structure
│   ├── 04_sample_grants.py          # 20 NSF + 20 NIH grants → explore abstract patterns
│   ├── 05_extract_sample.py         # LLM extraction on 10 abstracts → validate schema
│   └── 06_mini_pipeline.py          # end-to-end: 150 papers → top-10 leverage nodes
└── data/
    └── samples/                     # gitignored, <50MB
```

---

## Steps

### 1. Scaffolding
- `pyproject.toml` with deps: `httpx`, `anthropic`, `pydantic`, `networkx`, `sentence-transformers`, `rich`, `python-dotenv`, `lxml`
- `models.py`: Pydantic `Node` and `Edge` matching the canonical schemas in the spec docs
- `.env.example` and `.gitignore`

---

### 2. Proto 01 — OpenAlex Sampler
**File:** `proto/01_sample_openalex.py`

Fetch 50 review articles per field (Materials, AI/ML, Drug Discovery):
```
GET https://api.openalex.org/works
  ?filter=type:review,topics.id:{TOPIC_IDS}
  &sort=cited_by_count:desc
  &per_page=50
  &mailto=...
```
Print schema of returned records. Save to `data/samples/openalex_{field}.jsonl`.

**What we learn:** Which topic IDs exist for each field, how many papers have abstracts, how `topics` hierarchy looks, OA URL availability. Topic IDs in the current docs are placeholders — this proto validates the real ones.

---

### 3. Proto 02 — arXiv Sampler + LaTeX Section Parser
**File:** `proto/02_sample_arxiv.py`

1. Fetch 10 recent papers in `cond-mat.mtrl-sci` and 10 in `cs.LG` via arXiv API
2. For 3 papers per field: download individual LaTeX source tarball from `https://arxiv.org/src/{id}`
3. Apply regex to extract sections:
   ```python
   pattern = r'\\section\*?\{(Future Work|Limitations|Open Problems|Challenges|Conclusion).*?\}(.*?)(?=\\section|\Z)'
   ```
4. Print extracted sections + word counts

**What we learn:** How reliably section names match, typical section length, signal density. This establishes the pre-LLM filter that cuts token cost by ~80%.

---

### 4. Proto 03 — PubMed/PMC Sampler
**File:** `proto/03_sample_pubmed.py`

1. Fetch 20 drug discovery review abstracts via NCBI E-utilities (`esearch` + `efetch`)
2. Fetch 3 PMC OA full-text XMLs, parse with `lxml`, extract structured sections (`<sec sec-type="conclusions">` etc.)
3. Print MeSH term structure and XML section hierarchy

**What we learn:** MeSH term coverage, PMC XML section naming conventions, how to target "Future Directions" programmatically.

---

### 5. Proto 04 — Grants Sampler
**File:** `proto/04_sample_grants.py`

1. NSF Awards API: fetch 20 grants in DMR (materials) and 20 in IIS (AI):
   ```
   GET https://api.nsf.gov/services/v1/awards.json?agency=NSF&dircode=MPS&perPage=20
   ```
2. NIH RePORTER: fetch 20 active R01 grants in drug discovery:
   ```
   POST https://api.reporter.nih.gov/v2/projects/search
   ```
3. Print abstract text, highlight sentences containing "we need", "currently limited", "remains challenging"

**What we learn:** How explicitly grants state dependencies, typical abstract length/structure, signal density vs. papers.

---

### 6. Proto 05 — LLM Extraction on Small Batch
**File:** `proto/05_extract_sample.py`

1. Load 10 abstracts from OpenAlex samples (mix of fields)
2. Run Pass 1 (node extraction) via `anthropic` SDK with tool-use for structured JSON output
3. Validate each result against the `Node` Pydantic model — surface schema violations
4. Run Pass 2 (edge extraction) on same papers → validate against `Edge` model
5. Print: node count, type distribution, confidence histogram, schema violations, estimated cost

**What we learn:** Extraction quality, how often node types are confused, whether evidence quotes are grounded, whether the prompts need tuning before we scale up.

---

### 7. Proto 06 — Mini End-to-End Pipeline
**File:** `proto/06_mini_pipeline.py`

Full pipeline on a tiny batch:
1. Load 50 OpenAlex papers per field (150 total) — abstract-level only
2. Run Pass 1 + 2 on all 150
3. Embed node titles+descriptions with `sentence-transformers` (`all-MiniLM-L6-v2`)
4. Cluster by cosine similarity > 0.85, send clusters to Claude for merge/hierarchy/distinct decision
5. Build NetworkX directed graph from merged nodes + edges
6. Compute cascade scores (iterative propagation — importance flows from enablers outward):
   ```python
   importance = {n: 1.0 for n in graph.nodes}
   for _ in range(max_iterations):
       new_scores = {
           n: sum(d['strength'] * d['confidence'] * importance[t]
                  for _, t, d in graph.out_edges(n, data=True)
                  if d['type'] in ('ENABLES', 'PRODUCES_FOR'))
           for n in graph.nodes
       }
       importance = {n: 1.0 + damping * new_scores[n] for n in graph.nodes}
   ```
7. Compute cross-field leverage (BFS, count unique top-level domains in reachable set)
8. Compute bottleneck centrality (NetworkX betweenness over ENABLES edges only)
9. Print top-10 nodes by leverage index with component scores and field tags
10. Print: node count, edge count, cross-field edges, orphan %, field distribution

**Success gate:** Top-10 list contains plausible cross-field root problems — not just well-known grand challenges, but specific capability/data/theoretical gaps that cut across multiple fields.

---

## Key Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Graph store | NetworkX (in-memory) | Zero disk/server overhead for Phase 0 |
| Embeddings | `all-MiniLM-L6-v2` (80MB) | No bulk download; runs locally |
| LLM | Claude via `anthropic` SDK with tool-use | Structured JSON output + schema validation |
| arXiv access | Individual tarball downloads on demand | Disk-safe; only fetch what we need |
| HTTP client | `httpx` | Async, rate limiting, retry support |
| Data format | JSONL throughout | Direct compatibility with spec schemas |

---

## Run Order

```bash
uv run proto/01_sample_openalex.py   # prints ~50 records/field, validates topic IDs
uv run proto/02_sample_arxiv.py      # prints extracted LaTeX sections
uv run proto/03_sample_pubmed.py     # prints PMC XML structure
uv run proto/04_sample_grants.py     # prints grant abstract patterns
uv run proto/05_extract_sample.py    # prints nodes/edges + schema violations (target: 0)
uv run proto/06_mini_pipeline.py     # prints top-10 leverage nodes — the validation gate
```

Proto 06 is the go/no-go: if the top-10 looks sensible, we scale to the full pipeline. If not, we tune prompts in proto 05 first.
