---
artifact_type: closure
shipment_id: 063-S
feature_id: 072-F
title: 063-S Sanitize credential-bearing source_key on ELT error/persistence paths — post-merge closure
created_at: 2026-09-13T20:20:00-07:00
mode: post-merge
verifier: ship-agent
feature_pr: 199
feature_merge_commit: 3933dfc335e19bcd602bf104e82728268ae83156
reviewed_head: f1f5f8fd82fe83cc8095e210eac5ba47ccaf60cb
compaction_status: done
closure_status: READY_WITH_CONDITIONS
---

# 063-S / 072-F Post-Merge Closure

## Summary of Change

Adds a typed-config credential sanitizer (`sanitize_source_key`,
`sanitize_source_id`, `_sanitize_url_field` in `src/docline/elt/source_keys.py`,
wired through `src/docline/elt/execute.py`'s `_execute_single_source`) so a
credential-bearing `source_key` (userinfo + credential query params embedded in
a `web_crawl:`/`manifest_url:`/`github_repo:`/`manifest_git:` source) is never
persisted unredacted to `metadata.json` and never logged unredacted on ELT
error paths, including through exception-chain scrubbing
(`_clone_scrubbed_exception`).

## Merge Confirmation

* Feature PR [#199](https://github.com/softwaresalt/docline/pull/199) merged
  to `main` at `2026-09-14T03:02:32Z` with merge commit
  `3933dfc335e19bcd602bf104e82728268ae83156` (reviewed HEAD
  `f1f5f8fd82fe83cc8095e210eac5ba47ccaf60cb`).
* Ancestry confirmed: `git merge-base --is-ancestor 3933dfc origin/main` → exit 0.
* PR #199 replaced (superseded) PR #198, which is closed and retained (branch
  preserved) for review-history lineage. #198's branch was not deleted or
  rewritten.
* Operator approval: explicit message `PR 199: Merge approved` (approval
  contract: PR #199 only, approved reviewed HEAD `f1f5f8f`, merge-commit
  strategy, admin fallback not authorized, scope 063-S only). All conditions
  matched at merge time; normal merge (`gh pr merge --merge`) succeeded
  without admin fallback.

## Review & CI Evidence (restated from PR #199)

* Local Review Readiness: reviewed HEAD `f1f5f8f`, outcome
  `READY_WITH_FOLLOWUPS`, P0=0/P1=0.
* CI: all 8 required checks green (`detect code changes`, `pipeline-topology
  (ambient)`, `ruff lint`, `ruff format check`, `pyright`, `pytest
  (ubuntu-latest)`, `sdist + wheel`, `ci gate`).
* P-018 Copilot-review gate: `SATISFIED` for HEAD `f1f5f8f`, 0 unresolved
  threads.
* Quality gates at final HEAD: `ruff check .` clean, `ruff format --check .`
  clean (302 files), `pytest -q` 2346 passed / 6 skipped / 0 failed, `python -m
  build` succeeded.

## Runtime Verification

See
[`2026-09-13-sanitize-source-key-elt-error-paths-runtime-verification.md`](2026-09-13-sanitize-source-key-elt-error-paths-runtime-verification.md).

**Verdict: PASS_WITH_FOLLOW_UP.**

* CLI surface (`docline --help`, `docline --manifest`): PASS.
* MCP/API surface: `initialize` handshake PASS (automated this session);
  `tools/list` PASS (matches the intentional, pre-existing, documented
  callable-tool allow-list — `ingest_local_dir` is deliberately excluded from
  the untrusted MCP surface per `list_callable_tools()`, unrelated to and
  unmodified by this shipment).
* Change-specific functional verification: targeted pytest (114/114 passed)
  plus a live probe confirming `sanitize_source_key` fully strips userinfo and
  credential query parameters from a representative `web_crawl` source.
* No new findings; existing deferred residual risk stands (see Residual
  Follow-Ups below).

## Shipment / Backlog Reconciliation

* Pre-mode reconciliation (`expected_status: done`):
  `.backlogit/reconcile/063-S-pre-20260913T200543Z.md` —
  **PROCEED** (all 5 manifest items `pre-archived`; shipment record
  `record-consistent`; 0 orphans).
* P-015 classification: `classify_shipment_close_path` → **CASCADE** (root
  feature `072-F`, fully covered by manifest tasks `072.001-T`–`072.004-T`,
  terminal, no linked deliberation).
* Cascade close executed: `backlogit shipment ship 063-S --sha 3933dfc...`
  → `shipment_status: shipped`, `archived_ids: [072.001-T, 072.002-T,
  072.003-T, 072.004-T, 063-S, 072-F]`, `returned_ids: []`.
* Two-set gate verified: `archived_ids - allowed_ids = {}`,
  `required_ids - archived_ids = {}`. `parent_id` preserved on all 4 tasks.
  Provenance verified: `063-S` → `archived_status: shipped`; `072-F` and all
  4 tasks → `archived_status: done`.
  Full detail:
  `.backlogit/reconcile/063-S-safe-close-20260913T200543Z.md`.
* Post-mode reconciliation: archive presence confirmed for all 6 artifacts
  (shipment + feature + 4 tasks); no unrestored deletions
  (`git status --short -- .backlogit/archive/` showed only the expected
  rename/modifications) — **PROCEED**.
* `backlogit shipment get 063-S` now reports `status: archived`,
  `archived_status: shipped`, `commit: 3933dfc335e19bcd602bf104e82728268ae83156`.

## Source Artifact Cleanup

* `072-F.custom_fields.source_stash_id`: **not present**. The originating
  stash entry `D6E758F5` (referenced only in the feature's title/labels, e.g.
  `stash-D6E758F5`) is no longer present in `.backlogit/stash.jsonl` — it was
  already consumed by the `harvest_stash` operation that created `072-F`
  (harvest removes the source line directly; it does not leave a separate
  archivable stash artifact). No further archival action needed or possible.
* `072-F.custom_fields.source_deliberation_id`: **not present**. No linked
  deliberation ID found in `072-F`'s `custom_fields`, description, or
  references matching the deliberation-ID pattern. No further action.

## Residual Follow-Ups (already captured — no new stash entries)

The following P-021 deferred-scope-expansion stash entries were captured
during pre-merge build/review work for this shipment (and, for entries
inherited from superseded PR #198's lineage, during that PR's review cycles)
and remain **unchanged** by this closure — Ship creates no new stash entries
here because nothing new was identified by runtime-verification or
operational-closure beyond what is already recorded:

| ID | Priority | Summary |
|---|---|---|
| `0F1A653C` | high | Default (non-`--execute`) docline fetch path still has an unsanitized `source_key` sink (`orchestrate_fetch`/`create_staging_job`) |
| `06A59B1D` | medium | `_CREDENTIAL_PARAM_PREFIXES` coverage expansion (password/pwd/passwd/client_secret/refresh_token/code) |
| `95BD0DC7` | low | Exception `__notes__` (PEP 678) not scrubbed by `_clone_scrubbed_exception` (currently unreachable — no `add_note` call sites) |
| `709BDB53` | low | `ExceptionGroup`/`BaseExceptionGroup` chains not traversed by scrubbing (currently unreachable — no `TaskGroup`/`gather` usage) |
| `6076A65E` | low | Non-idempotent redaction passes can duplicate `<redacted>` sentinels |
| `4CEE1EA5` | low | `_is_url_shaped` over-broad bare `//`-prefix detection |
| `1B5CEF80` | low | "Architecturally unreachable" characterization on 95BD0DC7/709BDB53 needs periodic re-verification |
| `A6D7EEB9` | (see entry) | Percent-encoded query-separator hides a nested credential |
| `96E6C3F2` | (see entry) | `#`-fragment credential in exception scrubbers (deferred at #198's 3-cycle circuit-breaker limit) |
| `7D7222E3` | (see entry) | Nested URL as a query value bypasses outer-authority-only scrub |
| `E462E1F0` | high | `_URL_SCHEME_RE` relaxation (`:/*`) widened matching (known-scheme-allowlist fix landed; residual risk recorded) |
| `E89DC095` | high | `_URL_SCHEME_RE` scheme-name character class excludes underscore |
| `BF028CAE` | (see entry) | F2 residual from the E462E1F0/E89DC095 fix, deferred |
| `12925B3B` | (see entry) | Round-8 disputed/false-positive credential-leak claim on `sanitize_source_id`, deferred with discovery-lookup result |

All entries carry `requires_deliberation` flags and provisional priorities
per P-021 C6 — re-prioritization and any decision to pick up this work
remains Stage-only.

## Compaction Status (P-020)

**done** — `compact-context --target all` invoked at this closure step. Compacted 3
memory checkpoint files into `docs/memory/compacted/2026-09-13-063-s-compacted.md`
(originals archived to `docs/archive/memory/2026-09-13/`) and consolidated the plan
(8 revisions + review history) into
`docs/plans/2026-09-12-source-key-credential-sanitization-decided-plan.md` (original
archived to `docs/archive/plans/`). The carry-forward checkpoint file
(`docs/memory/2026-09-14/063-s-bounded-extension-round8-9-checkpoint.md`) was
intentionally excluded per the explicit carry-forward preservation directive for this
session and is also too recent for the default age threshold. See
[`063-S-072-F-post-merge-closure.md`](063-S-072-F-post-merge-closure.md) for the
machine-readable pointer record.

## Closure Status

**READY_WITH_CONDITIONS**

* **Condition 1** (informational, not blocking): the 14 residual deferred
  stash entries above remain open for Stage triage/deliberation; none are
  P0/P1 and none block this shipment's releasability.
* **Condition 2**: the post-merge closure PR (this branch,
  `post-merge/063-s-sanitize-credential-bearing-source-key`) requires its own
  separate explicit operator approval before merge — not yet obtained as of
  this writing.

## Monitoring / Rollback (release-observability)

* **Healthy signal**: no credential-bearing `source_key` values appear in
  `metadata.json` or ELT ERROR-level logs for any fetch source type.
* **Failure signal**: a raw userinfo (`user:pass@`) or credential query
  parameter (`token=`, `password=`, etc.) observed in persisted metadata or
  logs for `web_crawl:`/`manifest_url:`/`github_repo:`/`manifest_git:`
  sources.
* **Rollback trigger**: any confirmed credential leak via the sanitizer paths
  touched by this shipment.
* **Rollback procedure**: revert merge commit `3933dfc335e19bcd602bf104e82728268ae83156`
  on `main`; re-open PR #199 or file a new fix shipment.
* **Validation window**: next 2 weeks of ELT fetch runs across configured
  source types (operator-observed; no automated dashboard exists for this
  CLI/library surface).
* **Owner**: repository operator (softwaresalt).

## Follow-Up Tasks Stashed by This Closure

None — all identified follow-ups were already captured as stash entries prior
to this closure session (see Residual Follow-Ups above). No new stash items
created.
