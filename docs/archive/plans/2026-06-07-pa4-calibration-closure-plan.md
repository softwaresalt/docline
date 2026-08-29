---
title: Plan — Close PA4 calibration (markitdown baseline + Jaccard diff + layout-complexity signal)
date: 2026-06-07
source: docs/decisions/2026-06-07-pa4-calibration-closure.md
stashes: 3777859D, 60E6157D, 1380BD85
related_closure: docs/closure/021-S-triage-then-repair.md
related_compound: docs/compound/2026-06-06-triage-then-repair-pattern.md
---

## Problem frame

021-S triage-then-repair shipped with `status: verified` but PA4
(lock-in calibrated `_SIGNAL_WEIGHTS`) is blocked by three
interdependent gaps surfaced during PA4 cosmos verification on
2026-06-07. This plan implements the three fixes as a single
coherent shipment so PA3 + PA4 can be re-run once and converge.

Touched modules:

* `src/docline/process/pdf_triage.py` (orchestrator + report-only + QA tripwire path; current 467 LOC; touched by U1 + U2)
* `src/docline/process/fidelity_scorer.py` (7 signals + combiner; current 332 LOC; touched by U3)
* `pyproject.toml` (add required dep; touched by U4)
* `scripts/pa3_triage_cosmos.py` (verification script; touched by U5)

## Requirements trace

| Decision acceptance criterion | Implementation unit |
|---|---|
| Triage produces markdown with proper lists / code fences / headings on structured pages | U1 |
| `qa_disagreements` reflects only semantically meaningful disagreements | U2 |
| Page 470 (or equivalent) flags under new signal and routes to docling | U3 |
| Default-mode (`--pdf-mode auto`) bit-identical to pre-merge | guaranteed by triage being opt-in; verified by existing regression tests |
| PA3 + PA4 re-run on cosmos converges (operator action post-merge) | U5 produces the comparable summary; closure update is post-merge operator work |
| `pytest` 989 still pass; ruff + pyright clean | enforced by build-feature quality gates |

## Module placement

| New / changed | Purpose |
|---|---|
| `src/docline/process/pdf_triage.py` (modified, U1) | Add `baseline_engine: Literal["markitdown", "pypdf"] = "markitdown"` kwarg + `_heuristic_extract` helper that dispatches on engine; both `process_pdf_triaged` and `triage_report_only` honor it |
| `src/docline/process/pdf_triage.py` (modified, U2) | Replace `_normalize_markdown` with `_content_similarity(a, b) -> float` returning Jaccard token similarity in `[0.0, 1.0]`; extend `QASampling` with `similarity_threshold: float = 0.7`; rename / refactor the disagreement check |
| `src/docline/process/fidelity_scorer.py` (modified, U3) | Add `signal_layout_complexity(text, page_metadata)`; add `"layout_complexity"` to `_SIGNAL_NAMES`; add default weight `1.1` to `_DEFAULT_SIGNAL_WEIGHTS`; wire into `score_page` |
| `pyproject.toml` (modified, U4) | Add `markitdown[pdf]>=0.1.6` to project dependencies |
| `scripts/pa3_triage_cosmos.py` (modified, U5) | Emit `similarity_score_histogram` in summary; surface `baseline_engine` choice; document new defaults |
| `tests/process/test_pdf_triage.py` (modified, U1) | Add baseline-engine comparison test (markitdown produces lists; pypdf produces flat text) |
| `tests/process/test_pdf_triage_tripwire.py` (modified, U2) | Add similarity-threshold scenarios (high similarity → not flagged; low similarity → flagged) |
| `tests/process/test_fidelity_scorer.py` (modified, U3) | Add layout-complexity test case using a constructed multi-column fixture PDF |

## Implementation units

Each unit follows the 2-hour rule, width isolation, atomic milestone.
Test-first execution posture throughout.

### U1 — markitdown baseline engine in pdf_triage

* **Files**: `src/docline/process/pdf_triage.py` (modified), `tests/process/test_pdf_triage.py` (modified)
* **Changes**:
  * New helper `_heuristic_extract(reader, page_idx, engine) -> str` dispatches on `engine ∈ {"markitdown", "pypdf"}`. For markitdown, splice the single page to a temp PDF (reuse the splice cache) and invoke `MarkItDown(enable_plugins=False).convert(splice).text_content`. For pypdf, current `reader.pages[page_idx].extract_text() or ""`.
  * Add `baseline_engine: Literal["markitdown", "pypdf"] = "markitdown"` kwarg to `process_pdf_triaged` and `triage_report_only`. Default is markitdown — represents the new recommended baseline.
  * Wire `dispatch_pdf_mode` to forward `baseline_engine` from `**kwargs` if present.
  * Record `baseline_engine` in `TriageResult.metadata`.
* **Tests** (RED first):
  1. `markitdown` engine on a fixture PDF with a numbered list produces output containing `"\n1. "` markdown list markers; `pypdf` engine on the same PDF does not.
  2. Default `baseline_engine` (no kwarg) routes through markitdown — assertable via metadata field.
  3. Existing `process_pdf_triaged` tests still pass with the new default (`baseline_engine="pypdf"` if any explicit pypdf-shaped assertion exists; otherwise default markitdown is fine).
  4. `metadata["baseline_engine"]` is recorded correctly for both engines.
* **Execution posture**: Test-first.

### U2 — Jaccard-similarity diff metric in QA tripwire

* **Files**: `src/docline/process/pdf_triage.py` (modified), `tests/process/test_pdf_triage_tripwire.py` (modified)
* **Changes**:
  * New helper `_content_similarity(a: str, b: str) -> float` returns Jaccard similarity of lowercased + punctuation-stripped token sets. Empty inputs return `1.0` (both empty = identical). Single-empty returns `0.0`.
  * Extend `QASampling` frozen dataclass with `similarity_threshold: float = 0.7`.
  * In `process_pdf_triaged` QA tripwire path: compare via `_content_similarity(docling_text, heuristic_text)`. Count as disagreement when `similarity < qa_sampling.similarity_threshold`.
  * Record `metadata["qa_similarity_histogram"]` — bucketed counts of similarity scores (e.g., `{">=0.9": N, "0.7-0.9": N, "0.5-0.7": N, "<0.5": N}`) for downstream calibration.
  * Remove `_normalize_markdown` (it's a private helper; no external callers per a quick scan).
* **Tests** (RED first):
  1. `_content_similarity("hello world", "hello world")` returns `1.0`; with extra whitespace / case / punctuation also returns `1.0`.
  2. `_content_similarity("foo bar baz", "completely different")` returns near `0.0` (no overlap).
  3. `_content_similarity` with code-fence wrapping (matching content) returns ≥ `0.9` — the page 107 case from the PA4 finding.
  4. QA tripwire with `similarity_threshold=0.7`: high-similarity sampled outputs do NOT increment disagreement; low-similarity DO.
  5. `metadata["qa_similarity_histogram"]` is populated and sums to `qa_sampled_count`.
* **Execution posture**: Test-first.

### U3 — layout-complexity signal in fidelity_scorer

* **Files**: `src/docline/process/fidelity_scorer.py` (modified), `tests/process/test_fidelity_scorer.py` (modified)
* **Changes**:
  * Add `signal_layout_complexity(text: str, page_metadata: object | None = None) -> float`. Implementation: when `page_metadata` is a `pypdf.PageObject`, walk the page content stream to gather text-run X-coordinates; compute the number of distinct X-clusters (using a simple coordinate-quantization with a tolerance of ~10 PDF units). Compare cluster count vs heuristic-text line count — if X-cluster count is significantly higher than what the flat text suggests (e.g., ≥ 3 distinct columns where the text reads as one column), return a positive signal proportional to the mismatch. Fall back to `0.0` on any exception (defensive — pypdf content-stream APIs vary).
  * Add `"layout_complexity"` to `_SIGNAL_NAMES`.
  * Add `"layout_complexity": 1.1` to `_DEFAULT_SIGNAL_WEIGHTS` (slightly above char_density weight; layout structure is high-confidence when detected).
  * `score_page` automatically picks up the new signal via the existing `signals` dict construction and combiner loop.
* **Tests** (RED first):
  1. `signal_layout_complexity(text, page_metadata=None)` returns `0.0` (no metadata → can't score).
  2. With a fixture single-column page PDF, signal returns `0.0` (no false-positive on clean prose).
  3. With a fixture multi-column / table-like PDF (constructed via `pypdf.PdfWriter` with positioned text), signal returns ≥ `0.5`.
  4. `score_page` includes `"layout_complexity"` in `signals` dict and counts the new signal in the aggregate weighted mean.
* **Execution posture**: Test-first. Constructing the fixture multi-column PDF is the hardest part — use `reportlab` if already in deps, else hand-craft a minimal multi-column PDF with `pypdf` + raw content stream.

### U4 — pyproject.toml + dependency

* **Files**: `pyproject.toml` (modified)
* **Changes**:
  * Add `"markitdown[pdf]>=0.1.6"` to the project dependencies array.
  * No removal of pypdf — it remains required (used by `pdf_splitter.py`, the per-page `reader.pages[i]` metadata access, and the `baseline_engine="pypdf"` fallback in U1).
* **Tests**: No new tests; existing import sites verify on next CI install. Add a smoke import line to a startup test if a sentinel for "deps installed" exists; otherwise rely on CI catching import errors.
* **Execution posture**: Configuration change. Verified by `pip install -e .` + existing pytest suite.

### U5 — PA3 verification script update

* **Files**: `scripts/pa3_triage_cosmos.py` (modified)
* **Changes**:
  * Add `--baseline-engine {markitdown,pypdf}` flag forwarded to `process_pdf_triaged`.
  * Add `qa_similarity_histogram` to summary JSON when QA sampling is enabled.
  * Surface `baseline_engine` in summary.
  * Update module docstring with the new defaults.
* **Tests**: Out of scope (operator-facing verification script; smoke-verified by `--help` and one cosmos run).
* **Execution posture**: Direct edit; compile-check; `--help` smoke.

## Dependency graph

```
U4 (pyproject.toml dep) ────┐
                            ├──> U1 (markitdown baseline) ──┐
                            │                               │
U2 (Jaccard diff)  ─────────────────────────────────────────┼──> U5 (script update + verification)
                                                            │
U3 (layout-complexity signal) ──────────────────────────────┘
```

* U4 blocks U1 (markitdown must be installable before U1 imports it).
* U2 and U3 are independent of U1 and of each other.
* U5 depends on all of U1, U2, U3 (it surfaces the new behaviors via its summary output).

## Decisions and rationale

| Decision | Rationale |
|---|---|
| Default `baseline_engine="markitdown"` rather than `"pypdf"` | Empirical evidence (logs/markitdown-bench/) shows markitdown produces strictly richer output than pypdf for prose/lists/code while matching it on JSON/code-only pages. No fidelity regression observed; downstream consumers (RAG/graph) benefit immediately. pypdf remains available as a compatibility fallback. |
| Jaccard similarity over normalized Levenshtein | Jaccard is `O(n)` over token sets; Levenshtein is `O(n²)`. Cosmos has ~3,400 pages × ~50 sample max = ~170 comparisons per run; Levenshtein would add multi-second overhead per page. Token-set Jaccard is sufficient for the "is this substantially the same content?" question. |
| Similarity threshold default `0.7` | Plan-review P2 finding from 021-S noted threshold tuning is calibration work. `0.7` is a reasonable starting default (PA4 inspection showed ≥0.9 for code-fence / whitespace differences and clearly < 0.5 for page 470 vs heuristic). Operator can tune via QASampling kwarg. |
| `signal_layout_complexity` weight `1.1` (above char_density `1.0`) | Layout structure detection is high-confidence when it fires — false positives on legitimately structured prose pages are bounded. Slightly above the default median means a single positive layout-complexity signal can dominate the aggregate without other signals firing. Tunable via the JSON weights file. |
| Remove `_normalize_markdown` rather than keep it | Private helper, no external callers, no behavioral coupling. Replacing in-place with the similarity helper is cleaner than maintaining two adjacent functions that do similar things. |
| New required dep (not extras) | The opt-in `--pdf-mode triage` path will become the recommended mode for long PDFs after PA4 closes. Gating markitdown behind extras would force operators to remember an additional install step. The transitive footprint (~6 deps) is acceptable for the value delivered. |

## Plan hardening signals (REQUIRED)

| Signal | Present? | Justification |
|---|---|---|
| public API, schema, or contract change | **Yes** (additive) | New `baseline_engine` kwarg on `process_pdf_triaged` and `triage_report_only`; new `similarity_threshold` field on `QASampling`; new `"layout_complexity"` signal in PageScore.signals dict; new `baseline_engine` + `qa_similarity_histogram` keys in `TriageResult.metadata`. All additive; no field removed. |
| security, auth, permission, or compliance | No | Same code paths as 021-S; no new auth surface or secret handling. |
| migration, backfill, destructive | No | Opt-in via `--pdf-mode triage`; default-mode unchanged. No data migration. |
| external integration or external dependency | **Yes** | **`markitdown[pdf]>=0.1.6` becomes a required runtime dependency.** Transitively pulls in pdfminer-six, pdfplumber, magika, onnxruntime, cryptography, markdownify, humanfriendly, pyreadline3, pycparser, protobuf, flatbuffers, coloredlogs, cffi. CI install times will grow. |
| high runtime, rollout, or rollback risk | **Yes** (mild) | Default `baseline_engine` changes from pypdf-equivalent to markitdown. For triage-mode users, this changes the baseline output materially. Rollback path: `--baseline-engine pypdf` flag (or kwarg). Risk is opt-in only — auto-mode unchanged. |

**Requires plan hardening: yes**

plan-harden should deepen: (a) the dep-graph impact (CI install time
quantification, lock-file regeneration), (b) the markitdown default
change as an explicit ProposedAction with rollback, and (c) the
runtime-verification plan for the post-merge PA3 + PA4 re-run.

## Runtime verification and closure

| Unit | Runtime surface changed? | Verification required |
|---|---|---|
| U1 | Yes — triage output content shape | Unit tests + post-merge PA3 re-run on a 5-page fixture and the cosmos PDF |
| U2 | Yes — `qa_disagreements` semantics | Unit tests + post-merge PA4 re-run; expect disagreement rate well under 50% (vs the 97% under the old metric) |
| U3 | Yes — scorer flag rate | Unit tests + post-merge PA3 re-run; expect page 470 to flag; expect cosmos flag rate to rise from 3% to somewhere in the 5–15% range |
| U4 | Yes — install footprint | CI install green; `pytest` 989 still pass |
| U5 | Yes — verification surface | Smoke `--help`; post-merge full cosmos re-run with new flags |

Operational closure (post-merge):

* `docs/closure/2026-06-07-022-S-pa4-closure.md` — closure artifact
  recording the post-merge PA3 + PA4 re-run evidence.
* `docs/closure/021-S-triage-then-repair.md` — update PA4 to `applied`;
  transition `status:` from `verified` to `production-ready` if
  re-run criteria met.
* Operator follow-on if disagreement metric or flag rate still off:
  iterate weights via JSON file (no code change needed).

## Plan Hardening

### Hardening required and why

Required: **yes**. Two distinct risk surfaces:

1. **New required runtime dependency** (`markitdown[pdf]>=0.1.6`).
   Pulls in 13 transitive deps including `onnxruntime` (binary
   wheel, ~30+ MB), `pdfminer-six`, `pdfplumber`, `magika`,
   `cryptography`, `markdownify`, `humanfriendly`, `pyreadline3`,
   `pycparser`, `protobuf`, `flatbuffers`, `coloredlogs`, `cffi`.
   CI install time and lock-file footprint grow materially.
2. **Default baseline engine change**. For operators currently using
   `--pdf-mode triage`, the output character shape changes
   (numbered lists become markdown lists; code blocks get fenced;
   prose flows through pdfminer.six rather than pypdf). This is an
   improvement per empirical bench (logs/markitdown-bench/) but
   downstream consumers may have implicit assumptions on the
   pypdf-shaped output.

### Learnings and instructions consulted

| Source | Relevance |
|---|---|
| `docs/compound/2026-06-06-triage-then-repair-pattern.md` | The architectural lesson "an opt-in CLI flag is not wired until an end-to-end test verifies a real production code path responds to it" applies directly to U1: the new `baseline_engine` kwarg must be exercised through the full CLI → `execute_process` → `build_output_document_parts` → `process_pdf_triaged` path, not just unit-tested in isolation |
| `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md` | Indirect — no namespace mutation in this shipment, but a reminder that integration-shape changes have non-obvious downstream effects |
| `docs/closure/021-S-triage-then-repair.md` PA3/PA4 ledger | The PA3 + PA4 verification protocol is established; this shipment just re-uses it post-merge with the new defaults |
| `docs/decisions/2026-06-07-pa4-calibration-closure.md` (source) | The five options + rejection rationale; reaffirmed Option C |

### Protected invariants

| Invariant | Verification |
|---|---|
| Default mode (`--pdf-mode auto` or unset) is bit-identical to pre-merge | Existing `test_pdf_mode_auto_dispatches_to_existing_batch_pipeline`; `test_default_mode_is_auto`; full regression of `tests/test_cli_process.py` (3 tests) and `tests/process/test_media_sidecars_in_manifest.py` (6 tests) |
| markitdown import failure does not crash triage | U1 includes a try/except around the markitdown call that falls back to pypdf and records the fallback in `metadata["baseline_engine_fallback"]` |
| `signal_layout_complexity` returns 0.0 when `page_metadata is None` | U3 test scenario 1 (matches the charitable-when-no-metadata pattern from 021-S U1 `signal_char_density`) |
| Jaccard similarity returns 1.0 for empty-vs-empty and 0.0 for empty-vs-nonempty | U2 test edge-case scenarios; prevents division-by-zero on degenerate inputs |
| New `metadata["baseline_engine"]` field is additive — does not break existing TriageResult consumers | U1 test asserts `metadata["baseline_engine"]` is present; existing tests that don't read it continue to pass |
| Splice + QA temp files stay under `output_dir` (Constitution IV) | The new markitdown per-page splice reuses the existing splice cache directory; verified by U1 test |
| `dispatch_pdf_mode` forwards `baseline_engine` correctly when set via `**kwargs` | U1 test invokes `dispatch_pdf_mode("triage", path, output_dir=..., baseline_engine="pypdf")` and asserts the result reflects the explicit choice |

### Risky actions (ProposedAction / ActionRisk / ActionResult)

Carried forward into review, runtime verification, and closure.

#### PA1 — Switch default `baseline_engine` from pypdf-equivalent to markitdown

| Field | Value |
|---|---|
| `summary` | Change the default heuristic baseline in `process_pdf_triaged` from pypdf direct extraction to markitdown. Existing triage-mode users will see materially richer markdown output. |
| `targets` | `src/docline/process/pdf_triage.py`, downstream consumers of `TriageResult.pages` (graphtor / RAG indexers) |
| `change_kind` | Default behavior change for opt-in mode |
| `rollback` | Pass `baseline_engine="pypdf"` to `process_pdf_triaged` or `dispatch_pdf_mode`; CLI can expose a `--baseline-engine` flag in a follow-on if needed (out of scope this shipment per the open-question resolution) |
| `approval_required` | No (opt-in mode; not changing default-mode behavior) |
| `ActionRisk` | **moderate** |
| Initial `ActionResult` | `planned` |

#### PA2 — Add `markitdown[pdf]>=0.1.6` as required dependency

| Field | Value |
|---|---|
| `summary` | New runtime dependency pulling in 13 transitive packages |
| `targets` | `pyproject.toml`, CI install time, `requirements.lock` (if used) |
| `change_kind` | Dependency addition |
| `rollback` | Revert pyproject.toml change; the markitdown import path is the only call site; pypdf fallback works without it |
| `approval_required` | No (additive; covered by plan-review) |
| `ActionRisk` | **moderate** (install footprint grows ~30+ MB; CI install time grows ~10-30 s) |
| Initial `ActionResult` | `planned` |

#### PA3 — Add `signal_layout_complexity` to default signal set

| Field | Value |
|---|---|
| `summary` | New scorer signal with default weight 1.1; will increase flag rate on multi-column / table pages |
| `targets` | `src/docline/process/fidelity_scorer.py` |
| `change_kind` | Additive scorer signal |
| `rollback` | Set weight to 0 via `fidelity_weights.json` override; no code change needed |
| `approval_required` | No |
| `ActionRisk` | **low** |
| Initial `ActionResult` | `planned` |

#### PA4 — Post-merge cosmos PA3 + PA4 re-run

| Field | Value |
|---|---|
| `summary` | Operator runs `scripts/pa3_triage_cosmos.py` (with `--sample-rate 0.01`) on cosmos PDF from a plain shell; captures new wall-clock, flag rate, disagreement rate, similarity histogram |
| `targets` | `.elt/data/cosmosdb/azure-cosmos-db.pdf`; `.elt/output/cosmos-triage-022/` (new run dir to avoid clobbering 021-S evidence) |
| `change_kind` | Read-only verification with local writes to test directory |
| `rollback` | Delete output dir; no code rollback |
| `approval_required` | No (read-only on source; same RCA constraint applies — plain shell only) |
| `ActionRisk` | **low** |
| Initial `ActionResult` | `planned` (cannot proceed until merge lands) |

### Deepened runtime verification

#### Environment prechecks (before any triage invocation post-merge)

* Confirm `markitdown` extras installed (smoke import `from markitdown import MarkItDown`)
* Confirm `pypdf` still importable (compatibility fallback)
* Confirm `docling` extras installed (existing dependency probe)
* Confirm `output_dir` is writable AND under cwd per Constitution IV

#### CI install time guard

If CI install time grows by more than 60 s after this merge, capture
a follow-on stash for dependency pruning (e.g., conditional markitdown
import; lazy loading). Not a rollback trigger by itself.

#### Target verification scenarios (post-merge)

| Scenario | What it proves |
|---|---|
| 5-page fixture with mixed prose / list / code / table | markitdown produces lists; new scorer flags the table page |
| Cosmos PDF, full run with `--baseline-engine markitdown` (default) | New wall-clock target: ≤ 75 min (allowing for ~14 min markitdown overhead vs ~5 min pypdf); flag rate in 5–15% range |
| Cosmos PDF with `--baseline-engine pypdf` | Wall-clock matches 021-S PA3 baseline (~50 min); flag rate ~3% (unchanged); regression coverage for the pypdf fallback path |
| Cosmos PDF with `--sample-rate 0.01 --qa-random-seed 42` | Disagreement rate under new Jaccard metric: **target < 10%** (vs 97% under old metric); similarity histogram shows distribution clustered at high-similarity end |

#### Blocked-path handling

If PA4 post-merge run shows disagreement rate **still > 30%** under
new Jaccard metric, halt PA4 close. Investigate via splice inspection
similar to the 2026-06-07 PA4 analysis. Likely cause: similarity
threshold needs lowering (try 0.5) before signal weight tuning.

### Deepened operational closure

#### Monitoring signals (recorded automatically per triage run)

* `metadata["baseline_engine"]`: which engine ran the baseline
* `metadata["baseline_engine_fallback"]`: True when markitdown failed
  and pypdf served as fallback
* `metadata["qa_similarity_histogram"]`: bucketed similarity-score
  distribution from QA sampling
* Per-page engine distribution in `triage_stats` manifest summary
  (unchanged from 021-S)

#### Rollback triggers (any of these triggers immediate fallback)

1. CI install fails on any of the 3 OS targets after this merge.
2. Default mode (`--pdf-mode auto`) regression detected in existing
   `test_cli_process.py` / `test_media_sidecars_in_manifest.py` tests.
3. Disagreement rate under new Jaccard metric > 30% on cosmos PA4
   re-run (suggests the metric still mis-tunes).
4. Flag rate jumps above 25% (suggests `signal_layout_complexity` is
   over-firing on prose pages).
5. markitdown failure rate (via `baseline_engine_fallback`) exceeds
   5% of pages (suggests fragile markitdown install on production
   PDFs).

#### Rollback procedure

* **Per-invocation**: Operator passes `baseline_engine="pypdf"` to
  affected calls (CLI follow-on flag deferred; for now, code-level
  override only).
* **Per-deploy**: Revert this shipment's merge commit:
  `git revert -m 1 {merge_sha}`; push to main. Triage falls back to
  pypdf + old diff metric + old signal set.
* **Per-corpus** (no rollback needed): use `--pdf-mode auto` instead
  of `--pdf-mode triage`; the auto path is unchanged.

#### Owner and validation window

* Owner: docline maintainer
* Validation window: first 3 cosmos-class document triage runs after
  merge. If any rollback trigger fires, halt; otherwise close PA4.

### Operator checkpoints

| Checkpoint | When | What is decided |
|---|---|---|
| Plan-review gate | Before harvest | Plan-review skill validates the bundled scope; ADVISORY or PASS gate |
| Merge approval | After PR + CI green + Copilot review clean | Operator approves merge per P-014 |
| PA3 re-run | After merge, plain shell, on cosmos | Wall-clock + flag rate evidence captured in `.elt/output/cosmos-triage-022/pa3-summary.json` |
| PA4 re-run | After PA3 succeeds | Disagreement rate + similarity histogram capture |
| Closure transition | After PA3 + PA4 evidence collected | Update `docs/closure/021-S-triage-then-repair.md`: PA4 → applied; status → production-ready |

### Unresolved decisions still blocking safe execution

| Open question | Resolution path | Blocking? |
|---|---|---|
| Should `--baseline-engine` be exposed as a CLI flag in this shipment or deferred? | Deferred. Reverting to pypdf via kwarg is sufficient for rollback in this shipment. CLI flag added in a follow-on if operators need it. | Not blocking |
| Should `auto`-mode (`--pdf-mode auto`) also adopt markitdown? | Explicitly out of scope per the source decision doc. Auto-mode bit-identical-output invariant preserved. | Not blocking |
| Should the layout-complexity fixture PDF be hand-crafted or generated via `reportlab`? | Implementation decision in U3; either works. `reportlab` is not currently a dependency; hand-crafted is preferred to avoid adding a test-only dep. | Not blocking |
| Should the new dep be optional (extras) instead of required? | Decided in source doc: required. The opt-in `--pdf-mode triage` path is the recommended mode for long PDFs post-PA4. Gating behind extras would force a remember-this install step. | Not blocking |

## Plan Review

**Gate decision**: **ADVISORY** (proceed with operator acknowledgment).

**Hardening compliance**: Required and present. Four `ProposedAction`
entries (PA1–PA4) classified with risk + rollback + approval path.
Seven protected invariants enumerated with concrete verifying tests.
Five quantified rollback triggers. CI install-time guard documented. ✓

**Personas dispatched**: Constitution Reviewer, Python Reviewer, Scope
Boundary Auditor, Learnings Researcher, Architecture Strategist
(always-triggered), Security Lens Reviewer (lightly triggered —
new required external dependency crosses a supply-chain trust boundary).
Agent-Native Parity Reviewer **not** triggered (no MCP/agent-facing
surface change).

**Severity summary**: 0 P0, 0 P1, 1 P2, 6 P3. ADVISORY gate.

### Findings

#### P2 — Verify no test imports of `_normalize_markdown` before removing it

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U2 |
| Issue | U2 removes the existing `_normalize_markdown` helper rather than replacing it in-place. If any test file imports it directly, the test will break at collection time. |
| Verification | Searched `tests/**/*.py` for `_normalize_markdown` — zero matches. Safe to remove. |
| Recommendation | No code change needed; finding recorded as a guardrail for the harness-architect to keep the test scaffold consistent. |
| Action | Verified; no follow-up required. |

#### P3 — Constitution Principle VI (single responsibility) friction

| Field | Value |
|---|---|
| Persona | Constitution Reviewer |
| Unit | U4 |
| Issue | Adding `markitdown[pdf]` introduces 13 transitive deps including `onnxruntime` (~30+ MB binary wheel). Principle VI says "Every additional dependency increases build time, attack surface, and maintenance burden." |
| Recommendation | Plan acknowledges in hardening with empirical justification (markitdown produces strictly richer markdown than pypdf on the bench). Acceptable per "justified by a concrete requirement" clause. Document a follow-up stash for "evaluate lazy markitdown import" if CI install times prove painful. |
| Action | `advisory` — proceed; add lazy-import stash only if rollback trigger #1 (CI install fail) fires. |

#### P3 — `_content_similarity` tokenization edge cases

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U2 |
| Issue | Plan doesn't specify the exact tokenization: split on whitespace? collapse multiple spaces? handle Unicode? Empty strings after punctuation-strip? |
| Recommendation | Use `re.findall(r"\w+", text.lower())` — Unicode-aware, handles whitespace + punctuation in one pass, returns empty list on empty input. Document this explicitly in the docstring. Test scenarios: empty vs empty → 1.0; non-empty vs empty → 0.0; Unicode → tokens preserved. |
| Action | `advisory` — implementation detail for U2. |

#### P3 — `signal_layout_complexity` pypdf content-stream API fragility

| Field | Value |
|---|---|
| Persona | Python Reviewer |
| Unit | U3 |
| Issue | pypdf's content-stream walking API (`page.get_contents()` / extracting Tj / TJ operators with positions) varies across pypdf versions. Plan acknowledges "defensive — fall back to 0.0 on any exception". Risk: too-defensive masks real bugs. |
| Recommendation | Make the defensive try/except narrow (catch only `AttributeError`, `KeyError`, `TypeError`, `pypdf.errors.PdfReadError`) rather than bare `except`. Log a warning so silent-failure cases are discoverable. |
| Action | `advisory` — implementation guardrail for U3. |

#### P3 — U4 + U5 could fold into U1

| Field | Value |
|---|---|
| Persona | Scope Boundary Auditor |
| Unit | U4 + U5 |
| Issue | U4 (pyproject.toml edit, ~1 line) and U5 (script update, ~30 lines) are small enough to be subtasks under U1 rather than independent units. |
| Recommendation | Keep separate. Reason: pyproject.toml lives outside `src/`, and the script lives outside the production module. Width-isolation matters more than file count. Independent units make the dependency-on-merge order explicit (U4 before U1). |
| Action | None required. |

#### P3 — U1 + U2 both modify `pdf_triage.py` — sequencing matters

| Field | Value |
|---|---|
| Persona | Architecture Strategist |
| Unit | U1 + U2 |
| Issue | Both units edit `src/docline/process/pdf_triage.py`. Parallel implementation will produce merge conflicts in `build-feature`. |
| Recommendation | Sequence: U2 first (changes `_normalize_markdown` → `_content_similarity` and `QASampling` extension; touches lower portion of file), then U1 (adds `_heuristic_extract` + baseline_engine kwarg threaded through public APIs; touches signature + early-pass code). The two changes affect distinct logical regions of the file. harness-architect should implement them sequentially in this order, not in parallel. |
| Action | `advisory` — sequencing note for build-feature. |

#### P3 — markitdown couples docline to pdfminer.six lineage

| Field | Value |
|---|---|
| Persona | Architecture Strategist |
| Unit | U1 |
| Issue | markitdown's PDF backend is pdfminer.six; future markitdown versions could swap backends (e.g., to Marker, an LLM-based extractor) and silently change our triage output shape. |
| Recommendation | Pin markitdown to a minor-version range in pyproject.toml: `markitdown[pdf]>=0.1.6,<0.2`. Re-evaluate when upgrading. |
| Action | `advisory` — pin range tighter than the `>=` documented in the plan. |

#### P3 — Supply-chain audit of new transitive deps

| Field | Value |
|---|---|
| Persona | Security Lens Reviewer |
| Unit | U4 |
| Issue | New transitive deps include `magika` (Google's ONNX-based content-type detector) and `onnxruntime` (binary wheel). `magika` could be invoked auto-detect-style on operator-supplied PDFs by markitdown. While markitdown's documented PDF path is pdfminer.six (not magika), the dep is now in the venv. |
| Recommendation | After merge, audit markitdown's actual call graph to confirm `magika` is dead code or used only for content-type sniffing (not arbitrary code execution). If magika is invoked, document the call site. If unused, consider `pip install markitdown[pdf] --no-deps magika` (not natively supported by pip extras; would require a constraint file). |
| Action | `manual` — post-merge audit. Captured as advisory; not blocking. |

### Constitution principles coverage

| Principle | Plan coverage |
|---|---|
| I — Safety-first Python | ✓ All units state typed APIs; narrow exception classes recommended per P3 finding |
| II — Test-first | ✓ Every unit has explicit RED test list |
| III — Workspace isolation | ✓ Splice cache + markitdown writes stay under `output_dir` |
| IV — CLI containment | ✓ No new file writes outside cwd tree |
| V — Structured observability | ✓ New metadata fields documented (baseline_engine, baseline_engine_fallback, qa_similarity_histogram) |
| VI — Single responsibility | ⚠️ New required dep — justified empirically; P3 follow-on if CI install grows painfully |
| VII — Destructive approval | ✓ No destructive operations |
| VIII — Safety modes | ✓ Plan-harden done; PA1–PA4 classified |
| IX — Git-friendly persistence | ✓ No new persistence format |
| X — Context efficiency | ✓ Frozen dataclasses; pure-function signals + similarity helper |
| XI — Merge commit history | n/a — enforced at merge time |

### Runtime verification and closure coverage

* All 5 units have named verification scenarios. ✓
* Environment prechecks documented (markitdown import smoke). ✓
* CI install-time guard documented. ✓
* Quantified rollback triggers (5). ✓
* Operator checkpoints (5) explicit. ✓
* Post-merge PA3 + PA4 re-run protocol carries forward from 021-S. ✓

### Gate rationale

No P0 or P1 issues. One P2 (verify-no-callers-of-`_normalize_markdown`)
was verified inline — zero test imports found. Six P3 advisories are
implementation-discipline notes that should inform harness-architect
scaffolds and build-feature execution but do not block harvest.

Operator may proceed to **harvest**. harness-architect should
reflect:

* P3#5: implement U2 before U1 to avoid `pdf_triage.py` merge conflicts
* P3#3: narrow exception handling in U3 layout-complexity signal
* P3#2: use Unicode-aware `re.findall(r"\w+", ...)` tokenization in U2 similarity helper
* P3#6: pin `markitdown[pdf]>=0.1.6,<0.2` in U4 pyproject.toml (tighter than the `>=` initially planned)
