---
shipment: 011-S
title: "Closure record — docline CI workflow"
status: verified
merge_sha: e07ffe6
merged_pr: 21
---

This document captures the runtime verification evidence for the docline CI
workflow introduced by shipment `011-S`. It is created as a stub before the
probe PR is opened and is updated with observed CI evidence after the workflow
runs end-to-end.

## Scope

* Workflow file: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — commit `0b48637`
* Contributor guide: [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — commit `a786f52`
* Plan: [docs/plans/2026-06-03-docline-ci-workflow-plan.md](../plans/2026-06-03-docline-ci-workflow-plan.md)
* Deliberation: [docs/decisions/2026-06-03-docline-ci-workflow-deliberation.md](../decisions/2026-06-03-docline-ci-workflow-deliberation.md) (adopted Option C — Linux-only CI + document Windows noise)
* Plan review: [docs/decisions/2026-06-03-docline-ci-workflow-plan-review.md](../decisions/2026-06-03-docline-ci-workflow-plan-review.md) (APPROVED — 0 P0/P1)
* Stash bundling: harvested `9C40BF99` and `CE758832`; both archived during stage

## Action SHA pinning audit

| Action                    | Resolved SHA                                 | Intended semver |
|---------------------------|----------------------------------------------|-----------------|
| `actions/checkout`        | `df4cb1c069e1874edd31b4311f1884172cec0e10`   | v6.0.3          |
| `astral-sh/setup-uv`      | `fac544c07dec837d0ccb6301d7b5580bf5edae39`   | v8.2.0          |
| `actions/setup-python`    | `a309ff8b426b58ec0e2a45f0f869d46889d02405`   | v6.2.0          |

Plan recommended v4/v6/v5 as "latest at time of plan"; Ship resolved current
latest at implementation time per the plan's "Ship resolves SHAs at
implementation time" instruction. Each `uses:` line carries the SHA and a
trailing semver comment per `.github/instructions/ci-security.instructions.md`.

## Security control audit

The following greps were run against the final workflow file:

| Control                                              | Expected | Observed |
|------------------------------------------------------|----------|----------|
| `secrets.*` references                               | 0        | 0        |
| `pull_request_target` triggers                       | 0        | 0        |
| `persist-credentials: false` on every checkout       | 5 (one per job) | 5 |
| `actions/checkout@` references                       | 5        | 5        |
| Workflow-level `permissions: contents: read`         | present  | present  |
| Workflow-level concurrency `cancel-in-progress: true`| present  | present  |

## Per-job CI evidence

Probe PR: [#21](https://github.com/softwaresalt/docline/pull/21) — first PR exercising the new workflow end-to-end.

Final green run (head SHA `026aef4`, merged as `e07ffe6`):
[actions/runs/26911471341](https://github.com/softwaresalt/docline/actions/runs/26911471341)

| Job ID      | Display name        | Conclusion | Duration |
|-------------|---------------------|------------|----------|
| `lint`      | `ruff lint`         | success    | 13 s     |
| `format`    | `ruff format check` | success    | 12 s     |
| `typecheck` | `pyright`           | success    | 17 s     |
| `test`      | `pytest`            | success    | 17 s     |
| `build`     | `sdist + wheel`     | success    | 19 s     |

All five gates passed on `ubuntu-latest` per the plan's Linux-only decision.

### Real-world findings caught during the probe

The probe surfaced two genuine dependency issues that no local manual gate had caught:

1. **`defusedxml` missing from `uv.lock`** — runtime import dependency was not
   recorded in the lockfile. Fixed by adding it to `pyproject.toml` and
   running `uv lock`.
2. **No dev dependency group declared** — `pyright`, `ruff`, and `pytest` were
   not pinned in a `[dependency-groups.dev]` table, so `uv sync --group dev`
   resolved nothing. Added the group and re-locked.

These fixes were applied across runs `26910902443`, `26911040660`, and
`26911313237` (all `failure`) before run `26911471341` came back fully green.
Value-add of the CI probe on day 1: immediate detection of dependency-state
drift that local execution masks because globally-installed tools shadow the
lockfile.

## Rollback

Revert the workflow file commit (`0b48637`). CI stops triggering on subsequent
PRs and pushes. `CONTRIBUTING.md` is independent and may remain. There is no
data state and no external integration to recover.

## Stash follow-ups (not in 011-S scope)

* `7AA9FAA0` — release workflow (PyPI + GitHub Releases) once 1.0 ready (low)
* `ED74577A` — cross-OS CI matrix once Windows root cause is known (medium)
* `0AA8B223` — Windows `tmp_path` `PermissionError` root cause investigation (low)
