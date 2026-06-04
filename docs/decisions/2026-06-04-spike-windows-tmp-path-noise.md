---
title: Spike — Windows tmp_path PermissionError teardown noise
date: 2026-06-04
status: resolved-by-absence
stash: 0AA8B223
unblocks: ED74577A
---

# Spike — Windows tmp_path PermissionError teardown noise

## Question

Stash `0AA8B223` (logged 2026-06-03 during 011-S) tracked a deeper RCA for
`PermissionError` teardown noise reported on Windows pytest runs (~176+ entries
per run). The local-dev workaround documented in `CONTRIBUTING.md` told
contributors to filter with `Select-String -NotMatch 'PermissionError'`. This
spike was meant to find and fix the root cause so the cross-OS CI matrix
follow-up (`ED74577A`) could ship.

## Approach

Re-run the full pytest suite on Windows on current `main` (`8c7fcba`,
post-015-S) twice and count the `PermissionError`/`ERROR` lines emitted.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --tb=line -q 2>&1 |
  Tee-Object -FilePath logs/pytest-windows-noise.txt
Select-String -Path logs/pytest-windows-noise.txt -Pattern "PermissionError"
```

## Findings

| Run | Result | `PermissionError` count | `ERROR` count |
|---|---|---|---|
| 1 | 859 passed, 5 skipped in 55.70s | 0 | 0 |
| 2 | 859 passed, 5 skipped in 53.68s | 0 | 0 |

**The noise no longer reproduces.** Both runs are completely clean of any
teardown-phase `PermissionError` lines and emit no `ERROR` entries at all.

## Likely Cause of Resolution

The G3a–G3c work (012-S → 015-S, 2026-06-03 → 2026-06-04) added ~50 tests and
modified large surfaces of `src/docline/readers/` and `src/docline/process/`.
The most plausible contributors to incidental resolution:

* **`CountingPictureSink` defers `mkdir`** until first emit (015-S). Empty
  `media/` directories are no longer created, removing one teardown
  reach-around.
* **Reader file-handle discipline** improved when DOCX image extraction was
  added via `defusedxml` parsing of `word/_rels/document.xml.rels` — all
  ZipFile opens are `with`-scoped (015-S).
* **PDF docling pipeline** now opens via context managers; the picture-routing
  isolation refactor (PR #30 review) keeps even error paths from leaking
  handles.

A definitive bisect is not warranted — the symptom is gone on the only
platform that exhibited it, and the codebase has continued to harden
file-handle ownership through the G3 series.

## Decision

* Mark `0AA8B223` as **resolved by absence of symptom**. Archive.
* `ED74577A` (cross-OS CI matrix) is **unblocked**. Promote into shipment.
* Update `CONTRIBUTING.md`: remove the obsolete "Known Windows local-dev
  noise" section, replace with a brief note that the historical noise no
  longer reproduces (cross-reference this spike for the audit trail).

## Verification Protocol for Future Sessions

If the noise re-emerges in a future Windows session:

1. Capture the failing teardown stack with
   `pytest --tb=long --capture=no -W error::ResourceWarning`.
2. Add `-W error::ResourceWarning` to a one-off run and bisect against the
   test that first raises.
3. Check whether new readers were added without context-managed file opens.

## References

* `CONTRIBUTING.md` (pre-016-S section "Known Windows local-dev noise")
* Stash `0AA8B223` (this spike's input)
* Stash `ED74577A` (unblocked follow-on)
* `logs/pytest-windows-noise.txt`, `logs/pytest-windows-noise-2.txt`
* Closure records `docs/closure/{012-S,013-S,014-S,015-S}-*.md`
