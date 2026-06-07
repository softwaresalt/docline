---
title: Code Review — 022-S close PA4 calibration
date: 2026-06-07
shipment: 022-S
feature: 020-F
branch: feat/022-S-pa4-closure
status: PASS
gate_decision: PASS
plan: docs/plans/2026-06-07-pa4-calibration-closure-plan.md
decision: docs/decisions/2026-06-07-pa4-calibration-closure.md
related_closure: docs/closure/021-S-triage-then-repair.md
findings_summary: 0 P0, 0 P1, 1 P2, 7 P3
---

## Gate decision

**PASS** — proceed to fix-ci → pr-lifecycle.

| Severity | Count | Action |
|---|---|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 1 | Documented as advisory; safe failure mode (over-counting → more docling routing, never wrong content) |
| P3 | 7 | Advisory; tracked in this artifact |

No P0/P1 findings. The single P2 finding is bounded — its failure mode
is "scorer over-fires, routing extra pages to docling" rather than
"scorer misses content". Acceptable for ship; documented for future
calibration refinement.

## Scope

* **Files changed**: 17 (12 source/test/config, 5 backlog)
* **Lines changed**: +695 / −83
* **Branch**: `feat/022-S-pa4-closure`
* **Tasks completed**: U1–U5 (all 5 from feature 020-F)
* **Test results**: 1008 passed, 3 skipped, 0 failed (full repo pytest; +19 from baseline 989)
* **Lint**: clean on all new/modified files; only pre-existing `scripts/load_test.py` E501 violations remain (untouched per surgical-change discipline)

## Personas dispatched

| Persona | Triggered by | Findings |
|---|---|---|
| Constitution Reviewer | always-on | 0 P0/P1 |
| Python Reviewer | always-on | 3 P3 |
| Correctness Reviewer | always-on | 1 P2, 2 P3 |
| Maintainability Reviewer | always-on | 2 P3 |
| Learnings Researcher | always-on | 0 |
| Architecture Strategist | new abstractions in `process/` | 0 |
| Scope Boundary Auditor | multi-domain diff (pdf_triage + fidelity_scorer + cli + script + pyproject) | 0 |
| Security Reviewer | new external deps (markitdown + 13 transitive); content-stream parsing on untrusted input | 0 P0/P1 |

Agent-Native Parity Reviewer and Concurrency Reviewer not triggered.

## Findings

### P2 — `_count_x_clusters` regex parses content-stream bytes loosely (Correctness)

**File**: `src/docline/process/fidelity_scorer.py` (`_count_x_clusters`)

**Finding**: The regex `((?:-?\d+\.?\d*\s+){5}-?\d+\.?\d*)\s+Tm|...` matches anywhere in the latin-1-decoded content stream, including potentially inside `Tj` / `TJ` text strings. A PDF whose actual text content includes a substring like `"1.0 2.0 1.0 2.0 1.0 2.0 Tm"` would have that match as if it were a Tm operator, inflating the X-cluster count.

**Failure mode analysis**: Over-counting → `excess` artificially grows → signal_layout_complexity fires more aggressively → MORE pages routed to docling. The orchestrator's downstream behavior is correct (docling handles the page); the cost is wall-clock, not fidelity. The opposite failure (under-counting → missing real tables) would be worse, but this implementation is biased toward over-counting on adversarial inputs.

**Recommendation**: Acceptable for ship — failure mode is safe. For a stricter implementation, switch to a proper PDF content-stream tokenizer (e.g., `pypdf._cmap` or `pypdf.generic`). Tracked as advisory; no follow-up stash created since the bounded failure makes this unsuitable for prioritization.

**Action**: `advisory` — documented; no immediate change.

### P3 — Redundant `re.UNICODE` flag

**File**: `src/docline/process/pdf_triage.py` (`_TOKEN_RE`)

**Finding**: `re.compile(r"\w+", re.UNICODE)` — `re.UNICODE` is the default in Python 3.7+. The flag is redundant.

**Recommendation**: Drop the flag. `re.compile(r"\w+")` is equivalent and shorter.

**Action**: `advisory` — trivial cleanup; can land in any future hygiene PR.

### P3 — `_count_x_clusters` magic numbers

**File**: `src/docline/process/fidelity_scorer.py`

**Finding**: `tolerance: float = 10.0` and `min(1.0, excess / 4.0)` are hard-coded. Future calibration may want to tune these.

**Recommendation**: When PA4 calibration matures, externalize these alongside `_SIGNAL_WEIGHTS` in the weights JSON file. Defer.

**Action**: `advisory`.

### P3 — `# type: ignore[attr-defined]` could be replaced with a `cast()` or protocol

**File**: `src/docline/process/pdf_triage.py` (`_heuristic_extract`)

**Finding**: `reader.pages[page_idx].extract_text()  # type: ignore[attr-defined]` — `reader` is typed as `object` for testability (mocked stand-ins). The `type: ignore` works but loses static checking.

**Recommendation**: Define a `_PdfReaderLike` Protocol and type `reader` against it. Marginal improvement; defer unless other call sites grow.

**Action**: `advisory`.

### P3 — Lazy markitdown import not documented at module level

**File**: `src/docline/process/pdf_triage.py` (`_heuristic_extract`)

**Finding**: `from markitdown import MarkItDown` is inside the function body. Reader unfamiliar with the codebase might miss that markitdown is a runtime dep imported on the markitdown path only.

**Recommendation**: Add a module-level comment block documenting the lazy import rationale (supports pypdf fallback when markitdown is uninstalled; defers slow markitdown init).

**Action**: `advisory`.

### P3 — `pdf_triage.py` is ~580 LOC; approaching module-split territory

**File**: `src/docline/process/pdf_triage.py`

**Finding**: The file now contains TriageResult + QASampling + 5 helpers + 3 public functions. Cohesive but starting to feel dense.

**Recommendation**: When the next set of triage-related changes lands (e.g., when stash `5CFE4481` per-page docling output protocol ships), split into `pdf_triage/orchestrator.py` + `pdf_triage/diff.py` + `pdf_triage/baseline.py`. Not blocking; defer.

**Action**: `advisory`.

### P3 — U5 (script) has no end-to-end smoke beyond `--help`

**File**: `tests/test_pa3_script_flags.py`

**Finding**: Only `--help` content tests. The 021-S compound learning "an opt-in CLI flag isn't wired until end-to-end test verifies real production code path" applies here too — `--baseline-engine markitdown` could be silently dropped between argparse and the orchestrator call and `--help`-only tests wouldn't catch it.

**Recommendation**: Add a 1-page-fixture smoke test that actually invokes the script via subprocess and inspects `pa3-summary.json` for the engine choice. Adds ~10s test time. Could be a follow-on stash if the operator wants the protection.

**Action**: `advisory` — small follow-on candidate; not creating a stash unless requested.

### P3 — `magika` (ONNX-based content-type detector) is now in the dep graph

**File**: `pyproject.toml` (transitive via `markitdown[pdf]`)

**Finding**: markitdown's [pdf] extras pull in `magika` which runs an ONNX model for content-type detection. Not a direct vulnerability — ONNX inference is sandboxed within ONNX runtime — but adds binary code into the import path.

**Recommendation**: Confirm markitdown doesn't invoke magika on the hot PDF path (markitdown's documented PDF backend is pdfminer.six, not magika). If magika is only invoked for non-PDF content type detection, it's effectively dead code in our pipeline. Track as a security review follow-up.

**Action**: `advisory` — post-merge audit candidate.

## Plan-hardening Action ledger carry-forward

| ID | Description | Status after build |
|---|---|---|
| **PA1** | Switch default `baseline_engine` from pypdf to markitdown | **applied** (commit `343047c`) |
| **PA2** | Add `markitdown[pdf]>=0.1.6,<0.2` as required dep | **applied** (commit `343047c`) |
| **PA3** | Add `signal_layout_complexity` to default signal set | **applied** (commit `343047c`) |
| **PA4** | Post-merge cosmos PA3 + PA4 re-run | **planned** — operator action; must run from plain shell per 2026-06-04 RCA; deferred to post-merge |

## Constitution principles coverage

| Principle | Plan coverage |
|---|---|
| I — Safety-first Python | ✓ All public APIs typed; narrow exception handling (with documented broad-except in `_count_x_clusters` fallback) |
| II — Test-first | ✓ 19 RED tests authored before implementation; visible in commit history |
| III — Workspace isolation | ✓ markitdown splice files under `output_dir/splices/` |
| IV — CLI containment | ✓ No writes outside cwd tree |
| V — Structured observability | ✓ New metadata fields (baseline_engine, baseline_engine_fallback, qa_similarity_histogram) |
| VI — Single responsibility | ✓ New required dep justified by plan-hardening + empirical bench; tight version pin per plan-review P3#6 |
| VII — Destructive approval | ✓ No destructive operations |
| VIII — Safety modes | ✓ Plan-harden completed; PA1–PA4 classified |
| IX — Git-friendly persistence | ✓ No new persistence format |
| X — Context efficiency | ✓ Frozen dataclasses; pure-function helpers |

## Runtime verification recommendation

Post-merge runtime verification required (operator action, plain shell):

1. **PA3 re-run** — `scripts/pa3_triage_cosmos.py` against cosmos with default `--baseline-engine markitdown`. Capture wall-clock + engine distribution + flag rate.
2. **PA4 re-run** — same script with `--sample-rate 0.01 --qa-random-seed 42`. Capture disagreement rate under new Jaccard metric + similarity histogram.
3. **Closure transition** — when PA3 wall-clock ≤ 75 min AND PA4 disagreement rate < 30%, update `docs/closure/021-S-triage-then-repair.md` to `status: production-ready`.

## Gate rationale

No P0 or P1 findings. The single P2 finding has a safe failure mode
(over-routing pages to docling rather than missing content) and is
documented for future refinement. Seven P3 advisories are
implementation-discipline notes that do not block ship.

PR-lifecycle may proceed.
