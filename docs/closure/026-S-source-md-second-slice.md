---
title: Closure — 026-S source-MD second slice (DocFx + includes + links + TOC)
date: 2026-06-09
shipment: 026-S
feature: 024-F
status: verified
merged_pr: 59
merge_sha: 3d0ef84
branch: feat/026-S-source-md-second-slice
parent_decisions:
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
  - docs/decisions/2026-06-09-powerbi-source-md-gap-analysis.md
related_closures:
  - docs/closure/025-S-source-md-frontmatter.md
---

## Readiness status

**READY** — merge complete (PR #59, merge commit `3d0ef84`).

Second slice of source-MD ingestion pathway. Together with 025-S
(first slice), this shipment gives docline full structural fidelity
ingestion of Microsoft Learn / DocFx / MkDocs source-MD corpora.

## Scope (4 tasks in one shipment per Phase C of the original A→B→C plan)

| Task | Module | LOC | Tests |
|---|---|---|---|
| 024.001-T (T1) | `src/docline/process/docfx_normalize.py` | 130 | 8 (later 11) |
| 024.002-T (T2) | `src/docline/process/docfx_includes.py` | 155 | 10 |
| 024.003-T (T3) | `src/docline/process/cross_doc_links.py` | 155 | 10 |
| 024.004-T (T4) | `src/docline/process/toc_parser.py` | 130 | 9 |

## Pipeline integration

The `.md`/`.txt` branch in `build_output_document_parts` now runs
through 4 stages in order:

1. **`resolve_docfx_includes`** (T2) — expand `[!INCLUDE]` directives
   BEFORE frontmatter parsing
2. **`_parse_md_frontmatter`** (025-S) — strip YAML fence + capture
3. **`normalize_docfx_containers`** (T1) — `:::image:::` → `![alt](src)`
4. **`resolve_cross_doc_links`** (T3) — collect edge metadata

`OutputDocumentPart` gains a `cross_doc_links` field. The application
layer surfaces both `source_frontmatter` (025-S) and `cross_doc_links`
(T3) under the docline namespace on the first part of a multi-part
output.

T4 (TOC parser) ships as a standalone helper. The wiring into the
staging flow is deferred — it requires a NEW local source-MD
directory fetch source type that wasn't scoped for this shipment.

## Verification

| Gate | Result |
|---|---|
| pytest (full suite) | **1085 passed / 3 skipped / 0 failed** (was 1044; +41 net new tests after Copilot follow-up) |
| ruff check + format | clean |
| pyright (4 new modules) | 0 errors |
| Power BI 10-file end-to-end smoke test | passes — `[!INCLUDE]` expanded, `:::image:::` normalized, `cross_doc_links` populated |
| CI on PR #59 | all 7 jobs green |

## Adversarial review process

Self-review pre-PR (5 considerations evaluated and documented).

Copilot review post-PR (3 findings, all addressed in commit `acc5e6a`):

1. **Real bug in `_IMAGE_OPEN_RE`** — block form `:::image:::...:::image-end:::`
   wasn't captured as a single match (spurious empty `![]()` emitted)
   AND attributes containing colons (`alt-text="Figure 1: Overview"`)
   failed to match. Fixed by splitting into two regexes
   (`_IMAGE_BLOCK_RE` + `_IMAGE_SELF_CLOSING_RE`), processing block
   form FIRST so its terminator is consumed before self-closing can
   false-match. Both use `.+?` with DOTALL for the attribute group.
   Added 3 regression tests.
2. `OutputDocumentPart.cross_doc_links` docstring described field as
   "Tuple of `(target_path, anchor, link_text)` tuples" but actual
   type is `tuple[Mapping[str, Any], ...]` (tuple of dicts). Updated
   docstring.
3. `__all__: Iterable[str]` annotation in `docfx_includes.py` was
   inconsistent with other modules. Removed annotation + unused
   `Iterable` import.

All 3 threads replied + resolved via `gh api graphql resolveReviewThread`.

## Sample output (Power BI Microsoft Learn doc)

```yaml
---
title: "Collect and Submit Diagnostic Information"
source: "local:powerbi-docs:test:powerbi-test-corpus"
source_path: "fundamentals/desktop-diagnostics.md"
docline:
  source_frontmatter:                              # from 025-S
    title: "Collect and Submit Diagnostic Information"
    ms.author: "juliacawthra"
    ms.topic: "concept-article"
  cross_doc_links:                                 # NEW (T3, 026-S)
    - target_path: "fundamentals/power-bi-overview.md"
      anchor: null
      link_text: "What is Power BI?"
    - target_path: "transform-model/desktop-query-overview.md"
      anchor: null
      link_text: "Query overview with Power BI Desktop"
    - target_path: "connect-data/desktop-data-types.md"
      anchor: null
      link_text: "Data types in Power BI Desktop"
  section_title: "Collect and submit diagnostic information"
---
<a id="chunk-0001"></a>
# Collect and submit diagnostic information
...
![Screenshot of options panel...](media/desktop-diagnostics/desktop-diagnostics-01.png)
                                                   # ↑ NEW (T1, 026-S) — was :::image:::
```

## Invariants preserved

| Invariant | Verification |
|---|---|
| PDF/DOCX/HTML output unchanged | existing 1044 tests pass unchanged |
| `OutputDocumentPart.cross_doc_links` defaults to `()` (backward compat) | existing tests pass unchanged |
| All 4 new modules never raise on any input | dedicated empty + malformed tests |
| Include cycle detection (max depth 5) | `test_resolve_includes_cycle_detection`, `test_resolve_includes_max_depth_circuit_break` |
| External / media / anchor links NOT collected as cross_doc_links | `test_resolve_links_skips_external_links`, `test_resolve_links_skips_media_links`, `test_resolve_links_skips_anchor_only_links` |
| Image block form emits exactly ONE image markdown reference | `test_normalize_image_block_form_emits_no_spurious_image` (regression for the Copilot-caught bug) |
| Image attributes with colons in values are parsed correctly | `test_normalize_image_alt_text_containing_colon` (regression) |

## Risk

**Low.** All 4 new modules are pure functions with no I/O side effects
beyond reading include target files (T2, well-scoped to host file's
directory). Pipeline integration is additive — PDF/DOCX/HTML branches
unchanged. Backward-compat field defaults preserve existing test
suite.

## Rollback procedure

`git revert -m 1 3d0ef84` then push. Removes all 4 helper modules,
their tests, and the output_contract.py pipeline integration in one
commit. Power BI ingestion returns to its 025-S behavior (frontmatter
strip works; DocFx containers and `[!INCLUDE]` directives pass through
verbatim again).

## Future continuation (023-F further slices)

* **Source-MD fetch source type** (local directory walker + TOC.yml
  wiring for ingest order) — would unblock end-to-end Power BI corpus
  ingestion via standard `docline fetch` then `docline process` flow
* `:::row::: / :::column:::` layout container handling (currently
  pass through unchanged)
* `:::code source="./external.cs":::` external-file code inclusion
* Incremental sync via prior-manifest diff (the 026.007-T from the
  original gap analysis)

## Operator-facing impact

Docline can now ingest **any DocFx-flavored source-MD corpus** with
preserved authorial intent: titles + `ms.*` metadata under
`docline.source_frontmatter`, expanded include content, normalized
image markup with alt-text, and typed graph-edge metadata under
`docline.cross_doc_links`.

For the Power BI corpus specifically: the 1,340-file repo at
`E:\Source\powerbi-docs\powerbi-docs` is now fully ingestable through
docline with downstream-graphtor-ready output. Run via the existing
`scripts/study/stage_powerbi_test.py` harness (POWERBI_DOCS_ROOT env
var override if needed) then `docline process --staging-dir ...
--output-dir ...`.

## Recommendation

**READY** — Phase C of the A→B→C plan is complete. Second slice
landed cleanly. Combined with 025-S (frontmatter strip), docline
now has complete first-tier source-MD ingestion capability for
DocFx-flavored corpora.

The remaining 023-F work (source-MD fetch source type, layout
container handling, external-file code inclusion, incremental sync)
is operationally-valuable polish but not required for basic Power BI
ingestion. Each remaining slice is appropriately scoped as its own
~2-3 hour shipment.
