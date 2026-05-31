# Session Memory: 003-F Harness Architect

**Date:** 2026-05-31
**Skill:** harness-architect
**Feature:** 003-F — Document ingestion acquisition and reader adapters
**Branch:** feat/document-ingestion-acquisition-and-reader-adapters
**Commit:** 31ea559

## Scope

Tasks scaffolded (all 10):

| Task | Unit | Stubs | Test Harness |
|------|------|-------|--------------|
| 003.001-T | 10 | `src/docline/fetch/url_policy.py` | `tests/security/test_url_policy.py` |
| 003.002-T | 11 | `src/docline/fetch/crawl.py`, `src/docline/fetch/http.py` | `tests/fetch/test_crawl_limits.py` |
| 003.003-T | 11A | `src/docline/fetch/crawl.py` | `tests/fetch/test_crawl_backoff.py` |
| 003.004-T | 12 | `src/docline/fetch/html_extract.py` | `tests/fetch/test_html_extract.py` |
| 003.005-T | 13 | `src/docline/fetch/html_normalize.py` | `tests/fetch/test_header_normalization.py` |
| 003.006-T | 14 | `src/docline/readers/limits.py`, `src/docline/readers/documents.py` | `tests/security/test_reader_limits.py` |
| 003.007-T | 15 | `src/docline/readers/pdf.py` | `tests/readers/test_pdf_reader.py` |
| 003.008-T | 16 | `src/docline/readers/docx.py` | `tests/readers/test_docx_reader.py` |
| 003.009-T | 17 | `src/docline/readers/text.py`, `src/docline/readers/transcripts.py` | `tests/readers/test_text_vtt_readers.py` |
| 003.010-T | 18 | `src/docline/readers/transcripts.py` | `tests/readers/test_transcript_preprocess.py` |

## Test Counts

- 33 structural tests PASS (scaffold verification)
- 89 behavioral tests FAIL with `NotImplementedError` (correct red phase)
- 193 pre-existing tests continue to pass

## Key Decisions

### Red-phase harness pattern
Do NOT use `pytest.raises(NotImplementedError)` — that marks tests green (false positive).
Behavioral tests must either:
- Assert a return value directly (fails when `NotImplementedError` is raised instead), or
- Use `pytest.raises(SpecificTypedException)` where the type is NOT `NotImplementedError`

### No pytest-asyncio
`pytest-asyncio` is not installed. All async tests use `asyncio.run()` inside synchronous test functions.

### Stub import discipline
Stubs must not carry unused imports (ruff F401). Keep only what is directly referenced.
Removed speculative imports: `asyncio`, `dataclasses.field`, `ipaddress`, `urlparse`,
`DependencyUnavailableError`, `require_extra`.

### TRUSTED_LOCAL_ONLY_TYPES
`frozenset[str]` in `readers/limits.py` containing PDF and DOCX MIME types. These types
are restricted to trusted local paths in v1.

## Backlog State

All 10 tasks:
- Label: `harness-ready`
- `--harness-status`: `scaffolded`
- `Implementation Notes` section: set with harness cmd and stub paths

Feature 003-F:
- `--harness-status`: `scaffolded`

## Quality Gates

- `python -m py_compile src/docline/__init__.py` → Exit 0
- `ruff check .` → All checks passed
- `ruff format --check .` → 55 files already formatted

## CLI Limitation

`backlogit update --section` works for named body sections (discovered during this session).
The `--sections` flag mentioned in prior notes does NOT exist; use `--section name=value`.
