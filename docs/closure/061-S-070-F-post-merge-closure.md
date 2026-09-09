---
shipment: 061-S
feature: 070-F
tasks:
    - 070.001-T
    - 070.002-T
    - 070.003-T
    - 070.004-T
    - 070.005-T
    - 070.006-T
    - 070.007-T
    - 070.008-T
    - 070.009-T
    - 070.010-T
    - 070.011-T
feature_pr: 190
closure_pr: 191
merge_commit: b355041a713931db3f8ed06af64a78ea3194e49b
merged_at: "2026-09-09T18:42:05Z"
reviewed_head: 3397af4670d55788dc793caf1112f3637d22eeb6
closure_merge_commit: null
closure_reviewed_head: null
closure_status: READY
compaction_status: done
---

# 061-S / 070-F Post-Merge Closure — SPA/API-aware Crawl Link Discovery

Shipment 061-S (feature 070-F) resolved the operator-reported defect: `web_crawl` of a
Terraform Registry provider-docs start URL (for example
`https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`) previously fetched
only the one-page JavaScript SPA app-shell instead of the provider's full documentation set
(1,620 `azurerm` docs). The fix adds a pluggable, browserless discovery-source seam
(`src/docline/fetch/link_sources.py`) to the bounded crawl executor, plus a concrete Terraform
Registry v2 JSON:API adapter (`src/docline/fetch/tf_registry_source.py`), composed into
`crawl()` additively alongside static HTML link extraction, with `CrawlConfig.enable_api_discovery`
threaded end-to-end through the public `FetchRequest`/`WebCrawlSource`/`ManifestUrlSource`
surfaces as an operator-facing kill switch.

Full design/investigation record:
`docs/plans/2026-09-08-spa-api-crawl-discovery-decided-plan.md` (compacted decided-plan summary,
current) — the detailed, adversarially-reviewed original (PASS, attempt 3) is preserved at
`docs/archive/plans/2026-09-08-spa-api-crawl-discovery-plan.md` — and
`docs/decisions/2026-09-08-spa-api-crawl-discovery-deliberation.md`.

## Merge Confirmation

- Feature PR #190 merged to `main` at `2026-09-09T18:42:05Z` with merge commit
  `b355041a713931db3f8ed06af64a78ea3194e49b`.
- `git fetch origin main` + `git merge-base --is-ancestor b355041a... origin/main` confirmed
  exit 0.
- Merge used the merge-commit strategy (repo settings confirmed: `allow_merge_commit: true`,
  `allow_squash_merge: false`, `allow_rebase_merge: false`); no admin fallback was used.

## Pre-Merge Gate State (PR #190, reverified immediately before merge)

| Gate | PR #190 |
| --- | --- |
| CI | green at final HEAD `3397af4` (`ci gate`, `pyright`, `ruff lint`, `ruff format check`, `pytest (ubuntu-latest)`, `sdist + wheel`, `detect code changes`, `pipeline-topology (ambient)`) |
| P-018 Copilot review (`autoharness gate copilot-review`) | `SATISFIED` at final HEAD `3397af4` (re-confirmed immediately before merge, unconditionally) after **6 review rounds, 14 threads, all resolved** — see "Local + Copilot Review" below |
| P-014 local review readiness | `## Local Review Readiness` block present at reviewed HEAD `3397af4`, outcome `READY_WITH_FOLLOWUPS`, 0 unresolved P0/P1, full local build evidence (`uv run python -m build` PASS; full `pytest` 2112 passed / 6 skipped), 5 follow-up stash IDs recorded |
| Operator merge authorization | The operator's task instructions repeatedly directed autonomous implementation through true completion, explicitly treated as the P-014 approval signal for in-scope PR merges once every mandatory readiness/CI/Copilot-review/P-009/P-016/security/runtime gate passed — satisfied once all gates above passed; no admin fallback, no force override used |
| `pipeline-topology --phase lifecycle` | Passed cleanly at every invocation (pre-claim, post-claim, and pre-PR lifecycle checks) — no override needed for this shipment |
| P-009 (merge strategy) | Confirmed merge-commit-only repo configuration before executing `gh pr merge --merge` |

## Local + Copilot Review

**Local adversarial review** (5 personas: Correctness, Security, Python, Maintainability,
Constitution reviewers, plus a direct scope-boundary check) found and this PR fixed 2 P1s and 4
P2s before PR creation: a pinned-version silent-wrong-content bug, a non-hermetic test that could
attempt live network I/O, a frontier-truncation false-positive, a `.`/`..` path-segment allowlist
gap, a missing final-response-URL host check, and a missing INFO observability log (commit
`10bb4a1`).

**Copilot automated review** ran 6 rounds across the PR's lifetime, raising 14 total review
threads. **13 were fixed with regression tests**; **1 was deferred** (see below) — not all 14
were fixes:

1. Off-host redirect exposure — fixed via `max_redirects=0` for every adapter-internal API fetch.
2. `max_depth=0` default-contract interaction — clarified in docstrings (discovery is additive to
   static extraction regardless of depth), not code-gated.
3. Robots.txt bypass for the discovery seed — fixed by gating the seed on the same cached
   `_robots_allow()` check the main loop performs.
4. Cyclic `links.next` pagination risk — fixed by tracking seen pagination URLs.
5. `enable_api_discovery` unreachable from the public CLI/MCP/YAML surface — fixed end-to-end
   through `FetchRequest`/`WebCrawlSource`/`ManifestUrlSource`.
6. `max_pages`/1,620-doc expectation-setting gap — clarified in `docs/ARCHITECTURE.md`.
7. Guaranteed-unused-pagination-work efficiency issue — fixed by stopping the seed once the
   frontier queue covers the page budget.
8. Stale PR readiness record after HEAD advanced — fixed by re-running the readiness
   verification and updating the record.
9. Same-host cleartext-downgrade/non-standard-port gap in origin checks — fixed with a shared
   `_is_registry_origin` helper.
10. Malformed-port crash risk plus a recognizer/pagination origin-check inconsistency — fixed by
    hardening that helper and reusing it in the recognizer.
11. Malformed-IPv6-authority crash risk in that same helper and the recognizer — fixed by
    guarding the whole parse, not just the port access.

One finding (per-endpoint `robots.txt` enforcement for the adapter's own internal API calls) was
deferred via stash `0EE542D9`, since it asks for stricter behavior than the codebase's existing
precedent for auxiliary discovery fetches (mdBook `toc-*.js` scripts are not individually
robots-checked either).

## Live Runtime Verification (real Terraform Registry, bounded)

Live verification against this branch's own code (real network access confirmed available)
caught and fixed one additional critical defect **no fixture-based test could catch**:
`_resolve_provider_version` assumed a singular `relationships["latest-version"]` relationship
that does **not exist** in the real API response at all — confirmed by directly querying
`GET /v2/providers/hashicorp/azurerm?include=provider-versions` (real response exposes
`provider-versions` as a plain list of every published version, 405 for azurerm, with no
explicit "latest" flag anywhere). Fixed by selecting the maximum `published-at` timestamp
across the real `included` provider-versions set (commit `5ebbe98`).

Post-fix, a real, bounded `crawl()` call against
`https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`
(`max_pages=8, max_frontier=200`) discovered and fetched **7 additional real, distinct
provider-doc pages** beyond the start page (all HTTP 200, `frontier_truncated=False`) —
concretely resolving the operator's original one-page-only bug report against the *live*
target. The same call with `enable_api_discovery=False` reproduces the **exact original
one-page defect** (1 result), confirming the disable switch is a genuine, verified rollback
mechanism. Re-verified again after each subsequent hardening commit (scheme/port confinement,
malformed-port guard, IPv6-parse guard) — the live crawl continued to discover and fetch
multiple real pages correctly after every fix. Bounded settings were used throughout
(`max_pages` between 4 and 8 across re-verification runs) to avoid the uncontrolled ~1,620-page
cost of a full crawl, per the operator's explicit instruction.

## CLI/MCP Parity

`enable_api_discovery` is a schema addition to `FetchRequest` (MCP `fetch` tool + CLI's
underlying `execute_fetch`), `WebCrawlSource` (flat YAML `type: web_crawl`), and
`ManifestUrlSource` (graphtor-docs manifest `type: url`). The MCP tool schema picks up the new
field automatically via `FetchRequest.model_json_schema()` (Pydantic auto-derivation) — no
separate hand-maintained MCP schema existed to update. No new CLI flag was needed since CLI
web-crawl fields are reached via YAML manifest configs, not `argparse` flags. Parity verified by
`test_manifest_fetch_schema_advertises_enable_api_discovery`,
`test_manifest_url_source_parses_enable_api_discovery_false`, and
`test_execute_fetch_maps_enable_api_discovery_false`/`_default_true`.

## Compound Learnings

* Appended a "Refinement (061-S, 2026-09-09)" section to
  `docs/compound/2026-08-29-admission-cap-must-short-circuit-discovery.md`, extending the
  existing admission-cap lesson from a static in-memory candidate list to a paginated,
  network-backed async producer: the check-before-pull ordering generalizes but the cost model
  differs, and `max_frontier=0`/`max_pages` both needed explicit guards distinct from the
  within-loop short-circuit.
* Captured a new entry,
  `docs/compound/2026-09-09-third-party-api-shape-requires-live-verification.md`: passing tests
  against self-consistent fixtures is not evidence the fixtures match reality — the
  `_resolve_provider_version` real-API-shape defect (see "Live Runtime Verification" above)
  passed every fixture-based test, quality gate, and review round, and was only found by a
  mandatory live query against the real endpoint.

## Backlog Reconciliation (P-015)

`070-F`'s manifest (root feature, no `parent_id`; fully covered at every depth by its 11
manifest-member children `070.001-T`..`070.011-T`, confirmed via a direct `parent_id` query
before invoking the cascade — no member's own subtasks exist; nothing beyond the qualifying
root feature and its children in the manifest) qualified for the P-015 verified
fully-covered-root cascade exception.

`backlogit shipment ship 061-S --sha b355041a713931db3f8ed06af64a78ea3194e49b` was used in
place of manual safe-close, per that exception.

| Check | Result |
| --- | --- |
| `returned_ids` | `[]` |
| `archived_ids` (raw response) | 13 items — `070-F`, all 11 `070.0NN-T` tasks, `061-S` |
| Two-set gate (`allowed_ids`/`required_ids`) | Both satisfied exactly: no unexpected artifact archived, no required artifact missing |
| Shipment record | `061-S`: `status: archived`, `archived_status: shipped`, `commit: b355041a713931db3f8ed06af64a78ea3194e49b` (genuine `shipped` provenance) |
| Feature record | `070-F`: `status: archived`, `archived_status: done`, same commit stamped |
| P-007 archive-integrity check | `git status -- ".backlogit/archive/"` showed no deletions — clean |

## Source Artifact Cleanup

Neither `070-F` nor `061-S` carries a structured `custom_fields.source_stash_id` or
`custom_fields.source_deliberation_id` field (070-F's body narratively mentions "Origin stash:
FC174FA7," but this is prose text, not a structured field, so per Ship's role-boundary scope —
limited to retiring a source stash entry via the structured field only — no stash archival was
performed for it). No source artifacts were archived as part of this closure.

## Stash Disposition

Five deferred-scope-expansion stash entries were captured during local + Copilot review, all
low/medium priority, no PR-blocking risk:

| ID | Summary | Priority |
| --- | --- | --- |
| `D548B756` | Discovery-source registry test-isolation/import-time-side-effect hardening | medium |
| `DFF8E8E1` | Adapter defensive-parsing hardening (aclose, broad except, id-collision, type-filter, relative links.next) | low |
| `EF8503EC` | Second-adapter extensibility prep (shared fetch/JSON helper, registrations module, split page-extraction) | low |
| `8E0B4FB5` | Independent pull-count bound in the discovery seed as defense-in-depth | low |
| `0EE542D9` | Per-endpoint `robots.txt` enforcement for the adapter's own internal API calls | low |

No new post-merge-closure follow-ups were identified beyond these five; the live runtime
verification above surfaced no further residual risk requiring a stash entry. `061-S`'s own
scope is fully shipped; stash entries `D6E758F5`, `4C03AE14`, and `6BF410E2` remain untouched
throughout, per the operator's explicit out-of-scope instruction.

## Compaction (P-020)

`compact-context --target all` was invoked as part of this closure. Compaction candidates
identified: the single 061-S session memory file (completed-release-unit rule) and the
2026-09-08 plan file (feature complete, had 2 rounds of appended plan-review content).

* Memory: `docs/memory/2026-09-09/ship-061-s-pre-pr-review-complete.md` compacted into
  `docs/memory/compacted/2026-09-09-061-s-compacted.md`; verbose original archived to
  `docs/archive/memory/2026-09-09/`.
* Plan: `docs/plans/2026-09-08-spa-api-crawl-discovery-plan.md` (with its 2-round plan-review
  transcript) consolidated into
  `docs/plans/2026-09-08-spa-api-crawl-discovery-decided-plan.md`; verbose original archived to
  `docs/archive/plans/`.

`compaction_status: done` above reflects this completed outcome.

**Closure verdict: READY.** All mandatory closure work — merge confirmation, gate re-verification,
review record, live runtime verification proving the original defect is resolved, CLI/MCP parity,
P-015 backlog reconciliation with genuine provenance, source-artifact cleanup, and stash
disposition — is complete. No residual risk beyond the five recorded, non-blocking stash
follow-ups is outstanding for 061-S.
