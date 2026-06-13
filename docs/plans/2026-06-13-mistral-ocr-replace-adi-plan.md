---
date: 2026-06-13
shipment_target: 031-S
stash_origin: (partial) B26003B0 — supersedes ADI cleanup
references:
  - docs/closure/029-S-adi-spike.md  # KEEP-AS-PEER verdict that this shipment supersedes
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - scripts/study/adi_comparison.py  # template for the new mistral_comparison.py
---

# Plan: Replace ADI with Mistral OCR (rip + replace + spike)

## Problem

The 2026-06-12 empirical study (`docs/closure/029-S-adi-spike.md`) found
Azure Document Intelligence's `prebuilt-layout` model loses on every
structural fidelity metric vs docling on cosmos-class technical
reference PDFs (mean −70% chars, mean −74% headings, 100% table loss on
10/15 ranges, 100% list loss on 13/15 ranges). The 029-S verdict was
**KEEP-AS-PEER** — leave ADI available for explicit opt-in.

The operator's directive (2026-06-13): since ADI is empirically a bad
option for the docline → graphtor-docs pipeline, strip it out entirely
and evaluate Mistral OCR as its replacement cloud peer.

Mistral OCR (`mistral-ocr-latest`, released March 2025) is Mistral's
dedicated document-to-markdown product — different design intent from
ADI's form-extraction lineage. Reported strengths are tables, equations,
code, and dense text — precisely the failure modes ADI exhibited.
Pricing ~$1/1k pages (vs ADI $1.50). Empirical validation against the
same 15 cosmos ranges will decide whether Mistral becomes:

- **ADOPT** — make `mistral_ocr` the auto-preferred cloud engine
- **PROMOTE-AS-PEER** — ship as opt-in peer like ADI was (but
  potentially better positioned)
- **ABANDON** — file a follow-up shipment to remove Mistral the same
  way 031-S removes ADI

## Goals

1. Remove all ADI integration from the codebase — pyproject extra,
   reader module, dispatch path, ProcessRequest Literal, CLI choice,
   MCP manifest entry, dependencies helper, test fixtures + ADI test
   files, study script, README/env.example mentions.
2. Add Mistral OCR as a new `pdf_engine` peer with the same opt-in
   shape ADI had: optional `[mistral]` extra, env-var-or-arg API key,
   credential fast-fail, transient-error surfacing on explicit request.
3. Run the empirical comparison against the same 15 cosmos ranges
   already cached from the 029-S study so the result is apples-to-apples.
4. Document the verdict with the same rigor as 029-S — quantified
   per-metric findings, explicit rollout recommendation, follow-up
   stash candidates.

## Non-Goals

- Deprecation period for `pdf_engine="azure_di"`. The operator's own
  tool with no external consumers; clean removal is fine.
- Modifying the 029-S closure doc beyond adding a status note. It
  remains the historical record of why ADI was tried.
- Re-running the 2026-06-08 docling vs heuristic study. Those baselines
  are still valid.
- Changing the auto-policy default. Auto stays docling-first; Mistral is
  opt-in pending T4 verdict (mirrors the 029-S precedent).
- Self-hosted Mistral OCR. Out of scope for this spike; cloud API only.

## Acceptance Criteria

| ID | Criterion |
|---|---|
| AC1 | No reference to `azure_di`, `adi`, `azure-ai-documentintelligence`, `AZURE_DOCUMENT_INTELLIGENCE_*`, `AdiCredentialError`, or `read_pdf_adi` remains in `src/`, `tests/`, `scripts/study/` (except `docs/closure/029-S-adi-spike.md` as historical record). |
| AC2 | `pyproject.toml` has `[mistral]` optional extra pinned to `mistralai>=1,<2`. `[adi]` extra is removed. |
| AC3 | `src/docline/readers/mistral.py` exposes `read_pdf_mistral(path, api_key=None, model="mistral-ocr-latest") -> str` and `MistralCredentialError`. Returns markdown directly. Lazy SDK import. Telemetry: per-call page count + wall time + projected cost. |
| AC4 | `pdf_engine` Literal is `Literal["auto", "docling", "mistral_ocr", "heuristic"]`. `_SUPPORTED_LAYOUT_ENGINES = frozenset({"auto", "heuristic", "docling", "mistral_ocr"})`. CLI `--pdf-engine` choices match. MCP manifest enum matches. |
| AC5 | `_resolve_layout_engine("auto")` returns docling when installed, else heuristic. Mistral is NEVER auto-selected pending T4 verdict. |
| AC6 | `scripts/study/mistral_comparison.py` runs against the same 15 cosmos ranges already cached at `.elt/output/cosmos-triage-022/study/dataset/range-NNNN-NNNN/` and emits `mistral-findings.{json,md}` in the same format as the ADI comparison. Idempotent skip on `mistral.md` existence. |
| AC7 | `docs/closure/031-S-mistral-ocr-spike.md` documents the verdict (ADOPT / PROMOTE-AS-PEER / ABANDON) with quantified per-metric findings vs docling, mirroring the 029-S closure structure. |
| AC8 | All quality gates pass: `ruff check .`, `ruff format --check .`, `pyright src/`, `pytest`. No regressions in the existing 1198-test suite (modulo the ADI tests being deleted, which is expected). |
| AC9 | If verdict is ADOPT, the closure doc proposes the auto-policy revision as a follow-up stash item (do NOT change auto-policy in 031-S — that's a separate decision). |
| AC10 | If verdict is ABANDON, the closure doc files a follow-up stash item to remove Mistral in a subsequent shipment (do NOT remove in 031-S — operator confirms first). |

## Task Decomposition

| Task | Effort | Description |
|---|---|---|
| T1 | ~3h | **Remove ADI** — touches ~12 files: `pyproject.toml` (remove `[adi]`), `src/docline/dependencies.py` (remove `adi_available`), `src/docline/readers/adi.py` (delete), `src/docline/readers/pdf.py` (remove `azure_di` from supported engines, dispatch path, imports), `src/docline/app_models.py` (Literal), `src/docline/cli.py` (choices), `src/docline/app.py` (MCP manifest enum), `tests/readers/conftest.py` (remove `install_fake_adi_sdk`, FakeAzure shims), `tests/readers/test_adi_extractor.py` (delete), `tests/process/test_adi_extractor_optional.py` (delete), `tests/readers/test_pdf_engine_routing.py` (remove ADI-specific tests), `scripts/study/adi_comparison.py` (delete), `.env.example` (remove AZURE_DOCUMENT_INTELLIGENCE_* placeholders), `README.md` (any ADI mentions). Add a status note to `docs/closure/029-S-adi-spike.md` pointing to 031-S. |
| T2 | ~2h | **Add `[mistral]` extra + reader module** — `pyproject.toml` adds `mistral = ["mistralai>=1,<2"]`. `src/docline/dependencies.py` gains `mistral_available()`. New `src/docline/readers/mistral.py` with `read_pdf_mistral(path, api_key=None, model="mistral-ocr-latest") -> str` + `MistralCredentialError`. Lazy SDK import; env-var `MISTRAL_API_KEY` resolution; per-call telemetry. TDD: 8-10 tests covering happy path, credential resolution, SDK-missing, transient error, model parameter. |
| T3 | ~1.5h | **Wire `mistral_ocr` through full surface** — extend `_SUPPORTED_LAYOUT_ENGINES` and `pdf_engine` Literal. CLI `--pdf-engine` choices include `mistral_ocr`. MCP manifest auto-surfaces via Pydantic. `read_pdf_pages` dispatches `mistral_ocr` with credential fast-fail + explicit-request error surfacing (no silent fallback — same contract as the explicit-`azure_di` pattern we just established). Auto-policy unchanged (docling > heuristic; Mistral stays opt-in). TDD: 6-8 routing tests. |
| T4 | ~2.5h dev + ~10 min wall + ~$0.55 | **Empirical comparison + closure doc** — fork `scripts/study/adi_comparison.py` (already deleted in T1; restored from git history) as `scripts/study/mistral_comparison.py`. Same 15 cosmos ranges. Same `_compute_metrics` flow using `evaluate_markdown.metrics_for`. Same idempotent skip. Same split-and-retry on size errors if applicable. Run against operator's `MISTRAL_API_KEY`. Write `docs/closure/031-S-mistral-ocr-spike.md` with: empirical results table, per-metric mean/min/max, per-range table, throughput + cost summary, verdict (ADOPT / PROMOTE-AS-PEER / ABANDON), follow-up stash recommendations. |

**Total**: ~9h human-equivalent effort + ~$0.55 study cost.

Span: removes ~600 lines of ADI code/tests, adds ~500 lines of Mistral
code/tests + ~250 lines of study harness. Net code volume roughly
equivalent to 029-S since most of the work mirrors that shipment's
shape.

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Mistral SDK API surface differs significantly from ADI's, complicating the reader module | Mistral's official `mistralai` Python SDK has documented `client.ocr.process()` method that returns structured response; we mirror the ADI lazy-import + error-wrapping pattern | T2 isolated to one new module; revert just the reader if SDK proves unworkable |
| Mistral OCR rate limits constrain the empirical study | Mistral free tier allows enough requests for 551-page study; if rate-limited, add exponential backoff in `mistral_comparison.py` | T4 study is idempotent; partial results still inform verdict |
| Mistral also empirically loses to docling | Verdict becomes ABANDON; we file a follow-up stash to rip Mistral the same way 031-S rips ADI | Identical rollback pattern proven by this shipment |
| ADI removal breaks something I missed | Full test suite + grep audit before merge | Single revert commit restores all ADI code from git history |
| Operator's `.env.local` still has `AZURE_DOCUMENT_INTELLIGENCE_*` after ADI removal | Closure doc notes the operator should clean their local `.env.local` manually | Harmless — the env vars are simply ignored after T1 |

## Plan Constitution Check

* **I (Safety-First Python)**: All new functions typed, exceptions raised
  with typed subclasses, no bare `except`. ✓
* **II (Test-First)**: Each task starts with failing tests. T2 has 8-10
  tests, T3 has 6-8 tests. T4 validates empirically. ✓
* **III (Workspace Isolation)**: No new path operations. Study script
  uses existing `.elt/output/cosmos-triage-022/study/` workspace. ✓
* **VII (Destructive Approval)**: T1 deletes ~600 lines and 3 test files
  — operator's directive is explicit ("strip out anything to do with
  ADI"). Removal is approved by the request itself. ✓
* **X (Context Efficiency)**: Reader operates on per-page response;
  no bulk text loading. Study harness is incremental + idempotent. ✓

## Notes for Stage / Harvest

Single feature `029-F` with 4 tasks (`029.001-T` through `029.004-T`).
Ships under shipment `031-S`. No deliberation needed — problem framing
and architectural direction are well-established by 029-S precedent and
operator directive. No spike needed — this IS the spike, with the same
empirical-validation gate that 029-S used.
