---
title: "Harness artifacts are LF and manifest checksums are raw-byte hashes — probe before writing"
date: 2026-08-31
agent: ship
context: autoharness-harness
tags:
  - autoharness
  - harness-manifest
  - checksums
  - line-endings
  - windows
trigger:
  - "You are hand-installing or re-rendering an autoharness artifact on Windows"
  - "You need to add an artifacts[] entry with a checksum to harness-manifest.yaml"
  - "verify-workspace reports artifacts as drifted or user-modified right after you wrote them"
---

## Problem

When adding five new harness artifacts by hand on a Windows checkout, the natural assumption
is to write CRLF "to match the workspace." Doing so would have produced five manifest
checksums that never match, flagging all five artifacts as drifted on the very next
`verify-workspace` run — and inviting a future `tune-harness` to "repair" files that were
correct.

## Root cause

Two facts that must be established empirically rather than assumed:

1. **Installed harness artifacts are LF**, even in a CRLF-configured Windows checkout.
   Sampling existing installed artifacts showed `crlf=0` across the board.
2. **`harness-manifest.yaml` checksums are raw-byte SHA-256 of the file content** — they are
   *not* EOL-normalized before hashing. They only happen to be stable across platforms
   because the content is already LF.

Because (2) does no normalization, (1) is load-bearing. Write CRLF and every checksum breaks.

## Resolution

Probe both before writing anything:

```powershell
# 1. Confirm existing installed artifacts are LF
$b = [IO.File]::ReadAllBytes('.github/instructions/markdown.instructions.md')
$crlf = 0; for ($i=1; $i -lt $b.Length; $i++) { if ($b[$i] -eq 10 -and $b[$i-1] -eq 13) { $crlf++ } }
"crlf=$crlf"   # expect 0

# 2. Confirm the manifest checksum is a raw-byte hash of that same file
(Get-FileHash '.github/instructions/markdown.instructions.md' -Algorithm SHA256).Hash.ToLower()
# compare against the artifacts[] entry
```

Then write with explicit LF (`[IO.File]::WriteAllText` with `"\n"` joins, not
`Out-File`/`Set-Content`, which inject CRLF on Windows).

Note that `.autoharness/staging/` is gitignored, so probe scripts written there never dirty
the working tree.

## Lesson

A checksum manifest is only protective if the bytes you write match the bytes it records.
Two cheap read-only probes — one for line endings, one for hash semantics — cost seconds and
prevented five silently-wrong entries. When a convention is *inferable* but not documented,
measure it against artifacts that are already known-good rather than reasoning from platform
defaults.
