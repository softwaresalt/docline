---
shipment: 045-S
title: "Closure record — pre-Mistral hardening: OCR calibration test coverage + weights-path containment (042-F)"
status: verified
merge_sha: 31c8c5e
merged_pr: 118
---

## Scope delivered

Feature `042-F` groups two independent, agent-buildable follow-ups selected to
make progress while Mistral OCR v4 / Foundry access is unavailable. Neither task
depends on Mistral or Foundry.

| Task | Delivered |
|---|---|
| `042.001-T` | `scripts/study/ocr_memory_calibration.py` — extracted the previously-untested inline helpers from `_run` to module level: `page_megapixels`, `build_group_pdf`, `classify_outcome`. The docling/psutil subprocess `measure()` stays nested and availability-guarded. Unit tests added in `tests/test_ocr_memory_calibration.py`. |
| `042.002-T` | `src/docline/process/fidelity_scorer.py` — opt-in `workspace_root` keyword on `load_weights` and `load_pre_triage_weights`; when supplied, the weights path must be workspace-relative and resolve inside the root via `docline.paths` helpers, else a typed `FidelityScorerError`. `workspace_root=None` preserves trusted CLI behavior. Tests in `tests/process/test_fidelity_scorer.py`. |

## Verification

- `ruff check .` — clean
- `pyright src/` — 0 errors
- `pytest` — full suite green (7 new tests)
- `ruff format --check .` — clean
- Copilot review on PR #118 — COMMENTED, 0 inline findings on merged HEAD

CI is intentionally paused in `.github/workflows/ci.yml` (triggers only on tags /
releases / manual dispatch to conserve Actions minutes); gates were run locally
under `uv run`.

## Notes

- `042.002-T` containment is opt-in and currently exercised only by tests — no
  production caller passes `workspace_root` yet. It becomes active protection
  when `ProcessRequest` is exposed via the MCP server with a caller-controlled
  weights path.
- A pre-existing PR #117 Copilot comment (a stale test-path reference in the
  `042.002-T` backlog note) was corrected in `fca5e52`, replied to, and resolved
  before the build.
