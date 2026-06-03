---
shipment: 011-S
title: "Closure record — docline CI workflow"
status: probe-pending
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

To be populated after probe PR runs. Five jobs are expected on `ubuntu-latest`:

| Job ID      | Command                          | Conclusion | Duration |
|-------------|----------------------------------|------------|----------|
| `lint`      | `uv run ruff check .`            | pending    | pending  |
| `format`    | `uv run ruff format --check .`   | pending    | pending  |
| `typecheck` | `uv run pyright src/`            | pending    | pending  |
| `test`      | `uv run pytest`                  | pending    | pending  |
| `build`     | `uv run python -m build`         | pending    | pending  |

Probe PR number: pending (will be the 011-S feature PR — first PR with CI in scope).

Probe run URL: pending.

## Rollback

Revert the workflow file commit (`0b48637`). CI stops triggering on subsequent
PRs and pushes. `CONTRIBUTING.md` is independent and may remain. There is no
data state and no external integration to recover.

## Stash follow-ups (not in 011-S scope)

* `7AA9FAA0` — release workflow (PyPI + GitHub Releases) once 1.0 ready (low)
* `ED74577A` — cross-OS CI matrix once Windows root cause is known (medium)
* `0AA8B223` — Windows `tmp_path` `PermissionError` root cause investigation (low)
