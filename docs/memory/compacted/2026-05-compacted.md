---
type: compacted-summary
scope: memory
period: 2026-05
compacted_at: 2026-08-29
source_count: 15
---

## Overview

May 2026 memory covered initial backlog durability setup and the first document-ingestion release train: staging converted two stash entries into six features and queued shipments `001-S` through `006-S`; Ship delivered `001-S` backlog artifact persistence, `002-S` ingestion foundations, `003-S` acquisition and reader adapters, `004-S` processing validation and outputs, and `007-S` pyright regression cleanup while leaving several post-merge closure PRs for separate operator approval.

## Key Decisions

* `001-S` backlog persistence prerequisite
  * Replace blanket `.backlogit/` ignore with targeted volatile-runtime ignores so queue and archive artifacts remain trackable while logs, hooks queue, SQLite sidecars, and telemetry stay ignored
  * Treat missing `src/docline/__init__.py` as greenfield bootstrap, not product scope
  * Raise actionable `_GitCheckIgnoreError` when git ignore probing is unavailable
  * Proceeded with merge only after explicit operator override because fresh Copilot review could not be requested, with existing Copilot threads resolved
* Stage document ingestion program
  * Processed durable backlog persistence before ingestion because ignored backlog artifacts threatened remote durability
  * Used the design doc as the sole ingestion-program scope source, revised plans after review to add test-first mapping, 2-hour tasks, parity, path-containment, crawler safety, correction-payload, and transport hardening
  * Created a linear feature and shipment sequence: `001-F -> 002-F -> 003-F -> 004-F -> 005-F -> 006-F`
  * Recorded explicit dependencies for schema-before-parity, safety-before-reader, correction-policy-before-correction-loop, and output-before-parity ordering
* `002-S` document ingestion foundations
  * Standardized foundational contracts on Pydantic v2 and `datetime.UTC`
  * Anchored `.gitignore` `/build/` so `tests/build/` remains tracked
  * Preserved deterministic job identity by deriving `job_id` from the raw source before metadata sanitization
  * Fixed path containment by using `Path.is_relative_to()` instead of string `startswith()`
  * Required `create_staging_job()` to call `sanitize_source()` and reject UNC, rooted-Windows, and `file://` paths
* `003-F` / `003-S` acquisition and reader adapters
  * Harness tests must fail red by asserting intended behavior, not by expecting `NotImplementedError`
  * Avoided `pytest-asyncio`; async tests use `asyncio.run()` in synchronous tests
  * `TRUSTED_LOCAL_ONLY_TYPES` restricts PDF/DOCX MIME types to trusted local paths in v1
  * Fixed P0 SSRF redirect issue by validating every redirect target and enforcing redirect caps in `_ValidatingRedirectHandler`
  * Accepted PDF/DOCX empty output when docling is absent because tests explicitly allow that fallback
* `004-S` processing validation and outputs
  * Added `SourceKind.UNKNOWN` to support explicit document-type rejection paths
  * Changed `update_manifest_index(output_root, manifest_name, entry)` to match `write_markdown_output` containment style
  * Kept correction loop as a no-provider v1 stub that returns failure and preserves original markdown
  * Applied recursive secret redaction through nested dicts and lists
  * Normalized path separators for FILE and TRANSCRIPT UUID hashing
  * Created follow-up stash `F6CCF29C` when post-merge `pyright src/` found process-module type regressions
* `007-S` pyright regression cleanup
  * Used `Mapping[str, Any]` for Pydantic metadata unpacking because `object` was too restrictive for pyright while Pydantic validates at the boundary
  * Typed Markdown inline tokens with `markdown_it.token.Token`, matching `MarkdownIt().parse()` output

## Files & Areas Modified

* Backlog durability and repository bootstrap: `.gitignore`, `pyproject.toml`, `src/docline/__init__.py`, initial `tests/` packages
* Core ingestion contracts: `src/docline/types.py`, `router.py`, `schema/models.py`, `schema/library.py`, `app_models.py`, `app.py`, `cli.py`, `dependencies.py`, `paths.py`
* Fetch and staging: `src/docline/fetch/models.py`, `fetch/staging.py`, `fetch/url_policy.py`, `fetch/crawl.py`, `fetch/http.py`, `fetch/html_extract.py`, `fetch/html_normalize.py`
* Reader adapters and safety: `src/docline/readers/limits.py`, `readers/documents.py`, `readers/pdf.py`, `readers/docx.py`, `readers/text.py`, `readers/transcripts.py`
* Processing pipeline: `src/docline/process/identity.py`, `metadata.py`, `transcripts.py`, `assemble.py`, `ast_lint.py`, `prompts.py`, `correction.py`, `quarantine.py`, `output.py`, `manifest.py`, `config.py`
* Test suites: schema, parity, fetch, security, readers, process, and build tests, growing from bootstrap coverage to 367 passing tests by the end of the month
* Durable artifacts: deliberations, implementation plans, closure documents, reconcile reports, backlog queue/archive entries, and post-merge closure branches

## Key Learnings

* Red-phase harnesses should assert target behavior directly; expecting `NotImplementedError` creates false-green tests
* Path containment must be semantic (`is_relative_to`) and applied at every file-system boundary, including manifest writes and staged metadata
* Review gates caught high-value issues early: recursive redaction, manifest containment, redirect SSRF, UUID normalization, and heading text extraction
* CLI and MCP parity needs explicit models and manifest generation rather than duplicated ad hoc definitions
* Copilot review re-request was unreliable in this environment; merge readiness often required operator overrides after resolving all known threads
* Dedicated post-merge closure branches preserve backlog archival and closure documentation separately from feature implementation
* Backlogit CLI section editing uses `--section name=value`; the previously assumed `--sections` flag does not exist

## Failed Approaches / Halts

* `004-S` hit a §1.9 stale-Copilot review halt: latest review covered `bc2eaf6`, current head was `821579e`, all threads were resolved, all gates passed, but no fresh review appeared within 15 minutes and REST request returned 422
* Multiple main PRs required explicit operator-approved stale-review or admin overrides because Copilot review freshness or GitHub base-branch policy blocked the normal path
* Programmatic Copilot review requests for closure PRs often failed through `gh pr edit --add-reviewer copilot`
* Initial `004-S` correction stub made `corrected_markdown` indistinguishable from success; fixed to return `None`, `attempts=0`, and explicit stub documentation
* Initial `004-S` transcript merge did not update `end_ms` while appending; fixed after Copilot review

## Outcomes

* `001-S` merged and archived with merge commit `b7e3faa0bbe7be7ea9eb220f6d963911f41bd160`
* `002-S` merged and archived with merge commit `cf7e8d5236409f882a5f759ad141424baeef017b`; closure PR `#5` opened
* `003-S` merged and archived with merge commit `3f83a9715854bf77d36d4511e5f51ebf2fe8b38e`; closure PR `#7` opened
* `004-S` merged and archived with merge commit `b9d138904f7a9ff2f222cdd0a5103b07152de3cc`; closure PR `#9` opened and pyright follow-up stashed
* `007-S` merged and archived with merge commit `5c93476b49ffb68e8339feff062f0831293e430c`; closure PR `#11` opened
* Stage completed ingestion-program decomposition: six features, forty-four tasks, and six queued shipments with dependency edges

## Archived Originals

| Original | Archive path |
|---|---|
| `docs/archive/memory/2026-05-30/ship-001-s-final-memory.md` | `docs/archive/memory/2026-05-30/ship-001-s-final-memory.md` |
| `docs/archive/memory/2026-05-30/ship-001-s-resume-memory.md` | `docs/archive/memory/2026-05-30/ship-001-s-resume-memory.md` |
| `docs/archive/memory/2026-05-30/ship-002-s-ingestion-foundations.md` | `docs/archive/memory/2026-05-30/ship-002-s-ingestion-foundations.md` |
| `docs/archive/memory/2026-05-30/stage-document-ingestion-classification-checkpoint.md` | `docs/archive/memory/2026-05-30/stage-document-ingestion-classification-checkpoint.md` |
| `docs/archive/memory/2026-05-30/stage-document-ingestion-final-memory.md` | `docs/archive/memory/2026-05-30/stage-document-ingestion-final-memory.md` |
| `docs/archive/memory/2026-05-30/stage-document-ingestion-harvest-checkpoint.md` | `docs/archive/memory/2026-05-30/stage-document-ingestion-harvest-checkpoint.md` |
| `docs/archive/memory/2026-05-31/003-F-harness-architect-memory.md` | `docs/archive/memory/2026-05-31/003-F-harness-architect-memory.md` |
| `docs/archive/memory/2026-05-31/007-S-build-complete-memory.md` | `docs/archive/memory/2026-05-31/007-S-build-complete-memory.md` |
| `docs/archive/memory/2026-05-31/ship-002-s-final-memory.md` | `docs/archive/memory/2026-05-31/ship-002-s-final-memory.md` |
| `docs/archive/memory/2026-05-31/ship-003-s-build-checkpoint.md` | `docs/archive/memory/2026-05-31/ship-003-s-build-checkpoint.md` |
| `docs/archive/memory/2026-05-31/ship-003-s-final-memory.md` | `docs/archive/memory/2026-05-31/ship-003-s-final-memory.md` |
| `docs/archive/memory/2026-05-31/ship-004-s-build-checkpoint.md` | `docs/archive/memory/2026-05-31/ship-004-s-build-checkpoint.md` |
| `docs/archive/memory/2026-05-31/ship-004-s-final-memory.md` | `docs/archive/memory/2026-05-31/ship-004-s-final-memory.md` |
| `docs/archive/memory/2026-05-31/ship-004-s-review-gate-halt.md` | `docs/archive/memory/2026-05-31/ship-004-s-review-gate-halt.md` |
| `docs/archive/memory/2026-05-31/ship-007-s-final-memory.md` | `docs/archive/memory/2026-05-31/ship-007-s-final-memory.md` |
