---
title: "ELT multi-source ingestion pipeline implementation plan"
description: "Phased implementation plan for .elt staging area, multi-config loading, and end-to-end multi-source validation."
source_deliberation: "docs/decisions/2026-06-01-elt-multi-source-ingestion-deliberation.md"
stash_ids:
  - "D37D8AF7"
  - "5F0C557E"
tags:
  - "elt"
  - "config"
  - "multi-source"
  - "ingestion"
  - "validation"
requires_plan_hardening: false
---

# ELT multi-source ingestion pipeline implementation plan

## Objective

Deliver a working ELT multi-source ingestion feature where YAML configuration files in `.elt/config/` define heterogeneous document sources (local PDF/DOCX, website crawl, GitHub repos) and the `docline fetch` command orchestrates staging of all configured sources through the existing staging infrastructure to produce schema-conformant markdown output.

## Constitution Check

| Principle | Compliance |
|---|---|
| I. Safety-First Python | All new code uses typed Python 3.12 with Pydantic models |
| II. Test-First Development | Each task starts with a failing test harness |
| III. Workspace Isolation | `.elt/` resolves within workspace root via existing `paths.py` |
| IV. CLI Containment | All file ops use `safe_workspace_path` |
| VII. Destructive Approval | No destructive operations in this feature |
| XI. Merge Commits | Standard merge workflow |

## Implementation Units

### Unit 1: ELT directory convention and .gitignore

**Scope**: Establish the `.elt/` staging area convention. The `.gitignore` entry (already staged locally by operator) declares `.elt/` as local-only. Create a `src/docline/elt/__init__.py` package stub and path constants.

**Files**: `.gitignore`, `src/docline/elt/__init__.py`, `src/docline/elt/paths.py`
**Test**: `tests/elt/test_elt_paths.py` — verifies `.elt/` path resolution stays within workspace root
**Acceptance**: Path resolution tests pass; `.elt/` is excluded from Git tracking

### Unit 2: YAML config file discovery and parsing

**Scope**: Implement a config directory scanner that discovers `*.yaml` and `*.yml` files in `.elt/config/`, validates them against a Pydantic schema, and returns typed source descriptors.

**Files**: `src/docline/elt/config.py`, `src/docline/elt/models.py`
**Test**: `tests/elt/test_config_discovery.py` — tests directory scanning, YAML parsing, validation errors
**Acceptance**: Config scanner discovers files, parses valid YAML, raises typed errors on invalid configs

### Unit 3: Typed source descriptors

**Scope**: Define Pydantic models for each source type: `LocalFileSource` (PDF/DOCX paths), `WebCrawlSource` (URL + crawl policy), `GitHubRepoSource` (repo URL + path glob). Implement a discriminated union `SourceConfig` model.

**Files**: `src/docline/elt/models.py` (extend from Unit 2)
**Test**: `tests/elt/test_source_models.py` — validates each source type, discriminated union dispatch, serialization round-trip
**Acceptance**: All three source types parse from YAML fragments; invalid source types raise `ValidationError`

### Unit 4: Config-driven multi-source fetch orchestration

**Scope**: Wire the config scanner output into the existing `create_staging_job` infrastructure. Implement `orchestrate_fetch(config_dir: Path, staging_dir: Path) -> list[StagingJob]` that iterates sources and creates staging jobs for each.

**Files**: `src/docline/elt/orchestrate.py`
**Test**: `tests/elt/test_orchestrate.py` — mock-based tests verifying orchestration creates correct staging jobs per source type
**Acceptance**: Orchestrator produces one `StagingJob` per configured source with correct job IDs and cache paths

### Unit 5: CLI integration (`docline fetch` reads .elt/config)

**Scope**: Replace the `fetch` command stub in `cli.py` with a real implementation that invokes the ELT orchestrator when `.elt/config/` exists. Preserve existing CLI contract (exit codes, usage messages).

**Files**: `src/docline/cli.py`
**Test**: `tests/test_cli_fetch.py` — CLI integration tests with temporary `.elt/config/` directories
**Acceptance**: `docline fetch` with valid `.elt/config/` produces staging jobs and exits 0; missing config exits with informative error

### Unit 6: End-to-end validation tests

**Scope**: Integration tests proving the full pipeline from YAML config → fetch orchestration → schema-conformant markdown output for each source type (PDF, DOCX, web crawl, GitHub). Uses test fixtures and mocked HTTP responses.

**Files**: `tests/elt/test_e2e_multi_source.py`
**Test**: Self-contained integration test file marked `@pytest.mark.integration`
**Acceptance**: All source types produce markdown output conforming to the docline schema; test exercises PDF, DOCX, web crawl, and GitHub source paths

## Dependency Order

```text
Unit 1 (convention)
  → Unit 2 (config discovery)
    → Unit 3 (source models)
      → Unit 4 (orchestration)
        → Unit 5 (CLI integration)
          → Unit 6 (E2E validation)
```

Linear dependency chain — each unit builds on the prior. No parallelism possible.

## Risk Assessment

| Risk | Mitigation |
|---|---|
| GitHub source type complexity | Mock-based testing; defer actual HTTP integration to Ship |
| Scope creep into MCP adapter | Explicitly out of scope; MCP parity is 005-S |
| Config schema evolution | Use strict Pydantic models with `extra="forbid"` |

## Estimated Effort

6 tasks × ~2 hours each = ~12 hours total human-equivalent effort.
