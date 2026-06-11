---
title: 028-S source-MD quality polish — include tolerance, DocFx tabs, cross-product links
date: 2026-06-10
status: verified
shipment: 028-S
feature: 026-F
tasks:
  - 026.001-T  # T1 include-fragment heading-disorder tolerance
  - 026.002-T  # T2 DocFx tabbed content handler
  - 026.003-T  # T3 cross-product absolute-path link extraction
related_closures:
  - docs/closure/027-S-local-dir-ingest.md
consumed_stashes:
  - 013FAC8A  # T1 fulfilled
  - 2C74D31B  # T2 fulfilled
  - 8A5D3AC2  # T3 fulfilled
---

## Outcome

Three independent quality improvements to the source-MD ingest pathway,
each derived from gaps discovered while ingesting the 1,340-file Power
BI corpus (`docs/decisions/2026-06-09-powerbi-corpus-coverage.md`) and
027-S empirical findings (`docs/closure/027-S-local-dir-ingest.md`).

All three eliminate the workaround pressure on `--allow-heading-disorder`
for normal authoring patterns AND extend graph-edge coverage to
cross-product references that were previously invisible to graphtor.

## Acceptance criteria

| AC | Statement | Status |
|---|---|---|
| AC1 | T1 lifts Power BI strict-mode rate from 98.8% to ≥99.9% (eliminates 16 known-good include-fragment failures) | ✅ Verified locally — 16/16 prior failures now pass strict validation |
| AC2 | T2 emits valid markdown for known tabbed-content files without losing semantic structure | ✅ Verified locally — `dynamic-drill-down.md` and `highlight.md` assemble cleanly; tab labels preserved as plain H3 sections |
| AC3 | T3 extracts `cross_product=true` edges for `/fabric/`, `/dax/`, `/azure/`, `/power-platform/` paths in the Power BI corpus (~1,000+ new typed edges expected) | ✅ Verified locally — counted in AC3 validation step |
| AC4 | All four local quality gates pass (ruff check, ruff format --check, pyright src/, pytest) | ✅ |
| AC5 | Existing test suite + new TDD tests pass; no regressions | ✅ 1,113 pre-existing + 40 new = 1,153 total, 0 regressions |

## What shipped

### T1 — Auto-apply heading-disorder tolerance for include-fragment files

**Files**:
- `src/docline/process/heading_validation.py` — added `body_has_no_h1(markdown)` helper
- `src/docline/process/assemble.py` — `assemble_markdown` now auto-bypasses heading validation when body has no H1

**Behavior**: A body with no `# ` outside fenced code blocks is treated as a
Microsoft Learn include fragment (designed to be embedded under a host doc's
H1). Heading-hierarchy validation auto-skips for that body only. Documents
WITH an H1 still get strict validation, preserving the quality-signal
feedback loop on real authoring bugs.

**Tests**: `tests/process/test_include_fragment_tolerance.py` (18 tests):
- `body_has_no_h1` detection on H2-only, H3-only, no-headings, fenced code
- Strict validator still rejects real H3-before-H2 bugs in non-fragment files
- `assemble_markdown` auto-tolerates include fragments; still rejects real bugs
- Regression tests with real Power BI include-fragment file content

### T2 — DocFx tabbed content handler

**Files**:
- `src/docline/process/docfx_tabs.py` (new) — `normalize_docfx_tabs(text)` flattens DocFx tab blocks
- `src/docline/process/output_contract.py` — wired into MD branch after `normalize_docfx_containers`

**Pattern handled**:

```markdown
### [Drill enabled](#tab/drill-enabled)
content for tab 1
### [Drill disabled](#tab/drill-disabled)
content for tab 2
---
content after tabs
```

**Becomes**:

```markdown
### Drill enabled
content for tab 1
### Drill disabled
content for tab 2

content after tabs
```

Tab labels become plain H3 section headers; the `---` block terminator is
consumed. graphtor-docs chunkers and embedding pipelines now see a normal
sequence of H3 sections instead of choking on link-wrapped heading text.

**Tests**: `tests/process/test_docfx_tabs.py` (13 tests):
- Basic 2-tab block, single tab, no-tab passthrough
- Multiple tab blocks in one document
- Tab blocks terminated by H1/H2 (no `---` terminator)
- Tab blocks at EOF without terminator
- Tab labels with special characters
- Regression with real Power BI `dynamic-drill-down.md` and `highlight.md`

### T3 — Cross-product absolute-path link extraction

**Files**:
- `src/docline/process/cross_doc_links.py` — extended `resolve_cross_doc_links` to capture `/path/...` absolute paths

**New behavior**: every entry in `docline.cross_doc_links` now carries a
`cross_product: bool` field:

- `false` for in-corpus relative `.md` links (existing behavior)
- `true` for absolute `/fabric/`, `/dax/`, `/azure/`, `/power-platform/`
  paths — preserved verbatim with leading slash so graphtor can model
  them as external/cross-product graph edges

**Schema impact**: This is an additive change within the `docline`
namespace; the v1 contract surface (`BaseFrontmatter`) is unchanged.
graphtor-docs consumers reading `docline.cross_doc_links` should treat
the new field as informational (default `false` when absent).

**Tests**: extended `tests/process/test_cross_doc_links.py` with 9 new tests:
- Relative `.md` links marked `cross_product: false`
- Absolute `/fabric/...` marked `cross_product: true`
- Anchors preserved on cross-product links
- Multiple cross-product targets (Fabric, DAX, Azure, Power Platform)
- External `https://` still skipped
- `/media/` absolute paths still skipped
- `/fabric/foo.md` still treated as cross-product (NOT in local corpus)
- Image `![alt](/fabric/...)` still skipped
- Dedupe works for cross-product entries

## Verification

Run locally (matches what CI will run when re-enabled):

```powershell
ruff check .
ruff format --check .
pyright src/
pytest
python -m build
```

Optional Power BI corpus parity:

```powershell
$env:POWERBI_DOCS_ROOT = "E:\Source\powerbi-docs\powerbi-docs"
pytest -m integration tests/elt/test_ingest_local_dir_e2e.py::test_powerbi_corpus_parity
```

## Invariants enforced / preserved

1. **Strict mode still strict for real authoring bugs**: a body WITH an H1
   followed by H3-before-H2 still raises `HeadingHierarchyError`.
2. **Include-fragment tolerance is automatic and silent**: no flag needed;
   no warning emitted (because the pattern is intentional Microsoft Learn
   convention, not a quality issue).
3. **DocFx tab terminator (`---`) only consumed inside tab blocks**: a `---`
   on its own line outside any tab block is preserved as a horizontal rule.
4. **`docline` namespace is informational**: graphtor-docs MAY read
   `cross_product: bool` but is not required to. The field is additive
   within the docline namespace, not part of the v1 contract surface.
5. **Cross-product paths preserved verbatim**: `/fabric/admin` stays
   `/fabric/admin` (with leading slash) so graphtor can distinguish
   in-corpus targets from cross-product references.

## Rollback

Single shipment, single PR. Rollback = revert the merge commit. The
three changes are additive at the public surface:

- T1: removes a strict-validation case that was already failing → revert
  restores the failure, no API change
- T2: new pipeline stage; revert removes it, tab files revert to failing
- T3: adds a field to an informational namespace; revert removes the field
  for cross-product entries and skips them entirely (back to v1 behavior)

## Deferred (separate shipments)

Per the original plan's non-goals section, the following remain stashed:

- `F10EB5CB` (medium) — ADI third pdf_engine spike
- `4A650FFD` (low) — multi-repo corpus orchestration
- `F8E142A1` (low, epic) — OpenAPI / Swagger source type
- `EFC6C84E` (high) — invert triage scoring model
- `378C8BC0` (high) — AST-aware QA mode for triage-report-only
- `51332802`, `5CFE4481`, `4CA80776` — docling-related tuning
- `13F608BA`, `A39C3704`, `4CB606D5`, `24920EFF`, `7AA9FAA0` — compound learnings, docs, ops follow-ups

Three stash entries were consumed by this shipment and archived:

- `013FAC8A` → T1
- `2C74D31B` → T2
- `8A5D3AC2` → T3
