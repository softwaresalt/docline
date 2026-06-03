# Contributing to docline

Welcome. This guide covers the local quality gates, how to run them with `uv`,
known Windows local-dev noise, and the pre-PR checklist.

## Local quality gates

The five gates below are the authoritative quality bar. They are mirrored in
CI by [`.github/workflows/ci.yml`](.github/workflows/ci.yml); CI runs each gate
as a separate job on `ubuntu-latest`. Run the same commands locally before
opening a PR.

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

## Known Windows local-dev noise

When you run `pytest` on Windows you may see ~176 or more `PermissionError`
entries reported in the `ERROR` section of the output. These are environmental:
Windows holds file handles in `tmp_path` fixtures during pytest teardown, and
the cleanup raises `PermissionError` before the OS releases the handle. They do
NOT affect the pass/fail conclusion of any test and they do NOT indicate
regressions.

To filter the noise and see only test outcomes:

PowerShell:

```powershell
uv run pytest 2>&1 | Select-String -NotMatch 'PermissionError'
```

bash:

```bash
uv run pytest 2>&1 | grep -v 'PermissionError'
```

CI runs every gate on Linux (Ubuntu), where this noise does not occur. CI is
the authoritative gate for PR validation. If your local Windows `pytest` shows
clean `PASSED` results with only the known `tmp_path` `PermissionError` noise,
you can rely on CI to confirm the result.

A deeper root-cause investigation for the Windows `tmp_path` teardown noise is
tracked separately as a low-priority follow-up; see stash entry `0AA8B223`.

## Pre-PR checklist

Run all five gates locally before opening a pull request:

* `uv run ruff check .`
* `uv run ruff format --check .`
* `uv run pyright src/`
* `uv run pytest`
* `uv run python -m build`

Confirm the gates pass (Windows contributors: confirm the only noise is the
known `tmp_path` `PermissionError` entries). Then push your branch and open the
PR; CI will re-run the same five gates and act as the authoritative reviewer.
