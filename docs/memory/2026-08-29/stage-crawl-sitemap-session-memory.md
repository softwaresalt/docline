---
type: stage-session-checkpoint
date: 2026-08-29
agent: stage
phase: plan-review
branch: chore/stage-crawl-frontier-sitemap
base: origin/main @ edcaa12
stash_ids: [7F34A0D5, 8A99D90C, ABBE9BCC, F0F13C0B]
---

# Stage session — crawl frontier + sitemap preflight (checkpoint 1)

## Session framing

Dark-factory staging of all four active stash entries from `origin/main`. Operator priority:
**reliability and composability outrank feature convenience.** No source or test implementation
in this session — planning and backlog artifacts only.

Operator-owned worktree modifications that must not be touched or committed:
`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
`.github/agents/_ship.agent.md`, `.gitignore`.

## Step 0.0 / 0.1 — tool gate

- Backlog registry present at `.autoharness/backlog-registry.yaml`; tool `backlogit` v1.10.1.
- MCP surface not exposed to this agent session; operating via the registry-declared **CLI
  fallback** (`backlogit ...`). Status: `DEGRADED_MODE: backlogit MCP — CLI fallback in use`.
- `backlogit sync` succeeded (424 artifacts indexed). `INDEX_SYNC_OK`.
- Intercom not reachable in this session → `INTERCOM_DEGRADED`; engram not reachable →
  `ENGRAM_DEGRADED`. Discovery performed with targeted grep/glob/view per the fallback protocol.

## Step 1 — triage and classification

| Stash ID | Priority | Kind | Shape | Routing |
|---|---|---|---|---|
| 7F34A0D5 | medium | feature | feature-shaped | Group A covering feature |
| 8A99D90C | medium | task | task-shaped | Group A |
| ABBE9BCC | low | task | task-shaped | Group A |
| F0F13C0B | low | task | task-shaped | Group B (solo) |

## Step 1.5 — contextual grouping (operator-directed)

Grouping was specified by the operator and confirmed against the code surface:

- **Group A** {7F34A0D5, 8A99D90C, ABBE9BCC} — all three mutate the same ~30 lines of frontier
  admission logic in `src/docline/fetch/crawl.py` (lines 191-222, 290-291, 324-355). Shared
  mutation surface, forced ordering, one review surface.
- **Group B** {F0F13C0B} — `src/docline/fetch/sitemap.py` only. No shared file, no dependency
  edge with Group A. Security-boundary review width, deliberately not bundled.

## Step 1.8 — learnings retrieval

`docs/compound/` searched for crawl/frontier/observability and SSRF/preflight learnings. No
matching prior art. Governing prior context is
`docs/closure/2026-08-29-058-s-crawl-frontier-bound-closure.md` (source of the three Group A
entries; constrains Units 2-3: no per-link logging, no derived ceiling) and
`docs/decisions/2026-08-29-ssrf-classifier-pinning-deliberation.md` (Group B pinning invariant).

## Step 2 — deliberation artifacts (accepted)

- `docs/decisions/2026-08-29-crawl-frontier-observability-deliberation.md` — Option A chosen
  (extract `_Frontier` first, then layer observability and TOC ordering on it). Options B
  (three independent shipments in stash-priority order) and C (observability only) rejected:
  both are the feature-convenience ordering and both leave the admission rule untestable.
- `docs/decisions/2026-08-29-sitemap-preflight-dedup-deliberation.md` — Option A chosen
  (deterministic resolution-free preflight). Option C (pass preflight addresses into
  `fetch_page`) rejected as actively dangerous — it migrates authority out of the pinning path.

## Step 3 — plans written, hardening applied

- `docs/plans/2026-08-29-crawl-frontier-observability-plan.md` — **18 tasks** as reviewed,
  `requires_plan_hardening: yes`, `## Plan Hardening` with a **9-row** risk register (R1-R9).
  The first draft was 10 tasks with R1-R7; review split oversized tasks and added the CLI/MCP
  parity work.
- `docs/plans/2026-08-29-sitemap-preflight-dedup-plan.md` — **7 tasks** as reviewed,
  `requires_plan_hardening: yes`, `## Plan Hardening` with a **9-row** risk register (R1-R9).

Key grounded discovery that materially expanded Group B's honest scope: the sitemap preflight's
resolving behaviour is pinned by real tests —
`tests/fetch/test_sitemap.py` (hostname-resolution rejection expects `SitemapError`) and
`tests/fetch/test_sitemap_pinned_sink.py` (`_sequenced_getaddrinfo` schedules assume the
preflight consumes resolver answer #1; three tests exist solely because the preflight blocks on
DNS). Planned for explicitly as B.T2, B.T4, B.T5 rather than left to be discovered mid-build.

## Next steps

1. Collect the five adversarial plan-review verdicts (architecture, security, correctness, scope,
   python-safety), apply P1/P2 findings to the plans.
2. Harvest both groups into backlogit with dependency edges.
3. Assemble two shipments, parent-first.
4. Archive all four stash entries with forward references.
5. Commit, push, staging PR, Copilot review cycles, merge.

## Step 4 — plan review gate: PASS

Five personas, adversarial, grounded against source. Plan A took 4 rounds, plan B took 3.
Full per-persona finding tables are recorded in each plan's `## Plan Review Record` section.

Round-1 verdicts were Plan A FAIL / Plan B FAIL. Six P1s were closed:

1. (arch) Plan A's single-module split could not reach 400 lines — arithmetic was never stated.
2. (arch) That split introduced a **circular import**: `crawl_links` needs `_normalize_url`,
   which round 1 left in `crawl.py`.
3. (correctness) The `CrawlOutcome` caller inventory was incomplete — 6 modules listed, 9 real,
   including a root-level `tests/test_execute_fetch.py` whose *fake* also needed migrating.
4. (correctness) CLI/MCP parity was claimed but not achieved: `execute_fetch` builds a fresh
   `FetchResult` at `app.py:621`; `mcp/server.py` is a pass-through, so editing it is a no-op.
5. (correctness) D8 hard-coded `frontier_truncated: true` for zero-staged crawls, contradicting
   D3 — a print-page start with `max_frontier=0` stages nothing yet refuses nothing.
6. (scope) Round-1 plan B decision D3 changed `fetch_sitemap`'s timeout contract, which
   F0F13C0B never requested. **Rejected**; the executor offload is retained. Security reached
   the same conclusion independently via a post-timeout abandoned-worker concern.

The most valuable negative result: security **verified plan B's core premise** rather than
assuming it. `resolve_and_validate` screens *every* resolver answer through the same canonical
predicate, so deleting the sitemap preflight's screening creates no coverage gap. Had that check
failed, the whole shipment would have been invalid.

## Step 5 — harvest

| Group | Feature | Tasks | Shipment |
|---|---|---|---|
| A (crawl) | `068-F` | `068.001-T` … `068.018-T` (18) | **`059-S`** |
| B (sitemap) | `069-F` | `069.001-T` … `069.007-T` (7) | **`060-S`** |

Dependency edges were written explicitly. Note a CLI quirk: `backlogit add --dependencies a,b`
records only the **first** ID; the remaining edges were added with `backlogit dep add` and
verified via `backlogit dep list`. Multi-dependency tasks affected: `068.007-T`, `068.013-T`,
`068.014-T`, `068.017-T`, `068.018-T`, `069.003-T`.

## Step 5.5 / 5.6 — shipments and stash retirement

Both shipments assembled parent-first (covering feature at index 0, then tasks in dependency
order). All four stash entries retired: `7F34A0D5` → `068-F` and `F0F13C0B` → `069-F` via
`stash harvest`; `8A99D90C` and `ABBE9BCC` archived after being folded into `068-F` as tasks.
Active stash is now empty.

## Handoff

Ship claims **`059-S`** first (medium, reliability/composability), then **`060-S`** (low).
Both are independent — no cross-shipment dependency edge. The only shared file is
`docs/ARCHITECTURE.md`; whichever merges second rebases a trivial doc hunk (risk R8 in both plans).

## Step 6 — staging gate complete

**PR #177 merged as `9edbb91`** (true merge commit; repo has squash and rebase disabled).

### Copilot review cycles

> **Cutoff.** This section is written as an ongoing log rather than a running total, because two
> earlier attempts at a single "N findings" figure went stale the moment the next review landed.
> Each row is closed when its findings are fixed and its threads resolved; the final state is
> whatever the last row says. Do not re-derive a grand total — read the rows.

Every finding across every round was valid and every one was fixed. Rounds 1-4 (PR #177) produced
review threads only; round 5 produced **zero threads** but carried 7 suppressed findings in its
review *body*; PR #178's rounds produced a mix of both.

| Round | HEAD | Findings | Substance |
|---|---|---|---|
| 1 | `417b8e9` | 10 | `refused_any` blind to a cap filled by an earlier page; `D8` hard-coded `true`; CLI seam was a no-op edit; stale deliberation option; stale rollback list; stale frontmatter |
| 2 | `b6f3700` | 10 | TOC-only false negative; `job` not constructed until after the `except` block; `max_frontier` remedy not reachable by operators; missing `A.T12→A.T4` edge; archive forward refs; stale memory counts |
| 3 | `cecbddb` | 4 | `tests/parity/test_equivalence.py` asserts the **exact** `FetchResult` field set — a hard blocker; a 10th caller module (`test_execute_fetch_progress.py`) |
| 4 | `f1f85e8` | 2 | two internal count inconsistencies introduced by my own round-3 edits |
| 5 | `4558b0f` | **7 suppressed** | *not* clean — review `5060076290` surfaced 7 previously-missed findings as suppressed comments rather than threads |
| 6 | `63ab0a1` (PR #178) | 1 | caught my own inaccurate "clean" claim about round 5 |
| 7 | `e2a9ef7` (PR #178) | 2 + 3 suppressed | stale artifact `updated_at` after a bare `dep add`; PR description understated backlog changes; arithmetic and history errors in this very file |
| 8 | `e04fa26` (PR #178) | 3 + 1 suppressed | R9 still contradicted the corrected callback contract; A.T7 at four files broke the plan's own three-file ceiling; the running-total framing was itself the defect |

Four findings, producing three design changes rather than wording changes:

1. **The truncation signal was wrong twice — two separate findings, one design change.** Round 1: if the cap was filled by an earlier page,
   the short-circuits `continue` before extracting links, so later pages' links vanished with no
   refusal recorded. Fix: short-circuits must still parse and filter links (pure in-memory work)
   and set `refused_any`. Round 2: that still missed a depth-zero page with **no anchors but an
   eligible `toc-*.js`**. Fix: also parse `extract_toc_script_urls()` and set the flag
   conservatively — accepting over-reporting, because a false "may have truncated" is an operator
   prompt while a false "complete" is silent data loss. `_discover_toc_links()` (the network part)
   still stays skipped.
2. **`D8` was unimplementable as written.** `_fetch_url` raises before returning its tuple, and
   `_execute_source` builds the `StagingJob` *after* the `try`/`except` — so neither the tuple nor
   `job` could carry the flag. Fix: `CrawlStagedNothingError(OSError, DoclineError)` carries it,
   and a local threads it into the later `StagingJob(...)` construction.
3. **`FetchResult` has a contract test.** `tests/parity/test_equivalence.py` asserts the exact
   field set, so `A.T11b` would have failed a gate the plan claimed green. It now owns that
   assertion update.

### Lesson for the next session

My caller-inventory searches repeatedly matched `await crawl(` and missed **monkeypatch/stub
sites**. Reviewers found **four existing caller modules I had missed** (rounds 1 and 3) and,
separately, **one future caller my own plan created** — `test_crawl_control_flow.py`, introduced
by A.T2b and owned by no migration task (round 5). Those are two distinct failure modes: an
incomplete search of the current tree, and no re-check of callers the plan itself adds. `A.T6`'s mandatory pre-flight
re-search now requires matching stub sites, and exact-field contract assertions must be searched
before **any** model change.

### Final state on `origin/main`

- 29 artifacts, all `queued`: 2 features, 2 shipments, 25 tasks.
- Active stash empty; all four entries archived with `harvested_artifact_id` forward references.
- Operator-owned files (`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
  `.github/agents/_ship.agent.md`, `.gitignore`) never staged and left modified in the worktree.

**Ship claims `059-S` first, then `060-S`.**

### Round 5's suppressed findings (fixed in PR #178)

Copilot round 5 emitted **zero review threads** but its review body listed 7 suppressed
"previously missed" findings. I initially recorded the round as clean; round 6 caught that.
All 7 were valid:

1. **A.T2b created an unowned `crawl()` caller.** `tests/fetch/test_crawl_control_flow.py` is
   written before the return-type break and must inspect returned results, so it needed a
   migration task. Added to A.T7 / `068.008-T` (now four modules).
2. **`crawl()`'s public `Returns:` docstring** promises a list; A.T6 / `068.007-T` now requires
   updating the annotation *and* the Google-style return docs.
3. **The `except BaseException` claim was wrong.** The zero-staged raise happens *after* the
   `try/except/else`, so the success-path callback in the `else` branch has already fired and the
   handler never runs for `CrawlStagedNothingError`. A.T9 / `068.012-T` now states the real
   contract: exactly one completion callback before the error propagates, with the
   `except BaseException` path intact only for failures raised *during* crawl or result staging.
4. **A.T10's textual dependency list omitted A.T7**, and `068.013-T` was missing the
   `068.008-T` edge — so the chain could reach A.T11b's full-`pytest` gate with the crawl-core
   tests unmigrated. Both fixed and verified with `dep list`.

**Process note:** a Copilot review with zero threads is *not* necessarily a clean review. The
review **body** must be read for suppressed findings before declaring a gate clean.
### Round 7-8 findings (PR #178)

1. **`dep add` does not refresh `updated_at`.** Adding the `068.013-T → 068.008-T` edge changed
   the artifact's content but left stale freshness metadata. Refreshed via `backlogit update`.
   Worth remembering alongside the earlier `--dependencies` quirk: **both** dependency paths in
   this CLI have surprising side effects.
2. **`R9` still asserted the old callback contract** after `A.T9` was corrected, so an implementer
   reading the risk register and the task would get contradictory instructions. R9 now carries the
   corrected contract.
3. **`A.T7` grew to four files** when `test_crawl_control_flow.py` was added — breaking the very
   three-file ceiling this plan had invoked to split `A.T8`. Split into `A.T7` (3 files) and new
   **`A.T7b` / `068.019-T`** (1 file), wired into `A.T10`'s dependencies and added to `059-S`,
   which is now **20 items**.
4. **The running finding-total was itself the recurring defect** — corrected twice and stale both
   times. Replaced with a per-round log and an explicit cutoff note.

### Durable lessons

- **Zero review threads does not mean a clean review.** Read the review *body* for suppressed
  findings before declaring any gate clean. This one cost the most.
- **When a plan creates a new caller of an API it is about to change, that caller needs a
  migration owner too.** Searching only the current tree is not enough.
- **Do not record running totals that every subsequent round invalidates.** Log rounds; let the
  last row be the state.
- **A fix that resolves one section can contradict another.** After correcting a contract, grep
  the risk register and every task that references it.
