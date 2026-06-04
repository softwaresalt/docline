# Contributing to docline

Welcome. This guide covers the local quality gates, how to run them with `uv`,
the cross-OS CI matrix, and the pre-PR checklist.

## Local quality gates

The five gates below are the authoritative quality bar. They are mirrored in
CI by [`.github/workflows/ci.yml`](.github/workflows/ci.yml); CI runs lint,
format, typecheck, and build on `ubuntu-latest`, and runs pytest on a matrix
over `ubuntu-latest`, `windows-latest`, and `macos-latest`. Run the same
commands locally before opening a PR.

| Gate      | Command                          | Purpose                          |
|-----------|----------------------------------|----------------------------------|
| Lint      | `uv run ruff check .`            | ruff static lint                 |
| Format    | `uv run ruff format --check .`   | ruff formatting check            |
| Typecheck | `uv run pyright src/`            | pyright type analysis            |
| Test      | `uv run pytest`                  | pytest suite                     |
| Build     | `uv run python -m build`         | sdist and wheel artifact build   |

## Running gates with uv

docline uses [uv](https://docs.astral.sh/uv/) to manage the Python environment.
Sync the project's locked dev environment once with

```text
uv sync --all-extras --dev
```

then invoke each gate via `uv run <command>`. The `uv run` prefix activates the
project's virtualenv on demand so contributors do not need globally installed
`ruff`, `pyright`, `pytest`, or `build`. CI uses the same `uv run` pattern.

## Cross-OS CI matrix

CI runs the `pytest` job on `ubuntu-latest`, `windows-latest`, and
`macos-latest` via a strategy matrix. The other gates (`lint`, `format`,
`typecheck`, `build`) remain on `ubuntu-latest` because their outputs are
platform-deterministic and they run faster on a single OS. `fail-fast: false`
keeps a single-platform failure from cancelling signal from the others.

When you push a PR, expect three `pytest (<os>)` checks instead of one.

## Historical Windows local-dev noise (resolved)

Earlier versions of this guide warned about ~176+ `PermissionError` entries
emitted during `pytest` teardown on Windows (Windows holding `tmp_path` file
handles past pytest cleanup). That noise no longer reproduces on current
`main` — see
[`docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md`](docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md)
for the spike that confirmed two consecutive clean runs.

If you observe the noise re-emerging in a future Windows session, capture the
failing teardown with `pytest --tb=long --capture=no -W error::ResourceWarning`
and file a bug.

## Pre-PR checklist

Run all five gates locally before opening a pull request:

* `uv run ruff check .`
* `uv run ruff format --check .`
* `uv run pyright src/`
* `uv run pytest`
* `uv run python -m build`

Confirm the gates pass. Then push your branch and open the PR; CI will re-run
the same five gates (with pytest fanned out across ubuntu/windows/macos) and
act as the authoritative reviewer.
