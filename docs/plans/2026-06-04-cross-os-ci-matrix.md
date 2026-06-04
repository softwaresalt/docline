---
title: Cross-OS CI matrix + Windows noise resolution
date: 2026-06-04
status: ready
shipment: 016-S
feature: 017-F
inputs:
  - stash: 0AA8B223
    disposition: resolved by absence (see docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md)
  - stash: ED74577A
    disposition: harvested into 017-F
---

# Plan — Cross-OS CI matrix + Windows noise resolution

## Problem

`.github/workflows/ci.yml` runs all 5 quality gates on `ubuntu-latest` only.
The Windows-side noise that previously blocked a cross-OS matrix has
incidentally resolved (see linked spike). Without a Windows/macOS CI signal,
platform-specific regressions (path separators, encoding defaults, file
locking) can land on `main` undetected.

## Goal

Expand the `test` job to a matrix over `ubuntu-latest`, `windows-latest`, and
`macos-latest`. Keep lint/format/typecheck/build on `ubuntu-latest` (they are
platform-deterministic and faster on a single OS). Update `CONTRIBUTING.md` to
remove the obsolete Windows noise section.

## Non-Goals

* Expanding the matrix to multiple Python versions — Python 3.12 remains the
  baseline per operator directive.
* Adding new tests. The 859-test suite is the contract.
* Touching the OCR enhancement (`4CA80776`) or release tooling (`7AA9FAA0`).

## Design

### CI workflow change

In `.github/workflows/ci.yml`, convert the `test` job to:

```yaml
test:
  name: pytest (${{ matrix.os }})
  runs-on: ${{ matrix.os }}
  strategy:
    fail-fast: false
    matrix:
      os: [ubuntu-latest, windows-latest, macos-latest]
  steps:
    # same checkout / uv / setup-python / sync / pytest steps
```

`fail-fast: false` so a single-platform failure doesn't cancel signal from the
others. All other jobs stay on `ubuntu-latest`.

### CONTRIBUTING.md change

Replace the "Known Windows local-dev noise" section with a short note that the
historical noise no longer reproduces, cross-referencing the spike artifact.
Keep the pre-PR checklist intact.

### Spike artifact

Already written at `docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md`.

### Closure artifact

Will be written at `docs/closure/016-S-cross-os-ci-matrix.md` at the close of
the shipment.

## Tasks (under 017-F, in shipment 016-S)

1. **017.001-T** — TDD RED: add a workflow lint test that asserts the
   matrix structure is present and includes the three OS targets.
2. **017.002-T** — Implement CI matrix expansion in `.github/workflows/ci.yml`.
3. **017.003-T** — Update `CONTRIBUTING.md` to reflect the spike finding.
4. **017.004-T** — Author closure record for 016-S.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Tests pass on Linux but fail on Windows due to undiscovered platform deps | Medium | Spike shows current main is clean on Windows; matrix will surface anything | 
| Tests pass on Linux but fail on macOS | Low | Same architectural patterns hold; first matrix run will surface anything |
| CI cost or runtime grows | Low | Matrix parallelizes; runtime is dominated by sync + pytest, both already cached via uv |
| `uv sync --locked --all-extras --dev` behaves differently on Windows/macOS | Low | uv is single-binary, statically linked; same lock file is portable |
| Windows runner has a different bundled docling/dependency that exposes a new bug | Medium | docling-gated tests are `skipif(not pdf_available())`; matrix will report the truth |

## Verification

* Lint, format, typecheck, build jobs continue to pass on ubuntu.
* The 3 pytest jobs (one per OS) all show 859 passed, 5 skipped.
* If any non-ubuntu job fails, address the root cause inline before merge.
* Run the full local 5-gate suite (Windows) before pushing.

## Constitution Check

| Principle | Check |
|---|---|
| I. Safety-First Python | No production code change; only CI YAML + docs. |
| II. Test-First Development | TDD RED workflow lint test precedes CI YAML change. |
| III. Workspace Isolation | All edits under repo root. |
| V. Structured Observability | CI broadcasts per-OS pytest status. |
| VII. Destructive Approval | No destructive operations. |
| XI. Merge Commit History | Merge commit only. |
