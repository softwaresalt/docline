---
shipment: 048-S
title: "Closure record — canonical_url v2 (breadcrumb-path prefix derivation, 046-F)"
status: verified
merge_sha: e0e1df5
merged_pr: 127
---

## Scope delivered

Feature `046-F` fixes `canonical_url` derivation to work on real MS Learn corpora.
The 045-F spike measured v1 (044-F) at **~0% coverage** on real repos (none set
`url_path_prefix`); the prefix actually lives in `docfx.json`
`globalMetadata.breadcrumb_path`. v2 derives from it → **83% doc coverage**, exact.

| Task | Delivered |
|---|---|
| `046.001-T` | `src/docline/process/canonical_url.py` — `derive_url_prefix(docfx)` (breadcrumb parse: segments before `breadcrumb`/`bread`; `None` for `~/`-relative) and an optional `prefixes` map on `derive_canonical_url` (default `None` = exact v1; `url_path_prefix` still wins). |
| `046.002-T` | `src/docline/app.py` — `_build_docfx_prefixes` builds a per-docset prefix map from staged `docfx.json` (path contained via `safe_workspace_path`), passed to `derive_canonical_url`. `src/docline/cli.py` — `ingest local-dir` stages `**/docfx.json` (filtered from the process pass). |

## Process artifacts (batched into the single ship PR)

- Spike: `docs/decisions/2026-07-04-canonical-url-coverage-spike.md`
- Learning: `docs/compound/2026-07-04-ms-learn-canonical-url-from-breadcrumb.md`
- Plan (adversarial plan-review, gate PASS): `docs/plans/2026-07-04-canonical-url-v2-breadcrumb-derivation-plan.md`

Per operator direction, no intermediate PRs were created before the ship phase.

## Verification

- `ruff check .` / `pyright src/` / `pytest` (1419 passed, 6 skipped; +5 new) / `ruff format --check .` — all green.
- **Real-corpus runtime check**: `fabric-docs` → `/fabric` prefix; real docs map to
  `/fabric/admin/...` (0% → 100% for that docset).
- Copilot review: 1 thread — a workspace-isolation bug (`build_source_folder` `..`
  traversal in `_build_docfx_prefixes`) — fixed with `safe_workspace_path` +
  `PathContainmentError` guard + regression test (`06e27d0`), replied + resolved.

CI remains paused (tags/releases/manual only); gates run locally under `uv run`.

## Deferred follow-ups (documented, out of this shipment)

- **nosql `~/`-breadcrumb + nested-prefix fallback** (~17% of docs; cosmos-db →
  `/azure/cosmos-db`) — per-docset override or depot mapping.
- **Redirect-map emission** (`.openpublishing.redirection.json`; powerbi 1,563 /
  bi-shared 996 entries) — recovers in-corpus renamed-slug links; has a graphtor
  cross-tool contract.
- **Monikers** — deferred (not a meaningful failure class on the measured corpus).
- **graphtor Option B** (cross-source resolution keyed on `canonical_url`) — the
  paired half, already handed to the graphtor agent.
