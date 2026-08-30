---
title: "Pyright and pytest in a git worktree need the primary checkout's venv"
date: 2026-08-29
agent: ship
context: quality-gates
tags:
  - git-worktree
  - pyright
  - pytest
  - venv
  - false-positives
trigger:
  - "Shipping from an isolated git worktree instead of the primary checkout"
  - "pyright reports dozens of unresolved-import errors for installed packages"
  - "pytest fails with ModuleNotFoundError: No module named 'docline'"
---

## Problem

Running the quality gates from a `git worktree add` directory produced two failures that looked
like real defects but were pure environment artifacts:

- `pytest` failed at collection with `ModuleNotFoundError: No module named 'docline'`, then with
  `No module named 'pydantic'` once `src` was on the path.
- `pyright src/` reported **28 errors** — unresolved `pydantic`, `httpx`, `pypdf`, and friends.

Reacting to either as a code problem would have wasted a cycle, and the pyright count is alarming
enough to look like a genuine regression from the change under review.

## Root cause

`.venv` lives in the primary checkout and is not replicated into a linked worktree. The worktree
has the source tree but no environment: the package is not installed in editable mode there, and
the default interpreter on `PATH` has none of the project dependencies. Pyright independently
resolves its interpreter and, finding the bare system Python, reports every third-party import as
unresolved.

## Resolution

Point both tools at the primary checkout's interpreter explicitly. From the worktree root:

```powershell
$env:PYTHONPATH = "src"
C:\Source\GitHub\docline\.venv\Scripts\python.exe -m pytest -q
C:\Source\GitHub\docline\.venv\Scripts\python.exe -m pyright --pythonpath C:\Source\GitHub\docline\.venv\Scripts\python.exe src/
```

`PYTHONPATH=src` substitutes for the missing editable install; `--pythonpath` is required
separately because invoking pyright through the venv's `python -m` does **not** make it adopt that
interpreter for import resolution.

## Lesson

Before treating a mass of unresolved-import errors as a finding, confirm the tool is using the
project interpreter. In a worktree the source is isolated but the environment is not — so
establish the gate invocation once at session start and reuse it, rather than rediscovering it
mid-review when the error count is easy to misread as a regression.
