---
title: "Adversarial review — 053-F external/split-file $ref resolution"
type: review
date: 2026-07-06
feature: 053-F
status: reviewed
reviewers:
  - security
  - correctness
  - python
  - constitution
  - architecture
  - maintainability
  - scope-boundary
---

Adversarial multi-persona review of 053-F before the PR. The feature adds
external/split-file ``$ref`` resolution so operation docs cross-link to the
schema docs sibling spec files produce. This is the security-boundary feature —
the Security persona led.

## Findings

| # | Severity | Persona | Finding | Resolution |
|---|---|---|---|---|
| 1 | P3 | Correctness | `CorpusRefLinker.__init__` calls `referring_path.relative_to(corpus_root)`, which raises `ValueError` if the spec file is not under the corpus root. | **Accepted** — an internal invariant: the process pass always stages files under `files_dir`, and passing a non-containing `corpus_root` to `read_openapi_spec` is caller misuse. Documented. |
| 2 | P3 | Maintainability | `slug`'s empty-input default moved from `"operation"` (old reader) to `"item"` (shared loader). | **Accepted** — inconsequential: operation ids are derived from method+path (never empty) and schema names are non-empty, so the default is unreachable in practice. |

## Security persona (primary — no actionable findings)

- **Containment**: `resolve_contained_ref_file` normalizes via `resolve(strict=False)`
  (which also follows symlinks) then asserts `is_relative_to(corpus_root)`. Escapes
  (direct `../../..`, absolute, symlink-out) all land outside root and raise
  `PathContainmentError`. Tested: same-dir ✓, in-root `../common` ✓, escape ✗,
  absolute ✗.
- **URL-deny (SSRF)**: any scheme `://` (and `file://`) is refused with
  `OpenApiRefError` *before* any filesystem access; protocol-relative `//host` is
  caught as absolute. No URL is ever fetched. Tested.
- **No dangling / no over-reach**: the linker only *reads* target spec files to
  confirm the referenced schema exists; it never writes, never executes, and
  resolves at most one hop per ref (no cross-file recursion → inherently
  cycle-free; mutual A↔B refs terminate, tested).
- The fabric corpus has **0 URL refs and 0 absolute refs** (measured), so the
  gates are defense-in-depth here; they protect arbitrary corpora.

## Other personas (no actionable findings)

- **Correctness**: cross-file links resolve to real docs (verified on fabric —
  sampled link target exists on disk); the 78% operation coverage is correct
  (the unlinked 22% are legitimately schema-less DELETE/no-content operations);
  the corpus-relative `cross_link_path` makes the harvester record correct edge
  targets; single-file behavior is byte-identical (no corpus → local-only links).
- **Python/Constitution**: type hints throughout; no new dependency; Google
  docstrings; TDD red→green per task; typed errors (`OpenApiRefError`,
  `PathContainmentError`).
- **Architecture**: the renderer's link decision was generalized from a per-name
  `schema_href` to a `$ref`→href `RefLink`, with backward-compatible defaults;
  the `slug` helper was moved to `loader.py` to break a reader↔resolve cycle.
- **Scope**: changes limited to the OpenAPI subpackage + the app.py `files_dir`
  wiring + tests.

## Verification

- 15 resolve/linker tests (containment, URL-deny, escape, missing-target,
  examples-skip, mutual-cycle); reader + process cross-file tests.
- Runtime: re-ingested `fabric-rest-api-specs` → operation cross-linking
  **0% → 78%** (515/661 operations; **0 → 671** operation→schema edges), plus
  cross-file schema→schema edges. All sampled links resolve on disk (no
  dangling). No path escaped the corpus root; no URL fetched.
- Gates: ruff clean, pyright (venv) 0 errors, pytest 1538+ passed / 6 skipped,
  format clean.

## strict-safety action record

- **ProposedAction**: resolve external file `$ref` targets during ingestion.
  **ActionRisk**: high (filesystem read of config-derived relative paths).
  **Mitigation/rollback**: read-only, path-contained (`is_relative_to`),
  URL-denied; disabled entirely when `corpus_root` is not supplied.
  **ActionResult**: applied; verified on the fabric corpus with no escape.

## Runtime verification recommendation

Mode: **manual** — exercised end-to-end on the real fabric corpus with link
targets confirmed on disk. No API/browser surface.
