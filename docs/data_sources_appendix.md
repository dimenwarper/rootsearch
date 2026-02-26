# Appendix: Data Source Feasibility Assessment

**Companion to:** Scientific Progress Dependency Graph — System Specification v0.1

This appendix maps every data source the system needs, its availability, cost, access method, and practical constraints. The bottom line: **the core system is buildable on free/low-cost data**, with full-text access being the main cost bottleneck.

---

## Tier 1: Scientific Papers — Metadata & Abstracts

These are the primary sources for node and edge extraction. Abstracts alone are sufficient for Phase 0; full-text is needed for high-quality extraction at scale.

### OpenAlex (★ Recommended Primary Source)

| Attribute | Details |
|-----------|---------|
| **Coverage** | 240M+ scholarly works across all disciplines |
| **Data includes** | Titles, abstracts, authors, institutions, topics, citations, funders, open access URLs |
| **Cost** | Free. API key is free. Rate-limited to 10 req/sec with polite pool (add `mailto=` param). Full database snapshot downloadable for free (monthly updates) |
| **Rate limits** | 10 req/sec with polite pool; no daily cap. Snapshot download is unlimited |
| **Access** | REST API at `api.openalex.org`. Bulk snapshot also available |
| **Key advantage** | Aggregates Crossref, PubMed, arXiv, ORCID, Unpaywall. Includes topic classification hierarchy. Open replacement for Scopus/Web of Science |
| **Key limitation** | Abstracts only (no full text). Some publisher abstracts missing (e.g., Springer) |
| **Verdict** | **Use as the backbone.** Best coverage-to-cost ratio. Download the snapshot for the initial build; use API for incremental updates |

### Semantic Scholar

| Attribute | Details |
|-----------|---------|
| **Coverage** | 214M+ papers across all fields |
| **Data includes** | Titles, abstracts, authors, citations, venues, SPECTER2 embeddings, TLDRs (AI-generated summaries), citation intent classification |
| **Cost** | Free |
| **Rate limits** | 1 request/second with free API key. Unauthenticated: shared pool of 5,000 req/5min. Bulk datasets also downloadable for free |
| **Access** | REST API at `api.semanticscholar.org`. Bulk JSON datasets available |
| **Key advantage** | Pre-computed SPECTER2 embeddings (huge time-saver for dedup/similarity). Citation intent labels. AI-generated TLDRs |
| **Key limitation** | API key requests from free email domains no longer approved — use the bulk dataset download for embeddings and high-volume access instead |
| **Verdict** | **Use bulk dataset download as primary access method.** The pre-computed SPECTER2 embeddings are the most valuable asset; retrieve them via bulk download rather than the API |

### arXiv

| Attribute | Details |
|-----------|---------|
| **Coverage** | 2.4M+ preprints in physics, math, CS, quantitative biology, finance, statistics, EE |
| **Data includes** | Metadata (title, abstract, authors, categories), full-text source (LaTeX), PDFs |
| **Cost** | Metadata: free. Full PDFs via S3: requester-pays (~$100 for the full 2.7TB PDF corpus). LaTeX source: ~$100 for ~9.2TB |
| **Rate limits** | API: 1 request/3 seconds. OAI-PMH for bulk metadata: free, daily updates |
| **Access** | REST API, OAI-PMH, AWS S3 requester-pays buckets, Kaggle dataset |
| **Key advantage** | **Full text is available** — this is rare and extremely valuable. LaTeX source allows structured section extraction (e.g., "Future Work" sections) |
| **Key limitation** | Covers STEM only, no biomedical (use PubMed for that), no social sciences/humanities |
| **Verdict** | **Critical source for full-text extraction.** The LaTeX source is a goldmine — you can programmatically extract "Limitations," "Future Work," and "Open Problems" sections with high precision before any LLM call, reducing extraction cost by 5-10x |

### PubMed / Europe PMC

| Attribute | Details |
|-----------|---------|
| **Coverage** | 37M+ citations in biomedical and life sciences. Europe PMC adds ~43M records |
| **Data includes** | Abstracts, MeSH terms, author affiliations. PMC Open Access subset: ~4.7M full-text articles in XML |
| **Cost** | Free |
| **Rate limits** | NCBI E-utilities: 3 req/sec without API key, 10 req/sec with free NCBI API key. Bulk download via FTP |
| **Access** | E-utilities REST API, FTP bulk download, Europe PMC REST API |
| **Key advantage** | PMC Open Access subset provides structured full-text XML — allows precise section-level extraction. MeSH terms provide controlled vocabulary for biomedical topics |
| **Key limitation** | Biomedical only. Full text available only for open access subset |
| **Verdict** | **Essential for biomedical domain coverage.** The PMC OA subset with structured XML is the highest-quality full-text source available for bio/med |

### Unpaywall

| Attribute | Details |
|-----------|---------|
| **Coverage** | ~50% of recent papers across all disciplines |
| **Data includes** | Best legal open-access PDF URL for any DOI |
| **Cost** | Free |
| **Access** | REST API at `api.unpaywall.org`. Also integrated into OpenAlex |
| **Key advantage** | Fills the full-text gap for papers not on arXiv or PMC OA — returns the best legal OA link for ~half of recent literature |
| **Verdict** | **Add to the ingestion pipeline as a full-text resolver.** After retrieving metadata from OpenAlex, run DOIs through Unpaywall to get PDF links where available |

### bioRxiv / medRxiv

| Attribute | Details |
|-----------|---------|
| **Coverage** | Frontier preprints in biology and medicine, often 6-18 months ahead of publication |
| **Data includes** | Full text freely available via REST API |
| **Cost** | Free |
| **Access** | REST API at `api.biorxiv.org` |
| **Key advantage** | Full text freely available; captures cutting-edge research before formal publication — essential for identifying emerging bottlenecks |
| **Verdict** | **Tier 1 source for biomedical domain, especially for emerging bottleneck detection** |

### CORE (Open Access Full Text)

| Attribute | Details |
|-----------|---------|
| **Coverage** | 300M+ open access papers from 10,000+ repositories |
| **Data includes** | Metadata + full text for open access papers |
| **Cost** | Free for research use. API key required (free) |
| **Rate limits** | Rate-limited but generous for research |
| **Access** | REST API, bulk dataset downloads |
| **Key advantage** | Largest open access full-text aggregator — fills the gap between "metadata only" sources and paywalled content |
| **Key limitation** | Quality varies; OCR artifacts in some older papers; duplicate records and inconsistent metadata across the 10,000+ repositories it aggregates |
| **Verdict** | **Good supplementary source for full-text** where arXiv and PMC don't cover (social sciences, engineering, etc.). Budget extra time for deduplication |

---

## Tier 2: Patents

### USPTO PatentsView (★ Recommended for US Patents)

| Attribute | Details |
|-----------|---------|
| **Coverage** | All US patents granted since 1976 + published applications since 2001 |
| **Data includes** | Claims, abstracts, citations (patent-to-patent and patent-to-paper), inventors, assignees, CPC classifications |
| **Cost** | Free. CC BY 4.0 license |
| **Rate limits** | Generous; designed for bulk research use |
| **Access** | PatentSearch REST API. Full database downloadable as tab-delimited files or MySQL dump |
| **Key advantage** | Clean, disambiguated data. Patent citation links to scholarly literature enable PRODUCES_FOR edge detection. CPC codes map to technology domains |
| **Key limitation** | US patents only |
| **Verdict** | **Primary patent source.** Download the bulk data. The patent-to-scholarly-work citation links are extremely valuable for finding "problem X was solved by technology Y" patterns |

### Lens.org (★ Recommended for Global Patents + Scholar Links)

| Attribute | Details |
|-----------|---------|
| **Coverage** | 200M+ scholarly records + global patent records from 100+ jurisdictions |
| **Data includes** | Patents, scholarly works, and critically — the citation links between them |
| **Cost** | Free for search/export (up to 50K records with account). API access requires application — free for non-commercial/academic use. Premium tiers exist |
| **Rate limits** | API: varies by plan. Web export: 50K records per collection |
| **Access** | Web interface, REST API (by application), bulk data downloads |
| **Key advantage** | **The patent-to-scholarly-work citation graph is unique and pre-built.** This is exactly what we need for PRODUCES_FOR edges |
| **Key limitation** | API access requires manual approval. Premium features cost money |
| **Verdict** | **Use for cross-linking patents to scholarly work.** Apply for academic API access. The pre-built citation links save enormous effort |

### Google Patents

| Attribute | Details |
|-----------|---------|
| **Coverage** | 120M+ patents from 100+ offices |
| **Cost** | Free to search. No bulk API |
| **Verdict** | **Not suitable for bulk ingestion** — no programmatic API. Use as a manual verification tool only |

### EPO PATSTAT

| Attribute | Details |
|-----------|---------|
| **Coverage** | 90M+ records from worldwide patent offices |
| **Cost** | €1,250/year (two editions) or €630/single edition. Free 2-month trial for online version |
| **Verdict** | **Consider for Phase 2+** when global patent coverage matters. Expensive but comprehensive |

---

## Tier 3: Grants and Funded Research

### NSF Awards API

| Attribute | Details |
|-----------|---------|
| **Coverage** | All NSF-funded awards since 1989 (~500K+ awards) |
| **Data includes** | Title, abstract, PI name, institution, program, funding amount, keywords, associated publications |
| **Cost** | Free |
| **Rate limits** | Reasonable; occasional scheduled downtime on weekends |
| **Access** | REST API at `api.nsf.gov/services/v1/awards.json` |
| **Key advantage** | Award abstracts describe what researchers *plan to do* — these contain explicit statements about what problems they're attacking and what capabilities they need. This is high-signal for node extraction |
| **Key limitation** | US/NSF only. Abstracts are short |
| **Verdict** | **Valuable for Phase 1+.** Grant abstracts are underutilized — they're essentially structured problem statements with stated dependencies |

### NIH RePORTER API

| Attribute | Details |
|-----------|---------|
| **Coverage** | NIH and non-NIH federal science awards. Massive biomedical coverage |
| **Data includes** | Project abstracts, PI info, institutions, funding, publications, clinical trials, patents |
| **Cost** | Free. Bulk data also available for download |
| **Rate limits** | Not formally specified; must not negatively impact service |
| **Access** | REST API at `api.reporter.nih.gov`. Bulk CSV download at `reporter.nih.gov/exporter` |
| **Key advantage** | Project abstracts explicitly describe the problem being solved and what capabilities are needed — high signal for dependency extraction |
| **Key limitation** | Biomedical focus. Note: "specific aims" sections (the most structured sub-problem breakdowns) are not available via the API — only project abstracts are bulk-accessible |
| **Verdict** | **Excellent for biomedical domain.** Project abstracts are the accessible high-signal source; don't plan the pipeline around specific aims |

### Federal RePORTER

| Attribute | Details |
|-----------|---------|
| **Coverage** | Cross-agency federal science funding (NIH, NSF, DOE, DoD, USDA, etc.) |
| **Cost** | Free |
| **Access** | REST API at `api.federalreporter.nih.gov` |
| **Verdict** | **Good for cross-agency coverage** in later phases |

---

## Tier 4: Curated Problem Lists (Seed Nodes)

These are high-quality, human-curated sources that serve as anchor nodes for the graph. They should be the **first** data ingested in Phase 0 — they provide the highest-confidence starting point for validation.

| Source | Coverage | Access |
|--------|----------|--------|
| **NAE 14 Grand Challenges** | 14 engineering grand challenges with detailed reports | Free at engineeringchallenges.org |
| **Science 125 Questions** | 125 big science questions (2005) + updated 125 (2021) | Science magazine; partially open |
| **Convergent Research Gap Map** | Bottlenecks in science mapped by FRO methodology — closest existing analog to this system | Free at convergentresearch.org; treat as a validation set, not just seed data |
| **Wikipedia "Lists of Unsolved Problems"** | Curated per-field lists (physics, math, CS, bio, chem, etc.) — automatable via MediaWiki API | Free; can be scraped programmatically and re-ingested periodically |
| **Millennium Prize Problems** | 7 major math problems | Free at claymath.org |
| **DARPA Grand Challenges** | Current and historical DARPA challenge problems | Free at darpa.mil |
| **Hilbert-style field-specific lists** | Various fields maintain "open problem" lists | Varies; many are open |

**Ingestion strategy:** Programmatically parse these into seed nodes (Wikipedia via MediaWiki API; others via targeted scraping), then use them as anchor points for the automated extraction pipeline. The Convergent Research gap map is particularly valuable as a cross-validation source.

---

## Practical Strategy: Phased Data Ingestion

### Phase 0 — Proof of Concept (Cost: ~$0 data + ~$100-300 LLM)

| Source | What to Use | Volume |
|--------|-------------|--------|
| OpenAlex API | Abstracts of review articles in 3 seed fields | ~10K papers |
| Curated lists | NAE, Science 125, Wikipedia unsolved problems | ~500 seed nodes |
| Semantic Scholar | SPECTER2 embeddings for dedup | Bulk dataset download |

**Estimated LLM cost for extraction:** ~$100-300 (using Claude Sonnet for ~10K abstracts at abstract level)

### Phase 1 — Single Domain Deep Build (Cost: ~$200-1000)

| Source | What to Use | Volume |
|--------|-------------|--------|
| arXiv LaTeX (S3) | **Targeted section extraction** — filter to papers with "Future Work"/"Open Problems"/"Limitations" sections, extract only those sections | ~50K papers → ~5K target sections, ~$20 S3 transfer |
| OpenAlex snapshot | Full metadata for the domain | Subset of snapshot |
| NSF Awards API | Grant abstracts in the domain | ~50K awards |
| PatentsView bulk | Patents in relevant CPC codes | Download, free |

**Estimated LLM cost:**
- Abstract-level extraction (full domain): ~$500
- Full-text targeted section extraction (arXiv): ~$200-500 additional
- Key insight: filter arXiv LaTeX to relevant sections *before* any LLM call — reduces token volume by 80-90%

### Phase 2 — Cross-Domain (Cost: ~$1000-3000)

Add PMC Open Access full text, bioRxiv/medRxiv, Lens.org patent-scholar links, NIH RePORTER, expand arXiv to all categories, CORE for humanities/social science coverage.

### Phase 3 — Full Scale (Cost: ~$5000-10000/month ongoing)

Continuous ingestion across all sources. Main costs: LLM API calls for extraction (~$3-5K/month), compute for embeddings (~$500/month), graph database hosting (~$500/month).

---

## Key Insight: The arXiv LaTeX Section Extraction Strategy

The biggest practical win in the entire ingestion pipeline is **targeted LaTeX section extraction** from arXiv. The approach:

1. Download the arXiv bulk LaTeX corpus (one-time ~$100 S3 cost)
2. Filter papers to those containing section headers matching: `\section{Future Work}`, `\section{Open Problems}`, `\section{Limitations}`, `\section{Challenges}`, `\section{Discussion}` (using regex — no LLM needed)
3. Extract only those sections — reducing average document length from ~10,000 tokens to ~500-1,500 tokens per paper
4. Run LLM extraction on the filtered sections only

This turns a potentially $5,000-10,000 full-corpus extraction into a $500-1,000 targeted extraction with **better signal-to-noise** than full-text ingestion, because "Future Work" sections contain the densest concentration of unsolved problems and dependency statements in the scientific literature.

## Key Insight: The Full-Text Gap

For non-arXiv, non-OA papers, the landscape breaks down as:

- **Full text available free:** arXiv (STEM), PMC OA subset (biomedical), bioRxiv/medRxiv (biology/medicine), CORE (various OA)
- **Full text with institutional access:** Elsevier TDM API (also available via free developer registration for non-commercial research), Wiley TDM API, Springer Nature TDM API
- **No bulk full-text access:** Most paywalled journals

**Mitigation:** Abstracts contain ~60-70% of the signal for dependency extraction. Start there, then selectively retrieve full text via Unpaywall for high-priority papers where the abstract suggests rich dependency content.
