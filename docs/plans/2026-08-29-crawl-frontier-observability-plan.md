---
title: "Implementation Plan: Crawl frontier truncation observability and admission-policy composability"
date: 2026-08-29
status: reviewed
feature: "Group A (crawl reliability/composability)"
source_deliberation: docs/decisions/2026-08-29-crawl-frontier-observability-deliberation.md
stash_ids: [8A99D90C, 7F34A0D5, ABBE9BCC]
requires_plan_hardening: yes
plan_review: round 2 — revised against 5-persona adversarial review (architecture, security, correctness, scope, python-safety)
---

## Objective

Make the crawl frontier admission rule a testable, composable structure, then use that structure
to (a) make truncation visible to operators on **both** the CLI and MCP paths and (b) stop
truncation from preferentially discarding authoritative mdBook TOC navigation. No change to the
ceiling value or to the ceiling's semantics.

## Grounding (origin/main @ edcaa12)

- `src/docline/fetch/crawl.py` — **660 lines**, past the 400-line module convention.
  - `MAX_FRONTIER = 10_000` (28); `CrawlLimitExceededError` (37); `CrawlRobotsError` (41);
    `CrawlConfig` (46-74); `CrawlResult` (78-94); `_LinkExtractor` (96-120).
  - `crawl()` (123-356). `_report_ceiling()` (191-202) — `nonlocal ceiling_reported`, one
    `logger.debug(...)` with `sanitize_source(start)`. `_admit()` (204-222) — `nonlocal admitted`,
    mutates captured `visited` and `frontier`.
  - Ceiling short-circuits: print-page branch (290-291), main branch (324-329). Admission loop
    (344-355) `break`s on first refusal. Depth-zero TOC **tail-append** (331-341).
  - `visited` is mutated at three **non-admission** sites: 289 (print page), 318 (duplicate
    final), 322 (emit). Loop reads `frontier`/`popleft` at 224-225.
  - Non-counting `continue` at the final-URL section-scope branch (316) — no `page_count`
    increment, no progress event.
  - Helpers: `check_robots_allowed` (358), `extract_links` (376), `extract_toc_script_urls`
    (409), `extract_toc_links` (434), `_fetch_with_retries` (455), `_robots_allow` (484),
    `_is_html_response` (516), `_normalize_url` (522), `_dedup_key` (530), `_discover_toc_links`
    (544), `_derive_section_scope` (581), `_url_within_section_scope` (603), `_is_print_page`
    (612), `compute_backoff_seconds` (637), `__all__` (…-660).
  - **`_normalize_url` is called from `extract_links` (399), `extract_toc_script_urls` (424),
    `extract_toc_links` (445), `_dedup_key` (541), and `crawl()` (176, 270).**
- `src/docline/elt/execute.py` — `_fetch_url` (494-580) is the **sole `src/` caller** of
  `crawl()`; `results = asyncio.run(crawl(...))` at 521. `staged_count == 0` raises `OSError`
  at 568-569 **before** the manifest write at 570-578. `_crawl_config_from_source` (340-355)
  never sets `max_frontier`. `_execute_source` (196-235) builds the `StagingJob` returned to
  both interfaces and writes `metadata.json`.
- `src/docline/fetch/models.py` — `StagingJob(job_id, metadata, cache_path, complete)`; persisted
  as `metadata.json` and returned **directly** on the CLI execute path.
- **MCP does not return `StagingJob`.** `DoclineMcpServer.fetch` (`mcp/server.py:141-158`) returns
  `execute_fetch()` unchanged, and `execute_fetch` (`app.py`) converts the completed `StagingJob`
  into a **new** `FetchResult` at `app.py:621` (success) with failure returns at 592, 596, 611,
  and 615. `FetchResult` (`app_models.py:56-70`) carries only `source`, `staged_path`, `success`,
  `error`. The MCP-facing population point is therefore `app.py`, not `mcp/server.py`.
- **Full test caller inventory for `crawl()`** (verified by repo-wide search):
  `tests/fetch/test_crawl_limits.py`, `test_crawl_frontier_bound.py`, `test_aggregate_budget.py`,
  `test_crawl_backoff.py`, `test_crawl_progress.py`, `test_amplification.py`,
  **`test_crawl_section_scope.py`**, `tests/elt/test_elt_real_execution.py`, and
  **`tests/test_execute_fetch.py`** — root level, *not* under `tests/elt/`; it monkeypatches
  `docline.fetch.crawl.crawl` with a fake returning `list[CrawlResult]`, so the fake itself must
  be migrated.
- Ruff config selects `E, F, I, UP` only. The 400-line convention is **not** gate-enforced.

## Constitution Check

| Principle | Assessment |
|---|---|
| I. Safety-First Python | Full hints on every new symbol; dataclass configuration pinned in D1/D2; no bare `except`; existing `# noqa: BLE001` preserved. **PASS** |
| II. Test-First | Every source task is gated behind a red-harness task via an explicit dependency edge. **PASS** |
| III. Workspace Isolation | No filesystem-path trust changes. **PASS** |
| V. Structured Observability | The principle this work serves. **PASS** |
| VI. Single Responsibility | No new dependency; the split reduces per-module surface. **PASS** |
| No dead code | Moved symbols are re-exported from `crawl.__all__` only where they were already public; no orphan shims. **PASS** |
| CLI/MCP parity | Addressed by D7 and A.T10/A.T11a/A.T11b — see Objective. **PASS** |

## Design decisions (binding on implementation)

### D1 — `CrawlOutcome` is a non-frozen, slotted dataclass

```python
@dataclass(slots=True)
class CrawlOutcome:
    results: list[CrawlResult]
    frontier_truncated: bool
```

**`frozen=True` is rejected.** `frozen=True` with the default `eq=True` synthesizes `__hash__`,
and a `list` field makes that hash raise `TypeError` at runtime for any caller that puts the
value in a set or dict — a shallow-immutability trap. Frozenness buys nothing for a return
value. `slots=True` is used for the usual attribute-typo protection.

Rejected alternatives (recorded so review need not re-litigate): out-parameter
(`crawl(..., stats=...)`) — makes the truncation signal optional at the call site, which is the
exact failure mode 7F34A0D5 reports; `list` subclass carrying an attribute — the attribute is
lost through any `list(...)` copy; per-`CrawlResult` flag — wrong granularity.

This is a **breaking change to an internal API**. Every caller is in this repository (1 in
`src/`, 9 test modules) and is updated in-plan. No compatibility shim: a shim returning the old
shape would let a caller keep ignoring truncation.

### D2 — `_Frontier` owns admission state only; `visited` stays in the crawl loop

```python
@dataclass(slots=True)
class _Frontier:
    max_frontier: int
    start_label: str
    queue: deque[tuple[str, int]] = field(default_factory=deque)
    admitted: int = 0
    ceiling_reported: bool = False
    refused_any: bool = False
```

Binding constraints:

- **Not frozen** — it mutates `admitted`, `ceiling_reported`, `refused_any`, and `queue`.
- Container fields **must** use `field(default_factory=...)`; a literal `deque()` in the class
  body is a `ValueError` at class creation. Generic parameters are mandatory
  (`deque[tuple[str, int]]`), not bare `deque`.
- `visited` is **not** a `_Frontier` field. It is mutated at three non-admission sites (289, 318,
  322) that have nothing to do with the ceiling, and it serves emitted-page dedup — a separate
  responsibility. Folding it in would force the loop to reach through `_Frontier.visited`,
  defeating the encapsulation that justifies the dataclass. `admit()` therefore takes the
  `visited` set as an argument, or the caller adds the key on a `True` return; A.T3 must pick one
  and A.T1 must assert it.
- Method surface: `admit(link, key, depth, visited) -> bool`, `report_ceiling() -> None`,
  properties `exhausted -> bool` and `truncated -> bool`. `pop()`/`has_pending()` are **not**
  added; the loop uses `frontier.queue` for `popleft`/emptiness, which is a deliberate, documented
  seam and not an encapsulation break because queue ordering is the loop's concern.

### D3 — `frontier_truncated` means "at least one eligible link was refused"

`truncated` returns `refused_any`, **not** `ceiling_reported` and **not**
`admitted >= max_frontier`. This distinction is load-bearing:

- `report_ceiling()` fires from the two short-circuits (290-291, 324-329) merely because the cap
  is *full*, before any link is examined. A crawl that exactly fills the cap and then visits a
  link-free HTML page has lost nothing.
- `admitted >= max_frontier` is `True` the instant the cap is exactly reached — an off-by-one
  that reports truncation for a crawl that discarded nothing.

`refused_any` is set **only** in `admit()` on the refusal path, before returning `False`. The two
short-circuit sites continue to call `report_ceiling()` (operator-facing log) but must **not** set
`refused_any` unless a candidate link was actually rejected. A.T2 asserts all five cases:
under-cap, exactly-at-cap-with-no-further-candidates, exactly-at-cap-then-link-free-page,
print-page-branch refusal, main-branch refusal.

### D4 — The truncation record is WARNING with a reduced payload

`logger.debug` → `logger.warning`, still once per crawl. **The payload changes**: the full
sanitized start URL is replaced by the sanitized **origin** (scheme + host) plus the admission
count. `sanitize_source()` strips userinfo and a fixed list of credential-named query parameters
only; it does not redact path segments, unrecognized query names (`code`, `jwt`, `session`), or
control characters. Promoting a full URL from DEBUG to default-visible WARNING would widen that
exposure. An origin carries the operator-actionable information without the tail.

Lazy `%`-formatting is retained (positional args, never an f-string). Per-link drop logging
remains **rejected** (058-S: unbounded log volume under the adversarial condition).

### D5 — The split is two new modules, and the line arithmetic is stated

The single-module split proposed in review round 1 could not reach 400 lines and introduced a
circular import (`crawl_links` needs `_normalize_url`, which stays in `crawl`). Both are fixed:

- **`src/docline/fetch/crawl_models.py`** — `MAX_FRONTIER`, `CrawlLimitExceededError`,
  `CrawlRobotsError`, `CrawlConfig`, `CrawlResult`, `CrawlOutcome`, `_Frontier`. Imports nothing
  from `crawl` or `crawl_links`.
- **`src/docline/fetch/crawl_links.py`** — pure URL/HTML helpers with no crawl-loop state:
  `_LinkExtractor`, `extract_links`, `extract_toc_script_urls`, `extract_toc_links`,
  **`_normalize_url`**, `_dedup_key`, `_derive_section_scope`, `_url_within_section_scope`,
  `_is_print_page`. Imports only `re`, `urllib.parse`, `HTMLParser`, `url_canonical`, and
  `url_policy`. **Imports nothing from `crawl.py` or `crawl_models.py`.**
- **`crawl.py`** retains the loop, `check_robots_allowed`, `_robots_allow`, `_fetch_with_retries`,
  `_discover_toc_links`, `_is_html_response`, `compute_backoff_seconds`, and `__all__`.

Import direction is strictly one-way: `crawl_models` and `crawl_links` are leaves;
`crawl.py` imports both. **Acyclicity is an explicit acceptance criterion.**

Estimated arithmetic: 660 − ~120 (`crawl_models`) − ~200 (`crawl_links`) ≈ 340, plus ~20 lines of
imports and re-exports, minus ~10 net from replacing the closures with `_Frontier` ≈ **~350**.
This is an estimate; the actual count is verified at A.T4 acceptance. If the realized count
exceeds 400, `_discover_toc_links` + `_robots_allow` + `_fetch_with_retries` move to a third
module `crawl_discovery.py` (they depend on `CrawlConfig`, which now lives in `crawl_models`, so
this stays acyclic) — pre-authorized as a contingency, not speculative work.

### D6 — TOC-first ordering: what it does and does not guarantee

At depth zero, `discovered_links = toc_links + anchor_links`. Nothing else changes: no priority
queue, no reorder of the admitted frontier, no `_dedup_key` change, no change to
break-on-first-refusal.

Two claims from round 1 are **corrected**:

1. **The fetched page set is *not* invariant below the ceiling when `max_pages` binds.** The loop
   condition (225) stops after `max_pages` budget-consuming pages, so changing FIFO admission
   order changes *which* pages are fetched whenever eligible candidates exceed `max_pages`, even
   with no truncation at all. This is an accepted, documented behaviour change: on an mdBook site,
   fetching TOC-derived pages in preference to in-page anchors is the intent. A.T9 asserts it
   deliberately rather than asserting a false invariant.
2. **Not every syntactic TOC link is retained.** Links that are off-domain, out of section scope,
   already in `visited`, or duplicate under `_dedup_key` are skipped and leave capacity for
   anchors. A.T9 is therefore expressed over **eligible, unique, in-scope** TOC links.

### D7 — Parity: `frontier_truncated` reaches CLI and MCP, each through its own real seam

The manifest key alone does not satisfy 7F34A0D5, which states the partial crawl is
indistinguishable from a complete one *"on both the CLI and MCP paths"*. `crawl-manifest.json`
lives inside the staging cache; a caller must know the private layout to read it.

**The two interfaces do not share one response model**, and round 2's assumption that they did
was wrong:

- **CLI** serializes `StagingJob` directly. `StagingJob` gains `frontier_truncated: bool = False`
  (additive, defaulted, so every existing construction site and every persisted `metadata.json`
  stays valid). `_fetch_url` returns the staged count **and** the flag; `_execute_source` sets it
  on the job.
- **MCP** returns `FetchResult`, which `execute_fetch` constructs fresh from the completed
  `StagingJob` (`app.py:621`, with failure returns at 592, 596, 611, 615). `FetchResult` gains the
  same additive defaulted field, populated from `job.frontier_truncated` at the success return.
  Failure returns keep the default `False` — a request that never produced a job cannot report
  truncation. Editing `mcp/server.py` alone would be a no-op because that method performs no
  result transformation.

**Field placement rationale (layering exception, deliberate).** `frontier_truncated` is a
fetch-capture attribute, and `SourceMetadata` is where web/HTTP-specific capture attributes
(`http_status`, `content_type`) already live, so placing it there would be the more consistent
layering. It goes on `StagingJob` instead because **`SourceMetadata` is constructed before the
fetch runs** (`execute.py:202`, ahead of the `try:`), whereas `StagingJob` is constructed after
it completes (`execute.py:227`) — the only point at which the truncation outcome is known.
Putting it on `SourceMetadata` would require post-hoc mutation of an already-built pydantic model
inside the error-handling path. The cost of the exception is a field that is permanently `False`
for non-web sources; the cost of the alternative is mutation in a `try/except` path that A.T9 is
explicitly forbidden to restructure. If a future change makes `SourceMetadata` construction lazy,
the field should move.

### D8 — The manifest is written even when nothing is staged

`_fetch_url` currently raises `OSError` at 568-569 before writing the manifest, so a crawl that
truncates to zero stageable pages leaves no artifact — precisely the case where the operator most
needs the signal. The manifest write moves **before** the zero-staged guard, emitting
`{"pages": [], "frontier_truncated": <outcome.frontier_truncated>}`. The `OSError` still raises,
and the `except BaseException` completion-event contract is untouched.

**The value is the real flag, never a hard-coded `true`.** Zero pages staged does not imply
truncation: a print-page start URL with `max_frontier=0` hits the exhausted short-circuit at
`crawl.py:290-291`, which calls `report_ceiling()` but never calls `admit()` and so never sets
`refused_any`; robots-denied and failed-start crawls likewise stage nothing while refusing no
discovered link. Under D3 all of those report `False`. Writing `true` unconditionally would make
the persisted manifest contradict the CLI and MCP payloads that A.T10 requires to report `False`
for the same request.

### D9 — Out of scope

Changing `MAX_FRONTIER` or the ceiling semantics; per-link drop logging; a `crawl-manifest.json`
schema version field; changes to `WebCrawlSource`'s public manifest fields; a `max_frontier`
passthrough on `_crawl_config_from_source`; any general crawl redesign (priority queues, pluggable
admission policies).

## Task decomposition (harness-first, <=2h each, width-isolated)

### A.T1 — Harness: `_Frontier` admission unit semantics (red)

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_frontier_admission.py` (new).
- Unit assertions with **no crawl, no network, no event loop**: admits up to `max_frontier`;
  refuses beyond; refused links are **not** added to `visited` (the 058-S invariant); `admit()`
  returns `False` on refusal; `max_frontier=0` refuses everything; `report_ceiling()` emits once.
- Also asserts `_Frontier` is not frozen and that container fields are per-instance (two
  instances do not share a `queue`).
- **Acceptance:** fails red on `_Frontier` not existing. No source change.

### A.T2 — Harness: `truncated` predicate across all report sites (red)

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_frontier_admission.py` (extends A.T1).
- Asserts D3's five cases: under-cap → `False`; exactly-at-cap with no further candidates →
  `False`; exactly-at-cap then a link-free HTML page → `False`; refusal in the print-page branch →
  `True`; refusal in the main branch → `True`.
- **Acceptance:** red. No source change.
- **Depends on:** A.T1.

### A.T2b — Harness: non-counting control-flow characterization (red-or-green guard)

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_control_flow.py` (new).
- The existing `tests/fetch/test_crawl_section_scope.py` exercises rejection of a *discovered*
  sibling link before it enters the frontier — **not** the post-fetch final-URL branch at
  `crawl.py:316`, which is a non-counting `continue`. A refactor that moves queue/`visited` state
  around that branch could wrongly increment `page_count`, emit a progress event, append a
  result, or fall through into print-page / duplicate-final handling with no targeted failure.
- Characterize, against **current** source: an admitted in-scope URL whose *final* URL resolves
  outside the inferred section produces no `CrawlResult`, no `page_count` increment, no progress
  event, and no discovery from its body; subsequent queued work is unaffected. Retain separate
  cases for the redirect-alias and duplicate-final branches.
- **Acceptance:** green against current source (this is characterization, not a red harness), and
  must stay green through A.T3 and A.T4.
- **Depends on:** A.T2.

### A.T3 — Extract `_Frontier` and retire the admission closures

- **Domain:** src. **Files:** `src/docline/fetch/crawl.py`.
- Add `_Frontier` per D2 (module-level for now; it moves in A.T4). Delete `_admit` /
  `_report_ceiling` and all `nonlocal` admission state. Route the two short-circuits through
  `frontier.exhausted` and the refusal path through `admit()`.
- **Behaviour-preserving: no log-level change, no return-type change, no ordering change.**
- **Acceptance:** A.T1 + A.T2 + **A.T2b** green; **full `pytest` green with zero edits to existing
  tests** — needing to edit an existing test is treated as an unplanned behaviour change and halts
  the task. Control-flow paths preserved verbatim: the non-counting section-scope `continue`
  (316), the print-page branch, the duplicate-final branch, redirect-alias handling.
- **Depends on:** A.T2b.

### A.T4 — Split `crawl.py` into `crawl_models.py` + `crawl_links.py`

- **Domain:** src. **Files:** `src/docline/fetch/crawl_models.py` (new),
  `src/docline/fetch/crawl_links.py` (new), `src/docline/fetch/crawl.py`.
- Move the symbol sets named in D5 verbatim, `_normalize_url` included. Update `crawl.py` imports
  and `__all__` so every previously public name stays importable from its documented location.
  Google-style module docstrings on both new modules.
- **Acceptance:** `python -c "import docline.fetch.crawl"` succeeds (no circular import);
  `crawl_links.py` and `crawl_models.py` contain **zero** imports from `docline.fetch.crawl`;
  realized `crawl.py` line count recorded in the task log and **< 400** (if not, apply the D5
  contingency); `pytest` green with zero test edits; `pyright src/` 0 errors.
- **Depends on:** A.T3.

### A.T5 — Harness: truncation observability signal (red)

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_truncation_signal.py` (new).
- Asserts `crawl()` returns `CrawlOutcome`; `frontier_truncated` matches D3 semantics on a real
  crawl; **exactly one** WARNING via `caplog` on a truncated crawl and **zero** on an
  under-ceiling crawl.
- Payload assertions per D4: the record contains the sanitized origin and the admission count and
  **does not** contain the URL path, query string, fragment, or userinfo. Cases must include a
  credential in the path, an unrecognized credential-shaped query name (`code`, `jwt`, `session`),
  userinfo, and a control character in the URL.
- **Acceptance:** red. No source change.

### A.T6 — Introduce `CrawlOutcome`, promote the record to WARNING

- **Domain:** src. **Files:** `src/docline/fetch/crawl_models.py`, `src/docline/fetch/crawl.py`.
- Add `CrawlOutcome` per D1 with a Google-style docstring documenting both attributes. `crawl()`
  returns `CrawlOutcome(results=results, frontier_truncated=frontier.truncated)`. `report_ceiling`
  becomes `logger.warning` with the D4 payload, lazy `%` args. Export `CrawlOutcome`.
- **Acceptance:** A.T5 green; `pyright src/` 0 errors. Full `pytest` is **expected red** in caller
  modules here — see the Verification gate exception.
- **Depends on:** A.T5, A.T4.

### A.T7 — Migrate crawl-core test callers to `CrawlOutcome`

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_limits.py`,
  `tests/fetch/test_crawl_frontier_bound.py`, `tests/fetch/test_crawl_section_scope.py`.
- Mechanical: `results = await crawl(...)` → `outcome = await crawl(...)`; assertions read
  `outcome.results`. No assertion semantics change.
- **Acceptance:** these three modules green.
- **Depends on:** A.T6.

### A.T8a — Migrate ELT test callers to `CrawlOutcome`

- **Domain:** tests. **Files:** `tests/elt/test_elt_real_execution.py`,
  `tests/test_execute_fetch.py`.
- Same mechanical migration. **Both modules monkeypatch or stub `crawl`**, so their fakes must be
  updated to return a `CrawlOutcome`, not just their call sites. Also update any assertion on
  `_fetch_url`'s return value, which becomes a `(count, truncated)` pair in A.T9.
- **Acceptance:** these two modules green in isolation.
- **Depends on:** A.T6.

### A.T8b — Migrate budget and backoff test callers to `CrawlOutcome`

- **Domain:** tests. **Files:** `tests/fetch/test_aggregate_budget.py`,
  `tests/fetch/test_crawl_backoff.py`.
- **Acceptance:** these two modules green in isolation.
- **Depends on:** A.T6.

### A.T8c — Migrate progress and amplification test callers to `CrawlOutcome`

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_progress.py`,
  `tests/fetch/test_amplification.py`.
- **Acceptance:** these two modules green in isolation; with A.T7, A.T8a, and A.T8b applied, the
  whole `tests/` suite is green apart from work still owned by A.T9-A.T13.
- **Depends on:** A.T6.

> A.T7, A.T8a, A.T8b, and A.T8c split round-1's single migration task, which touched 6+ files and
> exceeded the 2-hour heuristic. Round 2 split it again: a 6-file task spanning both `tests/fetch/`
> and `tests/elt/` still violated the file-count rule and mixed two sub-domains. Each task now
> touches at most 3 files within one sub-domain. The inventory must be re-confirmed by a
> repo-wide search immediately before A.T6; three callers were missed in round 1.

### A.T9 — Thread truncation into the manifest and the staging job

- **Domain:** src. **Files:** `src/docline/elt/execute.py`, `src/docline/fetch/models.py`.
- `_fetch_url` consumes `CrawlOutcome` and returns `(staged_count, frontier_truncated)`. The
  outcome unpacking and the `for result in outcome.results` iteration must remain **inside** the
  existing `try:` so the `except BaseException` completion-event path still fires on partial
  staging failure. Manifest becomes
  `{"pages": manifest_pages, "frontier_truncated": <bool>}` and is written **before** the
  `staged_count == 0` guard (D8). `StagingJob` gains `frontier_truncated: bool = False` with an
  `Attributes:` docstring entry; `_execute_source` sets it from `_fetch_url`.
- **Acceptance:** manifest contains the key and is written even when zero pages stage, carrying
  the **real** flag value — regression cases required for (a) a no-refusal zero-staged path
  (print-page/exhausted short-circuit, `max_frontier=0`) → `false`, (b) a robots-denied or
  failed-start zero-staged crawl → `false`, and (c) any reachable zero-staged crawl that did
  refuse a link → `true`; `_load_crawl_manifest` still parses; existing `metadata.json` files
  without the field still validate (defaulted); the `OSError` still raises with the same message
  and the `except BaseException` completion event still fires; `pyright src/` 0 errors.
- **Depends on:** A.T6.

### A.T10 — Harness: CLI/MCP parity for the truncation signal (red)

- **Domain:** tests. **Files:** `tests/test_cli_mcp_truncation_parity.py` (new).
- Executes an equivalent truncating web-crawl request through the CLI surface and the MCP tool
  surface and asserts both report the **same** `frontier_truncated` value, and that both report
  `False` for an untruncated crawl.
- Assertions are made against the **actual serialized payloads** — the CLI's `StagingJob` output
  and the MCP tool's `FetchResult` — not against internal objects. Includes the failure and
  zero-staged cases, where both surfaces must report `False` rather than raising or omitting the
  field.
- **Acceptance:** red before A.T9/A.T11a/A.T11b land.
- **Depends on:** A.T8a, A.T8b, A.T8c.

### A.T11a — Surface `frontier_truncated` on the CLI response

- **Domain:** src. **Files:** `src/docline/cli.py`.
- Propagate the `StagingJob` field (added in A.T9) into the CLI's job output. Additive and
  defaulted; no existing field is renamed or removed.
- **Acceptance:** the CLI half of A.T10 green; `pyright src/` 0 errors.
- **Depends on:** A.T10, A.T9.

### A.T11b — Surface `frontier_truncated` on the MCP response

- **Domain:** src. **Files:** `src/docline/app_models.py`, `src/docline/app.py`.
- Add `frontier_truncated: bool = False` to `FetchResult` with an `Attributes:` docstring entry,
  and populate it from `job.frontier_truncated` at the `execute_fetch` success return
  (`app.py:621`). The four failure returns (592, 596, 611, 615) keep the default.
- **`mcp/server.py` is not edited** — it returns `execute_fetch()` unchanged, so the field
  propagates automatically once `FetchResult` carries it. Confirm this by test, not by assumption.
- **Acceptance:** A.T10 fully green (both halves); full `pytest` green; `pyright src/` 0 errors.
- **Depends on:** A.T11a.

> A.T11a/A.T11b split round-2's single A.T11, which touched 3 files and mixed the CLI and MCP
> skill domains. Round 3 also corrected the MCP seam: the field must be added to `FetchResult` in
> `app_models.py` and populated in `app.py`, because `execute_fetch` builds a fresh `FetchResult`
> rather than returning the `StagingJob`.

### A.T12 — Harness: TOC-first ordering under truncation (red)

- **Domain:** tests. **Files:** `tests/fetch/test_crawl_toc_priority.py` (new).
- A depth-zero page with N in-page anchors and M TOC links, ceiling below N+M: assert every
  **eligible, unique, in-scope** TOC link is admitted and that in-page anchors are the ones
  dropped (D6.2). Separately assert the documented `max_pages` interaction (D6.1): with
  `max_pages` below the eligible-candidate count and **no** truncation, TOC-derived pages are
  fetched in preference to anchors.
- Before writing, grep `tests/fetch/` for order-dependent assertions on crawl results and record
  the finding in the task log; any such test is updated **here**, in tests width, never in A.T13.
- **Acceptance:** red.

### A.T13 — Order TOC-derived links ahead of in-page anchors at depth zero

- **Domain:** src. **Files:** `src/docline/fetch/crawl.py`.
- Build `discovered_links = toc_links + anchor_links` at depth zero instead of tail-appending.
  `_discover_toc_links` is still awaited only at depth zero and only when the ceiling is not
  already exhausted.
- **Acceptance:** A.T12 green; full suite green; `crawl.py` still under 400 lines.
- **Depends on:** A.T12, A.T4.

### A.T14 — Document the truncation signal

- **Domain:** docs. **Files:** `docs/ARCHITECTURE.md`, `README.md`.
- Record the WARNING record and its reduced payload, the `frontier_truncated` manifest key, the
  `StagingJob` field, the CLI/MCP surfacing, and the operator remedy (raise `max_frontier` or
  narrow the crawl). Note that the ELT path always uses the `MAX_FRONTIER` default because
  `_crawl_config_from_source` does not override it.
- Edit **only** the crawl/fetch section of `docs/ARCHITECTURE.md`; Group B's doc task edits the
  sitemap section. The two shipments share this file (see R8).
- **Acceptance:** markdown gates pass; no source change.
- **Depends on:** A.T11b, A.T13.

## Dependency graph

```text
A.T1 → A.T2 → A.T2b → A.T3 → A.T4 ─┬──────────────→ A.T6 ─┬→ A.T7   ─┐
                           │  A.T5 ─────────┘      ├→ A.T8a  ─┤
                           │                       ├→ A.T8b  ─┼→ A.T10 → A.T11a → A.T11b ─┐
                           │                       ├→ A.T8c  ─┘                            ├→ A.T14
                           │                       └→ A.T9 ─────────────→ A.T11a           │
                           └──────────────────→ A.T12 → A.T13 ───────────────────────────  ┘
```

## Verification

Gates: `ruff check .`, `pyright src/`, `pytest`, `ruff format --check .`.

**Gate policy exception (aligns with R7).** Full-suite green is a *merge* precondition for the
atomic unit {A.T6, A.T7, A.T8a, A.T8b, A.T8c, A.T9, A.T10, A.T11a, A.T11b}, not a per-task gate.
Inside that unit, and for the red-harness tasks (A.T1, A.T2, A.T5, A.T10, A.T12), the per-task
gate is `ruff check` + `pyright src/` + the task's own targeted tests. Every other task carries
the full four-gate requirement.

Shipment exit criteria:

1. Realized `crawl.py` line count < 400, recorded in the A.T4 task log.
2. `crawl_models.py` and `crawl_links.py` import nothing from `crawl.py` (acyclic, asserted).
3. `_Frontier.admit()` exercised by unit tests with no network and no event loop.
4. A refusal sets `frontier_truncated`; exactly reaching the cap without a refusal does not.
5. A truncated crawl emits exactly one WARNING whose payload contains no path, query, fragment,
   or userinfo; an under-ceiling crawl emits none.
6. `crawl-manifest.json` carries `frontier_truncated` **including when zero pages stage**, and its
   value always equals the value reported by the CLI and MCP payloads for the same request —
   never a hard-coded `true`.
7. CLI and MCP report the same `frontier_truncated` value for an equivalent request.
8. Under truncation on an mdBook-shaped page, eligible in-scope TOC links are retained and
   anchors are dropped.
9. Full suite green with no skips added.

## Rollback

Single `git revert -m 1 <merge-sha>`. Non-additive changes are confined to D1 (return type), D6
(ordering), and D8 (manifest write position) — all inside `fetch/crawl*.py`, `fetch/models.py`,
`elt/execute.py`, `cli.py`, `mcp/server.py`, and their tests. Persisted artifacts survive a
revert harmlessly: `crawl-manifest.json` readers use only `"pages"`, and `StagingJob` gains a
defaulted field, so a reverted build still validates a `metadata.json` written by the new build
(the extra key is ignored by pydantic's default configuration — **A.T9 must confirm this against
the model's config and, if `extra="forbid"` is set, the rollback note is amended accordingly**).

## Plan Hardening

### Risk register

| ID | Risk | Likelihood | Blast radius | Mitigation |
|---|---|---|---|---|
| R1 | The `_Frontier` extraction silently changes admission behaviour and re-opens the 058-S memory-exhaustion vector | Medium | High — reintroduces a shipped security/availability fix | A.T1/A.T2 precede A.T3 and pin the 058-S invariants: refused links never enter `visited`; `admitted` increments only on success; report fires once. A.T3 must pass with **zero edits to existing tests**. |
| R2 | The `CrawlOutcome` change is missed at a caller and fails at runtime | Medium | Medium | `pyright src/` covers the single `src/` caller. **`pyright src/` does not type-check `tests/`**, so the "fails loudly" guarantee for test callers rests on runtime `AttributeError`, not type-check — hence the enumerated inventory in A.T7/A.T8a/A.T8b/A.T8c and the mandatory pre-A.T6 re-search. Round 1 missed 3 callers; that is why re-search is mandatory. |
| R3 | D6 ordering breaks an order-sensitive existing assertion | Medium | Low-Medium | A.T12 requires a grep for order-dependent assertions **before** implementation, and fixes them in tests width. D6.1 states the `max_pages` behaviour change openly instead of asserting a false invariant. |
| R4 | The WARNING leaks URL-carried secrets now that it is default-visible | Medium | Medium — credential disclosure in logs | D4 reduces the payload to sanitized origin + count. A.T5 asserts absence of path, query, fragment, userinfo, and control characters, using credential-in-path and unrecognized-credential-parameter cases that `sanitize_source` alone does not cover. |
| R5 | The module split introduces a circular import or breaks an undiscovered importer | Medium | Medium — unbuildable tree | Round 1's seam **was** circular (`_normalize_url`). D5 moves it into the leaf module and mandates a one-way direction. A.T4 acceptance includes an explicit import-and-acyclicity check plus a repo-wide grep for each moved symbol. |
| R6 | Scope creep into a general crawl redesign | Medium | Medium | D9 is binding. The third-module contingency in D5 is pre-authorized and bounded; anything else goes to the stash. |
| R7 | A partially-landed shipment leaves `main` with `crawl()` returning `CrawlOutcome` but callers expecting a list | Low | High — broken ELT/CLI/MCP path | {A.T6, A.T7, A.T8a, A.T8b, A.T8c, A.T9, A.T10, A.T11a, A.T11b} is atomic for merge. The Verification gate exception makes the red window explicit and bounded rather than contradicting the gate policy. |
| R8 | Both shipments edit `docs/ARCHITECTURE.md`, producing a merge conflict if they land concurrently | Medium | Low | Acknowledged: the two shipments share **no source file** but do share this doc. A.T14 is scoped to the crawl/fetch section, Group B's doc task to the sitemap section. Whichever shipment merges second rebases the doc hunk. |
| R9 | The zero-staged manifest write (D8) masks or reorders the existing `OSError` | Low | Medium | A.T9 acceptance requires the `OSError` still raise with the same message and the `except BaseException` completion event still fire. The write is inserted before the guard, not in place of it. |

### Rollback rehearsal

`git revert -m 1 <merge-sha>` restores the prior return type, ordering, manifest position, and
`StagingJob` shape in one operation, since every change is in one merge. The two surviving
artifacts are a `crawl-manifest.json` carrying an extra key (readers use `"pages"` only) and a
`metadata.json` carrying an extra field (tolerated unless the model forbids extras — confirmed in
A.T9). No migration step, no cleanup, safe at any point after merge.

### Guardrails carried into implementation

- No task may edit an existing test to make a refactor pass. Existing-test changes belong in a
  tests-width task with a stated rationale.
- `ceiling_reported`, `admitted`, `refused_any`, and `visited` semantics are frozen by A.T1/A.T2
  and may not be altered by any later task in this shipment.
- Every log record carrying a crawl URL keeps `sanitize_source()`, and the WARNING additionally
  carries origin only.
- The `except BaseException` progress-completion contract in `_fetch_url` is not restructured;
  outcome unpacking stays inside the `try:`.
- New public symbols (`CrawlOutcome`) and new modules get Google-style docstrings at landing time,
  not in a follow-up. Ruff does not enforce `D`; this is a review-enforced criterion.

### Verification depth

Beyond the gates, a runtime spot-check on the ELT path: run a crawl with `max_frontier` forced low
against a local fixture site and confirm (1) exactly one WARNING at default verbosity carrying no
URL tail, (2) `frontier_truncated: true` in the emitted `crawl-manifest.json`, (3) the same flag
on the returned `StagingJob` via both CLI and MCP, and (4) TOC-derived pages present in the staged
set.

## Plan Review Record

Multi-persona adversarial plan review, 4 rounds. Gate outcome: **PASS**.

| Persona | Round 1 | Final | Findings applied |
|---|---|---|---|
| Architecture | FAIL | **PASS** | P1 split could not reach 400 lines → D5 now two leaf modules with stated arithmetic + pre-authorized contingency. P1 circular import (`crawl_links` needs `_normalize_url`) → `_normalize_url` and `_dedup_key` moved into the leaf; acyclicity is an A.T4 gate. P2 `_Frontier` conflated responsibilities → `visited` excluded. P3 gate-policy contradiction → explicit exception. P3 shared `ARCHITECTURE.md` → R8. P3 field placement → D7 layering-exception rationale. |
| Correctness | FAIL | **PASS** | P1 caller inventory incomplete (6 → 9 modules, incl. `test_crawl_section_scope.py`, `tests/elt/test_elt_real_execution.py`, root-level `tests/test_execute_fetch.py`). P1 CLI/MCP parity not achieved → D7 + A.T10/A.T11a/A.T11b targeting the real seams. P1 D8 hard-coded `true` contradicted D3 → now the real flag with three zero-staged regression cases. P2 truncated predicate off-by-one → D3 `refused_any`. P2 zero-staged manifest never written → D8. P2 `max_pages` claim false → D6.1 retraction. P2 no characterization for the non-counting section-scope `continue` → A.T2b. |
| Scope | FAIL | **PASS** | P1 A.T6 at 6 files → split to A.T7 + A.T8a/b/c, each ≤2 files in one sub-domain. P2 A.T11 at 3 files mixing CLI and MCP → A.T11a/A.T11b. Ruled D7 parity and D8 manifest-write **in scope** (7F34A0D5 names both CLI and MCP paths). |
| Security | ADVISORY | **ADVISORY** | P2 WARNING payload widens URL-secret exposure (`sanitize_source` does not redact path segments, unrecognized query names, or control characters) → D4 reduces the payload to sanitized origin + count; A.T5 asserts absence of path/query/fragment/userinfo. Confirmed the manifest boolean leaks nothing. |
| Python-safety | ADVISORY | **ADVISORY** | P2 `frozen=True` + `list` field synthesizes an unhashable `__hash__` → D1 pins `@dataclass(slots=True)`, not frozen. P2 mutable dataclass defaults → D2 mandates `field(default_factory=...)`, precise generics, and states `_Frontier` is not frozen. P3 docstrings on new public symbols/modules → A.T4/A.T6 acceptance. P3 `pyright src/` does not cover `tests/` → recorded in R2. |
