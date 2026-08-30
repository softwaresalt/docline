---
title: "Deliberation: Remove duplicate sitemap DNS resolution without weakening the authoritative pin"
date: 2026-08-29
status: accepted
stage_session: "stash-to-backlog — sitemap security-efficiency group {F0F13C0B}"
stash_ids: [F0F13C0B]
related: docs/decisions/2026-08-29-ssrf-classifier-pinning-deliberation.md
---

## Problem frame

**F0F13C0B** (low, task). `fetch_sitemap` in `src/docline/fetch/sitemap.py` resolves the sitemap
hostname **twice** per fetch:

1. `validate_sitemap_url` (`sitemap.py:193-249`) calls `_resolve_all_addresses(host)` →
   `socket.getaddrinfo`, then screens every returned address through
   `is_unsafe_resolved_address`. Its own docstring states this resolution is *advisory and
   deliberately non-authoritative* — it returns the original URL, not an address.
2. `fetch_page` then performs the **authoritative** resolve → validate → pin sequence, connecting
   to the validated IP while preserving the hostname for `Host`, SNI, and certificate
   verification.

This is explicitly **not** a TOCTOU: the second resolution is the one that pins, so the security
property holds regardless of what the first resolution saw. The cost is efficiency and clarity:

* **~2x resolver load** per sitemap fetch, and therefore ~2x DNS amplification against an
  attacker-supplied hostname. `fetch_sitemap` is reachable from sitemap-index expansion, so the
  multiplier applies per child sitemap URL, not once per job.
* **Misleading naming.** A function called `validate_sitemap_url` that performs a DNS lookup and
  screens addresses reads like an authorization decision. It is not one. The next reader — or the
  next refactor — can plausibly treat a passing preflight as permission to connect, which is
  exactly the DNS-rebinding footgun the pinning design exists to close.

Flagged by the 057-S adversarial review as Security P3 + Architecture P2.

## Grouping decision

Ships **separately** from the crawl reliability group {7F34A0D5, 8A99D90C, ABBE9BCC}.

* No shared **source** file: this touches `fetch/sitemap.py`; that group touches `fetch/crawl.py`,
  `fetch/models.py`, and `elt/execute.py`. Both groups do edit `docs/ARCHITECTURE.md`, each in a
  distinct section, so the second to merge rebases a trivial doc hunk.
* No dependency edge in either direction.
* Different review width: this is a security-boundary change requiring a security persona to
  reason about what the preflight is *allowed* to stop doing. The crawl group is a
  reliability/observability change. Bundling them would force one reviewer to hold both models.

It is a group of one. That is valid here: it is the only active stash entry on this surface and
forcing it into an artificial pairing would be worse than shipping it alone.

## Non-negotiable invariant

**`fetch_page` remains the sole authoritative resolve-validate-pin path, and nothing in this work
weakens it.** Any option that moves authority into the preflight, or that lets a caller connect on
the strength of a preflight result, is rejected on sight. The stash entry says this explicitly and
the operator restated it: *preserve authoritative `fetch_page` validated-IP pinning.*

## Options considered

### Option A — Reduce the preflight to deterministic, resolution-free checks (chosen)

Strip `_resolve_all_addresses` from `validate_sitemap_url`. The preflight retains only checks that
need no network:

* scheme is `http`/`https`;
* host is present;
* host is not in `_METADATA_HOSTNAMES`;
* host parses as an IP literal → classify directly via `is_unsafe_resolved_address` (this is not
  a DNS lookup, and it is the branch that already returns early today).

Hostname resolution then happens exactly once, inside `fetch_page`, where it is pinned.

* **Pros:** halves resolver load; removes the amplification multiplier; makes the preflight
  honestly *deterministic* — the name stops implying an authorization decision because there is no
  address screening left to mistake for one; the IP-literal fast path is preserved verbatim, so
  IPv6 link-local / unique-local literals are still rejected before any I/O.
* **Cons:** an unsafe *hostname* now fails inside `fetch_page` rather than in the preflight, so the
  raised exception type changes from `SitemapError` to `CrawlUrlRejectedError` for that case. That
  is an observable contract change and must be handled deliberately — see "Scope decisions".
* **Security delta: none.** The removed check was, by its own docstring, advisory. Every rejection
  it could make, `fetch_page` still makes, on the resolution that actually pins.

### Option B — Keep the resolving preflight but rename it

e.g. `preflight_resolve_sitemap_url`, documented as advisory.

* **Rejected as the primary fix.** It addresses the Architecture P2 (naming/clarity) and leaves the
  Security P3 (2x amplification) entirely intact. The resolver load is the measurable half of the
  finding.

### Option C — Resolve once in the preflight and pass the addresses into `fetch_page`

Have the preflight hand its validated address set down to be pinned.

* **Rejected, and it is the dangerous option.** It inverts the invariant: authority migrates from
  the pinning path into the preflight, and re-opens the validate-then-connect gap that pinning
  closed. It also entangles `sitemap.py` with `http.py`'s internal pinning contract. Explicitly
  out of bounds for this work.

### Option D — Cache resolution results across the two call sites

* **Rejected.** A shared resolver cache is a new stateful component with its own TTL, eviction, and
  poisoning surface, introduced to avoid a lookup that Option A simply deletes. Strictly more
  machinery for strictly less benefit.

## Decision

Adopt **Option A**, with the exception-contract change handled as first-class scope rather than a
side effect.

Committed ordering:

```text
Unit 1  characterization harness pinning current behaviour   — red-first, no source change
   └─> Unit 2  strip resolution from validate_sitemap_url    — the efficiency + clarity fix
   └─> Unit 3  docstring/contract + naming reconciliation    — docs width, no behaviour change
```

Unit 1 must capture, before any change: that an unsafe-hostname sitemap URL is rejected end to
end; that an IP-literal unsafe URL is rejected by the preflight without DNS; and — the load-bearing
assertion — a **resolution-count** test proving `getaddrinfo` is invoked exactly once per
`fetch_sitemap` after Unit 2, and more than once before it.

## Scope decisions captured

* **In scope:** removing `_resolve_all_addresses` from the `validate_sitemap_url` path; the
  docstring correction that follows; a resolution-count regression test; reconciling the raised
  exception type for unsafe hostnames.
* **Exception contract:** the plan must choose *explicitly* between (a) letting
  `CrawlUrlRejectedError` propagate from `fetch_sitemap` and documenting it in the `Raises:` block,
  or (b) translating it to `SitemapError` at the `fetch_sitemap` boundary to preserve the current
  caller contract. `fetch_sitemap`'s docstring already documents **both** exception types today,
  which argues for (a) — but the call sites must be checked, not assumed. This is a required
  decision point in the plan, not an implementation detail.
* **Out of scope:** the shared-SSRF-classifier consolidation (stash `87F2C06D` on another branch,
  and `docs/decisions/2026-08-29-ssrf-classifier-pinning-deliberation.md`); any change to
  `is_unsafe_resolved_address` itself; any change to `fetch_page`; sitemap parsing.
* **Interaction note:** `87F2C06D` proposes consolidating `_is_unsafe_address`-style predicates
  onto one canonical classifier. Option A *reduces* the number of sitemap-side call sites that
  screen addresses, so it makes that future consolidation strictly smaller. No conflict; no
  ordering constraint imposed in either direction.
* **Whether `_resolve_all_addresses` survives:** if no caller remains after Unit 2, it must be
  removed rather than left as dead code (constitutional "no dead code"). The plan must state which.

## Prior art consulted

`docs/compound/` and `docs/decisions/` searched for SSRF/pinning/preflight learnings. The
governing prior art is `2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md` and
`2026-08-29-ssrf-classifier-pinning-deliberation.md`; neither constrains this change beyond the
pinning invariant restated above.
