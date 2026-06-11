---
title: "Deliberation — next PDF-pipeline shipment: triage scoring inversion, AST-aware QA mode, or ADI spike"
stash_ids: ["EFC6C84E", "378C8BC0", "F10EB5CB"]
status: decided
date: 2026-06-10
related_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/decisions/2026-06-09-powerbi-corpus-coverage.md
related_closures:
  - docs/closure/022-S-pa4-closure.md
  - docs/closure/027-S-local-dir-ingest.md
  - docs/closure/028-S-source-md-polish.md
---

# Deliberation: post-028-S next-shipment selection

## Source

Three high-leverage stash entries compete for the next PDF-pipeline shipment slot:

| ID | Priority | Kind | Frame |
|---|---|---|---|
| `EFC6C84E` | high | feature | **INVERT triage scoring model** — score source-PDF structural complexity (X-cluster count, font diversity) rather than heuristic output quality, so triage routing decisions don't depend on the very pipeline they're meant to bypass |
| `378C8BC0` | high | feature | **AST-aware QA mode** for `--triage-report-only` — emit structural density per 1k chars, section count, etc. so operators can audit triage routing decisions without running the full pipeline |
| `F10EB5CB` | medium | feature | **ADI spike** — add Azure Document Intelligence as third `pdf_engine` peer; offload high-fidelity layer to cloud API to fix throughput (cosmos PDF 25h → 30min) AND eliminate docling subprocess containment complexity |

All three address the cosmos PDF pain point surfaced in 021-S/022-S: docling produces excellent AST-aware output but throughput is unacceptable for production ingestion, and the existing triage scorer routes based on heuristic output (a self-referential signal).

## Decision criteria

| Criterion | Weight | EFC6C84E | 378C8BC0 | F10EB5CB |
|---|---|---|---|---|
| **Solves cosmos PDF throughput problem** | high | partial (better routing → fewer pages need docling) | no (observability only) | **yes** (cloud parallelism + no GIL/subprocess) |
| **Reduces operational complexity** | high | partial (still uses docling) | no | **yes** (eliminates `pdf_batch.py` subprocess containment) |
| **Cost (developer time)** | medium | ~2-3 days (scoring model rewrite + validation) | ~1 day (instrumentation + report formatter) | ~1-2 days (SDK integration + extractor wrapper) |
| **Cost (operational $)** | low | $0 (in-house) | $0 (in-house) | **~$0.0015/page** for ADI prebuilt-layout |
| **Risk (correctness)** | high | moderate (new scoring model needs calibration) | low (read-only observability) | low (replaces docling at the same interface) |
| **Risk (vendor lock-in)** | medium | none | none | **moderate** (Azure-specific; mitigated by keeping docling+heuristic as peers) |
| **Reversibility** | medium | additive; revert removes new scorer | additive; revert removes report | additive; revert removes one of three peers |
| **Unblocks downstream work** | high | yes (better triage → fewer expensive docling runs) | yes (operator can audit routing without re-ingesting) | **yes** (eliminates a whole class of operational issues) |
| **Empirical evidence already gathered** | medium | partial (PA4 calibration in 022-S surfaced the self-reference problem) | none | none (would generate during shipment) |

## Options analysis

### Option A — Ship EFC6C84E first (invert triage scoring)

**Argument for**: Addresses a known modeling defect. The current triage scorer routes pages to docling based on heuristic-output features that are themselves biased by heuristic limitations — a self-reference problem identified during 022-S PA4 calibration. Inverting to score source-PDF structural complexity directly (X-cluster count, font diversity, layout fragmentation) breaks the self-reference.

**Argument against**: Doesn't fundamentally fix throughput. Even if triage routing is perfect, docling still takes 15-30 s/page on the pages it processes. For a 4,500-page cosmos PDF with even a 20 % docling-routed rate, that's 4-7 hours — better than 25, still painful.

### Option B — Ship 378C8BC0 first (AST-aware QA mode)

**Argument for**: Cheapest of the three (~1 day). Pure observability win. Lets operators audit triage routing decisions without re-ingesting and gives empirical grounding for whether EFC6C84E or F10EB5CB matter more. Could inform the next shipment's scope.

**Argument against**: Doesn't change behavior, just visibility. The operator already knows the throughput problem is severe (raised the alarm twice during the cosmos PDF runs). Spending a day on observability when we already have the empirical evidence is a luxury we can't justify ahead of the throughput fix.

### Option C — Ship F10EB5CB first (ADI spike)

**Argument for**: Solves the throughput problem decisively (estimated 25h → 30min on cosmos). Eliminates an entire class of operational complexity (`pdf_batch.py` subprocess containment, OOM mitigation, serialization throttling — see closure/022-S-pa4-closure.md). ADI's prebuilt-layout model is comparable to docling's fidelity per Microsoft Research benchmarks. The operator has an Azure subscription and asked about ADI specifically earlier this session. Cost is operational ($0.0015/page × 4,500 pages = $6.75 per cosmos run) and trivial relative to compute cost saved.

**Argument against**: Introduces a cloud dependency. Some environments may not have Azure access. Mitigated by keeping docling+heuristic as fallback peers (the `pdf_engine: auto` policy can prefer ADI when credentials are configured, fall back to docling, then heuristic). Also mitigated by treating ADI as a SPIKE first — bounded time-boxed scope, measure quality empirically, then decide whether to commit.

## Decision

**Ship F10EB5CB (ADI spike) as the next shipment.**

Rationale:

1. **Highest expected throughput improvement** by orders of magnitude — the operator's headline pain.
2. **Largest reduction in operational complexity** — eliminates the entire `pdf_batch.py` subprocess containment surface that exists *solely* to work around docling's failure modes.
3. **Time-boxed spike scope** — bounded risk; if ADI quality is worse than docling on our corpus, abandon and try Option A next.
4. **Operator-pulled** — the ADI strategic Q&A on 2026-06-09 (recorded
   alongside this deliberation; stash `F10EB5CB` captures the spike
   intent) confirmed operator interest in ADI and existing Azure
   subscription availability. Direct alignment with stated interest.
5. **Cost is operational, not architectural** — $6.75 per cosmos run, scaling linearly. Cheap enough to be a budget item, not a capital decision.

EFC6C84E (invert scoring) and 378C8BC0 (QA mode) **stay stashed** as the natural follow-ups:

- If ADI works well: EFC6C84E becomes lower-priority (fewer pages get routed to docling anyway since ADI handles the high-fidelity work).
- If ADI works poorly or the operator opts out for cost reasons: EFC6C84E ships next (~2-3 days; modeling fix) followed by 378C8BC0 as the audit surface.

## Out of scope for the resulting shipment

- Production rollout of ADI as default `pdf_engine` — the spike output decides whether to default-prefer or default-disable
- Cost-control / quota guardrails for ADI usage — separate concern; would be a follow-up if we adopt ADI as the auto-preferred engine
- Multi-tenant ADI key management — not needed for single-operator use

## Shipment shape

Recommended decomposition for the harvest step:

| Task | Estimate | Scope |
|---|---|---|
| T1 | 2-3 h | Add `azure-ai-documentintelligence` to `pyproject.toml` optional `[adi]` extra |
| T2 | 3-4 h | New `src/docline/process/adi_extractor.py` — wrap `DocumentIntelligenceClient`, request `prebuilt-layout` with markdown output, return same shape as `_read_pdf_docling_pages` |
| T3 | 2-3 h | Extend `pdf_engine` literal in `app_models.py`: `Literal["auto", "docling", "azure_di", "heuristic"]`; wire `--pdf-engine azure_di` through CLI + MCP |
| T4 | 3-4 h | Empirical quality study — run ADI against 5 cosmos sample ranges from `.elt/output/cosmos-triage-022/study/results/` and compute the same 25 AST metrics as `scripts/study/evaluate_markdown.py`; amend the extraction-strategy decision doc |
| T5 | 1-2 h | Closure doc with decision matrix (ADI vs docling per range), recommended `auto` policy, cost analysis |

Total estimate: ~11-16 hours across 5 tasks. One PR. Validated locally; merged via admin gate (CI still paused).

## Constitution check

| Principle | Compliance |
|---|---|
| I. Safety-first Python | Typed extractor; SDK has type stubs |
| II. TDD | Per-task RED tests first; mock-based unit tests + empirical study for acceptance |
| III. Workspace isolation | All file ops via existing `safe_workspace_path` |
| V. Structured observability | Per-page extraction timing + ADI request ID logged for cost tracking |
| VI. Single responsibility | Optional extra; no new core deps; ADI imports gated by `try/except` |
| VII. Destructive approval | None (network reads only) |
| X. Context efficiency | Reuses existing extractor interface; no schema changes |

## Open questions for the operator (resolved at harvest time, not blockers)

1. **Default `auto` policy when ADI is available**: prefer ADI? prefer docling? operator-configurable? Recommendation: prefer ADI when `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` env var is set, fall back to docling, then heuristic. Operator can override per-run with `--pdf-engine`.
2. **Spike acceptance criterion**: define "ADI works well enough" — propose: structural density per 1k chars within 10% of docling on the 5 sample ranges, AND wall time <5 % of docling's, AND no per-page failures.
3. **Cost guardrail**: should the CLI warn if a run is projected to cost >$X? Recommendation: defer to a follow-up (`F8E142A1`-class concern); for the spike, just report total cost in the closure doc.
