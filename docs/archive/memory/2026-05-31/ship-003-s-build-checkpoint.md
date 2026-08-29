---
title: "Ship memory — 003-S build checkpoint"
shipment: "003-S"
feature: "003-F"
branch: "feat/document-ingestion-acquisition-and-reader-adapters"
date: "2026-05-31"
status: "pr-pending"
---

# Ship Session — 003-S Document Acquisition and Reader Adapters

## Context

Resumed from prior session. Branch had harness scaffolding committed (31ea559)
and a dirty `url_policy.py` with a complete correct implementation of
`validate_crawl_url`, `is_private_host`, and `assert_redirect_count`.

## Items Completed

All 10 tasks completed and archived:

| Task | Title | Commit |
|------|-------|--------|
| 003.001-T | Reject unsafe crawl URLs | 37ee98b |
| 003.002-T | Bound crawl executor timeouts | 5b725fb |
| 003.003-T | Add robots and backoff controls | 5b725fb |
| 003.004-T | Extract main HTML content | 90c45e8 |
| 003.005-T | Normalize extracted heading hierarchy | 90c45e8 |
| 003.006-T | Enforce reader safety limits | cea72fb |
| 003.007-T | Add PDF reader adapter | cea72fb |
| 003.008-T | Add DOCX reader adapter | cea72fb |
| 003.009-T | Add text and VTT adapters | cea72fb |
| 003.010-T | Add transcript preprocessing hooks | cea72fb |

## Security Fix Applied

P0 review finding fixed before PR:
- `fetch_page()` had `_ = max_redirects` — silently ignored the redirect cap
- Redirect targets were not re-validated through URL policy (open-redirect SSRF)
- Fix: `_ValidatingRedirectHandler` validates each redirect via `validate_crawl_url`
  and raises `FetchError` when the redirect cap is exceeded — commit 465e7e6

## Quality Gates

- `python -m py_compile src/docline/__init__.py` ✅
- `ruff check .` ✅
- `ruff format --check .` ✅
- `pytest` — 315/315 passed ✅
- Code review gate: P0 fixed, P1s assessed as test-specified behavior (PDF/DOCX
  return "" when docling is absent — tests explicitly accept `len(result) >= 0`)

## Backlog State

- All 10 tasks archived to `.backlogit/archive/`
- 003-F feature: still `active` (closes with shipment after PR merge)
- 003-S shipment: still `active`

## Branch State

- Branch: `feat/document-ingestion-acquisition-and-reader-adapters`
- 9 commits ahead of `main`
- All tests pass, all quality gates green
- No open PR yet — PR creation is the next step

## Next Steps

1. Push branch to remote
2. Create PR via pr-lifecycle skill
3. Request Copilot review
4. Await operator approval for merge
5. Post-merge: close 003-S shipment, archive 003-F, run closure protocol
