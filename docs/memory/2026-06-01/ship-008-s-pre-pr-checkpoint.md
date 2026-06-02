---
title: "Ship 008-S pre-PR checkpoint"
date: 2026-06-01
shipment: 008-S
branch: feat/elt-multi-source-ingestion
commit: fc471f0
phase: pre-pr
---

# Ship 008-S Pre-PR Checkpoint

## Items Completed

All 6 tasks completed and archived:

| Task | Title | Status |
|---|---|---|
| 008.001-T | Establish ELT directory convention and .gitignore entry | done |
| 008.002-T | Implement YAML config file discovery and parsing | done |
| 008.003-T | Define typed source descriptor models | done |
| 008.004-T | Implement config-driven multi-source fetch orchestration | done |
| 008.005-T | Integrate ELT orchestrator into CLI fetch command | done |
| 008.006-T | End-to-end multi-source ingestion validation tests | done |

## Files Modified/Created

**New production code:**

* `src/docline/elt/__init__.py` — package stub
* `src/docline/elt/paths.py` — ELT path constants (`get_elt_dir`, `get_elt_config_dir`, `get_elt_staging_dir`)
* `src/docline/elt/models.py` — typed source models (`LocalFileSource`, `WebCrawlSource`, `GitHubRepoSource`, `SourceConfig` discriminated union)
* `src/docline/elt/config.py` — YAML config discovery (`discover_configs`, `ConfigDiscoveryError`)
* `src/docline/elt/orchestrate.py` — multi-source orchestration (`orchestrate_fetch`)

**Modified:**

* `src/docline/cli.py` — replaced `fetch <source>` stub with ELT orchestrator integration
* `pyproject.toml` — added `integration` pytest marker

**New tests (470 total, all passing):**

* `tests/elt/test_elt_paths.py`
* `tests/elt/test_config_discovery.py`
* `tests/elt/test_source_models.py`
* `tests/elt/test_orchestrate.py`
* `tests/elt/test_e2e_multi_source.py`
* `tests/test_cli_fetch.py`
* Updated parity tests in `tests/parity/`

## Decisions and Rationale

**Job key collision fix (P1):** `_source_to_job_key` in `orchestrate.py` was
originally returning only the URL for `WebCrawlSource` and `repo@branch` for
`GitHubRepoSource`. Review found that configs differing only in `depth`,
`max_pages`, or `path_glob` would collide to the same staging job. Fixed to
include all behavior-affecting fields in the key:

* `web_crawl:<url>[:depth=N][:max_pages=N]`
* `github_repo:<repo>@<branch>:<path_glob>`

**MCP/manifest divergence (P1 accepted as scope limitation):** The MCP server
and `--manifest` command still expose `FetchRequest` (source/depth/output_dir).
The CLI fetch command now uses the ELT orchestrator. This divergence is
intentional — MCP adapter changes are explicitly out of scope for 008-S (deferred
to a follow-up shipment). All affected parity tests were updated.

## Branch State

* Branch: `feat/elt-multi-source-ingestion`
* Commit: `fc471f0`
* All quality gates passing: ruff ✅, pyright ✅, pytest 470/470 ✅, format ✅

## Next Steps

* Push branch to origin
* Create PR with Copilot review
* Await operator approval for merge
