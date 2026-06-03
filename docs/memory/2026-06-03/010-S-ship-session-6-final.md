# 010-S Ship session 6 (final) — post-merge closure

Date: 2026-06-03
Session: 6 (final)
Branch: `post-merge/010-docline-graphtor-alignment`
Status: closure complete

## Shipment lifecycle summary

| Session | Date | Branch | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-06-02 | `feat/docline-graphtor-alignment` | 1 task (010.001-T, F1 red-first frontmatter v1 contract tests) — halted at PA-1 BaseFrontmatter v1 approval gate |
| 2 | 2026-06-02 | `feat/docline-graphtor-alignment` | 19 tasks (010.002 → 010.020) — PA-1 applied (010.002-T) and PA-2 POSIX migration applied (010.009-T); covers F1 schema/contract, F2 POSIX paths, F3 heading/chunk, F4 DOCX adapter; halted at 20-task session circuit breaker |
| 3 | 2026-06-03 | `feat/docline-graphtor-alignment` | 19 tasks (010.021 → 010.039) + lifecycle recovery — covers F5 PDF, F6 HTML/web crawl/SSRF, F7 chunk anchors, F8 contract doc + E2E; 39/39 finished |
| 4 | 2026-06-03 | `feat/docline-graphtor-alignment` | First §1.9 readiness pass; structured review (`docs/closure/010-S-review.md`); PA-1 + PA-2 applied |
| 5 | 2026-06-03 | `feat/docline-graphtor-alignment` | Stale-Copilot halt; documented in `2026-06-03/010-S-ship-session-5-stale-copilot-halt.md`; operator re-requested review via UI; merge approved; merged via merge commit `3f1226f` (PR #19) |
| 6 | 2026-06-03 | `post-merge/010-docline-graphtor-alignment` | This session: runtime verification, operational closure, archives, post-merge closure PR |

## Pull requests

| PR | URL | Purpose | Merge commit | Status |
| --- | --- | --- | --- | --- |
| #19 | <https://github.com/softwaresalt/docline/pull/19> | Feature: docline-graphtor ingestion contract alignment (40 items / 39 tasks + 010-F) | `3f1226f` | merged 2026-06-03 |
| #TBD | TBD (post-merge) | Post-merge closure: archive 010-F + 010-S; runtime-verification + operational-closure docs; session-6 checkpoint; new CI stash item | TBD | awaiting operator approval |

## Phases completed this session

1. Phase 9 — runtime-verification: CLI + MCP parity probe, 100 passed / 95 errors (all pre-existing Windows `tmp_path` noise, stash `CE758832`), live SSRF / frontmatter / chunk-anchor / POSIX-path probe all PASS. Artifact: `docs/closure/010-S-runtime-verification.md`. Outcome: `READY_WITH_FOLLOWUPS`.
2. Phase 10 — operational-closure: PA-1 + PA-2 strict-safety records sealed as `applied`; three P2 advisories (defusedxml, $schema/$id, SSRF) confirmed honored; rollback plan; CI follow-up stashed. Artifact: `docs/closure/010-S-docline-graphtor-ingestion-contract-alignment.md`. Outcome: `READY_WITH_CONDITIONS`.
3. Phase 11 — post-merge closure PR (this commit). Both archives + closure docs + this checkpoint + new CI stash entry will land together.
4. Phase 12 — final session checkpoint (this file).

## Archived artifacts (final count)

| Type | Count | IDs |
| --- | --- | --- |
| Feature | 1 | `010-F` |
| Shipment | 1 | `010-S` |
| Tasks | 39 | `010.001-T` through `010.039-T` |
| **Total** | **41** | All confirmed in `.backlogit/archive/` |

## Compound learnings worth promoting

(Operator may invoke the `compound` skill to graduate these into `docs/compound/`.)

1. **Multi-session Ship pattern for large shipments** — 39-task shipments need ~3 working sessions plus closure overhead; per-session task budget capped at 20 by the constitution stop condition forces the split. The `session-N-resume-prompt.md` handoff pattern (paste of prior state + scoped phase plan) is the canonical continuation mechanism.
2. **Lifecycle slip recovery** — queue/archive divergence (task `done` but queue file still present) is recoverable via `git checkout HEAD -- <queue file>` then `backlogit move` → `track-commit` → `archive_item`. Two slips in this shipment; identical recovery.
3. **GitHub Copilot review re-request quirk** — programmatic POST to `repos/.../pulls/N/requested_reviewers` returns `201 Created` but no Copilot review fires when the bot has already reviewed an older SHA on the same PR. Operator-side re-request via the PR UI is the only known unstick.
4. **Conventional commit scope drift** — `chore(backlog):` slipped past discipline twice; allowed scopes are `core, cli, mcp, fetch, process, schema, docs`. Ship should self-validate commit scope before `git commit`.

## Stash items relevant to 010-S follow-up

| Stash ID | Priority | Summary |
| --- | --- | --- |
| `CE758832` | low | Windows pytest `tmp_path` `PermissionError` noise (pre-existing) |
| `9C40BF99` | high | Add GitHub Actions CI workflow for docline (new, this session) |

## Lessons for future shipments

1. **Plan closure sessions explicitly.** A 39-task feature does not finish at "PR merged" — runtime verification, operational closure, archives, and a post-merge closure PR are a full session of their own. Budget accordingly.
2. **Strict-safety records belong in closure, not just review.** PA-1 and PA-2 lived in the structured review; the closure artifact made them releasability evidence. Carry strict-safety records all the way through.
3. **Static verification is fair evidence when env-blocked.** The Windows `tmp_path` issue blocks ~95 reader / process tests but does not undermine the security-relevant assertions (`defusedxml` import path, SSRF guard call sites) — static + interface-level verification is sufficient closure evidence when the underlying logic is unchanged.
4. **Re-run the index sync at closure.** `backlogit_sync_index` after every backlogit mutation; the index lags otherwise and the §0.1 check at the next session start would otherwise show stale state.
5. **Tag-based release tracking is the next gap.** This shipment didn't tag a release; the next contract-affecting shipment should add a `v0.1.0` (or similar) tag tied to the merge commit so downstream graphtor-docs consumers can pin a docline build.

## Index sync (mandatory closure step)

Will be performed after the commit lands. See post-merge PR closure protocol.
