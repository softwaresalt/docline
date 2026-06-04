---
title: "Plan review — 015-S post-G3 hygiene"
plan: "docs/plans/2026-06-04-post-g3-hygiene-plan.md"
shipment: "015-S"
date: 2026-06-04
verdict: APPROVED
personas: [architecture, python, security, scope-boundary, constitution, test-discipline]
---

# Plan review — 015-S post-G3 hygiene

## Verdict: **APPROVED** (0 P0, 0 P1, 1 P2, 2 P3)

## Personas applied

| Persona | Outcome |
|---|---|
| Architecture | ✅ Adding `picture_sink` kwarg to `read_pdf`/`read_pdf_pages` is cleanly additive; routes through to docling only when available. Mirrors the DOCX branch contract from 014-S. |
| Python | ✅ Typed `PictureSink | None` kwarg; no `Any`; defusedxml not needed (docling handles parsing) |
| Security | ✅ Docling picture bytes already go through PictureSink which has the per-source-rooted media directory; no path traversal exposure introduced |
| Scope-boundary | ✅ Stays inside `process/segment.py` + `readers/pdf.py` + `process/output_contract.py`; tests scope is small |
| Constitution | ✅ I/II/VI/X satisfied |
| Test-discipline | ✅ 6 test scenarios named; docling tests skip-gated; CRLF tests use plain string inputs |

## Findings

| ID | Severity | Class | Detail |
|---|---|---|---|
| F1 | P2 | manual | The plan's `_route_docling_pictures` helper is sketched but its docling-2.x picture-iteration API isn't pinned to a specific attribute (`document.pictures` may or may not exist with rendered bytes attached). Implementer (016.003-T) must verify the exact attribute path at implementation time. If docling 2.x exposes pictures via `document.pictures` with `.image` attribute holding PIL Image objects, then PNG serialization is required (use `BytesIO` + `image.save(buf, format="PNG")`). If the attribute name differs, log a warning and skip picture emission rather than raising — the markdown still flows through. |
| F2 | P3 | advisory | The CRLF normalization is so simple (one-line replace at entry) that the dedicated test scenarios may feel over-thorough. Consider consolidating `test_segment_handles_crlf_paragraph_separator` and `test_segment_normalizes_mixed_endings` into a single parametrized test. Implementer's discretion. |
| F3 | P3 | advisory | The plan mentions `do_ocr=True` as out-of-scope. Worth stashing a follow-up if not already tracked — OCR is the most-requested next feature once docling-PDF picture extraction lands. |

## Adoption decision

**APPROVED for harvest** with F1 as an embedded refinement: implementation
(016.003-T) must verify the docling 2.x picture-iteration API and gracefully
skip picture emission (with `_log.warning`) when the expected attribute is
absent.

F2 is stylistic; F3 stashable as a future follow-up.

## Risk profile

| Dimension | Level |
|---|---|
| Blast radius | Low — additive kwargs throughout; existing callers unchanged |
| Reversibility | High — revert merge; outputs regenerate without enhanced docling output |
| Cross-cutting | 3 source files, 2 test files |
| External dependency | None new |
| Operator approval gates | Standard P-014 |

`plan-harden` not required.
