---
type: decided-plan
source_plan: 2026-06-02-docline-graphtor-alignment-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped alignment work made docline's emitted markdown conform to the graphtor-docs ingestion contract across frontmatter, path normalization, heading validity, reader fidelity, fetch semantics, staging metadata, optional chunk anchors, and cross-tool contract documentation. The plan intentionally treated the eleven gap-analysis findings as one cohesive release unit because schema, hashing, paths, chunking, and reader output interact at the downstream chunk-store boundary.

The final architecture kept core derivation pure and testable, made risky crawl and reader behaviors opt-in or fail-loud with escape hatches, and required runtime verification across CLI and MCP surfaces before closure.

## Implementation Units

* F1: shared frontmatter schema additions, `docline:` namespace, `content_sha256`, schema export, and schema drift regression
* F2: POSIX `source_path` normalization helper routed through all emissions
* F3: heading hierarchy validator with `HeadingHierarchyError` and `--allow-heading-disorder` parity escape hatch
* F4: DOCX style, list, and table fidelity with characterization snapshots
* F5: PDF layout-aware heuristic extraction plus opt-in `docling` path
* F6: HTML figure preservation, URL canonicalization, sitemap discovery, dedup, robots, and containment handling
* F7: staging metadata propagation and optional chunk anchors
* F8: graphtor-docs ingestion contract documentation and fixture-based integration test

## Key Constraints

* Preserve backward compatibility for existing frontmatter fixtures while declaring `schema_version: "1.0"` for the new contract shape
* Keep sitemap discovery default-off and bounded by robots and allowlists
* Keep `docling` opt-in; default PDF behavior remains deterministic
* Validate CLI and MCP parity for every new flag or option
* Keep JSON Schema export explicit, not a hidden build side effect
* Protect against reader regressions through characterization snapshots

## Rejected Alternatives

* Split `content_sha256` away from frontmatter schema — rejected because the hash is a frontmatter field with no standalone consumer
* Make sitemap discovery default-on — rejected because it silently widens crawl scope
* Make real graphtor-docs binary mandatory in CI — rejected as flaky and toolchain-coupled; fixture simulator became default
* Hide path normalization inside the canonical URL logic — rejected because every `source_path` emission needs a consistent POSIX contract
* Defer all PDF layout integration — rejected because the flag surface was needed to avoid reopening reader seams later

## Review Outcome

Plan review was advisory with no P0/P1 blockers. Three P2 items were carried into harvest: harden DOCX XML parsing against XXE, enforce SSRF guards for sitemap fetching, and normalize JSON Schema comparisons to avoid pydantic-version drift.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-02-docline-graphtor-alignment-plan.md

