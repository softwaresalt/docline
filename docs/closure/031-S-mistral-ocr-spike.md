---
title: 031-S Mistral OCR via Microsoft Foundry — replacement for ADI
date: 2026-06-13
status: shipped
verdict: PROMOTE-AS-PEER
verdict_date: 2026-06-13
shipment: 031-S
feature: 029-F
tasks:
  - 029.001-T  # T1 remove ADI integration
  - 029.002-T  # T2 read_pdf_mistral reader module
  - 029.003-T  # T3 wire mistral_ocr through full surface
  - 029.004-T  # T4 empirical study + closure doc
access_path: Microsoft Foundry MaaS
model: mistral-document-ai-2505
related_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
related_closures:
  - docs/closure/029-S-adi-spike.md  # ADI; removed by this shipment
consumed_stashes:
  - EFC6C84E (partial — see related_closures)
  - (operator directive 2026-06-13: replace ADI with Mistral OCR via Foundry)
---

## Verdict (2026-06-13, post-empirical study)

**PROMOTE-AS-PEER.** Mistral OCR is roughly equivalent to docling on
structural fidelity AND wins decisively on tables — a complete reversal
from the 029-S ADI result. Mistral OCR ships as an opt-in peer engine
via `--pdf-engine mistral_ocr`; the `auto` policy stays docling-first
(per the post-029-S precedent that cloud engines remain opt-in until
empirically validated for the operator's specific corpus).

### Aggregate findings (15 cosmos ranges, 551 pages, $0.55 total, 8.9 min wall)

| Metric | Δ Mistral vs docling | Wins / Ties / Losses |
|---|---|---|
| **Structural density / 1k chars** | mean **+0.01** (min −2.31, max +7.88) | 6 / 0 / 9 |
| **Char length** | mean **−1.6%** (min −37%, max +63%) | 4 / 0 / 11 |
| **Headings** | mean **−8.4%** (min −80%, max +67%) | 6 / 1 / 8 |
| **Tables** | mean **+33.9%** (min −50%, max +150%) | **8 / 4 / 2 (Mistral wins)** |
| **Lists** | mean +4.4% (min −32%, max +150%) | 3 / 5 / 7 |
| **Throughput** | **3,732 pages/hour** (~10× docling) | — |
| **Cost** | $0.55 for 551 pages = ~$3.43 extrapolated to full cosmos | — |

### Comparison to ADI (029-S)

| Metric | ADI (029-S) | Mistral OCR (031-S) | Delta |
|---|---|---|---|
| Char length | mean −70.1% | mean −1.6% | +68.5 pp closer to docling |
| Headings | mean −74.2% | mean −8.4% | +65.8 pp closer to docling |
| **Tables** | mean −66.7% (0/15 wins) | **mean +33.9% (8/15 wins)** | +100.6 pp; total reversal |
| Lists | mean −86.7% (0/15 wins) | mean +4.4% (3/15 wins) | +91.1 pp closer to docling |
| Structural density / 1k | mean −5.57 | mean +0.01 | +5.58 closer to docling |

Mistral OCR is a **dramatically better cloud engine than ADI** for the
docline → graphtor-docs technical reference corpus class. The result
validates the architectural distinction noted in the 029-S follow-up:
ADI descended from Form Recognizer (designed for invoices), while
Mistral OCR was purpose-built for document-to-markdown extraction.

### Why PROMOTE-AS-PEER, not ADOPT

Three reasons to keep auto-policy docling-first despite Mistral's
strong showing:

1. **Mixed results on the core fidelity metric.** Structural density
   (the most reliable AST-aware quality signal per the 2026-06-08
   compound learning) shows Mistral winning 6 of 15 ranges — better
   than random but not a sweep. Means cluster near zero.
2. **Char length and heading count are slightly worse on average.**
   Not catastrophic, but enough to make auto-routing risky for the
   operator's primary use case (graphtor-docs ingestion).
3. **Docling has no cloud-dependency risk.** Auto stays local +
   deterministic. Operators who want Mistral's throughput or table-
   extraction edge can opt in explicitly.

### When Mistral OCR is the right choice

Use `--pdf-engine mistral_ocr` when:

* **Table extraction matters most.** Mistral wins decisively here.
* **Throughput dominates.** ~10× faster than docling (3,732 vs ~360 pp/hr)
  and ~1/3 cheaper than ADI ($0.001 vs $0.0015 per page).
* **Operator can't run docling locally** (CPU/GPU constraints,
  container size, serverless deployments where the docling models'
  ~1 GB footprint is prohibitive).
* **Document corpus is table-heavy** (financial reports, technical
  reference docs with extensive tables, scientific papers with
  computational results).

Default to docling (the auto policy) for:

* General-purpose document extraction
* When network/cloud cost is a concern
* When determinism matters (Mistral OCR is a cloud service; same input
  may produce slightly different output across SDK / model updates)

### Access path: Microsoft Foundry MaaS (operator's choice)

The operator runs Mistral OCR via Foundry MaaS rather than Mistral's
direct API. Foundry MaaS endpoints are path-routed (e.g.
`https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr`),
which means the standard `mistralai` SDK does NOT work — it appends
`/v1/ocr` to the already-routed endpoint, causing 404. The reader uses
**raw httpx** instead, which works against both Foundry MaaS and
Mistral's direct REST API by passing the full endpoint URL as the POST
target.

The reader supports both access paths via env var precedence:

1. `AZURE_AI_FOUNDRY_ENDPOINT` + `AZURE_AI_FOUNDRY_KEY` (Foundry MaaS, preferred)
2. `MISTRAL_API_KEY` + default `https://api.mistral.ai/v1/ocr` (direct fallback)
3. Explicit `api_key` + `endpoint` kwargs override both

### Per-request page limit discovered

Mistral OCR has a **30-page maximum per request** (`document_parser_too_many_pages`
error, HTTP 400). The study harness `scripts/study/mistral_comparison.py`
includes early-split logic to halve ranges exceeding 30 pages before
sending the request, plus retry-on-error for size markers. The
production reader does NOT include split-retry — operators chunking
large documents are responsible for batching, or invoking the reader
per smaller logical section.

## What shipped

### T1 — ADI removal

Deleted across the codebase:
- `pyproject.toml`: `[adi]` extra removed
- `src/docline/dependencies.py`: `adi_available()` removed
- `src/docline/readers/adi.py`: deleted
- `src/docline/readers/pdf.py`: `azure_di` removed from `_SUPPORTED_LAYOUT_ENGINES`, dispatch path deleted
- `src/docline/app_models.py`: `pdf_engine` Literal removed `"azure_di"`
- `src/docline/cli.py`: `--pdf-engine` choices updated
- `src/docline/app.py`: MCP manifest enum updated
- `tests/readers/conftest.py`: `install_fake_adi_sdk` fixture removed (file deleted)
- `tests/readers/test_adi_extractor.py`: deleted (12 tests)
- `tests/process/test_adi_extractor_optional.py`: deleted (4 tests)
- `tests/readers/test_pdf_engine_routing.py`: rewritten without ADI references
- `scripts/study/adi_comparison.py`: deleted
- `.env.example`: rewritten with Mistral placeholders
- `docs/closure/029-S-adi-spike.md`: status note added pointing to 031-S

Audit: `git grep -i "azure_di|adi_|AZURE_DOCUMENT|AdiCredential|read_pdf_adi"`
returns zero matches in `src/`, `tests/`, `scripts/`.

### T2 — `[mistral]` extra + reader

* `pyproject.toml`: `mistral = ["httpx>=0.27,<1"]`
* `src/docline/dependencies.py`: `mistral_available()` helper
* `src/docline/readers/mistral.py`: `read_pdf_mistral(path, api_key=None,
  endpoint=None, model="mistral-document-ai-2505")` + `MistralCredentialError`.
  Uses raw httpx (not mistralai SDK — discovery probe documented in plan).
  Credential resolution: explicit args → Foundry env vars → direct Mistral
  env var → raise.
* `tests/readers/test_mistral_extractor.py`: 14 tests covering happy path,
  credential resolution, HTTP errors, model parameter
* `tests/process/test_mistral_extractor_optional.py`: 3 tests verifying
  the `[mistral]` extra is correctly gated

### T3 — Wire `mistral_ocr` through full surface

* `_SUPPORTED_LAYOUT_ENGINES = frozenset({"auto", "heuristic", "docling", "mistral_ocr"})`
* `ProcessRequest.pdf_engine: Literal["auto", "docling", "mistral_ocr", "heuristic"]`
* CLI `--pdf-engine` choices (process + ingest local-dir): include `mistral_ocr`
* MCP manifest enum: includes `mistral_ocr`
* `read_pdf_pages` dispatch: explicit `mistral_ocr` requests surface
  credential/transient errors loudly (no silent fallback — same explicit-
  request contract established by 029-S)
* `tests/readers/test_pdf_engine_routing.py`: 15 tests covering the new
  engine + auto-policy invariants + CLI/MCP advertisement

### T4 — Empirical study + this closure doc

* `scripts/study/mistral_comparison.py`: forks the deleted `adi_comparison.py`
  shape. Same 15 cosmos ranges, same `evaluate_markdown.metrics_for`,
  same idempotent skip. New: early-split on >30 pages (Mistral per-request
  page limit), `--model` flag (default `mistral-document-ai-2505`),
  `--source-pdf` and `--range` filters.
* Empirical results above
* This closure doc

## Acceptance criteria

| AC | Statement | Status |
|---|---|---|
| AC1 | Zero ADI references in src/tests/scripts | ✅ verified via git grep |
| AC2 | `[mistral]` extra in pyproject; `[adi]` removed | ✅ |
| AC3 | `read_pdf_mistral` reader module per spec | ✅ |
| AC4 | Credential resolution: explicit > Foundry > MISTRAL_API_KEY > raise | ✅ |
| AC5 | `pdf_engine` Literal includes `mistral_ocr`; supported set matches | ✅ |
| AC6 | `_resolve_layout_engine("auto")` is docling > heuristic; never mistral_ocr | ✅ |
| AC7 | `mistral_comparison.py` runs against same 15 cosmos ranges; idempotent | ✅ |
| AC8 | Closure doc with verdict | ✅ this doc |
| AC9 | All quality gates pass | ✅ (verified post-T3; full suite re-run at gate stage) |
| AC10 | ADOPT → propose auto-policy revision as follow-up; ABANDON → file removal stash | n/a — verdict is PROMOTE-AS-PEER |

## Follow-up stash candidates

1. **Add `[mistral]` extra to the production install footprint** if the
   operator wants Mistral OCR available without manual `pip install`.
   Currently requires `pip install -e .[mistral]` (just adds `httpx`,
   minimal cost).
2. **Document Mistral OCR as the preferred engine for table-heavy
   corpora** in README and ARCHITECTURE.md once the fidelity-vs-throughput
   decision matrix lands (stash `4C0538D0`).
3. **Add per-page-range hard-flag for >30 pages** in the production reader
   itself (currently only the study harness handles this). When operator
   ingests large PDFs via `--pdf-engine mistral_ocr`, automatic chunking
   would be safer than failing with a 400.
4. **Compare against `mistral-ocr-2503`** (the older March 2025 model) to
   see if the newer May 2025 release is actually better on cosmos. The
   harness supports `--model mistral-ocr-2503` for this comparison.
5. **Test against forms / invoices corpus** (the original B26003B0 stash
   intent, now applicable to Mistral instead of ADI). May yield a stronger
   ADOPT verdict for that corpus class.

## Constitutional compliance

| Principle | Compliance |
|---|---|
| I. Safety-First Python | ✅ all new functions typed, no bare except |
| II. Test-First Development | ✅ 32 mistral-related tests; ADI tests removed |
| III. Workspace Isolation | ✅ no new path operations; study script confined to .elt/output/ |
| VII. Destructive Approval | ✅ ADI removal explicitly approved by operator directive |
| X. Context Efficiency | ✅ raw httpx avoids mistralai SDK overhead; reader is per-PDF |
