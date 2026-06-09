---
title: Closure — 025-S source-MD YAML frontmatter strip (023-F first slice)
date: 2026-06-09
shipment: 025-S
feature: 023-F
status: verified
merged_pr: 56
merge_sha: 117fef0
branch: feat/025-S-source-md-frontmatter
harvested_stashes: 6A4E8059 (slice 1 of multi-shipment feature)
parent_decisions:
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
  - docs/decisions/2026-06-09-powerbi-source-md-gap-analysis.md
related_closures:
  - docs/closure/023-S-strategy-alignment.md
  - docs/closure/024-S-pass12-helper.md
---

## Readiness status

**READY** — merge complete (PR #56, merge commit `117fef0`).

First slice of multi-shipment feature 023-F (source-MD ingestion
pathway). Closes the gap identified in
`docs/decisions/2026-06-09-powerbi-source-md-gap-analysis.md` row #1:
docline's MD reader did not strip YAML frontmatter, causing every
Microsoft Learn / Hugo / Jekyll / MkDocs / Sphinx / DocFx source MD
file to fail frontmatter assembly with H2-before-H1 errors.

## Scope

Single-task shipment delivering the minimum-viable frontmatter
preservation behavior for source-MD inputs.

## Changes

| Path | Action |
|---|---|
| `src/docline/process/output_contract.py` | MODIFY — new `_parse_md_frontmatter` helper; `OutputDocumentPart.source_frontmatter` field; `.md`/`.txt` branch strips fence + parses YAML |
| `src/docline/app.py` | MODIFY — `execute_process` prefers source `title:` over body-H1 derivation; merges source frontmatter into `docline.source_frontmatter` namespace |
| `tests/process/test_source_md_frontmatter.py` | NEW — 11 tests including end-to-end regression against the PowerBI bug |

## Verification

| Gate | Result |
|---|---|
| pytest (full suite) | **1044 passed / 3 skipped / 0 failed** (was 1034 pre-shipment; +10 net new tests after Copilot follow-up) |
| ruff check / format | clean |
| pyright (touched files) | 0 errors |
| Power BI 10-file smoke test | **ZERO `Failed to build frontmatter` warnings** (was 10/10 failing pre-shipment) |
| CI on PR #56 | all 7 jobs green |

## Adversarial review process

Self-review pre-PR (3 considerations evaluated):

1. `_parse_md_frontmatter` manual fence-finding logic vs `yaml.safe_load_all` — manual approach necessary because `safe_load_all` doesn't naturally handle "frontmatter + non-yaml body"
2. `isinstance(parsed, Mapping)` check protects against YAML scalars / lists / None
3. Multi-part output: `source_frontmatter` attached only to first part (matches existing `media_files` pattern, avoids metadata duplication)

Copilot review post-PR (1 finding, addressed in commit `98c7b74`):

1. `test_parse_md_frontmatter_handles_multiline_yaml_values` docstring claimed to cover "quoted YAML value with `---` inside" but test data only had block scalars — fixed docstring + added `test_parse_md_frontmatter_handles_triple_dash_inside_value` that actually embeds `---` inside quoted YAML values. Confirms fence-finder correctly requires `---` to be on its own line. Thread replied + resolved via `gh api graphql resolveReviewThread`.

## Sample output validation

Input (Microsoft Learn Power BI source MD):
```yaml
---
title: Collect and Submit Diagnostic Information
ms.author: juliacawthra
ms.topic: concept-article
ms.date: 02/17/2026
---
# Collect and submit diagnostic information
...
```

Output (after `docline process`):
```yaml
---
title: "Collect and Submit Diagnostic Information"   # promoted from source
source: "local:powerbi-docs:test:powerbi-test-corpus"
source_path: "fundamentals/desktop-diagnostics.md"
docline:
  source_frontmatter:                                 # full preservation
    title: "Collect and Submit Diagnostic Information"
    ms.author: "juliacawthra"
    ms.topic: "concept-article"
    ms.date: "02/17/2026"
    description: "Learn how to collect..."
    ms.service: "powerbi"
    # ... all source fields preserved
  section_title: "Collect and submit diagnostic information"
  ...
---
<a id="chunk-0001"></a>
# Collect and submit diagnostic information
...
```

## Invariants preserved

| Invariant | Verification |
|---|---|
| `OutputDocumentPart.source_frontmatter` defaults to `None` (backward compat) | `test_output_document_part_source_frontmatter_default_is_none` |
| `OutputDocumentPart` remains a frozen dataclass | `test_output_document_part_is_frozen` |
| `_parse_md_frontmatter` never raises on any input | `test_parse_md_frontmatter_returns_none_on_empty_input`, malformed test |
| Closing `---` on a new line is required for fence detection | `test_parse_md_frontmatter_handles_triple_dash_inside_value` |
| PDF/DOCX/HTML output unchanged | existing 1034 tests pass unchanged |
| `triage_report_only` output unchanged | existing tests pass unchanged |

## Risk

**Low.** Pure additive change to MD/TXT input path. PDF/DOCX/HTML paths
unchanged. `OutputDocumentPart.source_frontmatter` defaults to `None`
so existing tests / callers / consumers see no change. The single
behavioral difference: on MD/TXT input, frontmatter is now stripped
from body (was incorrectly retained as malformed prose) and surfaces
in `docline.source_frontmatter` namespace.

## Deployment / rollback

Merge-only. No service deploy. No data migration. No config push.

Rollback: `git revert -m 1 117fef0` then push. Removes the frontmatter
strip + new field + tests in one commit. Power BI ingestion returns
to its pre-shipment "all 10 files fail frontmatter assembly" state.

## Follow-up — remaining tasks in feature 023-F

The 023-F feature continues across multiple shipments. Pending tasks
(each ~2-3 hour scope per Constitution task granularity, to be
captured as new task IDs when ready to ship):

1. DocFx `:::image type="content" source="..." alt-text="..." :::`
   container parser (extract alt-text into graphable form)
2. `[!INCLUDE [name](path.md)]` directive resolution (recursive
   include expansion)
3. TOC.yml parser for topological ingest order
4. Cross-doc `[text](other.md)` link resolution → graph-edge metadata
5. `:::moniker range="..." :::` zone-pivot handling
6. Source provenance: `docline.source_type`, `docline.source_repo`,
   `docline.source_commit` fields in manifest
7. Incremental sync via prior-manifest diff

## Operator-facing impact

**Immediate**: `docline process` now correctly handles any source-MD
corpus with YAML frontmatter (Power BI, Azure SQL, AWS docs,
Kubernetes website, React docs, Python docs, OSS libraries with
docs/ trees, MkDocs / Hugo / Jekyll / Sphinx-flavored sources).

**For the Power BI corpus specifically**: the 1,340-file repo at
`E:\Source\powerbi-docs\powerbi-docs` is now ingestible without
frontmatter assembly failures. Operator can verify on a larger
sample by extending `scripts/study/stage_powerbi_test.py` or by
staging the full corpus through the standard fetch-then-process
flow (when the local-folder fetch source is added in a future task).

## Recommendation

**READY** — first slice landed cleanly. Power BI and analogous corpora
are unblocked at the basic frontmatter level. Next slices in 023-F
(DocFx parsing, TOC.yml ordering, include resolution, cross-doc link
resolution) deliver progressively richer ingestion fidelity but are
not blockers for the current corpus class.
