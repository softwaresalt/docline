---
title: "CI ruff pin vs local ruff: whole-repo format-check drift on markdown code fences"
date: 2026-08-29
agent: ship
context: quality-gates
tags:
  - ruff
  - format-gate
  - ci-parity
  - version-drift
  - markdown
trigger:
  - "ruff format --check . flags many pre-existing docs/*.md files you did not touch"
  - "A code-change PR makes the CI format job scope the whole repo"
  - "Local ruff version differs from the version pinned in uv.lock"
---

# CI ruff pin vs local ruff: whole-repo format-check drift on markdown code fences

## Problem

Running `ruff format --check .` locally flagged ~11 pre-existing `docs/*.md` files (Python
code fences inside markdown) plus two of the shipment's own source files. The docs were
byte-identical to `origin/main` and untouched by the branch, yet the CI `format` job runs
`ruff format --check .` over the whole repo whenever a non-doc path changes — so it looked
like the PR would fail CI on unrelated files.

## Root cause

Version drift. The local environment had **ruff 0.16.4**, which formats Python code blocks
embedded in markdown; CI runs **`uv run ruff`** pinned in `uv.lock` to **0.15.15**, which does
not. The pre-existing docs were only flagged by the newer local ruff, never by CI.

## Resolution

1. Determine the version CI actually uses: `uv.lock` → `name = "ruff"` → `version`.
2. Verify against that exact version, not the locally-installed one. Install it isolated:
   `python -m pip install --target .rufftmp ruff==<pinned>` then run `.rufftmp\bin\ruff.exe
   format --check .`. (Delete `.rufftmp` afterward — never commit it.)
3. Only format files the pinned CI version actually flags. Here that was the shipment's own
   two source files (real first-slice debt); the pre-existing docs were left untouched (out of
   scope, and not a CI failure).

## Lesson

When a whole-repo lint/format gate flags files outside your change, confirm the **CI-pinned
tool version** before reformatting anything. Reformatting unrelated files to satisfy a
newer-local-tool artifact is scope creep and would produce a noisy, reviewer-flagged diff for a
non-existent CI problem. The `git show origin/main:<path> | tool --check -` trick is unreliable
for markdown (stdin is treated as `.py`); prefer an isolated pinned-version install.
