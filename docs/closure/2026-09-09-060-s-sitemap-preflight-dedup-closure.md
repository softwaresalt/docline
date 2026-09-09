---
title: "Operational closure: 060-S sitemap preflight de-duplication"
date: 2026-09-09
shipment: 060-S
feature: 069-F
pr: 186
merge_commit: f278cffc9743d19cae410a9ea7623bfeec0c7649
status: closed
compaction_status: done
---

## Released scope

| Item | Type | Commit |
|---|---|---|
| `069-F` | feature | `f278cff` (merge, via shipment cascade close) |
| `069.001-T` | task — B.T1 harness: one hostname resolution per `fetch_sitemap` (red) | `4d63388` |
| `069.002-T` | task — B.T2 migrate hostname-resolution assertions to `fetch_sitemap` (red) | `5ec9c63` |
| `069.003-T` | task — B.T3 strip hostname resolution from the preflight | `4226bb6` |
| `069.004-T` | task — B.T4 re-baseline the pinned-sink resolution schedules | `1662292` |
| `069.005-T` | task — B.T5 make the proxy-suppression exit criterion falsifiable | `39adc16` |
| `069.006-T` | task — B.T6 reconcile `sitemap.py` docstrings | `5a090a3` |
| `069.007-T` | task — B.T7 record the single-resolution model in `ARCHITECTURE.md` | `42b01d5` |

Copilot review remediation (4 fix commits across the review cycles, all threads resolved)
landed across `9dd9af1`, `224bead`, `a2524fd`, and `72d5d1b` on the same PR branch — see "Bot
review" below.

All 9 artifacts (shipment, feature, 7 tasks) are archived under `.backlogit/archive/` via
`backlogit shipment ship 060-S --sha f278cff...`, which completed successfully in the primary
workspace (~90s; the isolated-worktree deadlock documented for 059-S in
`docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md` did not recur here). The
shipment carries genuine `archived_status: shipped` provenance — `returned_ids: []` confirms no
unintended requeue or detachment outside the manifest.

## What shipped

`docline.fetch.sitemap.validate_sitemap_url` is now a deterministic, resolution-free SSRF
preflight: scheme allow-list, host presence, cloud-metadata hostname string match, and (for
IP-literal hosts only) reserved-address classification via the shared
`is_unsafe_resolved_address` predicate — never a DNS lookup for a hostname. The now-orphaned
`_resolve_all_addresses` helper and its `socket` import are deleted. `fetch_page` (unchanged,
read-only for this shipment) remains the sole authoritative hostname resolver and address gate;
`fetch_sitemap`'s executor-offload and deadline-arithmetic body is unchanged (D3, scope-preserving
per the plan's round-2 review finding).

Net effect: `fetch_sitemap` resolves the original hostname **exactly once** per successful,
non-redirected fetch (previously twice — once in the advisory preflight, once in `fetch_page`'s
connect). A followed redirect target is still resolved twice (revalidation precheck + pinned
connect) — unchanged, and now the only place a fetch resolves more than once.

## Risky action record

| Field | Value |
|---|---|
| ProposedAction | Remove the sitemap preflight's own DNS resolution, leaving `fetch_page` as the sole resolver/address gate |
| Targets | `src/docline/fetch/sitemap.py`; `tests/fetch/test_sitemap.py`, `test_sitemap_pinned_sink.py`, `test_sitemap_resolution_count.py` (new); `docs/ARCHITECTURE.md` |
| Change kind | Local edit to a security-adjacent preflight; net deletion (one helper + one import); no config, data, schema, or migration |
| ActionRisk | moderate — touches an SSRF-relevant code path, but `http.py`/`url_policy.py` (the actual authoritative gate) are read-only for this shipment, and the change is a pure de-duplication with no address-class dropped |
| Rollback | `git revert -m 1 f278cffc9743d19cae410a9ea7623bfeec0c7649` — pure source + test change, no persisted artifact, no migration; a revert restores the double resolution (a performance regression, never a security regression, since the authoritative gate is untouched in both directions) |
| Approval | Operator's task instruction explicitly authorized "merge after all mandatory readiness and Copilot-review gates pass" for 060-S, conditioned on those gates passing — satisfied (see Verification below) |
| ActionResult | applied |

## Authorized topology-gate override (carried forward from pre-merge)

Shipment 060-S was topology-gated on predecessor 059-S reaching a genuine `shipped` terminal
state; 059-S's post-merge closure had used the single-artifact safe-close fallback (documented
deadlock workaround), leaving `archived_status: active` rather than `shipped`. The operator
explicitly authorized, for shipment 060-S only, forcing the `pipeline-topology` gate citing 059-S's
verified material completeness (merge ancestry, full archival, commit backfill) — never
fabricating 059-S's own provenance. The override was applied identically at every phase the gate
recurred with the same root cause (`pre_claim` x2, `post_claim`, `lifecycle` x3), all audited under
`.autoharness/gates/060-S-*-force-audit.json` (committed). This closure's own shipment-cascade
close (see "Released scope" above) gives 060-S genuine `shipped` provenance, so **060-S itself will
not need a similar override to unblock 061-S** — the workaround was scoped to the historical 059-S
gap and does not propagate forward.

## Verification

### Quality gates

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `ruff format --check .` | pass (287-288 files already formatted across the session) |
| `pyright src/` | 0 errors, 0 warnings |
| `pytest` | 2057 passed, 6 skipped (full suite, verified multiple times across the session) |
| `uv run python -m build` | sdist + wheel built successfully (full local build for a code-changing PR) |

CI on PR #186's final head `72d5d1b` was green on all required jobs: `ci gate`, `pyright`,
`ruff lint`, `ruff format check`, `pytest (ubuntu-latest)`, `sdist + wheel`, `detect code changes`.
The advisory `pipeline-topology (ambient)` CI job reported the same `PREDECESSOR_NOT_SHIPPED`
block as the local gate (expected — CI cannot apply the operator-authorized `--force`); this job is
`continue-on-error: true` by repository configuration (`PIPELINE_TOPOLOGY_GATE_REQUIRED` unset) and
did not affect `ci gate`.

### Test-first evidence

069.001-T and 069.002-T (harness tasks) were written and verified red against the pre-change
source — 9 failures, every one an expected wrong-exception-type or wrong-lookup-count mismatch, no
compile error, no unrelated breakage — before 069.003-T made any source change. 069.003-T's
source change turned both harnesses green and produced the plan's predicted red window in
`test_sitemap_pinned_sink.py` (5 failures, matching D4/D5's stated re-baseline scope exactly).
069.004-T closed that window with zero vacuous passes and zero deleted security tests (the
retired initial-hop rebinding test's coverage was re-expressed, not dropped, on the
redirect-revalidation path, parametrized across the same 4 address classes).

### Runtime verification (post-merge, on `f278cff`)

Executed against merged `origin/main` (via the post-merge closure branch, based on the merged
tree):

```text
fetch_sitemap hostname-lookup count (successful, non-redirected fetch)  -> 1 (was 2 pre-change)
preflight alone, hostname URL, getaddrinfo made to raise if called      -> 0 lookups, PASS
preflight alone, public IP-literal URL, getaddrinfo made to raise       -> 0 lookups, PASS
IP-literal loopback (127.0.0.1)                                        -> SitemapError, PASS
hostname resolving to private (10.0.0.5), end to end through fetch_sitemap
                                                                         -> CrawlUrlRejectedError,
                                                                            zero connections opened, PASS
```

All 5 checks passed. This corroborates, on the freshly merged tree independent of the pytest
suite, the shipment's two headline invariants: exactly one hostname lookup per successful fetch,
and the address gate still rejects an unsafe resolved address before any connection.

## Review record

Local adversarial review (5 personas: Constitution, Security, Correctness, Maintainability,
Python — routed per the diff touching `src/docline/fetch/**`). Zero P0/P1 findings across all
five. Constitution and Security returned `READY`; Correctness, Maintainability, and Python returned
`READY_WITH_FOLLOWUPS` (P2/P3 test-hygiene items only, see "Follow-ups stashed" below).

Copilot review ran 5 cycles against successive HEADs on PR #186, ending with an "Approval
recommended" verdict on the final head `72d5d1b`, zero unresolved threads. Findings remediated
across the cycles:

- An audit-evidence-completeness gap: the PR/memory claimed every `pipeline-topology --force`
  invocation's JSON was preserved, but `pre_claim --force` actually ran twice and only the first
  was separately persisted. Corrected the claim rather than fabricate a backdated artifact (a
  fresh re-run at that point would have reported a different, unrelated block since 060-S was by
  then already `active`).
- Three separate instances of an unscoped "resolves a hostname exactly once **per fetch**" claim
  (in `sitemap.py`, `ARCHITECTURE.md`, and `test_sitemap.py`'s own docstring) that contradicted
  the shipment's own redirect lookup-count table — scoped to the initial hop of a
  non-redirected fetch in all three places.
  A "sole address gate" overclaim in `ARCHITECTURE.md` that ignored the preflight's own
  IP-literal address gate — scoped to addresses obtained via hostname resolution.
- A `CrawlUrlRejectedError` `Raises:` contract (in `sitemap.py` and `ARCHITECTURE.md`) that
  described only resolved-address rejection, omitting `fetch_page`'s malformed-port/DNS-failure
  paths — broadened to the full set of crawl-policy and address-gate rejections it enforces.
- Two stale red-harness/historical docstrings (`test_sitemap_pinned_sink.py`'s module docstring
  still described the pre-069.003-T resolving preflight; `test_sitemap.py`'s and
  `test_sitemap_resolution_count.py`'s docstrings retained obsolete red-phase/`NotImplementedError`
  framing) — reconciled with the current, completed state.

All fixes were docstring/documentation-accuracy corrections; no executable statement was altered
after the initial implementation commits (`4226bb6`, `1662292`).

## Source artifact cleanup

| Artifact | Action |
|---|---|
| Stash `F0F13C0B` | Already archived/harvested by Stage prior to this Ship session (feature `069-F`'s `source_stash_id`); `backlogit stash archive F0F13C0B` returned "not found" — skip, nothing further to do |
| Deliberation record | `docs/decisions/2026-08-29-sitemap-preflight-dedup-deliberation.md` (status `accepted`) remains the durable decision artifact referenced by the plan; `069-F` carries no `source_deliberation_id` custom field, so there is no backlog deliberation artifact to archive |

## Follow-ups stashed

| Stash ID | Priority | Summary |
|---|---|---|
| `6BF410E2` | low | Consolidate the now-triplicated scripted-socket/HTTP-response test helpers (`_ScriptedSocket`, `_http_response`/`_response`, `_create_connection_stub`/`_scripted_transport`) across `test_sitemap.py` / `test_sitemap_pinned_sink.py` / `test_sitemap_resolution_count.py` into one shared helper — flagged P2 by both Maintainability and Python local-review personas (drifted `send()`/`sendall()` semantics between copies noted as a latent DRY/regression-masking risk). Out of scope per P-021 C1: the plan's width-isolated, per-file task decomposition never authorized cross-file test-infra consolidation. Captured pre-PR, threadless path (no review thread existed at capture time) |

Remaining P3 findings from local review (missing test-helper type annotations, mixed
`monkeypatch.setattr` idiom, one pre-existing local import, minor documentation cross-reference
repetition across 4 locations) are advisory / user's-discretion per the review skill's severity
table — acknowledged, not independently deferred.

## Accepted risk carried forward

None specific to this shipment's own scope. The pre-existing observation that `validate_sitemap_url`
has no live `src/` caller other than `fetch_sitemap` (noted in 057-S's closure) is unchanged by
this shipment.

## Monitoring and rollback

This is a library-level fetch-path change with no new operator-visible surface, no config flag,
and no persisted-artifact schema change. There is no new monitoring signal to add: the existing
`CrawlUrlRejectedError`/`SitemapError` exception surface is unchanged in meaning (only the
*mechanism* that raises each moved), and callers already handle both types per the documented
`Raises:` contracts.

| Field | Value |
|---|---|
| Invariants | `fetch_page` remains the sole authoritative hostname resolver and address gate; every previously-rejected address class (loopback, private, link-local, multicast, reserved, unspecified, cloud-metadata, CGNAT, ULA, site-local) is still rejected via the same canonical predicate; the IP-literal early-return branch in the preflight is unchanged; `timeout_seconds` still bounds preflight-plus-fetch |
| Pre-deploy audit | All quality gates green on the merged head; CI green on all required jobs; 5-persona local review + 5 Copilot review cycles clean; runtime verification (5/5) executed against the merged tree |
| Rollout path | Merged to `main` via merge commit `f278cff`. No staged rollout, feature flag, or migration — a library-level behavior change on the fetch path, effective immediately for all `fetch_sitemap` callers (currently none in `src/`, per the pre-existing YAGNI note) |
| Post-deploy checks | Runtime verification (5/5) executed against the merged tree in this closure; no separate production environment to smoke-test (CLI/MCP library) |
| Healthy signal | `fetch_sitemap` succeeds for a safe hostname with exactly one resolver call attributable to that hostname; an unsafe hostname is rejected with `CrawlUrlRejectedError` before any connection |
| Failure signal | Any hostname-resolving unsafe address reaching a TCP connect; a `SitemapError` where `CrawlUrlRejectedError` is expected (or vice versa) escaping to a caller; a hostname lookup count for a successful non-redirected fetch other than 1 |
| Rollback trigger | Any failure signal above traced to this change |
| Rollback command | `git revert -m 1 f278cffc9743d19cae410a9ea7623bfeec0c7649` |
| Validation window | Covered by the post-merge runtime verification and CI; no extended soak required for a deterministic library change with no live caller yet |
| Readiness verdict | **READY** — merged, verified, and closed |
| Owner | Ship agent (session 060-S) |

## Compaction status (P-020)

`done` — `compact-context` (target: `all`) consolidated this shipment's two session memory files
into `docs/memory/compacted/2026-09-09-060-s-compacted.md`; verbose originals archived to
`docs/archive/memory/2026-09-08/`.
