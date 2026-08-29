# 2026-06-08 — PA3+PA4 cosmos re-run evidence + next-cycle plan

## Summary

PA3+PA4 cosmos re-run completed at 22:09 (4h 07m wall-clock). The two
architectural fixes shipped in 022-S (Blocker A: Jaccard QA metric;
Blocker B: layout-complexity signal) work as designed. But the
default-engine switch from `pypdf` to `markitdown` combined with the
new layout-complexity signal at weight 1.1 over-fired the scorer to
a 53.1 % flag rate, well outside the [5 %, 15 %] target band, with
unacceptable wall-clock as the downstream consequence.

021-S remains at `status: verified` (not promoted to `production-ready`)
until either an interim mitigation or a proper recalibration lands.

## Acceptance criteria result

| # | Criterion | Target | Actual | Verdict |
|---|---|---|---|---|
| 1 | Wall-clock | ≤ 75 min | 247 min (4h 07m) | ❌ FAIL — 3.3× |
| 2 | Flag rate | [5 %, 15 %] | 53.1 % (1818/3426) | ❌ FAIL — 3.5× |
| 3 | Jaccard disagreement | < 30 % | 0 % (0/9) | ✅ PASS |
| 4 | Subprocess fallback | < 10 % | 2.3 % (2/86) | ✅ PASS |

Evidence: `.elt/output/cosmos-triage-022/pa3-summary.json` (local only,
gitignored under `.elt/`).

## Files modified in this session

* `src/docline/process/pdf_triage.py` — added pdfminer logger suppression
  in `_get_markitdown()` (hotfix on PR #46)
* `tests/process/test_pdf_triage_baseline_engine.py` — added regression
  test using `monkeypatch.setattr` for singleton reset + try/finally for
  logger level restoration (addressed C1 + C2 Copilot review comments)
* `docs/closure/021-S-triage-then-repair.md` — annotated PA4 path with
  re-run outcome (stashed locally; not committed yet)
* `docs/closure/022-S-pa4-closure.md` — added "PA3+PA4 re-run evidence
  (2026-06-07, post-022-S)" section + linked new follow-on stashes
  (stashed locally; not committed yet)
* `.backlogit/stash.jsonl` — added 2 high-priority stashes
  (`79F23BDE`, `0AF15C3D`) (stashed locally; not committed yet)

## Active PRs

* **PR #46** (`fix/silence-pdfminer-warnings`, HEAD `2a79ff1`) —
  pdfminer logger suppression hotfix. All Copilot findings addressed
  and threads resolved. §1.9 stale-review condition (chronic pattern
  on this repo). All CI green. Awaiting operator merge approval.

## Local stash@{0}

`pa3-pa4-rerun-evidence-2026-06-08` contains:
* `.backlogit/stash.jsonl` (2 new entries)
* `docs/closure/021-S-triage-then-repair.md` (PA4 re-run outcome update)
* `docs/closure/022-S-pa4-closure.md` (re-run evidence section + stashes
  in `follow_up_stashes` frontmatter)

Apply with `git stash apply stash@{0}` after PR #46 merges and a fresh
branch is cut from updated `main`.

## New HIGH-priority stashes captured

| ID | Kind | Description |
|---|---|---|
| `79F23BDE` | bug | Scorer over-fires under markitdown baseline. Interim mitigation: revert default `baseline_engine` to `pypdf`; lower `signal_layout_complexity` weight 1.1 → ~0.6. Blocks 021-S production-ready. |
| `0AF15C3D` | task | Proper PA4 weight calibration against markitdown baseline. Run `triage_report_only` against cosmos; tune `fidelity_weights.json` to land flag rate in [5 %, 15 %]. Closes PA4 properly. |

## Recommended next cycle

After PR #46 merges:

1. **Apply stash@{0}** on a new branch (or include in the next
   shipment branch) — gets the closure-doc updates and the stash
   entries onto main.
2. **Run the next pipeline cycle** — orchestrator should pick up the
   2 new HIGH-priority stashes (`79F23BDE` + `0AF15C3D`) which are
   thematically linked. Stage them into a single shipment (call it
   023-S) targeting PA4 closure proper.
3. **Empirical calibration** can use the existing PA3 evidence:
   `.elt/output/cosmos-triage-022/pa3-engine-attribution.tsv` has
   per-page signal scores for all 3,426 pages — direct input for
   weight tuning.

## Key learnings to fold into compound

The 022-S → cosmos re-run cycle confirmed two pattern-level lessons
that should be added to (or referenced from)
`docs/compound/2026-06-06-triage-then-repair-pattern.md`:

1. **Baseline-engine swaps require re-calibration of downstream
   scoring signals.** Signals tuned against one extractor's output
   distribution do not transfer to a different extractor's
   distribution. Capture this as a pattern constraint: never swap
   the cheap-baseline engine without re-running calibration.
2. **Adding a new signal at moderate weight (1.1) on top of an
   already-tuned 7-signal aggregate can over-fire even when each
   signal is individually correct.** Per-signal correctness is
   necessary but not sufficient; aggregate threshold must be
   re-calibrated when signals are added.

These should be captured properly via the `compound` skill in the
023-S shipment closure.

## Untracked operator helper

`scripts/run_pa3_pa4_cosmos_022.ps1` exists locally as the operator's
PA3+PA4 runner. Decide in 023-S whether to commit it (with a
prefix-rename for the engine-revert variant) or keep it local.
