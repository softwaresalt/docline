---
title: Code Review — 021-S triage-then-repair hybrid PDF pipeline
date: 2026-06-06
shipment: 021-S
feature: 019-F
branch: feat/021-S-triage-then-repair
status: PASS
gate_decision: PASS
plan: docs/plans/2026-06-06-triage-then-repair-plan.md
decision: docs/decisions/2026-06-06-triage-then-repair-pdf-pipeline.md
findings_summary: 0 P0, 0 P1, 2 P2, 5 P3
follow_up_stashes: 5CFE4481, 24920EFF, DE3E7346
---

# Code Review — 021-S triage-then-repair hybrid PDF pipeline

## Gate decision

**PASS** — proceed to fix-ci → pr-lifecycle.

| Severity | Count | Action |
|---|---|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 2 | Captured as backlog stash entries (`5CFE4481`, `24920EFF`); not merge-blocking |
| P3 | 5 | Advisory; tracked in this artifact |

No P0/P1 findings. All P2 findings have documented mitigations or are
limitations whose resolution depends on a future architectural decision
(MCP exposure of triage mode; per-page docling worker protocol).

## Scope

* **Files changed**: 23 (12 source, 7 test, 4 doc/backlog)
* **Lines changed**: +1726 / −253
* **Branch**: `feat/021-S-triage-then-repair`
* **Tasks completed**: U1–U7 (all 7 from feature 019-F)
* **Test results**: 989 passed, 3 skipped, 0 failed (full repo pytest)
* **Lint**: clean on all new/modified files; pre-existing
  `scripts/load_test.py` lint warnings left untouched per surgical-change discipline

## Personas dispatched

| Persona | Triggered by | Findings |
|---|---|---|
| Constitution Reviewer | always-on | 1 P3 |
| Python Reviewer | always-on | 2 P3 |
| Correctness Reviewer | always-on | 1 P2, 1 P3 |
| Maintainability Reviewer | always-on | 1 P3 |
| Learnings Researcher | always-on | 0 |
| Architecture Strategist | new abstractions in `process/` | 0 |
| Scope Boundary Auditor | multi-domain diff (7 source files across 3 modules) | 0 |
| Security Reviewer | subprocess execution + filesystem paths + untrusted document parsing | 1 P2 |

Agent-Native Parity Reviewer and Concurrency Reviewer not triggered (no
MCP/agent-facing surface changes; no concurrent/async code added in this
shipment).

## Findings

### P2 — Per-page docling output limitation in splice-back (Correctness)

**File**: `src/docline/process/pdf_triage.py` (`process_pdf_triaged`,
splice-back loop)

**Finding**: When a flagged range covers N pages, the `docling_worker`
returns a single concatenated markdown blob (one subprocess invocation
per range). The orchestrator places that blob on the FIRST page of the
range and leaves subsequent pages as empty strings while marking
`engine_per_page` as `"docling"` for the whole range. Downstream
consumers that expect non-empty per-page content matching the
attribution may be surprised by the empty strings on continuation pages.

**Risk**: Moderate (impacts downstream RAG/graph consumers that use
per-page granularity).

**Recommendation**: Stash captured for follow-on design. Three options
documented (per-page subprocess; JSON envelope from worker; heuristic
re-split). Defer; document the known limitation in operational closure.

**Action**: `manual` — design decision required. **Stash**: `5CFE4481`.

### P2 — Weights-path validation when exposed via MCP (Security)

**File**: `src/docline/process/fidelity_scorer.py`
(`load_weights(weights_path)`)

**Finding**: `load_weights` accepts an arbitrary `Path` and reads
JSON from it without workspace containment validation. Today the only
caller is the CLI where the operator-supplied path is trusted. If
`ProcessRequest.pdf_mode='triage'` is later exposed via the MCP server
and a remote caller can supply a `weights_path`, this becomes a path
traversal vector.

**Risk**: Low today (CLI-only), would escalate to Medium when MCP
exposes the triage path with a caller-controlled weights argument.

**Recommendation**: Reuse `docline.paths.safe_workspace_path` /
`validate_workspace_relative_path` for the weights file when an
untrusted caller is the source. Not blocking — triage mode is
intentionally opt-in via CLI in this shipment.

**Action**: `manual` — apply when MCP exposes triage. **Stash**: `24920EFF`.

### P3 — Broad exception handlers narrowly scoped but could be tighter

**Files**: `src/docline/process/fidelity_scorer.py:_page_image_count`,
`signal_form_fields`; `src/docline/process/pdf_triage.py` per-page
extraction loops.

**Finding**: Several `except` clauses use specific exception tuples
(e.g. `except (AttributeError, KeyError, TypeError)`) and are narrowly
scoped to per-page extraction or per-call probing — they will not mask
genuine bugs. Could still be narrowed further once we observe which
real exceptions actually arise from pypdf in production.

**Action**: `advisory` — observe production behavior, tighten if needed.

### P3 — `**kwargs: object` in `dispatch_pdf_mode` loses static typing

**File**: `src/docline/process/pdf_triage.py:dispatch_pdf_mode`

**Finding**: The router uses `**kwargs: object` and `# type: ignore[arg-type]`
to forward arguments. Pragmatic for a thin router but loses pyright's
ability to catch arg-type mismatches at the dispatch boundary.

**Recommendation**: Acceptable for V1. If `dispatch_pdf_mode` grows or
gains additional modes, consider replacing `**kwargs` with a typed
`PipelineDispatchArgs` dataclass per mode.

**Action**: `advisory`.

### P3 — Weight-key validation in `load_weights` does not enforce known signal names

**File**: `src/docline/process/fidelity_scorer.py:load_weights`

**Finding**: A weights JSON file with unknown keys (e.g.
`{"foo_bar": 1.5}`) is accepted silently — the value is added to the
returned dict but is never consumed by the combiner (which iterates
`_SIGNAL_NAMES`). Not incorrect, but a typo in a weights file would
go undetected.

**Recommendation**: Warn (via `_log`) when a weights file contains
keys not in `_SIGNAL_NAMES`. Defer to calibration follow-on when
weights are produced empirically.

**Action**: `advisory`.

### P3 — Duplicate heuristic-extraction logic in orchestrator and report-only

**File**: `src/docline/process/pdf_triage.py`

**Finding**: Both `process_pdf_triaged` and `triage_report_only`
duplicate the per-page heuristic extraction loop (~12 lines each).
Extracting a private helper would reduce maintenance cost.

**Action**: `manual` — small refactor opportunity. **Stash**: `DE3E7346`.

### P3 — Random seed using `time.time()` is biased

**File**: `src/docline/process/pdf_triage.py:process_pdf_triaged`
(QA sampling)

**Finding**: When `qa_sampling.random_seed is None`, the orchestrator
uses `int(time.time() * 1000) & 0xFFFFFFFF` to seed. Adequate for
non-cryptographic sampling but `secrets.randbits(32)` is unbiased and
not noticeably slower.

**Action**: `advisory`. Replace if the QA tripwire is ever used in a
context where adversarial seed prediction matters.

### P3 — Manifest field name uses `pdf_mode` underscore vs CLI `--pdf-mode` hyphen

**File**: `src/docline/app_models.py`

**Finding**: The Pydantic field `pdf_mode` serializes as
`"pdf_mode"` in the JSON schema. The CLI flag is `--pdf-mode`. The test
`test_manifest_includes_pdf_mode_flag` matches either via the
description text (which references `--pdf-mode` explicitly). Works but
slightly indirect.

**Recommendation**: Acceptable. Field name mirrors Python convention;
hyphen-form is documented in the schema description.

**Action**: `advisory`.

## Plan-review P2 propagation

The plan-review skill flagged two P2 items in the implementation plan
that should land during this shipment. Verifying:

| Plan-review P2 | Status | Evidence |
|---|---|---|
| `process_pdf_triaged` should not take >10 kwargs — U6 should be a sibling, U7 a `QASampling` dataclass | ✓ Applied | `triage_report_only` is a sibling function (U6); `QASampling` is a frozen dataclass kwarg (U7) |
| `TriageResult` should be `@dataclass(frozen=True)` | ✓ Applied | `TriageResult` is frozen; `test_triage_result_is_frozen` verifies via FrozenInstanceError |

## Strict-safety carry-forward

Plan hardening identified 4 `ProposedAction` entries (PA1–PA4). Status
after build-feature loop:

| Action | Risk | Status after build |
|---|---|---|
| **PA1** — Land `--pdf-mode triage` wired to production batch path | moderate | **applied** (commit `15e3036`) |
| **PA2** — Add `engine` field to part frontmatter `docline:` namespace | moderate | **applied** (commit `14e7856`) |
| **PA3** — First end-to-end triage run on `azure-cosmos-db.pdf` | low | **planned** — must be run from plain shell per 2026-06-04 RCA, not from inside an AI agent process. Deferred to runtime-verification step after PR merge. |
| **PA4** — Lock-in default `_SIGNAL_WEIGHTS` based on calibration | low | **planned** — depends on PA3 output. Captured as a follow-on stash; this shipment ships the mechanism, not the calibrated weights. |

PA3 and PA4 remain `planned` because they require runtime verification
on a real corpus. Both are documented in operational-closure and the
session memory checkpoint. Neither blocks PR merge — they block the
operator's recommendation to use triage mode in production.

## Runtime verification recommendation

The shipment changes the production batch path (additive — opt-in via
`--pdf-mode triage`). Default mode behavior is bit-identical to today
and is covered by regression tests (`test_pdf_mode_auto_dispatches...`
asserts the `auto` path produces a `BatchResult`).

Triage-mode runtime verification (PA3) requires:

* **Manual** mode against `.elt/data/cosmosdb/azure-cosmos-db.pdf`
* Plain PowerShell session — NOT inside an AI agent tool call (per RCA)
* Wall-clock target: ≤ 2.4 h (Acceptance Criterion 6 in the plan)
* Per-page engine distribution recorded in manifest summary
* Compare output fidelity against a curated subset of the existing
  all-docling cosmos run

This is deferred to the operational-closure step.

## Operational closure carry-forward

Items to surface in `docs/closure/021-S-*.md` after merge:

1. PR merge SHA and PA1/PA2 result transitions to `applied`
2. PA3 runtime verification result (cosmos wall-clock, engine
   distribution, fidelity sample)
3. Compound learning entry candidate: **"triage-then-repair pattern
   for selective ML invocation in document pipelines"** — pattern is
   reusable for any pipeline where most inputs are cheap and a few need
   expensive specialized processing
4. Calibration stash registration (PA4) for follow-on weights tuning
5. The three review-follow-up stashes (`5CFE4481`, `24920EFF`,
   `DE3E7346`)

## Constitutional principles coverage

| Principle | Compliance |
|---|---|
| I — Safety-first Python | ✓ All public APIs typed; custom typed exceptions; `noqa: BLE001` with rationale where used |
| II — Test-first | ✓ All 7 tasks had RED tests verified before implementation; red→green pairs visible in commit history |
| III — Workspace isolation | ✓ All file writes go through caller-supplied `output_dir`; no out-of-workspace IO |
| IV — CLI containment | ✓ Splice cache stays under `output_dir/splices`; verified by orchestrator implementation |
| V — Structured observability | ✓ Per-page engine attribution in TriageResult.metadata + output contract; TSV emission for report-only |
| VI — Single responsibility | ✓ No new dependencies (only stdlib additions: csv, random, time, unicodedata, re) |
| VII — Destructive approval | ✓ No destructive operations introduced |
| VIII — Safety modes | ✓ Plan hardening produced ProposedAction tracking; PA1–PA4 status visible in this review |
| IX — Git-friendly persistence | ✓ Output is markdown + YAML; weights file is JSON |
| X — Context efficiency | ✓ Frozen dataclasses; pure-function scorer signals; injectable scorer/runner for test efficiency |
| XI — Merge commit history | n/a — to be enforced at merge time by Ship |

## Gate rationale

No P0/P1 findings. Both P2 findings have documented mitigations:

* P2 #1 (per-page output) is a known design limitation with three
  forward paths — captured as a stash for the next design conversation.
* P2 #2 (weights path validation) is a forward-looking security concern
  that does not affect the current CLI-only triage surface — captured
  as a stash to apply when MCP exposes the path.

Five P3 advisories are documented for awareness; none require action
for merge.

**Gate**: **PASS**. Proceed to fix-ci → pr-lifecycle.
