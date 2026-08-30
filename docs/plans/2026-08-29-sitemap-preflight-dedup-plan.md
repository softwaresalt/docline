---
title: "Implementation Plan: Remove duplicate sitemap DNS resolution, preserve authoritative pinning"
date: 2026-08-29
status: reviewed
feature: "Group B (sitemap security-efficiency)"
source_deliberation: docs/decisions/2026-08-29-sitemap-preflight-dedup-deliberation.md
stash_ids: [F0F13C0B]
requires_plan_hardening: yes
plan_review: "final — PASS. 3 rounds of 5-persona adversarial review (architecture, security, correctness, scope, python-safety), plus 1 Copilot review round on PR #177. See ## Plan Review Record."
---

## Objective

Resolve a sitemap hostname **exactly once** per `fetch_sitemap` call — inside `fetch_page`, where
the resolved address is pinned for the connection — instead of twice. Reduce
`validate_sitemap_url` to a deterministic, resolution-free preflight so its name can no longer be
mistaken for an authorization decision. **Do not weaken `fetch_page`'s authoritative
resolve-validate-pin sequence, and do not change any contract F0F13C0B did not ask to change.**

## Grounding (origin/main @ edcaa12)

- `src/docline/fetch/sitemap.py`
  - `_resolve_all_addresses(host)` (172) — `socket.getaddrinfo`; raises `SitemapError` on failure
    or empty answer. **Sole caller is line 241**, inside `validate_sitemap_url`.
  - `validate_sitemap_url(url)` (194) — non-empty; scheme in `{http, https}`; host present;
    `_METADATA_HOSTNAMES`; IP-literal fast path (`is_unsafe_resolved_address`, early return, **no
    DNS**); then `_resolve_all_addresses` + per-address screening. Its docstring already declares
    the resolution *"advisory and deliberately non-authoritative"*.
  - `fetch_sitemap` (251) — runs the preflight via `loop.run_in_executor(None, ...)` under
    `asyncio.wait_for(timeout_seconds)`, deducts elapsed time via `time.monotonic()`, then calls
    `fetch_page(url, timeout_seconds=remaining, max_redirects=...)`. Its `Raises:` block already
    documents `SitemapError`, `CrawlUrlRejectedError`, `FetchTimeoutError`, and `FetchError`.
  - `validate_sitemap_url` has **no `src/` caller other than `fetch_sitemap`**.
  - Imports at 34-39 include `socket`, `time`, `asyncio`, and
    `from docline.fetch.http import FetchResponse, FetchTimeoutError, fetch_page`.
- `src/docline/fetch/url_policy.py` — `is_unsafe_resolved_address` (42) is the canonical
  predicate. `CrawlUrlRejectedError` (38) is a `DoclineError` subclass. `validate_crawl_url`
  (127-180) is resolution-free for hostnames. `resolve_and_validate` (91-126) resolves and screens
  **every** returned address.
- `src/docline/fetch/http.py` — `_connect_validated_address` (173-216) calls
  `resolve_and_validate(host)` **exactly once** and connects to the already-validated addresses
  atomically; there is **no separate validate-then-connect gap inside a single hop**.
  `_ValidatingRedirectHandler.redirect_request` (299-332) calls `resolve_and_validate` on the
  redirect target, and the subsequent pinned connection resolves again.
- **Security review verified the core premise against the code:** every address class the sitemap
  preflight rejects — loopback, private, link-local, multicast, reserved, unspecified, CGNAT
  `100.64.0.0/10`, IPv6 ULA `fc00::/7`, site-local, metadata IPs including IPv4-mapped forms — is
  also rejected by `resolve_and_validate`, which screens *all* resolver answers. **No classifier
  gap, no multi-answer gap, no unsafe address reaches TCP connect.**
- Test surface pinning current behaviour:
  - `tests/fetch/test_sitemap.py` — hostname-resolution assertions calling `validate_sitemap_url`
    **directly** and expecting `SitemapError`: loopback (~249), private (~257), metadata-address
    hostname (~247), mixed public/private answers (~256), DNS-failure→`SitemapError` (~280),
    CGNAT hostname rows in the parametrization (~331), and the accepts-public-host case (~239).
    Module docstring at line 16 states the preflight resolves via `socket.getaddrinfo`.
  - `tests/fetch/test_sitemap_pinned_sink.py` — `_sequenced_getaddrinfo` (39-66) returns a
    different answer per call; `socket.create_connection` is patched.
    `test_preflight_resolution_runs_off_the_event_loop` (332),
    `test_preflight_is_bounded_by_the_request_timeout` (358),
    `test_preflight_elapsed_time_is_deducted_from_the_fetch_deadline` (385).

## Constitution Check

| Principle | Assessment |
|---|---|
| I. Safety-First Python | Typed exceptions preserved; `CrawlUrlRejectedError` confirmed a `DoclineError` subclass (`url_policy.py:38`); no bare `except`. **PASS** |
| II. Test-First | Every source task gated behind a red-harness or test-migration task via explicit dependency edges. **PASS** |
| III. Workspace Isolation / SSRF boundary | The boundary **moves nowhere**: `fetch_page` was and remains the sole authoritative gate. Verified by the security persona against `url_policy.resolve_and_validate`. **PASS** |
| VI. Single Responsibility | No new dependency; net deletion of a helper. **PASS** |
| No dead code | `_resolve_all_addresses` loses its only caller and is deleted; the `socket` import is removed unconditionally. **PASS** |

## Design decisions (binding on implementation)

### D1 — The preflight becomes deterministic and resolution-free

`validate_sitemap_url` keeps, in order: non-empty check; scheme in `{http, https}`; host present;
host not in `_METADATA_HOSTNAMES`; IP-literal parse → `is_unsafe_resolved_address` → early return.
It **loses** `_resolve_all_addresses` and the per-address loop; `_resolve_all_addresses` is
deleted with it.

The IP-literal branch is **not** a DNS lookup and is preserved verbatim, so IPv6 link-local and
unique-local literals are still rejected before any I/O.

### D2 — Unsafe *hostnames* are rejected by `fetch_page`, surfacing `CrawlUrlRejectedError`

Chosen over translating back to `SitemapError` at the `fetch_sitemap` boundary because
`fetch_sitemap`'s `Raises:` block already documents `CrawlUrlRejectedError`; because
`validate_sitemap_url` has no other `src/` caller; and because wrapping would re-assert that the
sitemap layer owns the address decision — the confusion this work removes.

The split becomes meaningful: `SitemapError` = malformed or statically-disqualified URL;
`CrawlUrlRejectedError` = the address gate said no. Tests must assert the exception **type**, not
a message substring.

### D3 — **The executor offload and the deadline arithmetic are RETAINED** (round-1 D3 rejected)

Round 1 proposed deleting the `run_in_executor` + `asyncio.wait_for` + `time.monotonic` wrapper
on the grounds that a resolution-free preflight cannot block. Two independent reviewers rejected
it and this plan adopts their finding:

- **Scope (P1, decisive on its own):** F0F13C0B asks only to remove duplicate DNS resolution.
  Changing `timeout_seconds` from bounding preflight-plus-HTTP to bounding HTTP alone is an
  unrequested contract change that widens the blast radius for no requested benefit. This ground
  alone justifies retention.
- **Security (P2, contributing but narrower than first stated):** the round-1 concern was that
  removing the wrapper moves the first blocking DNS lookup into `fetch_page`'s executor worker,
  where `asyncio.wait_for` can return a timeout without stopping the thread, so a late-arriving
  safe result could start TCP/TLS after the caller already saw `FetchTimeoutError`.
  **Qualification (architecture review, round 2):** after B.T3 the preflight performs no
  resolution *either way*, so the first blocking DNS is always inside `fetch_page`'s own executor
  under `fetch_page`'s own deadline. That post-timeout-connect property, to the extent it exists,
  is a property of `http.py` and is **unchanged** by whether the sitemap wrapper is present.
  Retaining the wrapper therefore does **not** close an SSRF timing hole, and removing it would
  **not** open one. A future maintainer must not read D3 as a security guarantee. It is recorded
  here only because it was raised, and because `http.py` is read-only for this shipment, making
  any investigation of that property out of scope.

Consequences of retaining the wrapper: `fetch_sitemap` is **unchanged**; `timeout_seconds` keeps
its current whole-operation meaning; `asyncio`, `time`, and `FetchTimeoutError` all remain used,
so no `F401`; and the three preflight-timing tests remain valid and are **not** retired. The
shipment shrinks to exactly what the stash asked for.

### D4 — Resolver-call accounting is defined in terms of *hostname* lookups

"Exactly one resolution" means **one `getaddrinfo` call whose host argument is the original
hostname**. It does not mean one total `socket.getaddrinfo` invocation: in production,
`socket.create_connection` also calls `getaddrinfo` on each already-validated numeric address, so
a raw global counter would be misleading. Verified expected hostname-lookup counts after the
change:

| Scenario | Hostname lookups |
|---|---|
| Successful initial hop | **1** (in `_connect_validated_address` → `resolve_and_validate`) |
| Each followed redirect target | **2** (`redirect_request` precheck + pinned connection) |
| Redirect target rejected at precheck | **1**, and **no connection attempted** |
| Preflight (post-change) | **0** |

B.T1 counts calls whose argument equals the original hostname, not all `getaddrinfo` calls.

### D5 — The rebinding test is re-expressed on the redirect path, not the initial hop

Round 1 instructed re-baselining the rebinding test across "`fetch_page`'s own validate and
connect steps". That is factually impossible: `_connect_validated_address` resolves **once** and
connects atomically — that single-resolution atomicity is exactly how pinning closes rebinding.
There is no intra-hop validate/connect divergence to script.

The only observable second resolution within a fetch is on a **redirect**
(`_ValidatingRedirectHandler.redirect_request` precheck, then the pinned connection). The
rebinding test is therefore re-expressed on the redirect-revalidation path as the **primary**
formulation. It is never deleted and never weakened to a smoke test. Exit criterion 4 is worded
to match what is actually being tested.

### D6 — Out of bounds

Passing preflight-resolved addresses into `fetch_page` (deliberation Option C) — **forbidden**,
it migrates authority out of the pinning path. Any change to `is_unsafe_resolved_address`,
`resolve_and_validate`, `fetch_page`, or the pinned connection classes — `http.py` and
`url_policy.py` are **read-only** for this shipment. The shared-classifier consolidation
(`87F2C06D`). Sitemap parsing. Any resolver cache. Any timeout-semantics change (D3).

## Task decomposition (harness-first, <=2h each, width-isolated)

### B.T1 — Harness: one hostname resolution per `fetch_sitemap` (red)

- **Domain:** tests. **Files:** `tests/fetch/test_sitemap_resolution_count.py` (new).
- A counting `getaddrinfo` wrapper that filters on the **original hostname** (D4) asserts
  `fetch_sitemap` performs exactly **one** hostname lookup for a successful fetch, and records
  the pre-change count (2) so the harness demonstrably fails red.
- Preflight-isolation assertion: call `fetch_sitemap` with `fetch_page` patched out and assert the
  preflight alone performs **zero** hostname lookups — for both a hostname URL and an IP-literal
  URL. (A global counter cannot express this: `fetch_page` legitimately resolves. The seam is the
  patch, and it must be stated in the test.)
- **Acceptance:** red against current source. No source change.

### B.T2 — Inventory and migrate every hostname-resolution assertion (red)

- **Domain:** tests. **Files:** `tests/fetch/test_sitemap.py`.
- **First action: a complete inventory.** Grep the module for every test that patches
  `socket.getaddrinfo` and calls `validate_sitemap_url`, and record the list in the task log.
  Round 1 enumerated three; the real set also includes the metadata-address hostname case, the
  mixed public/private answer case, the DNS-failure→`SitemapError` case, and the CGNAT hostname
  rows.
- Migrate each to assert **end to end through `fetch_sitemap`**, expecting
  `CrawlUrlRejectedError` (by type) for unsafe hostnames, and a fetch error for DNS failure.
- Keep, unchanged, every deterministic preflight test: empty input, non-http scheme, missing host,
  metadata **hostname-name** rejection (including its no-resolution assertion), and reserved **IP
  literals** — all still `SitemapError` from `validate_sitemap_url`.
- Correct the module docstring at line 16.
- **Acceptance:** red against current source. No source change.

### B.T3 — Strip hostname resolution from the preflight; delete the orphaned resolver

- **Domain:** src. **Files:** `src/docline/fetch/sitemap.py`.
- Remove the `_resolve_all_addresses` call and the per-address loop from `validate_sitemap_url`;
  delete `_resolve_all_addresses`; **delete the `socket` import unconditionally** (no remaining
  reference — `F401` would otherwise fail the lint gate). Update `validate_sitemap_url`'s
  docstring and `Raises:` block to describe a deterministic preflight.
- Do **not** touch `fetch_sitemap` (D3). `asyncio`, `time`, and `FetchTimeoutError` stay.
- **Acceptance:** B.T1 and B.T2 green; `ruff check .` clean; `pyright src/` 0 errors.
  `tests/fetch/test_sitemap_pinned_sink.py` is **expected red** here — B.T4 closes it.
- **Depends on:** B.T1, B.T2.

### B.T4 — Re-baseline the pinned-sink resolution schedules

- **Domain:** tests. **Files:** `tests/fetch/test_sitemap_pinned_sink.py`.
- `_sequenced_getaddrinfo` schedules currently allocate answer #1 to the preflight. Shift each
  schedule down by one to the counts in D4.
- Re-express the rebinding test on the **redirect-revalidation** path per D5, citing
  `_ValidatingRedirectHandler.redirect_request` as the site of the observable second resolution.
  Add a companion assertion that every address in a mixed DNS answer is screened before any
  connection is attempted.
- The three preflight-timing tests (332, 358, 385) exercise a wrapper that **is retained** (D3),
  but their stated *subject* no longer exists: after B.T3 the resolver call they observe comes
  from `fetch_page`'s executor worker, not from `validate_sitemap_url`. Left untouched,
  `test_preflight_resolution_runs_off_the_event_loop` would pass while proving nothing about the
  preflight, and the elapsed-deadline test's deliberately slow resolver is not called at all when
  `fetch_page` is patched.
  Therefore: **retain the wrapper/deadline contract but rename and re-assert these three tests**
  so they describe what they actually verify — that `fetch_sitemap` runs the preflight in the
  executor under `asyncio.wait_for`, that the wrapper bounds the call, and that elapsed preflight
  time is deducted from the deadline handed to `fetch_page`. Any delay must be injected at the
  **preflight execution seam**, not into `socket.getaddrinfo`. Add one direct test asserting the
  deterministic preflight performs zero resolver calls.
- **Acceptance:** whole `tests/fetch/` suite green; no security test deleted; each retained
  schedule reviewed by hand against D4's counts; no retained test passes vacuously.
- **Depends on:** B.T3.

### B.T5 — Harness: proxy-environment suppression regression (red-or-green guard)

- **Domain:** tests. **Files:** `tests/fetch/test_sitemap_pinned_sink.py`.
- Exit criterion 6 in round 1 ("proxy-environment suppression unchanged") was unfalsifiable —
  no task asserted it. `test_fetch_sitemap_ignores_inherited_proxy_environment` (264) already
  exists; this task explicitly verifies it still passes post-change and extends it if the
  re-baselined resolver schedule affects it.
- **Acceptance:** proxy suppression asserted and green; the exit criterion becomes falsifiable.
- **Depends on:** B.T4.

### B.T6 — Reconcile the `sitemap.py` docstrings with the deterministic preflight

- **Domain:** src (docstrings only). **Files:** `src/docline/fetch/sitemap.py`.
- Module header at line 8 and the `validate_sitemap_url` / `fetch_sitemap` docstrings: state that
  the preflight is deterministic and performs no name resolution; that `fetch_page` is the sole
  resolver and sole authority; that `timeout_seconds` still bounds preflight-plus-fetch (D3);
  and that `SitemapError` covers static disqualification while `CrawlUrlRejectedError` covers
  address rejection.
- **Must not alter a single executable statement.** If a behaviour fix appears necessary here, it
  belongs in a new src-width task.
- **Acceptance:** `ruff format --check .` clean; docstrings match implemented behaviour exactly;
  `git diff` shows only docstring/comment lines.
- **Depends on:** B.T5.

### B.T7 — Update the architecture documentation

- **Domain:** docs. **Files:** `docs/ARCHITECTURE.md`.
- Record the single-resolution model and the D4 lookup-count table in the sitemap/fetch section.
- Edit **only** the sitemap section; Group A's doc task edits the crawl section (see R8).
- **Acceptance:** markdown gates pass; no source file touched.
- **Depends on:** B.T6.

> B.T6 and B.T7 split round-1's single B.T7, which mixed a `.py` file and a `.md` file under one
> "docs" label. Editing docstrings inside a production source file is a src-width change even
> though the content is documentation; the two widths are now separate tasks.

## Dependency graph

```text
B.T1 ─┐
      ├─> B.T3 ──> B.T4 ──> B.T5 ──> B.T6 ──> B.T7
B.T2 ─┘
```

## Verification

Gates: `ruff check .`, `pyright src/`, `pytest`, `ruff format --check .`.

**Gate policy exception (aligns with R7).** The red-harness tasks (B.T1, B.T2) and the intentional
red window between B.T3 and B.T4 are explicit exceptions to the per-task full-`pytest` gate; their
per-task gate is `ruff check` + `pyright src/` + the task's own targeted tests. Full-suite green is
a **merge precondition** for the shipment as a whole. B.T4 onward carry the full four-gate
requirement.

Shipment exit criteria:

1. `fetch_sitemap` performs exactly **one** hostname lookup for a successful fetch (D4
   accounting), asserted by a hostname-filtered counter.
2. The preflight alone performs **zero** hostname lookups, for hostname and IP-literal URLs.
3. A hostname resolving to loopback / private / CGNAT / ULA / metadata is still rejected end to
   end, by exception **type**.
4. **Redirect-target revalidation still rejects a rebound address**, and every address in a
   mixed DNS answer is screened before any connection.
5. HTTPS SNI and certificate verification still use the hostname, not the pinned IP.
6. `test_fetch_sitemap_ignores_inherited_proxy_environment` passes (asserted by B.T5).
7. `timeout_seconds` still bounds preflight-plus-fetch; the three wrapper/deadline tests pass with
   assertions that describe what they actually verify (no vacuous passes), and one direct test
   asserts the deterministic preflight performs zero resolver calls.
8. `_resolve_all_addresses` and the `socket` import no longer exist in `sitemap.py`.

## Rollback

Single `git revert -m 1 <merge-sha>`. Pure source + test change; no persisted artifact, no
migration, no config surface. A revert restores the double resolution — a performance regression,
never a security regression, because the authoritative gate is untouched in both directions.

## Plan Hardening

### Risk register

| ID | Risk | Likelihood | Blast radius | Mitigation |
|---|---|---|---|---|
| R1 | An implementer "simplifies" by handing preflight-resolved addresses to `fetch_page`, moving authority out of the pinning path | Low | **Critical** — real SSRF regression | Forbidden by D6 and by the deliberation (Option C, rejected). `http.py` and `url_policy.py` are read-only; a diff touching either is an automatic review rejection. Exit criteria 3-5 assert the pinning properties survive. |
| R2 | The deleted preflight screening was not in fact a duplicate — some address class is rejected only by the preflight | Low | High | **Retired by evidence.** The security persona verified `resolve_and_validate` (`url_policy.py:91-126`) screens **every** resolver answer through the same canonical `is_unsafe_resolved_address`, covering all listed classes including CGNAT, ULA, site-local, and IPv4-mapped metadata. B.T2 still asserts each class end to end as a standing regression gate. |
| R3 | The `_sequenced_getaddrinfo` re-baseline turns a rebinding test into one that passes for the wrong reason | Medium | High — a security test that no longer tests anything | D4 fixes the expected counts and D5 fixes the formulation: the redirect path is primary because the initial hop has no intra-hop divergence to script. B.T4 requires hand review of each schedule and forbids deleting any security test. |
| R4 | Removing the preflight's bounded wrapper lets an abandoned DNS worker start a connection after the caller timed out | — | — | **Not applicable.** D3 retains the wrapper on **scope** grounds. Architecture review established that the post-timeout property is a property of `http.py` and is unchanged either way, so this is not a risk this shipment creates, closes, or carries. `http.py` is read-only here. |
| R5 | Deleting `_resolve_all_addresses` removes DNS-failure→`SitemapError` mapping a caller relies on | Low | Low | No `src/` caller other than `fetch_sitemap`. DNS failure now surfaces from `fetch_page` as a fetch error, already in the documented `Raises:` set. B.T2 migrates the test; B.T6 records the contract. |
| R6 | Lint gate failure from orphaned imports after the deletion | Medium | Low | `socket` removal is **unconditional** in B.T3 (`F401` is selected). `asyncio`, `time`, and `FetchTimeoutError` all remain in use because D3 retains the wrapper — the round-1 `F401` hazard on `FetchTimeoutError` no longer arises. |
| R7 | A partial merge lands a red test surface on `main` | Medium | High | B.T1-B.T7 are one atomic shipment; full-suite green is a stated merge precondition, and the red window is bounded and explicit in the Verification gate exception. |
| R8 | Both shipments edit `docs/ARCHITECTURE.md` | Medium | Low | The shipments share **no source file** but do share this doc. B.T7 is scoped to the sitemap section, Group A's to the crawl section; whichever merges second rebases the hunk. |
| R9 | Scope creep into the shared-classifier consolidation (`87F2C06D`) | Medium | High | D6 lists it out of bounds. This change *reduces* sitemap-side screening call sites, making that future consolidation smaller — no incentive to pull it forward. |

### Rollback rehearsal

`git revert -m 1 <merge-sha>` restores `_resolve_all_addresses`, the resolving preflight, and the
`socket` import together — all in one module, one merge. `fetch_sitemap` is untouched by this
shipment, so the timeout path needs no rollback consideration at all. No artifact, cache, config,
or persisted state survives. Post-revert the only delta is a doubled resolver call: the
pre-change status quo.

### Guardrails carried into implementation

- `http.py` and `url_policy.py` are read-only for this shipment.
- `fetch_sitemap`'s body is read-only for this shipment (D3); only its docstring changes, in B.T6.
- No test in `test_sitemap_pinned_sink.py` may be deleted without a replacement asserting the same
  security property.
- The IP-literal early-return branch is preserved verbatim.
- B.T6 must not change an executable statement.
- Exception assertions must be by type, not by message substring.

### Verification depth

Beyond the gates, a runtime spot-check: `fetch_sitemap` against a local fixture server with a
hostname-filtered resolver counter attached, confirming exactly one hostname lookup; and a
negative case confirming a hostname resolving to `127.0.0.1` is refused with **no connection
attempt**.

## Plan Review Record

Multi-persona adversarial plan review, 3 rounds. Gate outcome: **PASS**.

| Persona | Round 1 | Final | Findings applied |
|---|---|---|---|
| Security | ADVISORY | **ADVISORY** | **Core premise verified against source**: `resolve_and_validate` (`url_policy.py:91-126`) screens *every* resolver answer through the same canonical `is_unsafe_resolved_address`, covering loopback, private, link-local, multicast, reserved, unspecified, CGNAT, ULA, site-local, and IPv4-mapped metadata. No classifier gap, no multi-answer gap, no unsafe address reaches TCP connect — R2 retired by evidence. P2 on round-1 D3's post-timeout abandoned worker → D3 withdrawn entirely. P3 lookup-count model → D4. |
| Scope | FAIL | **PASS** | P1 round-1 D3 changed the `timeout_seconds` contract, which F0F13C0B never asked for → **D3 rejected; the executor offload and deadline arithmetic are retained and `fetch_sitemap`'s body is read-only.** P1 B.T7 mixed a `.py` file and a `.md` file under one "docs" label → split into B.T6 (src docstrings) and B.T7 (docs). P2 unfalsifiable proxy exit criterion → B.T5. |
| Architecture | ADVISORY | **PASS** | P2 round-1 B.T4 was factually wrong that `fetch_page` has an intra-hop validate/connect gap — `_connect_validated_address` resolves once and connects atomically → D5 makes the redirect-revalidation path the primary rebinding formulation. D4's count table verified accurate against `http.py`. P3 D3's security sub-rationale misattributed → restated on scope grounds with the security claim explicitly qualified. |
| Correctness | ADVISORY | **PASS** | P1 B.T2 migrated only 3 of the DNS-dependent tests → B.T2 now requires a complete grep inventory and names the metadata-address hostname, mixed-answer, DNS-failure, and CGNAT parametrization cases. P2 gate policy incompatible with intentional red windows → explicit exception. P2 IP-literal zero-DNS assertion ambiguous → D4 hostname accounting + `fetch_page` patched out. P3 three retained timing tests would pass vacuously → renamed and re-asserted, delay injected at the preflight seam. |
| Python-safety | ADVISORY | **ADVISORY** | P2 `FetchTimeoutError` would become an unused import under round-1 D3 → moot once D3 was withdrawn. P3 `socket` import removal must be unconditional (F401 is selected) → B.T3. P3 verified `CrawlUrlRejectedError` is a `DoclineError` subclass (`url_policy.py:38`) so D2's exception split is hierarchy-consistent; assertions must be by type. |
