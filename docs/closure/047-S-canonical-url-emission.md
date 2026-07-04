---
shipment: 047-S
title: "Closure record — canonical_url emission for local-dir ingestion (044-F)"
status: verified
merge_sha: 7a3009c
merged_pr: 125
---

## Scope delivered

Feature `044-F` emits a per-document `canonical_url` (Microsoft Learn URL path)
during local-dir ingestion so graphtor-docs can key its planned cross-source
cross-product link resolution (Option B) on a globally-unique identifier. This is
the docline half of the cross-repo work scoped in
`docs/decisions/2026-07-03-graphtor-cross-repo-link-resolution-spike.md`.

| Task | Delivered |
|---|---|
| `044.001-T` | `src/docline/process/canonical_url.py` — pure `derive_canonical_url(publish_config, source_rel_path)`. Selects the docset with the longest matching `build_source_folder`, joins its `url_path_prefix` with the path under that folder, drops `.md`, collapses `index.md`, lowercases. Returns `None` when unmatched or when the winning docset has no `url_path_prefix`. |
| `044.002-T` | `src/docline/app.py` — `execute_process` loads a staged `.openpublishing.publish.config.json` and stamps `docline:canonical_url` per doc (first part). `src/docline/cli.py` — `ingest local-dir` now stages the publish config; like `TOC.yml` it is filtered out of the process pass by `_SUPPORTED_EXTENSIONS`. Graceful no-op when no config is present. |

## Design notes

- **v1 scope**: base path + `url_path_prefix` + file→URL normalization. Monikers,
  redirect maps, documentId path-depot mappings, and `docfx.json` `base_path`
  fallback are explicitly deferred.
- **Longest-match-before-prefix (review fix)**: the initial implementation
  skipped prefix-less docsets before the longest-match, which could let a
  shorter, less-specific docset win and emit a wrong prefix. Fixed to select the
  longest folder match first, then return `None` when that winner lacks a prefix
  — a wrong prefix is worse than omission for a cross-source key. Commit
  `31dfea7`; regression test added.

## Verification

- `ruff check .` — clean
- `pyright src/` — 0 errors
- `pytest` — full suite green (1414 passed, 6 skipped; 13 new tests)
- `ruff format --check .` — clean
- Copilot review on PR #125 — 1 thread (the longest-match bug), fixed + resolved.

CI remains paused in `.github/workflows/ci.yml` (tags / releases / manual
dispatch only); gates were run locally under `uv run`.

## Follow-ups

- The graphtor-docs **Option B** feature (cross-source resolution keyed on
  `canonical_url`) is the paired half — spec captured in the spike artifact, to
  be handed to the graphtor agent.
- The deferred derivation complexity (monikers / redirects / documentId
  path-depot mappings) is a candidate for a future spike + task if real corpora
  need it.
