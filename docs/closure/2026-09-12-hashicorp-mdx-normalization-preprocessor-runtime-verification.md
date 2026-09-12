# Runtime Verification — HashiCorp unified-docs MDX->MD normalization preprocessor (071-F / 062-S)

**Date**: 2026-09-12
**Shipment**: `062-S` (shipped) · **Feature**: `071-F` (archived, `done`)
**PR**: [#192](https://github.com/softwaresalt/docline/pull/192) — merged
`d4a534e241c5daae592da12883ae0a522f9e762c`

## Scope

`071-F` is an explicitly **standalone, disposable** tooling deliverable: a
one-off Python CLI preprocessor (`scripts/hashicorp_mdx_normalize.py` +
`scripts/_hashicorp_mdx/`) that copies the latest-version directory of each
versioned HashiCorp product (plus all unversioned products) from an
external, read-only corpus, normalizing `.mdx -> .md` in-flight. It exists to
produce coverage/unhandled-construct inventory as **requirements evidence**
for a future first-class `docline` MDX feature. Per the feature's own scope
note: **"Out of scope: production docline MDX integration."** No `docline`
package surface (`src/docline/`) is part of this feature's runtime surface;
the changes visible to `src/docline/*` in the same PR belong to an earlier,
already-shipped feature that predates `062-S` on the same long-lived branch
(`feat/github-markdown-extension`) and are out of scope for this closure.

## Adapter Selection

* **Surface**: `cli` (command adapter) — the only runtime surface this
  feature exposes.
* Not applicable: `api`, `browser`, `background-job` — this feature has no
  MCP/API surface, no UI, and no scheduled job.

## Environment Prechecks

* Script entrypoint resolves and is executable via `python
  scripts/hashicorp_mdx_normalize.py` (no console-script entry point is
  registered for this disposable tool — direct invocation only, by design).
* Read-only synthetic fixture corpus available at
  `tests/scripts/fixtures/hashicorp/synthetic_corpus/` for repo-contained
  smoke verification.
* Real external corpus (`C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`)
  and destination (`C:\Source\Docs\tf-unified-dev-docs-normalized`) exist on
  the operator's machine but are **outside this repository** — per this
  closure session's explicit containment instruction ("Do not write outside
  `C:\Source\GitHub\docline`"), this session does not invoke the tool
  against those external paths. The prior build session (see
  `docs/memory/2026-09-11-ship-hashicorp-mdx-normalizer-cycle2.md` and
  `2026-09-12-ship-hashicorp-mdx-normalizer-cycle3.md`) already exercised the
  exact documented operator command read-only against the real external
  paths and confirmed **zero writes** (0 entries before/after in the real
  external `--dest`).

## Execution — Repo-Contained Smoke Check (this session)

* **Command**: `python scripts/hashicorp_mdx_normalize.py --source
  "tests/scripts/fixtures/hashicorp/synthetic_corpus" --dest
  "build/tmp-runtime-verify-dest" --report
  "build/tmp-runtime-verify-report.json"` (dry-run; no `--execute`).
* **Expected behavior**: exit 0, JSON plan on stdout, zero filesystem writes
  (dry-run is a zero-write contract by design), `--report` path ignored per
  the tool's own documented dry-run contract.
* **Observed behavior**: exit `0`. Plan reported 3 products
  (`hcp-docs` unversioned, `terraform` versioned → `v1.16.x` selected,
  `vault` versioned → `v2.x` selected), 1 unrecognized top-level dir
  (`mystery-product`) correctly excluded with a warning, `unresolved_constructs:
  {}`, `containment_violations: []`, `ambiguous_tokens: {}`. Neither
  `build/tmp-runtime-verify-dest` nor
  `build/tmp-runtime-verify-report.json` was created — confirmed via
  `Test-Path` immediately after the run (both `False`) — matching the
  documented zero-write dry-run contract exactly.

## Prior Session Evidence (carried forward, not re-executed this session)

* Exact documented operator command (`--execute --allow-unresolved-mdx`)
  run **read-only** (without `--execute`) against the real external
  `--source`/`--dest`/`--report` paths in the immediately-preceding build
  session: exit 0, `unresolved_constructs: {}`, 23 real products resolved.
  Real external `--dest` confirmed **0 entries before and 0 entries
  after** the session — never touched.
* Full local test suite for this feature
  (`tests/scripts/test_hashicorp_normalize.py`,
  `test_hashicorp_selection.py`, `test_hashicorp_dryrun_corpus.py`) passing
  as part of PR #192's own CI (`ci gate`, `pytest` checks — both green at
  merge HEAD `8ec7020`/`d4a534e`).

## Manual Checkpoints

None required. This tool has no OAuth, payment, email, SMS, or other
human-in-the-loop dependency. The single human-gated action — actually
writing the real external corpus — is explicitly deferred to the operator
(`--execute` is never run by an agent; the tool's own `--help` banner states
this) and is outside this closure's verification scope.

## Verdict

**PASS.** The CLI surface behaves as documented: dry-run is a true zero-write
operation, the plan output is well-formed and matches expectations for both
the synthetic fixture (this session) and the real external corpus (prior
session), and unresolved-construct detection reports empty for both corpora.

## Follow-up Recommendations

* None blocking. The tool is explicitly disposable/temporary
  (requirements-evidence only); no ongoing monitoring or rollback path
  applies since nothing is deployed or released to a running system.
* The operator's own `--execute` run against the real external corpus (per
  the tool's documented exact command) remains a manual, operator-owned
  action outside this closure's scope, as designed.
