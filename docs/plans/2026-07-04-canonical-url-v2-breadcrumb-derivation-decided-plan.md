---
type: decided-plan
source_plan: 2026-07-04-canonical-url-v2-breadcrumb-derivation-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped canonical URL v2 work replaced ineffective Learn URL prefix derivation from `.openpublishing.publish.config.json` with `docfx.json` breadcrumb-path prefix derivation. The change moved real-corpus coverage from near zero toward the spike's 83% doc coverage while preserving v1 behavior when no prefix map is supplied.

The shipment stayed focused on self-contained Units 1 and 2: pure prefix derivation plus CLI local-dir ingestion staging/wiring. Nested `~/` fallback and redirect-map application were deferred because they need separate corpus or cross-tool contract work.

## Implementation Units

* Unit 1: add pure `derive_url_prefix(docfx_config)` and optional `prefixes` mapping to `derive_canonical_url`
* Unit 2: stage `docfx.json`, derive per-docset breadcrumb prefixes, and pass the prefix map through ingestion processing
* Preserve `url_path_prefix` precedence over breadcrumb-derived prefixes
* Add pure derivation tests and synthetic ingestion coverage

## Key Constraints

* Existing caller behavior is unchanged when `prefixes=None`
* `url_path_prefix` wins whenever present
* Core canonical URL derivation remains pure and I/O-free
* `docfx.json` staging is CLI local-dir specific; pre-staged or MCP callers without staged docfx gracefully emit `None`
* Multi-docfx resolution chooses the docset root, not arbitrary nested files

## Rejected Alternatives

* Continue relying on `url_path_prefix` alone — rejected because real corpora omit it
* Implement `~/` fallback in this shipment — deferred for the nosql family and corpus-specific mapping
* Implement redirect maps in this shipment — deferred because it crosses into graphtor contract concerns
* Read original repo files directly inside `derive_canonical_url` — rejected to keep derivation pure and testable
* Treat CLI-only staging as a parity regression — rejected because shared `execute_process` behavior remains graceful for unstaged callers

## Review Outcome

Plan review passed after resolving three P2 findings in-plan: keep `derive_canonical_url` backward-compatible with an optional prefix map, add the Constitution Check, and document docfx-root resolution plus CLI staging parity limits. Deferred Units 3 and 4 remained follow-ups.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-07-04-canonical-url-v2-breadcrumb-derivation-plan.md

