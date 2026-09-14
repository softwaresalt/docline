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
closure_status: READY
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

## Residual Follow-Ups (reconciled — includes 4 newly captured this closure session)

The following P-021 deferred-scope-expansion stash entries are `shipment=063-S`-tagged.
Fourteen were captured during pre-merge build/review work for this shipment (and, for
entries inherited from superseded PR #198's lineage, during that PR's review cycles).
Four more (`9D44B6F3`, `1C433464`, `E7878B1B`, `E0B6EE0D`) are newly captured during this
closure session: PR #199's own `## Local Review Readiness` body text documented these as
follow-up findings without formally stashing them, and this closure session performs that
threadless-path P-021 C2 capture (Ship Step 6 item 6 — follow-ups identified by the
closure artifact must be stashed). Of the 14 pre-existing entries, 2 (`E462E1F0`,
`E89DC095`) were fixed pre-merge via commit `c547f93` (known-scheme-allowlist fix) and no
longer describe open residual risk — they are retained below as a historical record only,
per Ship's role boundary (Ship may create new stash entries but does not edit, archive, or
remove existing ones; stash entry lifecycle/disposition remains Stage-only). **Reconciled
total: 18 tagged entries, 2 fixed/historical, 16 open for Stage triage/deliberation** (none
P0/P1).

| ID | Priority | Status | Summary |
|---|---|---|---|
| `0F1A653C` | high | open | Default (non-`--execute`) docline fetch path still has an unsanitized `source_key` sink (`orchestrate_fetch`/`create_staging_job`) |
| `06A59B1D` | medium | open | `_CREDENTIAL_PARAM_PREFIXES` coverage expansion (password/pwd/passwd/client_secret/refresh_token/code) |
| `95BD0DC7` | low | open | Exception `__notes__` (PEP 678) not scrubbed by `_clone_scrubbed_exception` (currently unreachable — no `add_note` call sites) |
| `709BDB53` | low | open | `ExceptionGroup`/`BaseExceptionGroup` chains not traversed by scrubbing (currently unreachable — no `TaskGroup`/`gather` usage) |
| `6076A65E` | low | open | Non-idempotent redaction passes can duplicate `<redacted>` sentinels |
| `4CEE1EA5` | low | open | `_is_url_shaped` over-broad bare `//`-prefix detection |
| `1B5CEF80` | low | open | "Architecturally unreachable" characterization on 95BD0DC7/709BDB53 needs periodic re-verification |
| `A6D7EEB9` | (see entry) | open | Percent-encoded query-separator hides a nested credential |
| `96E6C3F2` | (see entry) | open | `#`-fragment credential in exception scrubbers (deferred at #198's 3-cycle circuit-breaker limit) |
| `7D7222E3` | (see entry) | open | Nested URL as a query value bypasses outer-authority-only scrub |
| `E462E1F0` | high | **fixed (`c547f93`)** | `_URL_SCHEME_RE` relaxation (`:/*`) widened matching — closed via known-scheme allowlist; no longer open residual risk |
| `E89DC095` | high | **fixed (`c547f93`)** | `_URL_SCHEME_RE` scheme-name character class excludes underscore — closed via known-scheme allowlist; no longer open residual risk |
| `BF028CAE` | (see entry) | open | F2 residual from the E462E1F0/E89DC095 fix, deferred |
| `12925B3B` | (see entry) | open | Round-8 disputed/false-positive credential-leak claim on `sanitize_source_id`, deferred with discovery-lookup result |
| `9D44B6F3` | medium | open (new) | Unicode format-category (`Cf`) character (e.g. U+200B, U+FEFF, U+2060) bypasses the `lstrip()`-based leading-whitespace fail-closed guard in `_sanitize_url_field` |
| `1C433464` | medium | open (new) | `_contains_userinfo_marker`'s ambiguous-authority (`count("@") != 1`) branch is unconditionally fail-closed while the single-`@` branch is allowlist-gated — a safe-direction (over-redaction) asymmetry |
| `E7878B1B` | low | open (new, advisory) | Possible redundancy between `_remove_credential_query_params` and `_strip_reversed_query_credentials` |
| `E0B6EE0D` | low | open (new, advisory) | Pre-existing cross-module private-symbol imports (`_is_credential_name`, `_strip_reversed_query_credentials`) from `source_keys.py` into `execute.py` |

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

**READY** — shipment `063-S`'s own substantive releasability is complete: all required
runtime-verification evidence passed (see above), the shipped feature (`072-F`) is fully
archived, and no blocking (P0/P1) risk remains against the shipped code. The 16 open
residual deferred-scope-expansion stash entries recorded above are informational and
non-blocking — none are P0/P1 and none gate this shipment's releasability; re-prioritization
and any decision to pick them up remains Stage-only (P-021 C6).

This post-merge closure PR (this branch, `post-merge/063-s-sanitize-credential-bearing-
source-key`) requires its own separate explicit operator approval before merge — not yet
obtained as of this writing. That approval requirement is the ordinary, always-present
state of any not-yet-merged closure PR and does not gate `063-S`'s own releasability
status; see `docs/closure/063-S-072-F-post-merge-closure.md`'s `closure_merge_commit`/
`closure_reviewed_head` fields (left `null` until this PR merges) for how that is tracked.

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

Four new P-021 deferred-scope-expansion stash entries were captured during this closure
session (`9D44B6F3`, `1C433464`, `E7878B1B`, `E0B6EE0D`) — see Residual Follow-Ups above
for full detail. These are threadless-path captures (PR #199's own body text documented
them as follow-up findings without formally stashing them at the time); Ship Step 6 item 6
requires stashing follow-ups identified by the closure artifact, so this closure session
performs that capture. All 14 previously-existing residual entries remain unchanged
(Ship's role boundary permits creating new stash entries but not editing, archiving, or
removing existing ones).
