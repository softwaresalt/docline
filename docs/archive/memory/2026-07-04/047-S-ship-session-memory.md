---
type: session-memory
date: 2026-07-04
agent: orchestrator (Ship inline)
shipment: 047-S
feature: 044-F
---

# Session memory — 047-S canonical_url emission

## Outcome

Staged and shipped feature `044-F` (shipment `047-S`): per-document
`canonical_url` emission for local-dir ingestion — the docline half of the
graphtor cross-repo link-resolution work.

## Tasks completed

- `044.001-T` — pure `derive_canonical_url` in `src/docline/process/canonical_url.py`;
  commits `3bd5738` (impl) + `31dfea7` (review fix: longest-match before prefix check).
- `044.002-T` — stamp `docline:canonical_url` in `execute_process`; stage the
  publish config in `ingest local-dir`; commit `73c93a6`.
- Merge SHA `7a3009c` (PR #125).

## Files modified

- `src/docline/process/canonical_url.py` (new)
- `src/docline/app.py` (config load + stamp)
- `src/docline/cli.py` (stage publish config)
- `tests/process/test_canonical_url.py`, `tests/process/test_canonical_url_ingestion.py` (new)

## Decisions / rationale

- Injected `canonical_url` via the existing `docline_namespace` merge in
  `_build_markdown_with_frontmatter` — no frontmatter schema change needed.
- Staged the publish config (`.json`) so `_load_publish_config` can read it;
  `_SUPPORTED_EXTENSIONS` naturally excludes it from the process pass.
- Longest-match-before-prefix fix: a wrong cross-source URL prefix is worse than
  omission, so return `None` when the most-specific docset has no prefix.

## Environment facts (this session)

- **backlogit MCP dropped mid-session** ("Transport closed"); fell back to the
  `backlogit` CLI at `C:\Tools\backlogit.exe` for all backlog ops (claim, move,
  get, shipment ship) — worked cleanly. Compound learning already exists for this.
- Runner is `uv run`; CI paused (tags/releases/manual). `read_powershell` tool
  unavailable — relied on completion notifications for long `pyright`/`pytest`.
- No real `.openpublishing.publish.config.json` sample in the workspaces; built
  and tested `derive_canonical_url` against synthetic configs.

## Open / next

- **graphtor Option B** feature spec (in the spike artifact) to hand to the
  graphtor agent — the paired half for end-to-end cross-repo graphs.
- Deferred canonical-URL derivation complexity (monikers/redirects/documentId
  path-depot mappings) — future spike if needed.
- Parked `.gitignore` / `uv.lock` stray changes still uncommitted per operator.
- Non-Mistral stash remainder: `A3E6D72C` (scanned-corpus OCR calibration,
  operator-supervised), `4CB606D5`, `3048007A`, `935F2694`, `7AA9FAA0`,
  `F8E142A1`. Mistral work blocked on Foundry.
