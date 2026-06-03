# Deliberation: docline CI workflow

| Field | Value |
|---|---|
| Date | 2026-06-03 |
| Stash sources | `9C40BF99` (high), `CE758832` (low) |
| Target shipment | `011-S` |
| Recommendation | Option C — Linux-only CI + documented Windows local-dev noise |

## Problem frame

docline is a Python 3.12 CLI + MCP server with a strict quality-gate model:

| Gate | Command |
|---|---|
| Lint | `ruff check .` |
| Typecheck | `pyright src/` |
| Test | `pytest` |
| Format | `ruff format --check .` |
| Build | `python -m build` |

No automated CI exists yet. Every push to `main` and every PR merge relies on the maintainer running these gates manually on a local workstation. PR #19 (`010-S`, 39 tasks) and PR #20 (post-merge closure) both merged without any automated CI verification. The constitution treats green CI as a precondition for operational closure (`docs/closure/`), so the project has been operating outside its own merge gate.

In parallel, local `pytest` runs on Windows emit 176+ `PermissionError` lines from `tmp_path` teardown (stash entry `CE758832`). The noise does not fail the suite, but it makes local gate execution hostile to read and obscures real failures. Investigating Windows `tmp_path` root cause is multi-hour speculative work with low yield against the immediate "no CI" risk.

## Options considered

### Option A — Minimal Linux-only CI

Single workflow on `ubuntu-latest`. Runs the four gates plus `python -m build` on `pull_request` and `push` to `main`. Ignores the Windows noise problem entirely.

| Pros | Cons |
|---|---|
| Smallest blast radius. | Does not validate Windows behavior in CI. |
| Fast — Linux Python toolchain is the most stable for ruff, pyright, pytest. | Windows-specific regressions only surface during manual local runs. |
| Sidesteps Windows `tmp_path` noise. | Windows noise stays undocumented, so newcomers will burn time on it. |
| Matches the project's actual deploy target (the CLI and MCP server are platform-agnostic Python). | |

### Option B — Multi-OS matrix

Matrix across `ubuntu-latest`, `windows-latest`, `macos-latest`. Catches cross-platform regressions earlier.

| Pros | Cons |
|---|---|
| Validates true cross-platform behavior. | Windows leg will be noisy because of `CE758832`. |
| Future-proof if docline grows OS-specific code paths. | 3× runner cost and 3× CI wall time. |
| | Greenfield project does not yet have OS-specific code worth matrixing against. |
| | Failures on the Windows leg from `tmp_path` teardown noise will produce false alarms that desensitize reviewers. |

### Option C — Linux-only CI plus documented Windows noise (recommended)

Option A plus a short `CONTRIBUTING.md` section that:

1. Lists the local quality gates.
2. Describes the known Windows `tmp_path` `PermissionError` teardown noise.
3. Suggests a grep filter for noisy lines during local runs.
4. Notes that CI runs on Linux, so PR validation is the authoritative gate.

This combines `9C40BF99` and `CE758832` into one coherent shipment without committing to the multi-OS matrix.

| Pros | Cons |
|---|---|
| Solves the immediate "no CI" risk on the same path as the noise problem. | Windows noise root cause remains unfixed (deferred to a future stash). |
| Documentation gives newcomers a recovery path without a code change. | Adds one small documentation surface (`CONTRIBUTING.md` did not exist). |
| Leaves the door open for Option B once Windows root cause is known. | |
| Aligns with the constitution's "single responsibility" and 2-hour task rules. | |

## Decision

**Adopt Option C.**

Rationale:

* The acute risk is "no automated gate enforcement," not "no Windows validation." Option A or C closes that gap.
* `CE758832` is a low-priority investigative item. Bundling its documentation surface with the CI workflow shipment retires the stash entry cheaply and gives newcomers a known-issue note rather than a silent foot-gun.
* Option B's matrix would multiply runner cost and surface noisy failures on Windows that would either need to be suppressed (defeating the purpose) or fixed (out of scope for a CI bootstrapping shipment).
* The path from Option C → Option B remains open: once Windows `tmp_path` root cause is understood, a follow-up shipment can add the Windows leg.

## Out of scope (follow-up stash entries to create during harvest)

| Stash text | Priority | Kind |
|---|---|---|
| Add release / publish workflow (PyPI, GitHub Releases) once a 1.0 release is ready. | low | feature |
| Add cross-OS test matrix (Windows + macOS) once Windows `tmp_path` PermissionError root cause is identified and fixed. | medium | task |
| Investigate root cause of Windows `tmp_path` `PermissionError` teardown noise (deeper than the local-dev workaround documented in 011-S). | low | task |

## Security and risk classification

| Surface | Risk | Notes |
|---|---|---|
| `.github/workflows/ci.yml` | moderate | Privileged operational surface; requires SHA-pinned actions, least-privilege permissions, no `pull_request_target`, no write access. |
| `CONTRIBUTING.md` | low | Documentation only. |

The workflow file design must comply with `.github/instructions/ci-security.instructions.md` and `.github/instructions/workflows.instructions.md`. Implementation hardening details are deferred to the plan and `plan-harden` invocation.

## Linked stash entries

| Stash ID | Disposition |
|---|---|
| `9C40BF99` | Harvest into 011-F as primary work item (CI workflow file). |
| `CE758832` | Harvest into 011-F as bundled documentation work item (CONTRIBUTING note). |
