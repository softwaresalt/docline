---
title: "Plan - docline CI workflow"
stash_ids: ["9C40BF99", "CE758832"]
source: "docs/decisions/2026-06-03-docline-ci-workflow-deliberation.md"
status: hardened
requires_plan_hardening: yes
---

# Plan: docline CI workflow

## Objective

Establish automated quality-gate enforcement on every PR and `main` push by adding a single GitHub Actions workflow that runs the docline lint, format, typecheck, test, and build gates on a Linux runner. Bundle a short `CONTRIBUTING.md` section that documents the known Windows local-dev `tmp_path` `PermissionError` noise so newcomers have a recovery path.

## Source

* Stash entries: `9C40BF99` (high — CI workflow), `CE758832` (low — Windows pytest noise documentation)
* Deliberation: `docs/decisions/2026-06-03-docline-ci-workflow-deliberation.md`
* Operational closure recommendation: `docs/closure/010-S-docline-graphtor-ingestion-contract-alignment.md`

## Constraints carried from deliberation

* Linux-only single matrix entry (`ubuntu-latest`). No Windows or macOS legs in this shipment.
* No deploy, no PyPI publish, no Codecov, no Docker, no signing, no `pull_request_target`.
* Scope is local-gate / CI-gate parity, nothing more.
* Compliant with `.github/instructions/ci-security.instructions.md` and `.github/instructions/workflows.instructions.md`.

## Implementation units

### F1 — CI workflow file

**Scope**: `.github/workflows/ci.yml`

**Triggers**:

* `pull_request` — all branches targeting `main`.
* `push` — `main` only.

**Workflow-level configuration**:

* `name: CI`
* `permissions: contents: read` (workflow-level, least privilege).
* `concurrency:` group `ci-${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true` to cancel superseded runs.
* No `pull_request_target`. No secrets reference.

**Jobs** (single `ubuntu-latest` runner, jobs run in sequence via `needs:` where ordering matters, otherwise parallel):

| Job ID | Purpose | Command |
|---|---|---|
| `lint` | ruff lint gate | `uv run ruff check .` |
| `format` | ruff format gate | `uv run ruff format --check .` |
| `typecheck` | pyright gate | `uv run pyright src/` |
| `test` | pytest gate | `uv run pytest` |
| `build` | sdist + wheel | `uv run python -m build` |

All jobs share the following step sequence:

1. `actions/checkout@<sha>` with `persist-credentials: false`.
2. `astral-sh/setup-uv@<sha>` with `enable-cache: true` and `cache-dependency-glob: "uv.lock"`.
3. `actions/setup-python@<sha>` pinned to Python 3.12 (uv reads `requires-python` but explicit pinning prevents drift).
4. `uv sync --locked --all-extras --dev` to install the locked dependency set.
5. Gate-specific command from the table above.

**Action SHA pinning** (per `ci-security.instructions.md` — full SHAs to be resolved by Ship at implementation time; SHA comments indicate the intended semver):

| Action | Intended version |
|---|---|
| `actions/checkout` | v4 (latest) |
| `actions/setup-python` | v5 (latest) |
| `astral-sh/setup-uv` | v6 (latest) |

Ship resolves SHAs at implementation time using `gh api repos/{owner}/{repo}/commits/{ref}` or by inspecting the latest release tag, then writes the SHA into `uses:` and the semver into the trailing comment.

**Acceptance criteria for F1**:

* `.github/workflows/ci.yml` exists, parses as valid YAML, and `actionlint` reports zero errors.
* All five jobs declared and reference the gate commands above unmodified.
* All third-party `uses:` references pinned to full commit SHA with trailing semver comment.
* Workflow-level `permissions: contents: read`, no job grants write.
* `persist-credentials: false` on every `actions/checkout` invocation.
* `concurrency` group declared at workflow level with `cancel-in-progress: true`.
* No `pull_request_target` trigger anywhere.
* No secret references (`secrets.*`) anywhere.
* Triggers limited to `pull_request` and `push` on `main`.
* All jobs run on `ubuntu-latest`.

### F2 — CONTRIBUTING.md with Windows local-dev note

**Scope**: `CONTRIBUTING.md` (new file at repo root)

**Required sections**:

1. **Local quality gates** — table listing the five gates and their `uv run` commands, mirroring the CI workflow.
2. **Running gates with uv** — one-paragraph note pointing at `uv sync --all-extras --dev` and `uv run` so contributors do not need a globally installed ruff or pyright.
3. **Known Windows local-dev noise** — describes the `tmp_path` `PermissionError` lines emitted during `pytest` teardown on Windows, notes they do not affect pass/fail, gives a `Select-String -NotMatch 'PermissionError'` (PowerShell) or `grep -v 'PermissionError'` (bash) filter for cleaner local output, and points at CI as the authoritative gate.
4. **Pre-PR checklist** — short bulleted list reminding contributors to run all five gates locally before opening a PR.

**Acceptance criteria for F2**:

* `CONTRIBUTING.md` exists at repo root.
* Contains all four required sections in the order above.
* Filter examples are accurate for both PowerShell and bash.
* Cross-references `.github/workflows/ci.yml` for the authoritative gate definitions.
* Passes the workspace markdownlint configuration (`scripts/pre-commit-markdownlint.ps1` / `.sh`).

### F3 — Probe and closure

**Scope**: Verification that the workflow actually runs end-to-end on a real PR before the shipment is closed.

**Steps**:

1. Open the implementation PR (containing F1 + F2) against `main`.
2. Confirm all five CI jobs run, complete, and report `success` on the implementation PR.
3. If any gate fails on the probe PR, fix locally, push, and re-poll per `.github/instructions/github-pr-automation.instructions.md` §2.3.
4. Run `actionlint` locally before push (Ship's responsibility — see Ship's `fix-ci` skill for installation).
5. Capture runtime verification evidence in `docs/closure/011-S-docline-ci-workflow.md` with: workflow file path, probe PR number, job names, conclusion for each, and the SHA pinning audit (each `uses:` line with resolved SHA).

**Acceptance criteria for F3**:

* Probe PR has at least one successful CI run where all five jobs report `conclusion: success`.
* `actionlint` reports zero issues.
* Closure document at `docs/closure/011-S-docline-ci-workflow.md` records job results and SHA pinning audit.

## Dependencies

* None external. uv is already used (see `uv.lock` at repo root).
* No prior shipment must close before this one starts.

## Risk assessment

| Dimension | Assessment |
|---|---|
| Blast radius | Moderate. Touches `.github/workflows/` (privileged operational surface) and adds a root `CONTRIBUTING.md`. No source code or schema changes. |
| Rollback | Trivial. Revert the workflow file commit and the `CONTRIBUTING.md` commit. CI returns to "no automated gate" state. |
| Failure modes | (a) Action SHA pinning errors — caught by `actionlint`. (b) `uv sync` slow on cold cache — mitigated by `enable-cache: true`. (c) Probe PR exposes pre-existing gate failure — Ship triages and either fixes inline or creates a follow-up backlog item. |

## Plan hardening (per `plan-harden`)

The CI workflow file is an `ActionRisk: moderate` surface because `.github/workflows/` is privileged and CI workflows are common supply-chain attack targets. Hardening focuses on:

| Control | Requirement | Verified by |
|---|---|---|
| Action pinning | Full commit SHA on every third-party `uses:`. | Manual audit in F3 closure. |
| Permissions | `contents: read` only at workflow level. No job grants write. | YAML inspection + `actionlint`. |
| Triggers | `pull_request` and `push` to `main` only. No `pull_request_target`. | YAML inspection. |
| Credentials | `persist-credentials: false` on every `actions/checkout`. | YAML inspection. |
| Secrets | Zero `secrets.*` references. | grep audit in F3 closure. |
| Concurrency | Workflow-level concurrency group with `cancel-in-progress: true`. | YAML inspection. |
| Runner | `ubuntu-latest` (default hosted tier). No self-hosted. | YAML inspection. |

## Constitution check

| Principle | Status |
|---|---|
| I — Safety-first Python | N/A (no Python code changes). |
| II — Test-first | Acceptance criteria are the test. F3 probe PR is the live verification. |
| III — Workspace isolation | All file edits inside repo root. |
| IV — CLI containment | N/A (Ship executes; not CLI agent context). |
| V — Structured observability | Closure document captures job results and audit trail. |
| VI — Single responsibility | Scope strictly limited to CI bootstrap and Windows-noise documentation. |
| VII — Destructive approval | None — additive only. |
| VIII — Safety modes | Plan hardened. Risky surface (`.github/workflows/`) flagged as moderate. |
| IX — Git-friendly persistence | Markdown + YAML, atomic commits. |
| X — Context efficiency | Plan is the single source for harvest; no duplicate prose. |
| XI — Merge commit history | Standard PR merge commit (Ship enforces). |

## Out-of-scope follow-up stash entries (Stage to create during harvest)

| Stash text | Priority | Kind |
|---|---|---|
| Add release / publish workflow (PyPI, GitHub Releases) once a 1.0 release is ready. | low | feature |
| Add cross-OS CI matrix (Windows + macOS) once Windows `tmp_path` PermissionError root cause is identified and fixed. | medium | task |
| Investigate root cause of Windows `tmp_path` `PermissionError` teardown noise (deeper than the local-dev workaround documented in 011-S). | low | task |
