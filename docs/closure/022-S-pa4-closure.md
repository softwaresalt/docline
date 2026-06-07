---
title: Closure — 022-S PA4 calibration closure (markitdown + Jaccard + layout-complexity)
date: 2026-06-07
shipment: 022-S
feature: 020-F
status: verified
merged_pr: 44
merge_sha: f4ef7f1
branch: feat/022-S-pa4-closure
decision: docs/decisions/2026-06-07-pa4-calibration-closure.md
plan: docs/plans/2026-06-07-pa4-calibration-closure-plan.md
review: docs/closure/022-S-review.md
parent_closure: docs/closure/021-S-triage-then-repair.md
compound_learnings: docs/compound/2026-06-06-triage-then-repair-pattern.md
follow_up_stashes: 7AA9FAA0, 4CA80776, 5CFE4481, 24920EFF, DE3E7346
---

## Readiness status

**READY** — merge to `main` is complete (PR #44, merge commit `f4ef7f1`).
Triage mode now ships with a tokenized Jaccard QA metric, a per-page
layout-complexity signal that fires on table-rich pages whose source
layout is collapsed by `pypdf` extraction, and a configurable
`baseline_engine` capable of running `markitdown` as an alternative
heuristic. The two blockers identified in 021-S PA4 (Blocker A —
coarse diff metric; Blocker B — scorer architectural blind spot) are
both closed at the code level. Operator re-run of PA3 + PA4 on the
cosmos corpus remains the final step before promoting 021-S closure
to `production-ready`.

## Scope

* **U1 — markitdown baseline engine** (`src/docline/process/pdf_triage.py`):
  added `baseline_engine` kwarg (`"pypdf"` default, `"markitdown"`
  opt-in) to `process_pdf_triaged` and `triage_report_only`. A module-
  level `_get_markitdown()` singleton avoids per-page `MarkItDown()`
  reinstantiation (~250 ms each).
* **U2 — Jaccard QA tripwire** (`src/docline/process/pdf_triage.py`):
  added `_TOKEN_RE`, `_content_similarity` (lowercased, punctuation-
  stripped tokenized Jaccard), and `QASampling.similarity_threshold`
  (default 0.7). QA disagreements are now recorded with a
  `qa_similarity_histogram` (`[0,0.3) | [0.3,0.5) | [0.5,0.7) | [0.7,1.0]`),
  collapsing formatting-only noise into the high bucket so calibration
  reflects true content drift only.
* **U3 — layout-complexity signal** (`src/docline/process/fidelity_scorer.py`):
  added `signal_layout_complexity` + `_count_x_clusters` (a PDF
  content-stream `Tm/Td/TD` regex-based X-coordinate cluster counter)
  to the eight-signal scorer; weight 1.1 in `_DEFAULT_SIGNAL_WEIGHTS`.
  Fires when source X-clusters are dense but heuristic-extracted text
  is sparse — the exact failure mode that hid page 470 in PA4.
* **U4 — PA3 script flag surface** (`scripts/pa3_triage_cosmos.py`):
  added `--baseline-engine`, `--similarity-threshold`, `--qa-random-seed`,
  `--qa-max-pages` flags wired through `QASampling` + `process_pdf_triaged`.
* **U5 — markitdown dependency** (`pyproject.toml`, `uv.lock`):
  added `markitdown[pdf]>=0.1.6,<0.2`; refreshed `uv.lock` (+7 transitive
  deps) so CI `uv sync --locked` succeeds.

## Files changed

| Path | Change |
|---|---|
| `pyproject.toml` | ADD — `markitdown[pdf]>=0.1.6,<0.2` runtime dep |
| `uv.lock` | REFRESH — markitdown + 7 transitive deps locked |
| `src/docline/process/pdf_triage.py` | MODIFY — `_TOKEN_RE`, `_get_markitdown`, `_content_similarity`, `_heuristic_extract`, `baseline_engine` kwarg, `qa_similarity_histogram`; removed dead `_normalize_markdown` |
| `src/docline/process/fidelity_scorer.py` | MODIFY — `signal_layout_complexity` + `_count_x_clusters`; layout_complexity added to `_SIGNAL_NAMES` and `_DEFAULT_SIGNAL_WEIGHTS` |
| `scripts/pa3_triage_cosmos.py` | MODIFY — 4 new flags |
| `tests/test_markitdown_dependency.py` | ADD — import + version contract |
| `tests/process/test_pdf_triage_baseline_engine.py` | ADD — dispatch and ordering tests |
| `tests/process/test_pdf_triage_similarity.py` | ADD — Jaccard threshold + histogram tests |
| `tests/process/test_fidelity_scorer_layout.py` | ADD — X-cluster signal tests |
| `tests/test_pa3_script_flags.py` | ADD — script argparse contract |
| `docs/decisions/2026-06-07-pa4-calibration-closure.md` | ADD — decision artifact |
| `docs/plans/2026-06-07-pa4-calibration-closure-plan.md` | ADD — plan with hardening + review |
| `docs/closure/022-S-review.md` | ADD — code review record |

## Invariants to preserve

| Invariant | Verification |
|---|---|
| `baseline_engine="pypdf"` remains the default; existing callers unaffected | `test_pdf_triage_baseline_engine.py::test_default_baseline_is_pypdf` |
| `_get_markitdown()` returns a singleton; only instantiated once per process | `test_pdf_triage_baseline_engine.py::test_markitdown_instantiated_once` |
| Jaccard similarity ∈ [0, 1.0]; identical strings → 1.0; disjoint → 0.0 | `test_pdf_triage_similarity.py::test_content_similarity_bounds` |
| QA histogram buckets sum to `qa_sampled_count` | `test_pdf_triage_similarity.py::test_histogram_total_matches_sample_count` |
| `signal_layout_complexity` returns 0 for empty/whitespace pages | `test_fidelity_scorer_layout.py::test_layout_signal_zero_on_empty` |
| `_SIGNAL_NAMES` lists exactly 8 signals | `test_fidelity_scorer_layout.py::test_signal_count_is_eight` |
| `_DEFAULT_SIGNAL_WEIGHTS` contains exactly the 8 named signals | `test_fidelity_scorer_layout.py::test_default_weights_match_signal_names` |

## Pre-deploy audits

* ✅ 1008 passed / 3 skipped / 0 failed (full pytest)
* ✅ Ruff lint + format clean on all new/modified files (pre-existing
  `scripts/load_test.py` E501 violations untouched per surgical-changes
  discipline)
* ✅ Pyright clean
* ✅ Plan-review gate: ADVISORY (0 P0/P1)
* ✅ Code-review gate: PASS (0 P0/P1, 1 P2 bounded-safe, 7 P3 advisory)
* ✅ Copilot Review on PR #44: 4 valid findings (dead `_normalize_markdown`,
  per-page `MarkItDown()` instantiation, missing docstrings, signal count
  mismatch) all addressed in commit `2171578`; suppressed-low-confidence
  docstring symmetry note addressed in commit `07ddbdb`; threads replied +
  resolved
* ✅ Merge commit history preserved (used `--merge`, not `--squash` /
  `--rebase`, per Constitution XI / P-009)
* ✅ All 5 task acceptance criteria satisfied

## Deployment / rollout path

Merge-only. No service deploy. No data migration. No config push.

* `--pdf-mode triage` continues to default to `baseline_engine="pypdf"`;
  existing operator invocations unchanged.
* Markitdown is now an opt-in via `--baseline-engine markitdown`
  (PA3 script flag wired; library kwarg public).
* QA tripwire similarity threshold is configurable per-run via
  `--similarity-threshold` (default 0.7).

## Post-merge checks (PA3 + PA4 re-run on cosmos)

Operator runs in plain PowerShell (per 2026-06-04 RCA — never inside
agent process):

```powershell
cd D:\Source\GitHub\docline
.\.venv\Scripts\python.exe scripts\pa3_triage_cosmos.py `
    --output-dir .elt\output\cosmos-triage-022 `
    --log-path logs\pa3-cosmos-triage-022.log `
    --sample-rate 0.01 --qa-random-seed 42
```

Acceptance criteria for promoting 021-S to `production-ready`:

* ☐ Wall-clock ≤ 75 minutes (≤ 25 % of all-docling baseline; previous
  PA3 ran 50 min)
* ☐ Flag rate in [5 %, 15 %] of total pages (page 470 RBAC table and
  analogous pages must now flag thanks to U3)
* ☐ `qa_disagreements / qa_sampled_count < 30 %` under the new Jaccard
  metric (Blocker A resolution; previously 97 % under the broken
  string-equality metric)
* ☐ `subprocess_fallback_count` < 10 % of flagged ranges

If all four pass, update `docs/closure/021-S-triage-then-repair.md`
frontmatter `status: verified` → `status: production-ready` and append a
"PA3 + PA4 re-run evidence (post-022-S)" subsection citing the new
`pa3-summary.json`.

## Risky-action ledger

| ID | ProposedAction | ActionRisk | ActionResult |
|---|---|---|---|
| **PA1** | Add `markitdown[pdf]` to runtime dependencies | low | **applied** (commit `0e94340`; `uv.lock` regenerated in `fc55c94`) |
| **PA2** | Add `baseline_engine` kwarg to public `process_pdf_triaged` API | low | **applied** — default is `"pypdf"`, existing callers unaffected |
| **PA3** | Replace string-equality QA metric with tokenized Jaccard | moderate | **applied** — old `_normalize_markdown` removed in same commit; `qa_similarity_histogram` added so calibration retains visibility into the distribution |
| **PA4** | Add layout-complexity signal that introspects PDF content streams | moderate | **applied** — `_count_x_clusters` parses Tm/Td/TD operators directly; tested against synthetic and real fixtures; weight 1.1 in defaults |
| **PA5** | Re-run PA3 + PA4 on cosmos to confirm Blocker A + B closed end-to-end | low | **deferred to operator** — see "Post-merge checks" above; must run from plain shell |

## Failure signals (rollback triggers)

Same as 021-S, plus two new metrics introduced in 022-S:

1. `qa_similarity_histogram[[0,0.3)] / qa_sampled_count > 0.20` —
   genuine content-drift disagreements exceed 20 %; scorer is missing
   real fidelity gaps.
2. Layout-complexity signal fires on > 50 % of pages on a known
   prose-heavy corpus (e.g., a published novel PDF) — `_count_x_clusters`
   is over-detecting columnar structure.

Rollback procedure for 022-S follows the 021-S procedure: triage is a
CLI flag, not a code path that auto-activates. To revert just 022-S
without losing 021-S, `git revert -m 1 f4ef7f1`.

## Monitoring plan

No always-on monitoring. Per-run signals captured in the manifest
`triage_stats` block and run log:

* `qa_similarity_histogram` (4 buckets)
* `qa_random_seed_used`
* `baseline_engine_used` (`pypdf` or `markitdown`)
* `signal_layout_complexity` per-page scores (in `--triage-report-only`
  TSV)

## Owner

* **Implementation owner**: docline maintainer (current single-maintainer
  workspace)
* **Calibration owner**: same — operator runs PA3 + PA4 from plain shell
* **Watch window**: 1 week / 3 cosmos-class invocations, whichever
  comes first

## Follow-up work captured

Carried forward from 021-S (still open):

| Stash | Priority | Description |
|---|---|---|
| `5CFE4481` | medium | Per-page docling output protocol (single blob per range) |
| `24920EFF` | low | Validate `weights_path` in `load_weights` for MCP exposure |
| `DE3E7346` | low | Extract shared Pass 1-2 helper |

New / unrelated stashes:

| Stash | Priority | Description |
|---|---|---|
| `7AA9FAA0` | low | PyPI release workflow |
| `4CA80776` | low | Docling OCR tuning |

## Compound learning

022-S did not invalidate `docs/compound/2026-06-06-triage-then-repair-pattern.md`.
It strengthens two pattern recommendations originally captured there:

1. The QA tripwire must use a content-similarity metric, not a string-
   equality metric. (Blocker A confirmed this empirically with the
   97 % false-positive rate on cosmos.)
2. Heuristic-only scoring is insufficient when the heuristic itself
   silently destroys layout structure. Source-document introspection
   (in this case, PDF content streams) is required for the failure
   class where "the output looks fine but the input had structure".

Both items reinforce the original pattern rather than supersede it; no
edits to `2026-06-06-triage-then-repair-pattern.md` required.

## Recommendation

**READY** — merge has landed. The two blockers identified in 021-S PA4
are closed at code level. Operator PA3 + PA4 re-run on cosmos is the
final step; expected to confirm page 470 (and analogous tables) now
flag correctly, with disagreement rate dropping from the misleading
97 % to a meaningful single-digit-to-mid-double-digit percent that
reflects true content drift only.

After the re-run lands and the four acceptance criteria above pass,
021-S transitions to `status: production-ready`.
