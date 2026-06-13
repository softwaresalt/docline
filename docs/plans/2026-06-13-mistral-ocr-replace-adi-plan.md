---
date: 2026-06-13
shipment_target: 031-S
stash_origin: (partial) B26003B0 — supersedes ADI cleanup
references:
  - docs/closure/029-S-adi-spike.md  # KEEP-AS-PEER verdict that this shipment supersedes
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - scripts/study/adi_comparison.py  # template for the new mistral_comparison.py
---

# Plan: Replace ADI with Mistral OCR via Microsoft Foundry (rip + replace + spike)

## Problem

The 2026-06-12 empirical study (`docs/closure/029-S-adi-spike.md`) found
Azure Document Intelligence's `prebuilt-layout` model loses on every
structural fidelity metric vs docling on cosmos-class technical
reference PDFs (mean −70% chars, mean −74% headings, 100% table loss on
10/15 ranges, 100% list loss on 13/15 ranges). The 029-S verdict was
**KEEP-AS-PEER** — leave ADI available for explicit opt-in.

The operator's directive (2026-06-13): since ADI is empirically a bad
option for the docline → graphtor-docs pipeline, strip it out entirely
and evaluate Mistral OCR as its replacement cloud peer. The operator
has chosen to access Mistral OCR via **Microsoft Foundry MaaS** (not
Mistral's direct API) because they have stronger existing access to
Foundry models through their organizational accounts.

Mistral OCR (`mistral-ocr-2503` released March 2025, `mistral-document-ai-2505`
released May 2025) is Mistral's dedicated document-to-markdown product —
different design intent from ADI's form-extraction lineage. Reported
strengths are tables, equations, code, and dense text — precisely the
failure modes ADI exhibited. Hosted on Foundry MaaS at standard model
catalog rates (operator handles their Foundry billing). Empirical
validation against the same 15 cosmos ranges will decide whether
Mistral OCR becomes:

- **ADOPT** — make `mistral_ocr` the auto-preferred cloud engine
- **PROMOTE-AS-PEER** — ship as opt-in peer like ADI was (but
  potentially better positioned)
- **ABANDON** — file a follow-up shipment to remove Mistral the same
  way 031-S removes ADI

## Access pattern: Foundry MaaS + `mistralai` SDK

Microsoft Foundry hosts Mistral OCR models via the standard MaaS
deployment shape. The official `mistralai>=1,<2` Python SDK supports a
custom `server_url` parameter that points at any Mistral-compatible
endpoint — including a Foundry deployment URL of the form:

```
https://<deployment-name>.<region>.models.ai.azure.com/
```

This means the same reader module works against either:

1. **Microsoft Foundry** (operator's chosen path) — `server_url` set
   from `AZURE_AI_FOUNDRY_ENDPOINT` env var; auth from
   `AZURE_AI_FOUNDRY_KEY`.
2. **Mistral's direct API** (fallback / future option) — `server_url`
   left at SDK default; auth from `MISTRAL_API_KEY` env var.

Operators pick by setting whichever env var pair they have. The reader
prefers Foundry when `AZURE_AI_FOUNDRY_*` is set and falls back to
direct Mistral when only `MISTRAL_API_KEY` is set.

## Model selection

Two Mistral document models on Foundry as of 2026-06:

| Model | Release | Notes |
|---|---|---|
| `mistral-ocr-2503` | March 2025 | Original Mistral OCR; the canonical "document → markdown" model |
| `mistral-document-ai-2505` | May 2025 | Newer "Document AI" branded successor with improved layout + table extraction |

Default to `mistral-document-ai-2505` (newer + improved). Operator
overrides via `--model` CLI flag or `MISTRAL_OCR_MODEL` env var.

## Goals

1. Remove all ADI integration from the codebase — pyproject extra,
   reader module, dispatch path, ProcessRequest Literal, CLI choice,
   MCP manifest entry, dependencies helper, test fixtures + ADI test
   files, study script, README/env.example mentions.
2. Add Mistral OCR as a new `pdf_engine` peer with the same opt-in
   shape ADI had: optional `[mistral]` extra, env-var-or-arg auth +
   endpoint, credential fast-fail, transient-error surfacing on
   explicit request.
3. Default deployment target is Microsoft Foundry MaaS via
   `AZURE_AI_FOUNDRY_ENDPOINT` + `AZURE_AI_FOUNDRY_KEY`. Direct
   Mistral API works as a fallback when only `MISTRAL_API_KEY` is set.
4. Run the empirical comparison against the same 15 cosmos ranges
   already cached from the 029-S study so the result is apples-to-apples.
5. Document the verdict with the same rigor as 029-S — quantified
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
- Self-hosted Mistral OCR. Out of scope for this spike; Foundry MaaS
  (or direct Mistral API) only.
- Deploying anything TO Foundry. The operator's Mistral OCR deployment
  is assumed to already exist on their Foundry tenant.

## Acceptance Criteria

| ID | Criterion |
|---|---|
| AC1 | No reference to `azure_di`, `adi`, `azure-ai-documentintelligence`, `AZURE_DOCUMENT_INTELLIGENCE_*`, `AdiCredentialError`, or `read_pdf_adi` remains in `src/`, `tests/`, `scripts/study/` (except `docs/closure/029-S-adi-spike.md` as historical record). |
| AC2 | `pyproject.toml` has `[mistral]` optional extra pinned to `mistralai>=1,<2`. `[adi]` extra is removed. |
| AC3 | `src/docline/readers/mistral.py` exposes `read_pdf_mistral(path, api_key=None, server_url=None, model="mistral-document-ai-2505") -> str` and `MistralCredentialError`. Returns markdown directly. Lazy SDK import. Telemetry: per-call page count + wall time + projected cost. |
| AC4 | Credential resolution order: explicit `api_key`/`server_url` args → `AZURE_AI_FOUNDRY_KEY`+`AZURE_AI_FOUNDRY_ENDPOINT` (Foundry preferred) → `MISTRAL_API_KEY` with SDK default `server_url` (direct Mistral fallback). Raises `MistralCredentialError` when neither pair is resolvable. |
| AC5 | `pdf_engine` Literal is `Literal["auto", "docling", "mistral_ocr", "heuristic"]`. `_SUPPORTED_LAYOUT_ENGINES = frozenset({"auto", "heuristic", "docling", "mistral_ocr"})`. CLI `--pdf-engine` choices match. MCP manifest enum matches. |
| AC6 | `_resolve_layout_engine("auto")` returns docling when installed, else heuristic. Mistral is NEVER auto-selected pending T4 verdict. |
| AC7 | `scripts/study/mistral_comparison.py` runs against the same 15 cosmos ranges already cached at `.elt/output/cosmos-triage-022/study/dataset/range-NNNN-NNNN/` and emits `mistral-findings.{json,md}` in the same format as the ADI comparison. Idempotent skip on `mistral.md` existence. |
| AC8 | `docs/closure/031-S-mistral-ocr-spike.md` documents the verdict (ADOPT / PROMOTE-AS-PEER / ABANDON) with quantified per-metric findings vs docling, mirroring the 029-S closure structure. |
| AC9 | All quality gates pass: `ruff check .`, `ruff format --check .`, `pyright src/`, `pytest`. No regressions in the existing 1198-test suite (modulo the ADI tests being deleted, which is expected). |
| AC10 | If verdict is ADOPT, the closure doc proposes the auto-policy revision as a follow-up stash item (do NOT change auto-policy in 031-S — that's a separate decision). If verdict is ABANDON, the closure doc files a follow-up stash item to remove Mistral in a subsequent shipment (do NOT remove in 031-S — operator confirms first). |

## Task Decomposition

| Task | Effort | Description |
|---|---|---|
| T1 | ~3h | **Remove ADI** — touches ~12 files (see T1 task description for full list). Audit: zero matches for ADI-related identifiers in src/tests/scripts. |
| T2 | ~2.5h | **Add `[mistral]` extra + reader module** — `mistralai>=1,<2`. `read_pdf_mistral(path, api_key=None, server_url=None, model="mistral-document-ai-2505")`. Credential resolution prefers Foundry env vars. Per-call telemetry. 11-14 TDD tests. |
| T3 | ~1.5h | **Wire `mistral_ocr` through full surface** — pdf.py, app_models.py, cli.py, MCP manifest. Auto-policy preserves docling-first. 6-8 routing tests. |
| T4 | ~2.5h + ~$0.55 | **Empirical comparison + closure doc** — fork study harness, run against same 15 cosmos ranges, write closure with verdict. |

**Total**: ~9.5h human-equivalent effort + ~$0.55 study cost (operator's Foundry quota).

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Foundry MaaS Mistral OCR deployment uses a different API shape than direct Mistral (e.g. Azure Inference SDK pattern) | T2 starts with a 30-min discovery probe against the operator's actual Foundry deployment to confirm `mistralai` SDK + custom `server_url` works. If not, switch SDK choice to `azure-ai-inference` and adjust dependency pin. | Single new module; isolate change to T2 |
| Operator's Foundry deployment has a regional quota limit that breaks the 551-page study | mistral_comparison.py is idempotent; partial results still inform verdict. Operator runs against a smaller cosmos subset if needed. | Reduce study to fewer ranges; verdict still actionable |
| Mistral also empirically loses to docling | Verdict becomes ABANDON; we file a follow-up stash to rip Mistral the same way 031-S rips ADI | Identical rollback pattern proven by this shipment |
| ADI removal breaks something I missed | Full test suite + grep audit before merge | Single revert commit restores all ADI code from git history |
| Operator's `.env.local` still has `AZURE_DOCUMENT_INTELLIGENCE_*` after ADI removal | Closure doc notes the operator should clean their local `.env.local` manually | Harmless — the env vars are simply ignored after T1 |
| Operator confuses Foundry endpoint with the wrong service (e.g. Azure OpenAI endpoint) | Reader validates the endpoint URL shape (`.models.ai.azure.com/` for MaaS) and raises a clear `MistralCredentialError` with the expected pattern | Operator corrects env var |

## Plan Constitution Check

* **I (Safety-First Python)**: All new functions typed, exceptions raised
  with typed subclasses, no bare `except`. ✓
* **II (Test-First)**: Each task starts with failing tests. T2 has 11-14
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
Ships under shipment `031-S`. No deliberation needed — problem framing,
architectural direction, and access path (Foundry MaaS) are all
established by 029-S precedent + operator directive. No spike needed —
this IS the spike, with the same empirical-validation gate that 029-S
used.
