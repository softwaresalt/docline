---
type: decided-plan
title: "Decided plan: 059-S crawl frontier truncation observability"
source_plan: 2026-08-29-crawl-frontier-observability-plan.md
consolidated_at: 2026-08-30
status: shipped
shipment: 059-S
feature: 068-F
pr: 179
merge_commit: 58ba5c5b67abf5c73457d11e5af76c60bdd483b1
---

## Decision Summary

The 058-S admission ceiling worked but shipped as an untestable closure whose only output was a
DEBUG line: a truncated crawl was byte-identical to a complete one on both the CLI and MCP paths,
and `crawl.py` had grown to 660 lines. 059-S makes the admission rule a composable, testable
structure and uses it to surface truncation to operators and to stop truncation from preferentially
dropping authoritative mdBook TOC navigation. The ceiling value and semantics are unchanged.

The shipped decision:

* Extracts a `_Frontier` dataclass owning admission state (`admit()`, `report_ceiling()`,
  `exhausted`, `truncated`), and splits `crawl.py` into three acyclic leaf modules —
  `crawl_models.py`, `crawl_links.py`, `crawl_discovery.py` — leaving the loop module at 399 lines.
  The fetch-calling helpers stayed in `crawl.py` to preserve the `docline.fetch.crawl.fetch_page`
  monkeypatch seam (the D5 contingency was adapted, not applied literally).
* Changes `crawl()` to return `CrawlOutcome(results, frontier_truncated)`. `frontier_truncated`
  means the ceiling **cost the crawl an eligible link** — a direct admission refusal, or, at a
  depth-zero exhausted short-circuit, an eligible `toc-*.js` reference that cannot be examined
  without a network fetch. The signal is deliberately conservative: it may over-report but never
  under-reports.
* Promotes the truncation record from DEBUG to a once-per-crawl WARNING at default verbosity with
  an **origin-only** payload (scheme + host + admission count) so a default-visible log cannot leak
  URL-carried credentials.
* Threads the flag through `crawl-manifest.json` (written even when zero pages stage),
  `StagingJob.frontier_truncated`, and `FetchResult.frontier_truncated` for exact CLI/MCP parity;
  `CrawlStagedNothingError(OSError, DoclineError)` carries it across the zero-staged boundary.
  `cli.py` and `mcp/server.py` are unchanged.
* Orders TOC-derived links ahead of in-page anchors at depth zero so a truncated mdBook crawl sheds
  anchors and keeps the authoritative TOC set.

## Implementation Units

Nineteen tasks (068.001-T … 068.019-T) executed harness-first in manifest dependency order:

* Composability (A.T1–A.T4): `_Frontier` admission + truncated-predicate unit harness, non-counting
  control-flow characterization, `_Frontier` extraction, and the three-module split.
* Observability (A.T5–A.T9): truncation-signal harness, `CrawlOutcome` + WARNING, five caller
  migrations to `CrawlOutcome`, and threading the flag into the manifest and `StagingJob` with
  `CrawlStagedNothingError`.
* Parity (A.T10–A.T11b): CLI/MCP parity harness, CLI-no-change verification, and the `FetchResult`
  field.
* Ordering + docs (A.T12–A.T14): TOC-first ordering harness and implementation, and the
  architecture/README documentation.

## Binding Constraints (survive compaction)

* **`CrawlOutcome` is `@dataclass(slots=True)`, not frozen.** `frozen=True` with the default
  `eq=True` synthesizes `__hash__`, which raises `TypeError` at runtime for a `list` field placed in
  a set/dict — a shallow-immutability trap. Frozenness buys nothing for a return value.
* **`_Frontier` owns admission state only; `visited` stays in the crawl loop.** `visited` is mutated
  at three non-admission sites and serves emitted-page dedup — a separate responsibility. `admit()`
  takes `visited` as an argument and records a key on success only; a refused link never enters
  `visited` (the 058-S memory-bound invariant). Container fields use `field(default_factory=...)`.
* **`frontier_truncated` means the ceiling cost the crawl an eligible link** (`refused_any`), not
  that the cap was reached or that `ceiling_reported` fired. It is deliberately conservative at the
  depth-zero TOC short-circuit (D3): a pure `toc-*.js` parse can set it even when the script would
  yield no admissible links — it over-reports, never under-reports.
* **The WARNING payload is origin-only** (scheme + host + admission count), never the URL path,
  query, fragment, or userinfo, because promoting the record from DEBUG to a default-visible WARNING
  would otherwise widen credential exposure that `sanitize_source` does not fully close.
* **The CLI/MCP seams differ.** The CLI serializes `StagingJob` wholesale (`model_dump`), so the
  additive `StagingJob.frontier_truncated` field appears with no `cli.py` edit. MCP builds a fresh
  `FetchResult` in `execute_fetch`, so the field is added there and populated at the success and
  zero-staged returns; `mcp/server.py` performs no transformation and is not edited.
* **Field placement on `StagingJob`, not `SourceMetadata`.** `SourceMetadata` is constructed before
  the fetch runs; `StagingJob` is constructed after it completes — the only point where the
  truncation outcome is known. The cost is a permanently-`False` field for non-web sources.
* **Zero-staged exception transport.** `CrawlStagedNothingError(OSError, DoclineError)` carries the
  real flag across the zero-staged boundary because `_execute_source` builds the `StagingJob` only
  after the `try/except`; a local `frontier_truncated = False` is initialised before the `try` so
  non-URL sources never hit an unbound local. The manifest is written before the zero-staged guard.

## Rejected Alternatives

* **Out-parameter (`crawl(..., stats=...)`) or a `list` subclass carrying an attribute** for the
  truncation signal — the out-parameter makes truncation optional at the call site (the exact
  failure mode being fixed); the attribute is lost through any `list(...)` copy. `CrawlOutcome` is
  the explicit return shape instead. A per-`CrawlResult` flag is the wrong granularity.
* **A compatibility shim returning the old `list` shape** — rejected; it would let a caller keep
  ignoring truncation. All 1 `src/` and 10 test callers were migrated in-shipment.
* **Per-link drop logging** — rejected (058-S): unbounded log volume under the adversarial
  fan-out. The record stays once-per-crawl.
* **D9 out of scope:** changing `MAX_FRONTIER` or the ceiling semantics; a `crawl-manifest.json`
  schema-version field; a `max_frontier` passthrough on `_crawl_config_from_source`; any general
  crawl redesign (priority queues, pluggable admission policies).
* **D5 literal contingency** (moving the fetch-calling helpers to `crawl_discovery.py`) — adapted,
  not applied: relocating them would rebind the `docline.fetch.crawl.fetch_page` monkeypatch seam
  used by five test modules and force forbidden test edits. Only the stateless fetch-free helpers
  moved; `crawl.py` still landed under 400 lines.

## Verification

Quality gates on PR #179's final head `31f4954`: `ruff check` pass, `pyright src/` 0 errors,
`pytest` 2049 passed / 6 skipped, `ruff format --check` clean. CI green across all seven checks; the
merge commit `58ba5c5` was produced from that verified head. Post-merge runtime verification ran 18
checks across direct-refusal truncation, the conservative depth-zero TOC signal (no network fetch),
sanitized WARNING payloads, manifest persistence, CLI/MCP flag parity, malformed-port typed
rejection, and unchanged uncapped behavior — all passed.

## Review Outcome

Five-persona adversarial review (no P0/P1) plus seven Copilot review cycles ending in "Approval
recommended" with zero unresolved threads. Notable remediations: IPv6 origin-label bracket
preservation, typed rejection of malformed crawl-URL ports, mutation-coverage tests for the
exhausted TOC and print-page branches and the zero-staged `_fetch_url` D8 contract, and reconciling
the truncation contract wording with the conservative TOC signal across code, docs, and the PR.

## Accepted Risk

The conservative depth-zero TOC signal can over-report when a `toc-*.js` reference yields no
admissible links (plan decision D3). A follow-up stash (`D6E758F5`, high) records a pre-existing
credential leak in the ELT ERROR log that is out of scope for 059-S.

The full plan, including the D1–D9 decisions, task decomposition, risk register, and plan-review
record, is archived at `docs/archive/plans/2026-08-29-crawl-frontier-observability-plan.md`.
