---
title: Closure — 016-S Cross-OS CI matrix + Windows noise resolution
date: 2026-06-04
shipment: 016-S
feature: 017-F
merge_sha: e58c4312c77c806642da80c0d98f94c736357912
pr: 32
status: shipped
---

# Closure — 016-S: Cross-OS CI matrix + Windows noise resolution

## Outcome

`.github/workflows/ci.yml` now runs `pytest` on a strategy matrix over
`ubuntu-latest`, `windows-latest`, and `macos-latest`. The other gates
(`lint`, `format`, `typecheck`, `build`) remain on `ubuntu-latest`.
`fail-fast: false` keeps a single-platform failure from cancelling signal
from the others.

The previously documented Windows `tmp_path` `PermissionError` teardown
noise no longer reproduces (see linked spike). `CONTRIBUTING.md` was
updated to remove the obsolete workaround and document the new CI shape.

## Tasks

| Task | Title | Outcome |
|---|---|---|
| 017.001-T | TDD RED workflow lint | 4/9 failing → all 9 PASS after GREEN |
| 017.002-T | TDD GREEN ci.yml matrix | matrix over 3 OSes, fail-fast: false, runs-on: ${{ matrix.os }} |
| 017.003-T | CONTRIBUTING.md update | Obsolete Windows-noise section removed; cross-OS matrix section + spike cross-reference added |
| 017.004-T | Closure record | This file |

## Quality Gate Evidence

### Local (Windows, pre-PR)

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 152 files clean |
| `pyright src/` | 0 errors, 0 warnings, 0 informations |
| `pytest` | 868 passed, 5 skipped (~66 s, incl. 9 new workflow lint tests) |
| `python -m build` | sdist + wheel built |

### CI (PR #32, HEAD `4e237ab`)

| Check | Duration | Result |
|---|---|---|
| ruff lint | 38 s | ✅ pass |
| ruff format check | 41 s | ✅ pass |
| pyright | 47 s | ✅ pass |
| sdist + wheel | 51 s | ✅ pass |
| pytest (ubuntu-latest) | 1 m 6 s | ✅ pass |
| pytest (windows-latest) | 1 m 39 s | ✅ pass |
| pytest (macos-latest) | 39 s | ✅ pass |

All 868 tests pass on all three OSes with no platform-specific guards.
The G3a–G3c hardening (file-handle discipline, CRLF normalization, deferred
mkdir in `CountingPictureSink`) made the suite cross-platform-portable in
addition to fixing the Windows teardown noise.

## Review

* Copilot review (PR #32): 1 P3 finding — test functions missing docstrings
  per project convention. Fixed in commit `4e237ab` (one-line docstrings on
  all 9 test functions). Replied to comment and resolved thread.
* No other reviewer findings.

## Spike Outcome

The spike for stash `0AA8B223` (Windows `tmp_path` RCA) was **resolved by
absence of symptom**:

* Two consecutive `pytest` runs on current `main` (post-015-S, pre-PR-32)
  emitted 0 `PermissionError` and 0 `ERROR` entries.
* Likely cause: file-handle discipline introduced in 012-S → 015-S
  (`CountingPictureSink.emit` deferred mkdir; DOCX/PDF readers using
  context-managed file/zip opens; isolated picture-routing try/except).
* No code fix required; the noise that was the entire point of `0AA8B223`
  simply does not occur any more.

Spike artifact: `docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md`

Both `0AA8B223` (resolved) and `ED74577A` (unblocked → harvested into
`017-F`) archived from stash.

## Follow-ups

None gated by this shipment. Remaining stash:

| ID | Priority | Notes |
|---|---|---|
| `4CA80776` | low | docling `do_ocr=True` enhancement |
| `7AA9FAA0` | low | PyPI/Releases workflow (defer to 1.0) |

## References

* PR #32: https://github.com/softwaresalt/docline/pull/32
* Merge SHA: `e58c4312c77c806642da80c0d98f94c736357912`
* Plan: `docs/plans/2026-06-04-cross-os-ci-matrix.md`
* Spike: `docs/decisions/2026-06-04-spike-windows-tmp-path-noise.md`
* CI run (final): https://github.com/softwaresalt/docline/actions/runs/26984936664
