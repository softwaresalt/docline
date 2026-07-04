---
type: session-memory
date: 2026-07-04
agent: orchestrator (Stage + Ship + spike/plan-review inline)
shipment: 048-S
feature: 046-F
---

# Session memory — 048-S canonical_url v2

## Outcome

Routed the 045-F spike outcome through the full pipeline in one sequence —
learnings → plan → stage → adversarial plan-review → shipment → ship — and
shipped `canonical_url` v2 (breadcrumb-path prefix derivation). Batched all
artifacts into a single ship PR per operator direction (no intermediate PRs).

## Tasks completed

- `046.001-T` — `derive_url_prefix` + optional `prefixes` map (commit `3d11afe`-era).
- `046.002-T` — `_build_docfx_prefixes` + docfx staging (`f986133`); review fix
  `06e27d0` (path containment). Merge SHA `e0e1df5` (PR #127).

## Files modified

- `src/docline/process/canonical_url.py`, `src/docline/app.py`, `src/docline/cli.py`
- `tests/process/test_canonical_url.py`, `tests/process/test_canonical_url_ingestion.py`
- Docs: spike `docs/decisions/2026-07-04-canonical-url-coverage-spike.md`, learning
  `docs/compound/2026-07-04-ms-learn-canonical-url-from-breadcrumb.md`, plan
  `docs/plans/2026-07-04-canonical-url-v2-breadcrumb-derivation-plan.md`.

## Key facts / decisions

- **v1 was ~0% on real repos**; MS Learn URL prefix comes from docfx
  `breadcrumb_path`, not `url_path_prefix`. Redirect data at repo roots
  (`.openpublishing.redirection.json`), not the config field.
- Optional `prefixes` param keeps v1 callers/tests intact (backward-compatible).
- Contain the docfx path with `safe_workspace_path` — config-derived
  `build_source_folder` is untrusted.
- Adversarial plan-review (inline personas) caught: signature backward-compat,
  missing Constitution Check, docfx-staging parity — all resolved pre-stage.

## Environment facts (this session)

- **backlogit MCP down all session** ("Transport closed"); used the CLI
  (`C:\Tools\backlogit.exe`) for every backlog op — `spike` is not a registered
  type, so the spike was modeled as a feature labeled `spike` (045-F).
- Runner `uv run`; CI paused; `read_powershell` unavailable (redirect script
  output to files). Operator corpus at `C:\Source\Docs` (fabric/powerbi/query/
  bi-shared/nosql/azure).

## Open / next

- Deferred: nosql `~/`-breadcrumb fallback, redirect-map emission (graphtor
  contract), monikers.
- Stash `3CFD945D` (CI paths-ignore / PR-title guards) — pending.
- Parked `.gitignore`/`uv.lock` still uncommitted per operator.
- Non-Mistral remainder: `A3E6D72C`, `4CB606D5`, `3048007A`, `935F2694`,
  `7AA9FAA0`, `F8E142A1`. Mistral blocked on Foundry.
