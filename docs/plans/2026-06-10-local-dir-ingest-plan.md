---
title: Local-directory git-repo ingest with TOC ordering and frontmatter robustness
date: 2026-06-10
status: proposed
goal_feature: tentative — Stage agent assigns the real ID at harvest time
related_decisions:
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
  - docs/decisions/2026-06-09-powerbi-corpus-coverage.md
related_closures:
  - docs/closure/025-S-source-md-frontmatter.md
  - docs/closure/026-S-source-md-second-slice.md
related_stashes:
  - 62E6FAF4  # local-dir fetch source type (the unblocker)
  - 0FC71B03  # frontmatter parser robustness
---

## Operator goal (verbatim)

> "enable full processing of git repo sources of markdown content such
> that I can target a source from the cli and an output directory to
> build a standardized content source for graphtor to consume."

## Problem statement

Today, ingesting a local clone of a Microsoft-Learn-style git repo into
docline requires the operator to either:

1. **Write a `.elt/config/*.sources.yaml` file** with `type: local`,
   `path:`, `include:` — works, but is friction for ad-hoc ingestion of
   newly-cloned repos
2. **Use the test staging harness** at `scripts/study/stage_powerbi_full.py`
   — works, but is a developer script, not a product surface

The Power BI evaluation
(`docs/decisions/2026-06-09-powerbi-corpus-coverage.md`) validated
that the source-MD processing pipeline (023-F shipped via 025-S + 026-S)
produces high-quality graphtor-ready output:

* 100 % per-file output rate, 98.8 % well-formed frontmatter
* 8,001 typed `cross_doc_links` extracted
* 142 s for 1,340 files (9.4 files/sec)

The remaining gaps are **product-shape** and **fidelity-edge-case**:

1. **No single-command CLI** that takes a path and an output dir; the
   workflow is two-step (`fetch` then `process`) and depends on YAML
   config.
2. **TOC.yml ordering is not applied during fetch** — `toc_parser.py`
   exists (shipped in 026-S T4) but its output isn't yet consumed by
   `_fetch_manifest_local` to write a `pages`-ordered crawl-manifest.
3. **16 of 1,340 Power BI files fail frontmatter assembly** because of
   include-fragment YAML with mixed indentation (8 files), DocFx tabbed
   content (4 files), or legitimate H3-before-H2 authoring (4 files).
4. **Cross-product `/path/` links** (e.g. `[text](/fabric/...)` from a
   `powerbi-docs/` file) are not yet extracted as typed graph edges.

## Goals (in this plan)

1. Ship a **one-shot CLI command** `docline ingest local-dir <path>
   --output <dir>` that does fetch + process in a single invocation
   without YAML config
2. **TOC.yml-aware ingest ordering** in `_fetch_manifest_local` so the
   emitted crawl-manifest.json preserves the source-of-truth chunk
   sequence
3. **Frontmatter parser robustness fix** to lift the Power BI baseline
   from 98.8 % to ≥99.5 % (eliminate category B failures: 8 of 16)
4. **End-to-end verification suite** that runs against a small fixture
   repo (always) and the Power BI corpus (opt-in via env var)

## Non-goals (deferred to follow-on shipments)

* DocFx `#tab/` tabbed content handler — stashed as `2C74D31B`
* Cross-product `/path/` absolute-path link extraction — stashed as `8A5D3AC2`
* Multi-repo corpus orchestration — stashed as `4A650FFD`
* OpenAPI / Swagger source type — stashed as `F8E142A1` (epic)
* Azure Document Intelligence pdf_engine — stashed as `F10EB5CB`
* Cloning git repos from URL in this command — `type: git` already exists
  via `ManifestGitSource`; this command is for **already-cloned local trees**
* Auto-discovery of which clones the operator has (single-repo only in v1)

## Current state (grounded in code)

```text
src/docline/elt/
├── manifest_models.py    # ManifestLocalSource (type: local) — REUSE
├── models.py             # SourceConfig discriminated union — EXTEND if needed
├── execute.py            # _fetch_manifest_local — EXTEND to emit crawl-manifest.json
└── orchestrate.py        # execute_elt_fetch entrypoint — REUSE

src/docline/process/
├── output_contract.py    # _parse_md_frontmatter — FIX for mixed-indent YAML
├── toc_parser.py         # parse_toc + merge_toc_files — REUSE
├── docfx_includes.py     # resolve_docfx_includes — REUSE
├── cross_doc_links.py    # extract typed graph edges — REUSE
└── docfx_normalize.py    # :::image::: normalization — REUSE

src/docline/
├── cli.py                # add `ingest` subcommand
├── app.py                # execute_process — REUSE
└── app_models.py         # ProcessRequest — REUSE
```

**Key insight**: 95 % of the implementation already exists. This plan
binds the existing primitives behind a new CLI command and patches two
specific gaps (TOC ordering, frontmatter robustness).

## Proposed solution

### Component A: `docline ingest local-dir` CLI command

A new subcommand that takes a local directory path and an output dir
and runs the full pipeline:

```text
docline ingest local-dir <source-path> --output <output-dir>
        [--include "**/*.md"]    # default
        [--exclude PATTERN]      # repeatable
        [--staging-dir PATH]     # default: tmp dir, cleaned up after
        [--keep-staging]         # debug: don't delete staging
        [--allow-heading-disorder]  # passthrough to process
```

Implementation:

1. Generate a `ManifestLocalSource(type="local", id=<derived>, path=<path>,
   include=<include>)` in memory (no YAML file needed)
2. Wrap it as a `SourcesManifest` and call `execute_elt_fetch` against a
   temp staging dir
3. Immediately call `execute_process` against the staging dir with the
   operator's `--output` path
4. Return success/failure summary (file counts, throughput, failure count)

### Component B: TOC.yml-aware crawl-manifest emission

In `_fetch_manifest_local` (`src/docline/elt/execute.py`):

1. After copying files to `files_dir`, scan for `TOC.yml` / `toc.yml`
2. If found, call `toc_parser.merge_toc_files(toc_paths, base=files_dir)`
   to derive an ordered list of relative paths
3. Build `crawl-manifest.json` `{"pages": [{"path": ..., "order": ...,
   "crawl_order": ...} ...]}` and write to `files_dir.parent / "crawl-manifest.json"`
4. When no TOC.yml present, derive alphabetical ordering as a fallback
5. Files in the staging dir that aren't in any TOC are appended at the
   end in alphabetical order, marked `toc_referenced: false`

### Component C: Frontmatter parser robustness

In `_parse_md_frontmatter` (`src/docline/process/output_contract.py`):

1. Before `yaml.safe_load(yaml_text)`, detect uniform leading-whitespace
   pattern: if EVERY non-blank line starts with the same N spaces (N>0),
   strip those N spaces from each line before parsing
2. On `yaml.YAMLError`, attempt a regex-based key/value extraction fallback
   (capture `^\s*([A-Za-z_][A-Za-z0-9._-]*)\s*:\s*(.+)$` per line) and
   return that as a `Mapping[str, str]`
3. Only return `None` when both attempts fail OR when the input is genuinely
   not frontmatter (no opening `---\n` fence)

### Component D: Verification suite

Two integration test surfaces:

1. **`tests/integration/test_ingest_local_dir.py`** (always runs):
   builds a 5-file fixture repo under `tests/fixtures/local-dir-fixture/`
   with mixed valid + edge-case frontmatter, runs the new CLI, asserts
   on the output shape and counts.
2. **`tests/integration/test_powerbi_corpus_parity.py`** (opt-in via
   `POWERBI_DOCS_ROOT` env var): runs the new CLI on the full Power BI
   corpus, asserts ≥99.5 % frontmatter success, ≥8,000 cross_doc_links,
   wall time ≤300 s. Skipped when env var absent.

## Work decomposition

All tasks scoped to ≤2 hours of human-equivalent effort per Constitution
Principle (Task Granularity). All produce verifiable state change.

### T1 — Implement `docline ingest local-dir` CLI subcommand (~2 h)

**Files**: `src/docline/cli.py`, `src/docline/app.py` (new
`execute_ingest_local_dir` function or equivalent dispatch).

**Pre-conditions**:
* No external changes; reads `ManifestLocalSource` model that exists today

**Acceptance criteria**:
* `docline ingest local-dir <path> --output <dir>` returns exit 0 on a
  fixture with ≥1 .md file
* Without `--keep-staging`, the staging dir is removed after process completes
* `--include` and repeatable `--exclude` flags work and pass through to
  the underlying glob matching
* CLI help text describes the command, defaults, and expected output shape
* `docline --manifest` JSON includes the new subcommand schema

**Tests** (`tests/test_cli_ingest.py`, new):
* Smoke: temp dir with 3 .md files → 3 outputs in --output dir
* `--exclude` excludes the matching file
* Missing source path → exit code != 0 with sensible error message
* `--keep-staging` retains the staging dir; default removes it
* Manifest export includes `ingest local-dir` subcommand

### T2 — TOC.yml-aware crawl-manifest emission (~2 h)

**Files**: `src/docline/elt/execute.py` (`_fetch_manifest_local`),
new helper module if extraction warrants it.

**Pre-conditions**:
* T1 not required; this task is independent
* `toc_parser.merge_toc_files` already shipped in 026-S T4

**Acceptance criteria**:
* When `files_dir` contains any `TOC.yml` / `toc.yml`, the emitted
  `crawl-manifest.json` has `"pages": [...]` in TOC-derived order
* When no TOC.yml is present, alphabetical fallback ordering applied
* Files not referenced by any TOC are appended at the end with
  `"toc_referenced": false`
* Existing behavior preserved when source is non-MD (e.g., PDFs):
  alphabetical fallback only

**Tests** (`tests/elt/test_fetch_manifest_local_toc.py`, new):
* Fixture with TOC.yml referencing 3 of 5 files → manifest has the 3 in
  TOC order, the 2 others appended alphabetically with the flag
* Fixture with nested TOCs → merged ordering correct
* Fixture with no TOC.yml → alphabetical fallback
* Fixture with malformed TOC.yml → fallback to alphabetical + log warning

### T3 — Frontmatter parser robustness (~1.5 h)

**Files**: `src/docline/process/output_contract.py` (`_parse_md_frontmatter`),
possibly extract helpers into a private module if function exceeds 100 lines.

**Pre-conditions**:
* T1, T2 not required; this is the smallest unit, can land first

**Acceptance criteria**:
* `_parse_md_frontmatter` correctly parses YAML where every non-blank
  key line has the same N>0 leading spaces (the Microsoft Learn
  include-fragment pattern)
* On `yaml.YAMLError` after whitespace normalization, falls back to
  regex-based key extraction; returns `Mapping[str, str]`
* When both attempts fail, returns `(None, original_text)` so the
  caller's existing fallback path is preserved
* Clean canonical YAML is unaffected (existing tests in
  `tests/process/test_source_md_frontmatter.py` still pass)

**Tests** (extend `tests/process/test_source_md_frontmatter.py`):
* Leading-space YAML keys → parsed correctly with stripped keys
* Mixed indentation (some keys indented, some not) → regex fallback parses
* Truly malformed YAML (e.g., `: : :`) → returns `(None, text)`
* Three real-world include fragments from
  `E:\Source\powerbi-docs\powerbi-docs\includes\{copilot-notes,yes-paginated,
  yes-report-server}.md` parse successfully
* Bonus regression: outputs from these files now have valid `---\n...\n---`
  frontmatter fences

### T4 — End-to-end CLI smoke + Power BI corpus parity test (~2 h)

**Files**: `tests/integration/test_ingest_local_dir.py` (new),
`tests/integration/test_powerbi_corpus_parity.py` (new),
`tests/fixtures/local-dir-fixture/**` (new fixture).

**Pre-conditions**:
* T1 must be complete (defines the CLI surface under test)
* T2 enhances assertion (ordering check) but T4 still works without it
* T3 enhances assertion (frontmatter success rate) but T4 still works without it

**Acceptance criteria**:
* Fixture-based test always runs in `pytest` and asserts the full
  contract: file counts, frontmatter fields, cross_doc_links shape
* Power BI parity test marked `@pytest.mark.integration`, skips when
  `POWERBI_DOCS_ROOT` env var absent
* When enabled, parity test asserts:
  * ≥99.5 % frontmatter success rate (vs 98.8 % baseline)
  * ≥8,000 cross_doc_links (vs 8,001 baseline; ±5 % tolerance)
  * Wall time ≤300 s on a typical dev machine (vs 142 s baseline; 2× headroom)
  * 100 % per-file output rate
* Fixture lives under `tests/fixtures/local-dir-fixture/`, includes one
  file per category: clean frontmatter, leading-space frontmatter,
  include-with-bracket-include directive, file referenced by TOC.yml,
  file not referenced by TOC.yml

### T5 — User-facing documentation (~1.5 h)

**Files**: `README.md` (or equivalent), `src/docline/cli.py` help text
consistency review.

**Pre-conditions**:
* T1 must be complete (command exists to document)

**Acceptance criteria**:
* README has a new "Ingest a local docs repo" quick-start section
  showing the one-line command and a sample output snippet
* CLI `--help` output is consistent with README examples (no
  inconsistency in flag names or defaults)
* The decision doc
  `docs/decisions/2026-06-09-powerbi-corpus-coverage.md` is amended
  with a "Status update" note pointing to this plan and the resulting
  shipment when known
* Quick-start references the corrected repo URLs from the earlier
  operator Q&A (`MicrosoftDocs/query-docs`, `bi-shared-docs`,
  `fabric-docs`)

## Verification tests of the final product

Beyond per-task acceptance criteria, the **feature is shippable only when
all six end-to-end acceptance criteria pass**:

| AC | Statement | How verified |
|---|---|---|
| **AC1** | Single command ingests a local docs repo | Run `docline ingest local-dir tests/fixtures/local-dir-fixture --output /tmp/out`; exit 0 + ≥1 output file |
| **AC2** | Output preserves source directory structure | Files in `<output>/<job-hash>/<original-relative-path>.md` |
| **AC3** | Output frontmatter is graphtor-compatible | Each output has `chunk_strategy`, `content_sha256`, `doc_type`, `title`, `source_path`, `source`, `docline.source_frontmatter`, `docline.cross_doc_links` keys |
| **AC4** | TOC.yml ordering preserved when present | Fixture with TOC.yml + parity test on Power BI corpus (`paginated-reports/TOC.yml`, etc.) |
| **AC5** | Power BI corpus frontmatter ≥99.5 % | Parity integration test against `E:\Source\powerbi-docs` |
| **AC6** | All four quality gates green | `ruff check .` + `ruff format --check .` + `pyright src/` + `pytest` |

The feature is **NOT shippable** until all six pass. Failures at AC5
when AC1-4 pass mean T3 frontmatter robustness wasn't sufficient and
needs to be extended (or scope reduced).

## Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| TOC ordering edge cases (deeply-nested TOCs, broken refs) | Low | `merge_toc_files` already tolerates missing refs; add a warn-and-fallback path |
| Leading-space YAML parser changes breaking existing tests | Medium | Run full source-MD test suite before/after; AC6 catches |
| Power BI corpus runs > 300 s on slower hardware | Low | Parity test is opt-in; bump ceiling if real-world data warrants |
| Operator's clones diverge from the 1,340-file baseline | Low | Parity test uses thresholds with tolerance, not absolutes |
| New CLI subcommand collides with future "ingest" types (URL, git) | Low | The shape `ingest local-dir` reserves a noun-verb namespace that scales: `ingest local-dir`, `ingest git-url`, `ingest local-files` |
| `_fetch_manifest_local` already used by PDF ingestion — TOC-aware change could regress | Medium | TOC scan only triggers when `*.yml` files present in the source; PDFs unaffected. Regression test added |

## Rollout / rollback

* Single shipment, single PR per task (5 total). Merge order: T3 (smallest,
  isolated) → T1 (CLI surface) → T2 (TOC enhancement) → T4 (tests) → T5 (docs)
* All changes are additive at the public surface (new CLI subcommand,
  new code paths). No deprecation or breaking change to existing commands.
* Rollback: revert the merge commit. The new CLI subcommand simply
  disappears; existing `fetch` + `process` workflows are unaffected
  because they aren't touched.

## Constitution check

* **Principle I (Safety-First Python)**: All new modules carry type hints;
  no bare excepts; custom exceptions via `DoclineError` lineage. ✅
* **Principle II (Test-First)**: Each task lists tests that must be written
  BEFORE implementation (red phase) — verified via harness-architect skill
  during build phase. ✅
* **Principle III (Workspace Isolation)**: All file ops go through
  `safe_workspace_path`; the staging dir is workspace-relative. ✅
* **Principle IV (CLI Containment)**: The new subcommand creates its
  staging dir inside the workspace under `.elt/staging/` or a user-specified
  path; never writes outside the cwd tree without explicit `--output`. ✅
* **Principle V (Structured Observability)**: Use existing `_log` logger;
  emit summary stats at end of run. ✅
* **Principle VI (Single Responsibility)**: No new external deps. Reuses
  `pyyaml` (already present), `pydantic` (already present). ✅
* **Principle VII (Destructive Command Approval)**: No destructive ops;
  `--keep-staging` is opt-in for retention, default cleanup is non-destructive
  (only the auto-created tmp dir, not user data). ✅
* **Principle X (Context Efficiency)**: Output is structured YAML
  frontmatter + markdown body, queryable by markdown-it-py. ✅
* **Principle XI (Merge Commit History)**: Ship pipeline enforces merge
  commits per existing convention. ✅

## Open questions

1. **Command name**: `docline ingest local-dir <path>` vs `docline ingest
   <path>` with auto-detection of source type? Recommend explicit subtype
   for future expansion (git-url, manifest-file).
2. **Default output location**: Should `--output` be required, or default
   to `./output/<job-hash>/`? Recommend required for safety (force
   operator to choose).
3. **Should `ingest` also support pushing to a queue or remote sink?**
   Recommend NO for v1 — keep local-file-write only; remote sinks are a
   separate concern.
4. **Should T2 (TOC ordering) emit the `pages` order as the docline
   process ingest_order field?** Yes — already plumbed via
   `_resolve_ingest_order(next_ingest_order, page_metadata)` in `app.py`,
   so a TOC-derived order will flow naturally into output frontmatter.

## Estimated effort

| Task | Effort | Cumulative |
|---|---|---|
| T1 — CLI subcommand | 2 h | 2 h |
| T2 — TOC-aware crawl-manifest | 2 h | 4 h |
| T3 — Frontmatter robustness | 1.5 h | 5.5 h |
| T4 — Integration tests | 2 h | 7.5 h |
| T5 — Documentation | 1.5 h | 9 h |

Total: **~9 hours of focused work** across 5 right-sized tasks.
Suggested order: T3 → T1 → T2 → T4 → T5 (smallest-first; allows T4 to
verify all preceding work).

## Recommended next steps

1. **Plan review** — invoke the `plan-review` skill to validate
   architectural soundness and scope boundaries before harvest
2. **Harvest** — invoke the `harvest` skill to decompose this plan
   into a feature + 5 backlog tasks under a new shipment
3. **Ship** — invoke the Ship agent to execute the shipment
4. **Verify** — run the verification suite (AC1-AC6) on a clean clone

Operator chooses whether to do this as a single pipeline cycle
(`run pipeline`) or to drive each step explicitly.
