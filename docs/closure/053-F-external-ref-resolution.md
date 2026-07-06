---
title: "Closure — 053-F external/split-file OpenAPI $ref resolution"
status: verified
feature: 053-F
merged_pr: 142
merge_sha: e6ee9cb
date: 2026-07-06
---

Resolved external / split-file OpenAPI `$ref` values so operation docs cross-link
to the schema docs sibling spec files produce — the security-boundary feature
that completes the fabric REST corpus for graphtor.

## Delivered

- `readers/openapi/resolve.py` — `resolve_contained_ref_file` (path-contained
  external resolution; URL-deny SSRF; absolute-deny; escape-reject via
  `resolve()` + `is_relative_to`) and `CorpusRefLinker` (maps a `$ref` to the
  sibling file's schema doc, verifying the target schema exists → no dangling;
  one-hop → inherently cycle-free).
- `render.py` — generalized the link decision from a per-name `schema_href` to a
  `$ref`→href `RefLink` (backward-compatible defaults).
- `reader.py` — optional `corpus_root` enables cross-file linking; corpus-relative
  `cross_link_path` so the harvester records correct edge targets. `slug` moved to
  `loader.py` (breaks a reader↔resolve import cycle).
- `app.py` — threads the staged `files_dir` (corpus root) through `execute_process`.

## Verification

- 15 resolve/linker tests (containment, URL-deny, escape, missing-target,
  examples-skip, mutual-cycle) + reader/process cross-file tests.
- Runtime: re-ingested `fabric-rest-api-specs` → operation cross-linking
  **0% → 78%** (515/661 operations; **0 → 671** operation→schema edges), plus
  cross-file schema→schema edges. Every sampled link resolves on disk (no
  dangling). The unlinked 22% are legitimately schema-less (DELETE/no-content
  operations). No path escaped the corpus root; no URL was fetched.
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1540 passed / 6 skipped,
  format clean.
- Adversarial + Copilot review: `053-F-external-ref-resolution-review.md`.
  Copilot raised 2 findings on PR #142 — a botched test edit (restored the lost
  unknown-root rejection test) and a `RefLink` alias duplication (imported from
  render). Both resolved; re-review clean.

## Security note

This was the elevated-risk boundary item. File refs resolve only within the
corpus root (`../common/…` allowed; `../../..`/absolute/symlink escapes →
`PathContainmentError`); URL refs are refused before any filesystem access,
never fetched. The fabric corpus has 0 URL and 0 absolute refs (measured); the
gates protect arbitrary corpora.

## Carried forward

Residual OpenAPI follow-ups remain in stash `D9AC2CD6` (API versioning/monikers,
pagination/LRO, security-scheme deep render, corpus-wide sweep) plus a P3
(path-level body/formData param distribution in the Swagger converter). Deeply
nested (non-top-level) schema refs inside operation request/response bodies are
summarized as `object` rather than linked — a possible future enhancement.
