---
title: Plan-review — H1 header synthesis spike
date: 2026-06-04
plan: docs/plans/2026-06-04-h1-header-synthesis-spike.md
verdict: APPROVED
status: ready-for-harvest
---

# Plan-review — 017-S H1 header synthesis spike

## Reviewer personas (inline)

### Architecture strategist

* The plan keeps the spike out of `src/` — correct. Production wiring
  belongs to a follow-on shipment after the recommendation is approved.
* The decision artifact + plan stub split is the right two-layer output:
  the artifact records what was learned; the stub records what to build
  next. Future Stage cycles can hydrate from either.
* Module placement guidance in the stub (`src/docline/process/header_synthesis.py`)
  is plausible but should be revisited in the follow-on plan when the
  recommended approach is known. Acknowledged as such in the plan.

**Verdict: PASS**

### Correctness reviewer

* The corpus analysis criteria are explicit: 4 measurable counts per
  source. No fuzzy "lots of parts look bad" language.
* The follow-on rescue-rate metric is well-defined: "what fraction of
  headerless parts does tier T fix when applied in isolation".
* Risk register acknowledges sample-size limitation. Good.

**Verdict: PASS**

### Scope boundary auditor

* Non-goals section is explicit and tight: no implementation, no SLM, no
  `--allow-heading-disorder` removal, no `assemble.py` change.
* Task count is 4. Budget is ~2.5 h with 4 h hard ceiling. Within
  2-hour-rule per task.
* The plan does NOT try to slip in a small "deterministic prototype" —
  correctly deferred to the follow-on shipment.

**Verdict: PASS**

### Maintainability reviewer

* The throwaway script under `scripts/` will get formatted and linted by
  ruff. That's enough hygiene for a spike artifact — no test gating
  required.
* Decision artifact convention follows the spike skill's documented format.
* Closure artifact convention matches the G3 series frontmatter
  (`status: verified`, `merged_pr: N`, 7-char `merge_sha`) — note this
  was the convention Copilot caught on PR #33; the follow-on author of
  the closure file MUST use this convention from the start.

**Verdict: PASS** (with note: closure author must use G3 frontmatter
convention)

### Constitution reviewer

* No NON-NEGOTIABLE principle is violated.
* P-001 (one active shipment) is satisfied — backlog has 0 active.
* P-005 (destructive approval) does not apply — no destructive ops.
* P-009 (merge commit only) is reaffirmed in the plan's Constitution Check.
* P-011 (branch creation gate) will be enforced by Ship when it claims
  the shipment.

**Verdict: PASS**

## Findings

None blocking. One advisory:

* **A1 (advisory)**: When the spike runs the corpus analysis script, it
  will load all 965 `.md` files. The script must use
  `with` context-managed file opens to avoid the file-handle hygiene
  issue from 014-S-era code. Trivial to satisfy.

## Final verdict

**APPROVED — proceed to harvest.**

The plan is small, well-scoped, time-boxed, and aligned with the spike
skill's pattern. The follow-on shipment plan stub is a clean handoff for
the next Stage cycle.
