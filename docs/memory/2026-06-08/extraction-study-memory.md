# 2026-06-08 — extraction-strategy study (overnight autonomous session)

## Goal

Operator requested an autonomous comparative study of markitdown vs
docling output to determine the most effective + efficient extraction
strategy for the stated downstream consumers: graph databases, vector
embedding stores, and LLM context windows.

## What I did

1. Wrote 3 study scripts under `scripts/study/`:
   * `build_comparison_dataset.py` — stratified sample of 15 flagged
     ranges (5 small / 5 medium / 5 large), regenerates markitdown
     for each, pairs against existing docling splice
   * `evaluate_markdown.py` — parses both outputs with markdown-it-py,
     computes 25 AST-aware metrics per output
   * `analyze_study.py` — classifies ranges (docling-wins / tied /
     markitdown-wins) and emits findings.md + findings.json
2. Ran the pipeline against existing cosmos PA3+PA4 evidence (no
   fresh docling subprocesses — RCA-safe)
3. Wrote decision: `docs/decisions/2026-06-08-extraction-strategy-study.md`
4. Wrote roadmap: `docs/plans/2026-06-08-extraction-strategy-roadmap.md`
5. Captured 7 new stashes; tried to archive the 2 prior-session
   stashes (79F23BDE, 0AF15C3D) but they aren't in this branch's
   stash.jsonl — they live in the git stash@{0} on the fix branch
6. Did all work on a fresh branch `study/extraction-strategy-2026-06-08`
   from `origin/main` so PR #46 stays clean

## Headline finding

**Docling wins 14 of 15 sampled ranges (93%)** on AST-quality metrics
that correlate with the stated use cases. Earlier "over-fire"
hypothesis from the PA3+PA4 closure (52% flag rate looked excessive
because char-count delta was small on many ranges) was a measurement
artifact — char count is the wrong metric for graph/embedding/LLM
consumers.

Key per-engine averages across 577 sample pages:

| Metric | markitdown | docling | ratio |
|---|---|---|---|
| heading count | 0.93 | 66.2 | 71× |
| section count | 1.8 | 66.8 | 37× |
| median section chars | 29,161 | 571 | 0.02× (docling provides natural embedding chunks) |
| structural density per 1k chars | 2.62 | 6.80 | 2.6× |
| table count | 0.53 | 3.47 | 6.5× |
| total chars | 50,700 | 41,358 | 0.82 (docling is leaner — filters boilerplate) |

## Key reversal

The interim mitigation in stash `79F23BDE` (revert default
`baseline_engine` to `pypdf`, lower `signal_layout_complexity` weight)
would **regress on output quality** by every metric that matters. The
proper PA4 calibration in stash `0AF15C3D` should **pivot** from
"land flag rate in [5%, 15%]" to "maximize structural density and
section count, conditional on per-page cost budget".

Both prior stashes superseded by this study's 7 new stashes.

## Recommended next-action sequence

Per `docs/plans/2026-06-08-extraction-strategy-roadmap.md`:

1. **Merge PR #46** (pdfminer warning suppression — independent hotfix)
2. **Open 023-S** for strategy alignment (4 stashes, ~1-2 days):
   `13F608BA`, `A39C3704`, `5A622B72`, `378C8BC0`
3. **Open 024-S** for scoring-model inversion (1 stash, 3-5 days):
   `EFC6C84E` — the real architectural win
4. **Spike then 025-S** for docling speed-up: `51332802`
5. **Optional research spike** for generalization: `4CB606D5`

## Files modified this session

| Path | Action |
|---|---|
| `scripts/study/build_comparison_dataset.py` | new |
| `scripts/study/evaluate_markdown.py` | new |
| `scripts/study/analyze_study.py` | new |
| `docs/decisions/2026-06-08-extraction-strategy-study.md` | new |
| `docs/plans/2026-06-08-extraction-strategy-roadmap.md` | new |
| `docs/memory/2026-06-08/extraction-study-memory.md` | new (this file) |
| `.backlogit/stash.jsonl` | +7 new stash entries |

Plus gitignored evidence under `.elt/output/cosmos-triage-022/study/`:
* `dataset/` — 15 range subdirs each with markitdown.md + docling.md + meta.json
* `dataset/index.json` — sample index
* `results/per-range-metrics.tsv` — 15 rows × ~55 columns
* `results/per-range-metrics.json` — same data, JSON
* `results/findings.md` — human-readable analysis
* `results/findings.json` — analysis data structure

## Branch state at session end

* Working branch: `study/extraction-strategy-2026-06-08`
* Base: `origin/main` (commit `629a9d6`)
* Uncommitted at session end: the 6 new files above, ready to commit
  as a single docs+scripts shipment
* `scripts/compare_markitdown_vs_docling.py` (from earlier session)
  remains untracked

## Things worth remembering

1. **`baseline_engine_fallback: 0` in PA3+PA4 metadata** confirms
   markitdown succeeded on all 3,426 pages with no per-page rescue
   needed. Markitdown is operationally reliable, just inferior in
   AST quality.
2. **Cosmos doc has 2 docling subprocess failures**: ranges
   `splice-0319-0446` (128 pages) and `splice-1783-1990` (208
   pages). These are the largest splices — possible OOM under the
   current subprocess sizing. Tied to stash `51332802`.
3. **The `baseline-NNNN.pdf` files are valuable diagnostic
   artifacts** — preserve them via the new `--keep-page-pdfs` flag
   (stash `5A622B72`) when future runs need offline inspection.
4. **markitdown handles all PDF input via pdfminer.six** — same
   FontBBox warnings fixed in PR #46 apply across any markitdown
   future use.
5. The study scripts are designed to be re-run on different corpora
   trivially — just point `splice_dir`/`summary_path` at a new run's
   output. Stash `4CB606D5` exists to do exactly this.

## Open items for operator

* Review and decide whether 021-S transitions to `production-ready`
  given the new strategic direction (probably yes, with a note that
  the new direction shapes future work, not retroactively invalidates
  021-S's architecture).
* PR #46 merge approval still pending (separate concern).
* Confirm whether to proceed with the proposed 023-S → 024-S → 025-S
  sequence or to want the generalization study (`4CB606D5`) first.
