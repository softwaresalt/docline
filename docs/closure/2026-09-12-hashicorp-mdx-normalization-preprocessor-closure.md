# Operational Closure — HashiCorp unified-docs MDX->MD normalization preprocessor (071-F / 062-S)

**Mode**: `post-merge`
**Date**: 2026-09-12
**Shipment**: `062-S` (`shipped`, archived) · **Feature**: `071-F` (`archived`,
`done`) · **Tasks**: `071.001-T`..`071.011-T` (all `archived`, `done`)
**PR**: [#192](https://github.com/softwaresalt/docline/pull/192) — merged
**Merge commit SHA**: `d4a534e241c5daae592da12883ae0a522f9e762c`
**Merged at**: `2026-09-12T07:55:48Z`

## Summary of Change

Standalone, disposable Python CLI preprocessor
(`scripts/hashicorp_mdx_normalize.py` + `scripts/_hashicorp_mdx/`) that
selectively copies the latest-version directory of each versioned HashiCorp
product (plus all unversioned products) from an external read-only corpus,
normalizing `.mdx -> .md` in-flight. Produces coverage and
unhandled-construct-inventory JSON as requirements evidence for a future
first-class `docline` MDX ingestion feature. Explicitly out of scope:
production `docline` MDX integration — no `docline` package runtime
surface is touched by this feature.

## CI Status and Review

* All required CI checks green at merge HEAD (`ci gate`, `pyright`,
  `pytest`, `ruff lint`, `ruff format check`, `sdist + wheel`, `detect code
  changes`).
* Local adversarial review readiness: `READY_WITH_FOLLOWUPS` at reviewed
  HEAD `8ec7020` (PR body "Local Review Readiness" section), P0=0, P1=0.
* P-018 Copilot-review gate: `SATISFIED` (confirmed twice pre-merge).
* `pipeline-topology (ambient)` CI check: pre-existing, non-blocking
  `BRANCH_MISMATCH` (branch predates shipment-slug naming convention;
  advisory-only per repo config, `PIPELINE_TOPOLOGY_GATE_REQUIRED` unset;
  deferred as stash `ADE96404`). Handled at merge time via an audited
  `--force` override of the agent-mode lifecycle gate — durable, committed
  audit record: `.autoharness/gates/062-S-lifecycle-force-audit.json` (the
  raw append-only `.autoharness/gates/pipeline-topology-force-audit.log`
  source line is gitignored and local-only; the JSON record above is the
  repo-committed, verifiable evidence).
* 18 P-021 deferred-scope-expansion findings from the review-fix cycles are
  already captured in `.backlogit/stash.jsonl` as part of PR #192's own
  commits: `1EDE36E7`, `1E7CCBF7`, `E3129374`, `13F7C7C3`, `ADE96404`,
  `387E5F82`, `C0E88586`, `7D71CBEA`, `48D6D05A`, `360FB708`, `8FA344D0`,
  `87BFB31B`, `7F80C39E`, `F49E7D65`, `F42911A1`, `F144B331`, `81815867`,
  `19675EF9`. No duplicate entries created by this closure.

## Runtime Verification

See
`docs/closure/2026-09-12-hashicorp-mdx-normalization-preprocessor-runtime-verification.md`.
**Verdict: PASS.** CLI surface (dry-run mode) verified both against a
repo-local synthetic fixture (this session) and, in the prior build
session, against the real external corpus read-only. Zero-write contract
confirmed in both cases.

## Invariants to Preserve

* Dry-run is, and must remain, a true zero-write operation.
* `--execute` never runs unattended by an agent; it is an explicit,
  documented, operator-only action.
* `--dest` claim exclusivity (`os.O_CREAT | os.O_EXCL` sentinel) prevents
  two concurrent `--execute` invocations from corrupting the same
  destination.
* The tool never writes outside the explicit `--dest` (and, for
  `--report`, a path validated to resolve inside `--dest`).

## Pre-Deploy Audits

Not applicable — this is a standalone, disposable, operator-invoked CLI
tool with no deployment path, no migration, no feature flag, and no
running-service rollout. "Release" for this artifact means the code is
merged and available on `main` for the operator to run manually per the
tool's own documented command.

## Deployment / Rollout Path

**Merge-only.** No deploy, canary, or phased rollout applies. The tool is
invoked manually by the operator when they choose to generate a fresh
requirements-evidence snapshot from the real external HashiCorp corpus.

## Post-Deploy Checks

* First operator-initiated `--execute` run (whenever the operator chooses
  to run it) should be checked for: exit code 0 and a `_normalize-report.json`
  written inside `--dest`. **`unresolved_constructs` is expected to be
  non-empty** — the honest final baseline (established in cycle 4, see
  runtime-verification report) is `{"EnterpriseAlert": 12, "Note": 1,
  "VideoEmbed": 8, "Warning": 2}` (stash `7F80C39E`) — so the operator's
  documented command **must include `--allow-unresolved-mdx`**; a run that
  aborts with `EXIT_UNRESOLVED_MDX_CONSTRUCTS` because that flag was
  omitted is an expected, documented failure mode, not a defect. A
  genuinely successful, zero-write/runtime-verified check therefore means:
  exit 0 with either the known 4-category baseline reported (flag was
  supplied) or a smaller/different bucket only if the corpus itself
  changed since cycle 4.

## Risky Action Record

* No `ProposedAction`/`ActionRisk` entries were required — this session
  never invoked `--execute` and never wrote outside
  `C:\Source\GitHub\docline`, consistent with the explicit operator
  containment instruction for this closure.

## Healthy Signals

* `--help` resolves and documents the exact operator command.
* Dry-run against any corpus returns exit 0 with a well-formed JSON plan
  and empty `containment_violations`. `unresolved_constructs` is empty
  only for the synthetic fixture; the real external corpus's honest
  baseline is the known 4-category `7F80C39E` bucket (see Post-Deploy
  Checks above) — its presence at that exact size is itself a healthy
  signal, not a regression.
* Full test suite for this feature
  (`tests/scripts/test_hashicorp_normalize.py`,
  `test_hashicorp_selection.py`, `test_hashicorp_dryrun_corpus.py`) passes.

## Failure Signals

* Any `containment_violations` entry in the JSON report (would indicate a
  planned write escaping `--dest`).
* Non-empty `unresolved_constructs` without an explicit
  `--allow-unresolved-mdx` override during a real `--execute` run.
* `EXIT_DEST_ALREADY_EXISTS` / `EXIT_REPORT_PATH_RESERVED` on an operator
  `--execute` attempt (expected, documented failure modes — not a defect
  unless unexpected).

## Monitoring Plan

None required beyond the tool's own report output — this is a disposable,
manually-invoked, non-deployed CLI utility. There is no running service,
dashboard, or alert surface to monitor.

## Rollback Trigger / Procedure

Not applicable — no deployment exists to roll back. If a future
`--execute` run produces unexpected output, the operator simply does not
use the generated snapshot; the tool never mutates the repository or any
already-normalized prior output in place (exclusive-claim + no-overlay
guarantees).

## Validation Window

N/A (no post-deploy observation window; the tool is validated per-invocation
by its own dry-run output and exit code, not by a time-boxed monitoring
period).

## Owner

Derek Williams (repository operator; the sole invoker of `--execute` for
this disposable tool).

## Compaction Status (P-020)

`done` — `compact-context` was invoked with `target: all` immediately after
this closure and after the final session memory was written. Candidates
(this shipment's own memory files and plan+review, all part of the
just-closed release unit): 5 memory files consolidated into
`docs/memory/compacted/2026-09-12-062-s-compacted.md` (verbose originals
moved to `docs/archive/memory/2026-09-11/` and `docs/archive/memory/2026-09-12/`);
1 plan + its appended review consolidated into
`docs/plans/2026-09-12-hashicorp-mdx-normalization-preprocessor-decided-plan.md`
(verbose originals moved to `docs/archive/plans/`). Closure records in
`docs/closure/` for this release unit were **not** compacted this run (0
days old, below the `threshold_days` candidacy gate) — this is the correct,
expected outcome per the skill's own threshold-gated candidate selection,
not a compaction failure.

## Releasability Evidence

Per `runtime_validation.releasability` (workspace-profile), applied to this
feature's own actual surface (CLI only — this feature has no MCP/API
surface):

* **healthy-signal** (required): CLI smoke test passes (`--help` +
  dry-run plan) — **satisfied**, see runtime-verification report.
* **owner** (required): named owner accountable for the released change —
  **satisfied** (Derek Williams).
* **follow-up** (optional): residual P2/P3 review findings captured as
  backlog items — **satisfied**; 18 P-021 deferred stash entries already
  captured (see CI Status and Review above), none newly required by this
  closure.
* The workspace-profile's `mcp-initialize-handshake` manual checkpoint does
  not apply to this feature (071-F exposes no MCP surface).

## Releasability Status

**READY.** All required evidence for this feature's actual (CLI-only)
runtime surface is satisfied. No conditions remain outstanding.

## Follow-ups

None newly identified during this closure beyond the 18 P-021 entries
already captured pre-merge (cross-checked against `.backlogit/stash.jsonl`,
no duplicates created).
