---
type: compacted-summary
scope: memory
period: 2026-06
compacted_at: 2026-08-29
source_count: 18
---

## Overview

June 2026 memory spans CLI/MCP parity, packaging and quarantine tooling, ELT multi-source ingestion, docline-graphtor contract alignment, CI workflow creation, heading-aware segmentation, frontmatter referentiality, docling sidecars, extraction-strategy research, PA3/PA4 triage evidence, overnight autonomous shipments, and the later OCR OOM containment fix. The month also captured the major 2026-06-04 load-test OOM RCA, which reframed docling large-PDF work around resource probes, splitting, subprocess isolation, and operator-run load tests.

## Key Decisions

* `005-S` CLI and MCP parity
  * Merged with explicit operator-approved stale-review admin override after all Copilot threads were resolved and fresh review could not be requested
  * Kept backlog archival and documentation isolated on `post-merge/005-cli-mcp-parity`
* `006-S` packaging and quarantine tooling
  * Kept quarantine viewer file-local instead of adding a loopback server
  * Enforced workspace containment for both artifact input and viewer output
  * Reused the existing CLI manifest path for `python -m docline` package entrypoint
* `008-S` ELT multi-source ingestion
  * Grouped `.elt/config` and multi-source stash entries into one feature because they shared staging-directory and orchestration concepts
  * Left Copilot review requestability as unrelated infrastructure work
  * Fixed job-key collisions by including behavior-affecting fields (`depth`, `max_pages`, `path_glob`) in source keys
  * Accepted temporary MCP/manifest divergence because MCP adapter changes were explicitly out of scope
* `010-S` docline-graphtor alignment
  * Split a 39-task shipment over multiple sessions because the 20-task session circuit breaker required it
  * Carried strict-safety records through closure as release evidence, not only implementation review evidence
  * Used static and interface-level verification when Windows `tmp_path` noise blocked full local runtime proof
  * Identified release tags as the next contract-pinning gap for downstream consumers
* `011-S` CI workflow
  * Adopted Linux-only CI to bypass known Windows `tmp_path` noise
  * Used a real CI probe and fixed dependency drift that local globally-installed tools had masked (`defusedxml` and missing dev dependency group)
  * Resolved Copilot threads and passed §1.9 readiness before operator-approved merge
* `012-S` heading-aware segmentation
  * Scoped G3a separately; held G3b referentiality and G3c docling sidecars for later cycles
  * Enabled MarkdownIt table support so GFM tables remain block-level tokens
  * Updated PDF regression expectations: flat pypdf text now emits one segment until docling provides headings
  * Deferred CRLF normalization in `_char_bin` because current extractors emit `\n`
* `013-S` / G3b referentiality
  * Put `section_title` on `OutputDocumentPart` rather than changing `segment_markdown` return shape
  * Applied `extract_section_title` across all body inputs, including HTML
  * Preserved existing `docline:` namespace keys by merging rather than overwriting
  * Deferred graphtor-docs schema snapshot refresh to a cross-repo operator task
* `014-S` / G3c docling sidecars
  * Kept reader-level PDF defaults at `heuristic` for backward compatibility; production uses `auto`
  * Made `auto` silently fall back to heuristic on docling `PdfReadError`
  * Stored `OutputDocumentPart.media_files` as immutable tuples and serialized lists in manifests
  * Put media files only on the first output part to avoid duplication
  * Forced multipart layout when media is present so relative sidecar image links resolve
* 2026-06-04 OOM RCA
  * Determined the reboot came from Windows paging collapse caused by docling `rt_detr-l4` processing a 109.5 MB cosmos PDF alongside the Copilot CLI, not from H1 synthetic header generation or any local SLM
  * Pivoted from detect-OOM-and-fallback to split-and-throttle-so-OOM-cannot-happen
  * Recommended a runtime resource probe, size/page gates, PDF splitting, broader fallback exceptions, thread caps, subprocess-isolated docling chunks, and operator-run load tests outside the agent process
  * Rejected GPU acceleration on the current GTX 770M host because compute capability, driver, and VRAM are insufficient
* 2026-06-08 extraction strategy
  * Found docling wins 14/15 sampled ranges on AST-aware metrics for graph, embedding, and LLM use cases
  * Reversed the interim pypdf/markitdown mitigation idea: char-count delta was the wrong fidelity lens; future PA4 work should optimize structure and cost, not only flag-rate bands
* `023-S` and `024-S` overnight shipments
  * Added AST-aware `QualityMetrics` and `triage_report_only` `qm_*` columns, then refactored the scoring pass helper without behavior change
  * Used adversarial self-review before PRs; this caught dead code, exception handling, missing tests, repeated parser construction, and YAML mutation hazards
* `038-F` / `041-S` OCR OOM fix
  * Decided conditional OCR gating was already correct; the real defect was page-count grouping ignoring OCR bitmap memory and allowing one OCR crash to kill the whole batch
  * Added OCR-aware grouping, an 8-page OCR batch cap, and adaptive group halving retry before fallback to heuristic

## Files & Areas Modified

* Packaging and CLI: `pyproject.toml`, `src/docline/cli.py`, `src/docline/__main__.py`, package entrypoint wiring, quarantine viewer CLI
* ELT ingestion: `src/docline/elt/paths.py`, `models.py`, `config.py`, `orchestrate.py`, `execute.py`, `manifest_models.py`, `source_keys.py`; tests under `tests/elt/`
* CI: `.github/workflows/ci.yml`, dependency lock/dev group surfaces, closure docs for CI workflow
* Process and output contracts: `src/docline/process/segment.py`, `output_contract.py`, frontmatter referentiality, quality metrics, PDF triage/scoring helpers
* Reader/PDF surfaces: docling PDF reader, sidecar PictureSink, DOCX media walk, PDF engine wiring, pdfminer warning suppression
* Runtime safety and OCR batching: `src/docline/process/page_range.py`, `batch_dispatch.py`, `pdf_triage.py`, `pdf_batch.py`, `fidelity_scorer.py`
* Study and decision artifacts: extraction comparison scripts under `scripts/study/`, extraction-strategy decision and roadmap, OOM RCA, closure records, compound-learning candidates, backlog stashes
* Backlog and archive surfaces: features and shipments `005-S`, `006-S`, `008-S`, `010-S`, `011-S`, `012-S`, `013-S`, `014-S`, `023-S`, `024-S`, and `041-S`

## Key Learnings

* CI probes reveal dependency-state drift that local gates may hide because globally installed tools and packages mask missing lockfile entries
* Linux-only CI was a deliberate, effective way to avoid known Windows `tmp_path` cleanup noise while preserving project gates
* Backlog lifecycle drift is recoverable by restoring the queue artifact from `HEAD`, then rerunning `move`, `track-commit`, and archive operations in order
* Programmatic Copilot review re-request may return success but fail to trigger when Copilot already reviewed an older SHA; operator UI re-request is the reliable unstick path
* Baseline-engine swaps and added scoring signals require empirical recalibration; per-signal correctness does not guarantee aggregate score behavior
* Char count is the wrong quality metric for graph and RAG consumers; structural density, section counts, table preservation, and natural chunk boundaries matter more
* Extending Pydantic-populated namespace dictionaries must merge with existing content; overwriting silently discards source metadata
* Large docling workloads should not run inside an agent session; split documents, isolate worker processes, cap threads, and run full-corpus tests from a plain shell
* Stash harvesting should either use `backlogit harvest` or explicitly archive source stashes after direct item creation to avoid dangling active stash entries
* Regex-based YAML mutation is risky; matching `id:` accidentally caught `parent_id:` and produced duplicate commit keys
* Hoist Markdown parsers in tight per-page loops; per-page parser construction is measurable cost on large corpora
* For pyright, `hasattr(obj, "get")` did not narrow `object`; aliasing to `Any` was the working narrow for metadata-shaped values

## Failed Approaches / Halts

* `010-S` had a stale-Copilot halt; operator-side UI re-request was required before merge approval
* Windows `tmp_path` `PermissionError` produced large local pytest noise for some runtime verification, so closure relied on targeted/static verification and kept the issue in stash
* 2026-06-04 load test caused system OOM and hard reboot due to docling `rt_detr-l4` memory pressure and pagefile thrashing
* Synthetic H1 header generation was suspected but disproven as the OOM source; it was deterministic regex/YAML analysis, not model inference
* GPU acceleration was evaluated and rejected on the current host because GTX 770M lacks modern CUDA compatibility and enough VRAM
* PA3/PA4 re-run missed goals: 247 minutes wall-clock versus 75-minute target and 53.1% flag rate versus 5-15% target, despite Jaccard and subprocess fallback criteria passing
* Markitdown/pypdf interim mitigation was superseded when the extraction study showed docling quality dominance for downstream consumers
* `backlogit` MCP or transport was sometimes unavailable, requiring CLI fallback in later sessions
* `038-F` PR #109 remained unmerged at memory time because it awaited operator merge approval, and Copilot re-review did not retrigger on the latest HEAD

## Outcomes

* `005-S` merged and archived with merge commit `160153ac56851b69dd97c2a07cf1129543ddbdea`
* `006-S` merged and archived with merge commit `afde2886730cae4479af91fed7654c5f06e9f5b3`
* `008-S` ELT ingestion completed and later verified as shipped by PR #16 at `52ae1c9d3b8a6fd6c3b432a82ef6c936f1a00c20`
* `010-S` merged in PR #19 with merge commit `3f1226f`; 41 artifacts archived
* `011-S` merged in PR #21 with merge commit `e07ffe6`; CI workflow closure recorded in PR #22
* `012-S` built to PR-ready state with HEAD `fa7291b`, four tasks done, feature archived, and closure document written
* `013-S` and `014-S` built to PR-ready state with all local gates green and follow-up stashes recorded
* PRs #46 through #53 merged overnight, closing `023-S` and `024-S` and landing pdfminer suppression, extraction study artifacts, quality metrics, and helper refactor
* `041-S` / `038-F` staged and built with PR #109 open, all local gates green, and operator approval pending

## Archived Originals

| Original | Archive path |
|---|---|
| `docs/archive/memory/2026-06-01/ship-005-s-final-memory.md` | `docs/archive/memory/2026-06-01/ship-005-s-final-memory.md` |
| `docs/archive/memory/2026-06-01/ship-006-s-final-memory.md` | `docs/archive/memory/2026-06-01/ship-006-s-final-memory.md` |
| `docs/archive/memory/2026-06-01/ship-006-s-memory.md` | `docs/archive/memory/2026-06-01/ship-006-s-memory.md` |
| `docs/archive/memory/2026-06-01/ship-008-s-pre-pr-checkpoint.md` | `docs/archive/memory/2026-06-01/ship-008-s-pre-pr-checkpoint.md` |
| `docs/archive/memory/2026-06-01/stage-elt-multi-source-memory.md` | `docs/archive/memory/2026-06-01/stage-elt-multi-source-memory.md` |
| `docs/archive/memory/2026-06-03/010-S-ship-session-6-final.md` | `docs/archive/memory/2026-06-03/010-S-ship-session-6-final.md` |
| `docs/archive/memory/2026-06-03/011-S-ship-session-final.md` | `docs/archive/memory/2026-06-03/011-S-ship-session-final.md` |
| `docs/archive/memory/2026-06-03/g2-multi-source-ingestion-stage-memory.md` | `docs/archive/memory/2026-06-03/g2-multi-source-ingestion-stage-memory.md` |
| `docs/archive/memory/2026-06-03/ship-012-S-session-memory.md` | `docs/archive/memory/2026-06-03/ship-012-S-session-memory.md` |
| `docs/archive/memory/2026-06-03/stage-012-S-segmentation-memory.md` | `docs/archive/memory/2026-06-03/stage-012-S-segmentation-memory.md` |
| `docs/archive/memory/2026-06-04/stage-ship-013-S-session-memory.md` | `docs/archive/memory/2026-06-04/stage-ship-013-S-session-memory.md` |
| `docs/archive/memory/2026-06-04/stage-ship-014-S-session-memory.md` | `docs/archive/memory/2026-06-04/stage-ship-014-S-session-memory.md` |
| `docs/archive/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md` | `docs/archive/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md` |
| `docs/archive/memory/2026-06-07/compaction-report.md` | `docs/archive/memory/2026-06-07/compaction-report.md` |
| `docs/archive/memory/2026-06-08/extraction-study-memory.md` | `docs/archive/memory/2026-06-08/extraction-study-memory.md` |
| `docs/archive/memory/2026-06-08/pa3-pa4-cosmos-rerun-evidence-memory.md` | `docs/archive/memory/2026-06-08/pa3-pa4-cosmos-rerun-evidence-memory.md` |
| `docs/archive/memory/2026-06-09/overnight-shipment-session-memory.md` | `docs/archive/memory/2026-06-09/overnight-shipment-session-memory.md` |
| `docs/archive/memory/2026-06-29/038-F-ocr-oom-ship-memory.md` | `docs/archive/memory/2026-06-29/038-F-ocr-oom-ship-memory.md` |
