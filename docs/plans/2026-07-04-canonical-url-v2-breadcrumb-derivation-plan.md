---
title: "canonical_url v2 — breadcrumb-path prefix derivation"
type: implementation-plan
date: 2026-07-04
source: docs/decisions/2026-07-04-canonical-url-coverage-spike.md
slug: canonical-url-v2-breadcrumb-derivation
---

## Problem Frame

`canonical_url` v1 (feature 044-F, `src/docline/process/canonical_url.py`) derives
the Learn URL prefix from `.openpublishing.publish.config.json`
`docsets_to_publish[].url_path_prefix`. The 045-F spike measured that field to be
absent in every real MS Learn repo (`docfx.json` `base_path` too) → **~0% coverage
on real corpora**. The real prefix lives in `docfx.json`
`build.globalMetadata.breadcrumb_path` (the path before the `breadcrumb`/`bread`
segment), which yields **83% doc coverage** and is exact (0 wrong URLs for
existing files). This plan makes v1 actually work by deriving the prefix from
`breadcrumb_path`.

## Requirements Trace

| Spike recommendation | Implementation |
|---|---|
| ADOPT breadcrumb-path prefix derivation (item 1) | Unit 1 (pure derivation) + Unit 2 (wiring) — **this shipment** |
| PROTOTYPE `~/`/nested-prefix fallback for nosql (item 3) | Unit 3 — **deferred follow-up** (documented) |
| PROTOTYPE redirect-map application (item 2) | Unit 4 — **deferred follow-up** (cross-tool contract with graphtor) |
| DEFER monikers (item 4) | Not planned |
| Corpus completeness (item 5) | Operator ingestion scope, not docline |

## Implementation Units

### Unit 1 — Pure breadcrumb prefix derivation (test-first)

- **Change**: In `canonical_url.py`, add `derive_url_prefix(docfx_config: Mapping) -> str | None`
  that reads `build.globalMetadata.breadcrumb_path` and returns the prefix (segments
  before `breadcrumb`/`bread`; `None` for `~/`-relative or empty). Extend
  `derive_canonical_url` with an **optional** keyword `prefixes: Mapping[str, str] | None = None`
  (keyed by `build_source_folder`); precedence per docset is `url_path_prefix` (from the
  docset) → `prefixes[build_source_folder]` → skip. **Default `None` preserves exact v1
  behavior**, so the existing 044.002-T caller and current tests are unaffected.
- **Files**: `src/docline/process/canonical_url.py` (+ `tests/process/test_canonical_url.py`).
- **Tests**: `derive_url_prefix` — absolute (`/dax/breadcrumb/...`→`/dax`, `/azure/bread/...`→`/azure`), `~/`-relative→None, missing→None; `derive_canonical_url` with an explicit prefix map (longest-match + prefix precedence preserved).
- **Posture**: test-first.

### Unit 2 — Wire docfx breadcrumb into ingestion (test-first)

- **Change**: In `app.py`, replace `_load_publish_config` with a loader that, per
  docset, reads the staged `docfx.json` at `files_dir/<build_source_folder>/docfx.json`,
  derives the prefix via `derive_url_prefix` (url_path_prefix takes precedence), and
  builds the `{build_source_folder: prefix}` map passed to `derive_canonical_url`.
  In `cli.py` `_run_ingest_local_dir`, add `**/docfx.json` to the staged include set
  (filtered from the process pass by `_SUPPORTED_EXTENSIONS`, like the config).
- **Files**: `src/docline/app.py`, `src/docline/cli.py` (+ end-to-end test in `tests/process/test_canonical_url_ingestion.py`).
- **Tests**: synthetic repo with `.openpublishing.publish.config.json` (no `url_path_prefix`) + `docs/docfx.json` (breadcrumb `/fabric/breadcrumb/toc.json`) → doc gets `docline:canonical_url == /fabric/...`; no docfx/no breadcrumb → graceful `None`; `url_path_prefix` still wins when present.
- **Posture**: test-first.

## Dependency Graph

Unit 2 depends on Unit 1 (`derive_url_prefix` + prefix-map signature). No cycles.
Deferred Units 3, 4 are independent follow-ups.

## Decisions and Rationale

- **Prefix precedence `url_path_prefix` > breadcrumb**: preserves correctness if a
  repo ever sets `url_path_prefix`, while covering the real (breadcrumb-only) case.
- **Prefix map passed in, not read inside `derive_canonical_url`**: keeps the core
  derivation pure/unit-testable; I/O (reading docfx.json) stays in the app layer,
  matching the v1 factoring.
- **Stage `docfx.json` (not parse original repo)**: consistent with how v1 stages the
  publish config; `.json` is already excluded from the process pass.
- **Shipment scope = Units 1+2 only**: they are docline-self-contained and deliver
  the 0→83% win. Units 3 (nosql `~/` fallback) and 4 (redirect emission, which has a
  graphtor cross-tool contract) are deferred to keep the shipment focused and low-risk.

## Risks and Caveats

- **Coverage gap remains for `~/`-breadcrumb docsets** (nosql family, ~17%): v2 emits
  `None` for them (graceful, same as today). Mitigation: Unit 3 follow-up (per-docset
  override or depot mapping).
- **Redirect links stay unresolved** (in-corpus renamed slugs): out of this shipment;
  Unit 4 follow-up, and partly graphtor's concern.
- **Emitted-frontmatter behavior change**: v2 emits `canonical_url` for many docs that
  previously had none. This is additive (never overwrites other fields) and matches the
  graphtor consumption contract; low risk. Verified by the runtime check below.
- **`bread` vs `breadcrumb` second-segment variance**: handled by matching both tokens.
- **docfx.json location / multi-docfx (P2/P3 review follow-up)**: `**/docfx.json`
  staging may capture several files; the loader resolves the docset's docfx at the
  `build_source_folder` root (nearest to `bsf`), not an arbitrary nested one. Absent
  docfx → `None` (graceful).
- **Dual-interface parity (P2 review follow-up)**: the derivation lives in the shared
  `execute_process`, so CLI and MCP process paths behave identically. However, the
  docfx.json *staging* is wired only in the CLI `ingest local-dir` path (as the publish
  config already is in 044-F); MCP/pre-staged callers that do not stage docfx.json get
  `None` (unchanged, graceful). Not a regression; documented limitation. A shared
  staging contract is a future item.

## Constitution Check

| Principle | Assessment |
|---|---|
| I. Safety-First Python | Typed signatures (`derive_url_prefix`, optional `prefixes`); tolerant docfx parsing; no bare except. ✓ |
| II. Test-First (NON-NEGOTIABLE) | Both units are test-first; pure derivation + end-to-end ingestion tests. ✓ |
| III/IV. Workspace isolation / CLI containment | Reads only staged files under the workspace; no writes outside output/staging. ✓ |
| VI. Single responsibility | No new dependencies; reuses `posixify_path` and the existing staging path. ✓ |
| Task granularity (NON-NEGOTIABLE) | Unit 1 = 1 src file; Unit 2 = 2 src files; each width-isolated to process code with its own tests. ✓ |
| X. Context efficiency | Pure derivation isolated from I/O; caller passes parsed configs. ✓ |
No violations. No justified deviations required.

## Plan Hardening Signals

- public API/schema/contract change: **present (minor)** — internal
  `derive_canonical_url` signature changes; emitted frontmatter gains `canonical_url`
  coverage (additive; existing graphtor contract). No external public API break.
- security/auth/compliance: **absent**.
- migration/backfill/destructive/irreversible: **absent**.
- external integration/operator checkpoint/external dependency: **absent for this
  shipment** (graphtor already consumes `canonical_url`; the new redirect cross-tool
  contract is deferred to Unit 4).
- high runtime/rollout/rollback risk: **absent** — additive, fully unit + end-to-end
  tested; trivially reversible (revert derivation source).

**Requires plan hardening: no.**

## Runtime Verification and Closure

- **Runtime surface changed**: `docline ingest local-dir` / `docline process` emitted
  frontmatter.
- **Verification**: after build, run `docline ingest local-dir C:\Source\Docs\fabric-docs\... --output <tmp>` (or a synthetic docfx-bearing repo) and confirm emitted docs carry `docline:canonical_url` at `/fabric/...` — i.e. coverage jumps from ~0% (v1) to ~100% for that docset, matching the spike's breadcrumb derivation. Confirm the four quality gates pass.
- **Closure artifact**: post-merge closure record noting the coverage improvement and the deferred Units 3/4; update the 045-F spike's promoted_to; compound learning already captured.

## Plan Review

**Reviewers (inline, multi-persona — no subagent tool available):** Constitution,
Python, Scope Boundary, Learnings Researcher, Architecture Strategist, Dual-Interface
Parity.

**Gate: PASS** (initial ADVISORY with 3×P2 / 2×P3; all resolved in-plan below; 0 P0/P1).
Plan hardening was required: **no** (justified — additive, no destructive/migration/
security/external-contract change in shipment scope). Requirement satisfied.

Findings and resolution:

- **P2 (Python/contract) — resolved**: `derive_canonical_url` must not break the
  existing 044.002-T caller/tests. Revised Unit 1 to add an **optional** `prefixes`
  keyword (default `None` = exact v1 behavior).
- **P2 (Constitution) — resolved**: added the required **Constitution Check** section
  (no violations).
- **P2 (Architecture/Parity) — resolved**: documented docfx-root resolution + the
  CLI-only staging / shared-`execute_process` parity note under Risks.
- **P3 — resolved**: multi-docfx edge noted; compound learning cited (below).
- Learnings Researcher: plan **aligns with** and does not contradict
  `docs/compound/2026-07-04-ms-learn-canonical-url-from-breadcrumb.md`.

Runtime verification + closure: present and specific (real-corpus coverage check). No
gaps.

**References**: `docs/decisions/2026-07-04-canonical-url-coverage-spike.md`,
`docs/compound/2026-07-04-ms-learn-canonical-url-from-breadcrumb.md`.
