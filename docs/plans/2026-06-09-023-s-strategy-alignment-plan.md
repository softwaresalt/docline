---
title: Implementation plan — 023-S strategy alignment (AST metrics + doc updates)
date: 2026-06-09
shipment: 023-S
feature: 023-F
status: planned
related_decisions:
  - docs/decisions/2026-06-08-extraction-strategy-study.md
  - docs/decisions/2026-06-08-source-md-ingestion-extension.md
related_closures:
  - docs/closure/021-S-triage-then-repair.md
  - docs/closure/022-S-pa4-closure.md
harvested_stashes:
  - 13F608BA
  - 378C8BC0
  - A39C3704
archived_stashes:
  - 5A622B72
---

## Scope

Lock in the 2026-06-08 extraction-study findings as durable institutional
knowledge and surface goal-aligned (AST-aware) metrics in docline's
triage-report-only calibration mode. Update operator-facing docs so the
new default-mode guidance is official.

**Out of scope** (future shipments):

* Scoring-model inversion → 024-S (`EFC6C84E`)
* Source-MD ingestion pathway → 026-F multi-shipment (`6A4E8059`)
* Docling speedup → 025-S (`51332802`)
* Generalization study → research spike (`4CB606D5`)

## Decomposition

4 tasks under feature `023-F`. Estimated total effort: 7-10 hours.

### T1 — Compound learning capture (stash `13F608BA`)

**Type**: docs only
**Effort**: 1-2 h

Create `docs/compound/2026-06-08-ast-fidelity-metrics.md` capturing the
durable lesson:

* **The lesson**: char count is not a fidelity metric for AST-aware
  consumers (graph DBs, vector embeddings, LLMs). Structural density
  (per-1k chars), section count, heading count, table cell count
  are the right metrics.
* **The evidence**: 2026-06-08 study findings (14/15 ranges,
  per-engine averages, 1487-1490 case study showing identical char
  counts but 18× structural density difference).
* **When to apply**: any time the question "is this extraction
  output good enough?" is being asked. Default to AST metrics; only
  fall back to char counts when no AST parser is available.
* **Decision rule**: a markdown extraction has reached "acceptable
  quality" when structural density ≥ 5 per 1k chars OR section count
  ≥ 30 per 50 KB content, whichever is achievable for the source
  material.

**Acceptance criteria**:

* New file `docs/compound/2026-06-08-ast-fidelity-metrics.md` (≥ 80 lines)
* Cites `docs/decisions/2026-06-08-extraction-strategy-study.md` as primary
* Frontmatter includes `applies_to`, `evidence`, `supersedes` fields
* Links to relevant test/script references

### T2 — Production `quality_metrics` module (stash `378C8BC0`)

**Type**: library code + tests
**Effort**: 3-4 h

Promote `scripts/study/evaluate_markdown.py` (research prototype) to
`src/docline/process/quality_metrics.py` (production module).

**Module surface**:

```python
@dataclass(frozen=True)
class QualityMetrics:
    """AST-aware quality metrics for extracted markdown.

    Computed via markdown-it-py parsing. See
    docs/compound/2026-06-08-ast-fidelity-metrics.md for the decision
    rule and rationale.
    """
    parse_ok: bool
    char_len: int
    token_count: int
    heading_count: int
    heading_depth_max: int
    list_item_count: int
    code_block_count: int
    table_count: int
    table_cell_count: int
    section_count: int
    median_section_chars: int
    structural_density_per_1k: float


def compute_quality_metrics(text: str) -> QualityMetrics:
    """Parse markdown with markdown-it-py and compute AST-aware quality metrics.

    Args:
        text: Markdown source. Empty string returns an all-zero
            QualityMetrics with parse_ok=True.

    Returns:
        QualityMetrics dataclass with 12 computed fields.

    Raises:
        Never raises on malformed input — instead sets parse_ok=False
        and returns best-effort metrics derived from raw text.
    """
```

**Design constraints**:

* Use `markdown_it` (already a direct runtime dep: `markdown-it-py>=4,<5`
  in `pyproject.toml`; installed at v4.2.0)
* Frozen dataclass for output (Constitution principle on immutability)
* No side effects (no file I/O, no logging)
* Google-style docstrings on public members
* Accept optional `md_parser: MarkdownIt | None = None` parameter so
  callers can inject a configured parser; default constructs a
  commonmark+tables parser internally
* Test surface: 12+ tests covering: empty input, plain prose,
  headings-only, tables, code blocks, malformed markdown, all
  metrics individually

**Acceptance criteria**:

* New module `src/docline/process/quality_metrics.py` with
  `QualityMetrics` + `compute_quality_metrics` public symbols
* `tests/process/test_quality_metrics.py` with ≥ 12 tests, all passing
* ruff check + format clean
* Public symbols re-exported from `docline.process` namespace
* `scripts/study/evaluate_markdown.py` updated to import from
  production module (single source of truth)
* `markdown-it-py` already in `pyproject.toml` — no dep change needed

### T3 — `triage_report_only` integration (stash `378C8BC0` continued)

**Type**: library integration + tests
**Effort**: 1-2 h

Wire the production `QualityMetrics` into `triage_report_only` so the
per-page TSV emitted in calibration mode includes AST-aware quality
columns alongside the existing 8 fidelity signal scores.

**Changes**:

* `src/docline/process/pdf_triage.py::triage_report_only`: after
  computing per-page heuristic text, compute `QualityMetrics` per page
  via `compute_quality_metrics`. Emit the following additional TSV
  columns: `qm_parse_ok`, `qm_heading_count`, `qm_section_count`,
  `qm_table_count`, `qm_table_cell_count`, `qm_structural_density_per_1k`,
  `qm_median_section_chars`. Keep existing columns unchanged for
  backward compatibility.
* `src/docline/process/pdf_triage.py::TriageReport` (if dataclass) or
  the JSON-mode emission: add a top-level `quality_metrics_summary`
  block with mean/median of each AST metric across all pages.

**Acceptance criteria**:

* Existing `triage_report_only` tests still pass unchanged
* New test asserting TSV has the new 7 columns
* New test asserting JSON output (if applicable) has
  `quality_metrics_summary` block
* No change to default-mode `process_pdf_triaged` behavior
* No new CLI flags required (the metrics are emitted unconditionally
  in `--triage-report-only` mode since the cost is negligible)

### T4 — Documentation alignment (stash `A39C3704` + folded `5A622B72`)

**Type**: docs only
**Effort**: 1-2 h

Three doc updates landing the new strategic direction in
operator-facing material:

1. **README.md**: add section "Choosing PDF processing mode" or
   similar — explain `--pdf-mode auto` (default, all-docling, best
   AST quality for technical reference PDFs) vs `--pdf-mode triage`
   (heuristic + selective docling, best for prose-dominated corpora).
   Cite the study decision.

2. **docs/ARCHITECTURE.md**: update PDF pipeline section to reflect
   docling-primary direction and reference the triage pattern as
   an opt-in optimization for specific corpus classes.

3. **docs/closure/021-S-triage-then-repair.md**: update PA4
   resolution path section to note the 2026-06-08 study reversal:
   triage is opt-in for prose corpora, not the default for technical
   PDFs. Add explicit pointer to 023-S as the strategic-alignment
   shipment. **Do NOT transition status to `production-ready`** —
   leave at `verified` since the underlying triage architecture
   remains valid for its narrower scope; production-ready status
   gets reconsidered after 024-S (scoring inversion) and/or 026-F
   (source-MD) land.

4. **docs/ARCHITECTURE.md or new section in 021-S closure**:
   document that triage output preserves splice + baseline PDFs
   under `output_dir/splices/` (this is the existing behavior;
   was previously implicit and led to stash `5A622B72` being
   captured as a false-premise feature request).

**Acceptance criteria**:

* README.md has a "PDF processing modes" section
* ARCHITECTURE.md reflects docling-primary direction
* 021-S closure annotated with 2026-06-08 study reversal
* Splice-artifact preservation behavior documented somewhere visible
* No source code changes
* Cross-references to relevant decision docs valid

## Sequencing and dependencies

```
T1 (compound learning) ──┐
                         │
T2 (quality_metrics) ────┼──► T3 (triage_report_only integration) ──► T4 (doc updates)
                         │
                         └──► T4 (cites T1 + T2)
```

T1 and T2 are independent. T3 depends on T2 (uses the new module).
T4 cites T1, T2, and T3. All 4 tasks land in a single PR.

## Risk assessment

**Low.** T2 is the only task that introduces code; the implementation
is well-scoped (pure parsing + dataclass output, no I/O, no state).
The reference implementation in `scripts/study/evaluate_markdown.py`
already works end-to-end on real data (verified during the study run).

## Invariants to preserve

| Invariant | Verification |
|---|---|
| `markdown_it` is declared in `pyproject.toml` runtime deps (was previously transitive only) | uv sync --locked succeeds; CI install step passes |
| `QualityMetrics` is immutable (frozen dataclass) | test asserts `FrozenInstanceError` on mutation attempt |
| `compute_quality_metrics("")` returns valid QualityMetrics with `parse_ok=True` | dedicated test |
| `compute_quality_metrics` on malformed input returns `parse_ok=False` without raising | dedicated test |
| Public symbols exported from `docline.process` | `from docline.process import compute_quality_metrics, QualityMetrics` succeeds |
| No behavioral change to existing `process_pdf_triaged` or `triage_report_only` | existing test suite passes unchanged |

## Verification plan

1. T2 unit tests: 12+ tests covering all edge cases
2. T2 lint + format + pyright clean
3. Full pytest suite green (no regressions)
4. T1 + T3 markdown lint (if any) — confirm format conformance
5. Manual smoke: import `QualityMetrics` from `docline.process`
   namespace and compute on a small markdown sample

## Open questions

None. Scope is bounded; reference implementation exists; decision is
explicit.

## Rollback plan

T1 + T3 are documentation only — revert is trivial. T2 introduces a
new module with no callers (intentionally — integration into
`triage_report_only` would be a follow-on shipment); revert removes
the module without affecting any existing code path.

## Plan-review notes

(To be filled in by plan-review skill before harvest.)
