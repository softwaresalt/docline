---
date: 2026-06-11
shipment_target: 030-S
stash_origin: EFC6C84E
references:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/closure/021-S-triage-then-repair.md
  - src/docline/process/fidelity_scorer.py
  - src/docline/process/pdf_triage.py
---

# Plan: Invert Triage Scoring Model — Pre-Extraction Routing

## Problem

The current `--pdf-mode triage` fidelity scorer fires **after** running
heuristic extraction (`markitdown` or `pypdf`) across the whole document. The
2026-06-08 extraction-strategy study found that on cosmos-class technical PDFs
docling wins 14 of 15 sampled ranges on AST quality regardless of how the
heuristic scored them — so the heuristic extraction work was wasted on pages
already destined for docling.

The existing fidelity scorer has 8 signals split into two categories:

* **Text-based signals** (5): `char_density`, `non_ascii_ratio`,
  `long_unbroken_line`, `column_gap`, `table_char_density` — require heuristic
  extraction first.
* **Source-aware signals** (3): `image_heavy`, `form_fields`,
  `layout_complexity` — operate directly on the `pypdf.PageObject` and need no
  heuristic extraction.

The inversion is to extract a **pre-extraction scorer** that uses only
source-aware signals to short-circuit obviously-complex pages directly to
docling. Pages that the pre-scorer cannot confidently classify continue
through the existing heuristic-then-score path as a fallback.

## Goals

1. Add two new source-aware signals (`font_diversity`,
   `text_flow_consistency`) extending the existing 3, for a total of 5
   pre-extraction signals.
2. Extract a `pre_triage_score(page_metadata) -> PreTriageDecision` function
   that returns one of three classifications: `route_to_docling`,
   `route_to_heuristic`, `uncertain`.
3. Re-wire `pdf_triage.py`'s main pass to call the pre-triage scorer first.
   Pages classified `route_to_docling` skip heuristic extraction entirely and
   are added to docling ranges immediately. Pages classified `uncertain`
   continue through the existing heuristic + post-extraction scoring path.
   Pages classified `route_to_heuristic` accept the heuristic output without
   scoring.
4. Add a new opt-in CLI flag `--triage-pre-score` (default: off for backward
   compatibility) so existing triage runs are not silently re-routed.
5. Add a deterministic, page-level pre-triage report mode that emits the new
   5-signal scores for calibration without invoking docling.
6. Validate on the cosmos study fixture: pre-triage classifications should
   match docling's empirical wins from the 2026-06-08 study (≥85% agreement).

## Non-Goals

* Removing the existing post-extraction scoring path. It remains the safety
  net for `uncertain` pre-triage classifications.
* Changing `--pdf-mode auto` (the default) or any default behavior. The new
  pre-triage path is opt-in via `--triage-pre-score`.
* Re-tuning the existing 8 signal weights. Tuning of the new 5-signal
  pre-triage weights is a separate calibration follow-up.
* GPU acceleration or docling batch tuning (separate stash `51332802`).
* Cross-product analysis with markitdown or ADI (separate stashes).

## Acceptance Criteria

| ID | Criterion |
|---|---|
| AC1 | Two new source-aware signal functions exist in `fidelity_scorer.py`: `signal_font_diversity(page_metadata)` and `signal_text_flow_consistency(page_metadata)`. Each is pure (no network, no extraction), deterministic, and returns a `float` in `[0.0, 1.0]`. |
| AC2 | A new `pre_triage_score(page_metadata, weights_path=None) -> PreTriageDecision` function exists with frozen result type `PreTriageDecision(page_index, signals, aggregate, classification, reason)` where `classification` is `Literal["route_to_docling", "route_to_heuristic", "uncertain"]`. |
| AC3 | The `--triage-pre-score` CLI + MCP flag is wired through `app_models.ProcessRequest` and `pdf_triage.py`. When unset (default), behavior is identical to current `--pdf-mode triage`. When set, the new pre-triage path runs. |
| AC4 | A `--triage-pre-score-report-only` mode emits a per-page TSV with the 5 pre-triage signal scores + classification + reason, without invoking docling. |
| AC5 | Validation harness `scripts/study/validate_pre_triage.py` runs the pre-triage scorer against the cosmos study fixtures, emits agreement-percentage vs the 2026-06-08 docling-winners ground truth, and exits non-zero if agreement < 85%. |
| AC6 | All quality gates pass: `ruff check .`, `ruff format --check .`, `pyright src/`, `pytest`. No regressions in the existing 1198-test suite. |
| AC7 | Closure doc at `docs/closure/030-S-invert-triage-scoring.md` documents the new flag, the calibration results, and a rollout recommendation (ADOPT / KEEP-AS-OPT-IN / ABANDON). |

## Task Decomposition

| Task | Effort | Description |
|---|---|---|
| T1 | ~1.5h | Add `signal_font_diversity` and `signal_text_flow_consistency` to `fidelity_scorer.py` with TDD. Each signal walks the `pypdf.PageObject` content stream; defensive-degrade to `0.0` on parse errors (same pattern as `signal_layout_complexity`). |
| T2 | ~1.5h | Add `PreTriageDecision` dataclass, `pre_triage_score` function, and `_PRE_TRIAGE_SIGNAL_NAMES` + `_DEFAULT_PRE_TRIAGE_WEIGHTS` constants. Pre-triage uses 5 signals: the 3 existing source-aware + the 2 new. Classification thresholds are configurable via the same weights-path mechanism. |
| T3 | ~2h | Wire `--triage-pre-score` and `--triage-pre-score-report-only` through CLI (`cli.py`), MCP (manifest), and `ProcessRequest` (`app_models.py`). Modify `pdf_triage.py`'s main pass to short-circuit when pre-scoring classifies as `route_to_docling` or `route_to_heuristic`. |
| T4 | ~1.5h | Build `scripts/study/validate_pre_triage.py` — runs pre-triage scorer against cosmos study fixtures, emits agreement-percentage, exits non-zero if < 85%. Write closure doc with calibration results and rollout recommendation. |

**Total**: ~6.5h human-equivalent effort. Spans `fidelity_scorer.py` (compute),
`pdf_triage.py` (orchestration), `cli.py` + `app_models.py` (surfaces),
`scripts/study/` (validation). Single thematic concern (pre-extraction
scoring) so all tasks fit one shipment.

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| New signals over-fire and route too many pages to docling, hurting throughput | Validation harness AC5 enforces ≥85% agreement against ground truth before rollout | Disable `--triage-pre-score` flag in CLI; existing path is unchanged |
| `_count_x_clusters`-style content-stream parsing breaks on edge-case PDFs | Both new signals follow the defensive-degrade pattern: return `0.0` on any `pypdf` exception, log at DEBUG, continue with remaining signals | New signals contribute 0.0; pre-triage falls back to `uncertain` and uses heuristic path |
| Pre-triage classifications diverge between Python 3.12 and 3.14 due to dict ordering | All signal computation is order-independent (dict access by key, no iteration order dependencies); tests run on both versions | N/A — orderable by construction |
| Operator misuses `--triage-pre-score` and surprises themselves | Default is off; help text + closure doc explain when to enable; report-only mode lets operator calibrate first | Drop the flag from invocation |

## Plan Constitution Check

* **Principle I (Safety-First Python)**: All new functions typed, all errors
  via raise-with-typed-exception, no bare except. ✓
* **Principle II (Test-First)**: Each task starts with failing tests. T1 has
  4 tests (2 per signal × happy + parse-error); T2 has 6 tests covering all 3
  classifications + edge cases; T3 has 4 tests covering CLI flag passthrough;
  T4 has 2 tests + the validation script itself. ✓
* **Principle III (Workspace Isolation)**: No new path operations. Weights JSON
  path validation reuses existing `safe_workspace_path`. ✓
* **Principle X (Context Efficiency)**: Pre-triage decision is one
  `PreTriageDecision` instance per page; no bulk text loading when
  pre-scoring short-circuits to docling. ✓

## Notes for Stage / Harvest

Single feature `028-F` with 4 tasks (`028.001-T` through `028.004-T`). Ships
under shipment `030-S` for the next merge cycle. No deliberation needed —
problem framing and architectural direction are well-defined by the
2026-06-08 study. No spike needed — the new signals are concrete extensions
of the existing pattern.
