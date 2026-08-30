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

Four rounds, **26 findings**, all valid, all fixed / replied with fix SHA / thread resolved.

| Round | HEAD | Findings | Substance |
|---|---|---|---|
| 1 | `417b8e9` | 10 | `refused_any` blind to a cap filled by an earlier page; `D8` hard-coded `true`; CLI seam was a no-op edit; stale deliberation option; stale rollback list; stale frontmatter |
| 2 | `b6f3700` | 10 | TOC-only false negative; `job` not constructed until after the `except` block; `max_frontier` remedy not reachable by operators; missing `A.T12→A.T4` edge; archive forward refs; stale memory counts |
| 3 | `cecbddb` | 4 | `tests/parity/test_equivalence.py` asserts the **exact** `FetchResult` field set — a hard blocker; a 10th caller module (`test_execute_fetch_progress.py`) |
| 4 | `f1f85e8` | 2 | two internal count inconsistencies introduced by my own round-3 edits |
| 5 | `4558b0f` | **0** | clean review on current HEAD |

Three findings changed the design rather than the wording:

1. **The truncation signal was wrong twice.** Round 1: if the cap was filled by an earlier page,
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
sites**. Four callers were found by reviewers across three rounds. `A.T6`'s mandatory pre-flight
re-search now requires matching stub sites, and exact-field contract assertions must be searched
before **any** model change.

### Final state on `origin/main`

- 29 artifacts, all `queued`: 2 features, 2 shipments, 25 tasks.
- Active stash empty; all four entries archived with `harvested_artifact_id` forward references.
- Operator-owned files (`.autoharness/config.yaml`, `.github/agents/_orchestrator.agent.md`,
  `.github/agents/_ship.agent.md`, `.gitignore`) never staged and left modified in the worktree.

**Ship claims `059-S` first, then `060-S`.**
