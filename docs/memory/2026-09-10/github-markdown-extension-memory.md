---
title: GitHub Markdown Extension Support Session
date: 2026-09-10
---

## Outcome

GitHub repository ingestion now treats `.markdown` files as Markdown alongside
`.md` files. The default `**/*.md` GitHub filter includes both extensions, and
the processing pipeline accepts, parses, links, orders, and derives canonical
URLs for `.markdown` sources.

## Changes

* Updated GitHub glob matching in `src/docline/readers/github.py`
* Added `.markdown` to staged-file processing in `src/docline/app.py`
* Routed `.markdown` through Markdown parsing in
  `src/docline/process/output_contract.py`
* Added `.markdown` handling for canonical URLs, cross-document links, and TOC
  entries
* Added regression coverage across GitHub fetching and Markdown processing

## Decisions

* Preserved the existing `path_glob` configuration and source-key format
* Treated a GitHub include pattern ending in `.md` as including the equivalent
  `.markdown` extension
* Preserved `.markdown` link targets while normalizing generated output files
  to `.md`

## Verification

* Ruff lint passed
* Pyright passed with the project interpreter
* All 2,126 tests passed
* Ruff format check passed
* Python package build passed

## Failed Approaches

* Global `ruff` was not on `PATH`; the project virtual environment executable
  was used
* Pyright initially used the wrong interpreter; rerunning with
  `--pythonpath .venv\Scripts\python.exe` resolved the declared optional
  `httpx` import

## Open Questions

None.

## Next Steps

None.
