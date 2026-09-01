---
title: "Fixing a .sh hook without its .ps1 twin leaves a fail-open parity gap"
date: 2026-08-31
agent: ship
context: git-hooks
tags:
  - powershell
  - bash
  - git-hooks
  - fail-closed
  - shell-parity
trigger:
  - "You fix repo-root discovery or an error path in one of a .sh/.ps1 hook pair"
  - "A hook uses git rev-parse to locate the repo root"
  - "A PowerShell script relies on a command failing to stop execution"
---

## Problem

The harness ships every git hook as a `.sh` / `.ps1` pair. A review round fixed fail-open
repo-root discovery in the Bash hooks; a later round flagged that the PowerShell twins still
failed open. Same defect, same file family, missed because only one shell was audited.

The PowerShell path was worse than "did not exit" — it silently ran the gate **against the
caller's current directory** instead of the repo root.

## Root cause

Outside a Git repository, `git rev-parse --show-toplevel` exits 128 and prints nothing, so
`$RepoRoot` is empty. Then:

```powershell
Set-Location $RepoRoot     # PSArgumentNullException — but NON-TERMINATING
```

Under the default `$ErrorActionPreference = 'Continue'`, a non-terminating error writes to the
error stream and **execution continues**. The script proceeds in whatever directory the caller
happened to be in.

Bash has an analogous trap: `set -uo pipefail` without `-e` means `cd ""` returns rc=1 and
execution continues — after which `git diff --cached` returns empty and the hook exits 0
having linted nothing.

## Resolution

Check the exit status explicitly rather than relying on an error to halt anything:

```powershell
$RepoRoot = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RepoRoot)) {
    Write-Error "Not inside a git repository."
    exit 1
}
Set-Location -LiteralPath $RepoRoot
```

Verify the real exit code with `Start-Process -Wait -PassThru`. `$LASTEXITCODE` after a
pipeline reflects the **pipeline**, not the child process, so a piped invocation will happily
report success for a script that exited 1.

## Lesson

Treat `.sh` / `.ps1` hook pairs as a single unit of work: when you fix one, diff the other in
the same change. And never assume a failed command stops a PowerShell script — the default
`Continue` preference makes most errors non-terminating, which converts a fail-closed intent
into fail-open behavior. Explicit `$LASTEXITCODE` checks are the only reliable gate.
