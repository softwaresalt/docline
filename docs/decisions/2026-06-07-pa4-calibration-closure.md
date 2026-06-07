---
title: Decision — Close PA4 calibration via markitdown baseline + Jaccard diff + layout-complexity signal
date: 2026-06-07
kind: deliberation
status: decided
stashes: 3777859D, 60E6157D, 1380BD85
related_closure: docs/closure/021-S-triage-then-repair.md
related_compound: docs/compound/2026-06-06-triage-then-repair-pattern.md
poc_evidence: logs/markitdown-bench/, .elt/output/cosmos-tripwire/pa3-summary.json
---

## TL;DR

021-S shipped triage-then-repair with ~11.4× speedup on cosmos but
left PA4 (lock-in calibrated `_SIGNAL_WEIGHTS`) blocked by three
distinct, complementary gaps surfaced during PA4 verification:

1. **Baseline quality** — pypdf returns flat text where markitdown
   produces real markdown (numbered lists, code fences). This costs
   nothing in fidelity terms but loses richness downstream consumers
   can use.
2. **Diff metric** — `_normalize_markdown` in `pdf_triage.py` is too
   coarse; the 97 % QA-disagreement rate observed in PA4 is mostly
   measurement noise (4 of 5 manually inspected disagreements were
   formatting / reading-order differences). Without a meaningful
   diff metric, PA4 calibration is impossible.
3. **Scorer blind spot** — none of the 7 existing fidelity signals
   can detect tables that pypdf flattens into single-column words
   that look like ordinary prose. Page 470 of cosmos (Azure RBAC
   permissions table) is the canonical example: heuristic returns
   2,109 chars of broken text; docling reconstructs a proper
   markdown table at 4,519 chars.

These three are interdependent and most valuable shipped together.
Decision: bundle all three into a single shipment that closes PA4
cleanly with a coherent re-verification cycle (re-run PA3 + PA4 on
cosmos after merge).

## Problem frame

After 021-S merged with `status: verified`, two follow-on conditions
were left for transition to `status: production-ready`:

* **PA3** — empirical runtime verification on cosmos PDF
  (operator-side; ran 2026-06-06 with 50 min wall-clock, 3.0 % flag
  rate, 11.4× speedup vs all-docling baseline; ✓ applied)
* **PA4** — lock calibrated `_SIGNAL_WEIGHTS` after empirical
  validation (operator-side; ran 2026-06-07 QA tripwire; **blocked**)

PA4 surfaced two distinct findings:

* **97 % disagreement rate is misleading** — 4 of 5 manually inspected
  splice outputs revealed the disagreement was a formatting artifact
  (code fences, reading-order, whitespace) rather than a real
  fidelity gap
* **One real false negative** — page 470 (RBAC permissions table)
  is mangled by heuristic into broken vertical text; none of the
  existing scorer signals can detect it because they all score the
  heuristic OUTPUT, not the source PDF layout structure

A parallel inquiry into deterministic alternatives (operator question:
"why not markitdown?") produced a third finding:

* **markitdown is a real baseline upgrade for prose** — produces
  proper markdown lists, code fences, and structural formatting on
  the typical page; but its pdfminer.six backend has the same table
  limitation as pypdf (verified empirically on page 470)

## Options considered

### Option A — Ship just `60E6157D` (diff metric improvement) alone

* **Pro**: Smallest change; unblocks PA4 calibration without other
  risk.
* **Pro**: Could re-run PA4 immediately after merge to get a real
  disagreement rate.
* **Con**: Even with a meaningful disagreement metric, the page-470
  false-negative class is not addressable until `1380BD85` lands.
  Calibration of current `_SIGNAL_WEIGHTS` cannot improve scorer
  coverage of mangled tables.
* **Verdict**: Reject — necessary but not sufficient.

### Option B — Ship `60E6157D` + `1380BD85` (diff metric + new signal)

* **Pro**: Closes both PA4 blockers identified by the QA tripwire
  evidence.
* **Pro**: A re-run of PA3 + PA4 after merge would meaningfully
  verify both fixes.
* **Con**: Leaves on the table the markitdown baseline-quality win
  that's already empirically validated (logs/markitdown-bench/).
  Downstream RAG/graph consumers would benefit immediately from
  richer markdown without waiting for a follow-on shipment.
* **Verdict**: Reject — leaves obvious value on the table.

### Option C — Ship all three (chosen)

Bundle `3777859D` + `60E6157D` + `1380BD85` into one shipment that
addresses baseline quality, diff metric correctness, and scorer
coverage in one coherent unit.

* **Pro**: Single PA3 + PA4 re-verification cycle validates the
  whole system rather than three independent rounds.
* **Pro**: Empirical evidence for all three already exists (PA4
  cosmos run, markitdown bench, page 470 splice).
* **Pro**: All three touch related files (`pdf_triage.py`,
  `fidelity_scorer.py`) so the integration risk is bounded.
* **Pro**: Stage harvest + Ship build can run in parallel where the
  3 source modules don't conflict.
* **Con**: Adds markitdown as a runtime dependency (and pdfminer-six,
  pdfplumber, magika, onnxruntime, cryptography transitively). CI
  install times increase.
* **Con**: Larger blast radius than three small shipments — if any
  one of the three regresses default-mode behavior, all three need
  to be debugged together.
* **Verdict**: **Selected.** Coherent scope; empirical evidence
  ready; single verification cycle.

### Option D — Defer entirely (spike first)

* **Pro**: More empirical data before committing implementation
  effort.
* **Con**: Each stash already has concrete evidence and a clear
  implementation path. Further spike work would not change the
  decision.
* **Verdict**: Reject. Empirical evidence already collected.

## Chosen direction

**Option C** — single shipment containing:

1. **markitdown baseline swap** (stash `3777859D`): replace
   `reader.pages[i].extract_text()` in `process_pdf_triaged` with a
   markitdown call. Parameterize the heuristic engine choice so the
   existing pypdf path remains available as a fallback.
2. **Jaccard-similarity diff metric** (stash `60E6157D`): replace
   `_normalize_markdown` with a tokenized-Jaccard-similarity
   comparator with a configurable threshold (default ~0.7). Count as
   disagreement only when similarity falls below the threshold.
3. **Layout-complexity signal** (stash `1380BD85`): add a new
   `signal_layout_complexity` to `fidelity_scorer` that inspects
   the source `pypdf.PageObject` for text-run X-coordinate
   clustering, column count, and grid-like positioning. Fires when
   heuristic-extracted text is suspiciously sparse relative to
   source layout complexity.

Plus the cross-cutting work:

4. **Add markitdown to `pyproject.toml`** as a required dependency.
5. **Update output contract emission** — both `process_pdf_triaged`
   and `triage_report_only` need to honor the new baseline.
6. **Re-run PA3 + PA4 verification** on cosmos after merge; update
   `docs/closure/021-S-triage-then-repair.md` to transition to
   `status: production-ready` after evidence confirms calibration
   converges.

## Constitution check

| Principle | Compliance |
|---|---|
| I — Safety-first Python | All new code typed; custom typed exceptions where applicable; no bare except |
| II — Test-first | RED tests for every new module / signal / metric before implementation |
| III — Workspace isolation | All file IO under caller-supplied output_dir |
| IV — CLI containment | No new CLI flags this shipment; existing `--pdf-mode triage` keeps current behavior with richer baseline |
| V — Structured observability | TriageResult.metadata extends to include similarity score distributions for the new diff metric |
| VI — Single responsibility | markitdown is a NEW required dependency — flagged in plan hardening |
| X — Context efficiency | Reuse existing frozen dataclasses; no new abstractions beyond the new signal function |

## Open questions

1. **Heuristic baseline engine selector** — should the new markitdown
   path replace pypdf entirely, or coexist as a choice (e.g.
   `--baseline-engine {pypdf,markitdown}`)? Resolution: coexist as a
   choice with markitdown as the default; pypdf available as a
   compatibility fallback. Removes regression risk.
2. **Jaccard threshold default** — POC suggests 0.7; calibrate
   empirically during PA4 re-run on cosmos.
3. **Layout-complexity signal weight** — defaults TBD; calibrate
   empirically during PA4 re-run.
4. **Should the `auto`-mode pipeline also adopt markitdown?** — out
   of scope this shipment; tracked as a follow-on after triage-mode
   adoption is validated.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| markitdown adds 6+ transitive deps; CI install times grow | Pin major version; gate as required dep behind plan-harden review |
| Default-mode (`--pdf-mode auto`) bit-identical-output invariant could break if `build_output_document_parts` PDF branch changes | Triage mode keeps a separate code path; auto-mode path not modified this shipment |
| Layout-complexity signal could produce false positives on legitimately structured prose pages | Tune via calibration; cap signal weight in default `_SIGNAL_WEIGHTS` |
| markitdown's ~250 ms per-page is acceptable for whole-doc but adds ~14 min on cosmos triage baseline | Acceptable trade for richer output; document in closure |
| PA4 re-run could surface yet another finding (rinse and repeat) | Accept; the calibration gate IS the validation step. If new findings emerge, ship another iteration. |

## Acceptance criteria

Satisfied when:

1. Triage mode produces markdown that includes proper numbered
   lists, code fences, and headings on pages where the underlying
   PDF has these structures (verified by test fixture).
2. `qa_disagreements` in `TriageResult.metadata` reflects only
   semantically meaningful disagreements; trivial formatting noise
   does not count as a disagreement.
3. Page 470 of cosmos (or an equivalent fixture) flags under the
   new `signal_layout_complexity` and routes through docling.
4. Default-mode (`--pdf-mode auto`) output is bit-identical to
   pre-merge behavior (verified by existing regression tests).
5. After merge, operator re-runs PA3 + PA4 on cosmos. Disagreement
   rate < 5 % under the new metric; flag rate stays in the 5-25 %
   sanity band (or empirically validated to be lower with the new
   scorer); operator transitions `021-S` closure status to
   `production-ready`.
6. All existing `pytest` (989 tests) still pass; ruff lint + format
   clean; pyright clean.
