# Implementation Plan: Temporary HashiCorp unified-docs MDX→MD normalization preprocessor

- **Date:** 2026-09-11
- **Source deliberation:** `docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`
- **Kind:** feature (temporary tooling → requirements evidence)
- **Owner of execution:** Ship (Stage does NOT implement)
- **Requires plan hardening:** yes
- **Plan-review-attempt:** see trailing HTML comment
<!-- plan-review-attempt: 1 -->

## Primary objective

Deliver a standalone, disposable Python preprocessing script (+ tests) inside docline that
selectively copies only the latest-version directory of each versioned HashiCorp product
plus all unversioned products from the external read-only corpus, normalizing `.mdx` → `.md`
**in-flight during the copy**, and captures the resulting coverage + unhandled-construct
inventory as requirements evidence for a future first-class docline MDX feature.

## Containment contract (NON-NEGOTIABLE — applies to Ship execution)

- Read-only access to `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content` is permitted.
- **No session agent may write, modify, or delete outside `C:\Source\GitHub\docline`.**
- `C:\Source\Docs\tf-unified-dev-docs-normalized` MUST NOT be written this session.
- The script defaults to **dry-run** (zero writes anywhere). `--execute` is required to
  write, and Ship MUST NOT run `--execute` against the external destination. Ship documents
  the exact operator command; the operator runs it.
- Tests MUST write only within the repo tree. Configure pytest `--basetemp` to a repo-local,
  git-ignored scratch dir (e.g. `build/.pytest-tmp/`) rather than the OS temp dir, so the
  test run itself does not create files outside the repo.
- A runtime **containment guard** in the script refuses any write whose resolved absolute
  path is outside the operator-provided `--dest` root, and dry-run performs zero filesystem
  writes.

## Planned files (all inside docline)

| Path | Kind | Purpose |
|---|---|---|
| `scripts/hashicorp_mdx_normalize.py` | code | Standalone CLI: selection + normalize-on-copy orchestrator + dry-run/execute + containment guard |
| `scripts/_hashicorp_mdx/__init__.py` | code | Package marker for the helper module (keeps the script testable/importable) |
| `scripts/_hashicorp_mdx/selection.py` | code | Product classification (versioned/unversioned) + latest-version selection (semver port) |
| `scripts/_hashicorp_mdx/normalize.py` | code | MDX→MD normalization engine (frontmatter/fence/placeholder protection + construct transforms) |
| `tests/scripts/test_hashicorp_selection.py` | tests | Unit tests for selection layer |
| `tests/scripts/test_hashicorp_normalize.py` | tests | Unit tests + golden files for normalization engine |
| `tests/scripts/test_hashicorp_dryrun_corpus.py` | tests | Full-corpus read-only dry-run integration test (skipped if corpus absent) |
| `tests/scripts/fixtures/hashicorp/**` | tests | Synthetic corpus + construct fixtures + expected-latest table |
| `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md` | docs | Requirements-evidence writeup (findings, gaps, productionization requirements) |

> Note: `scripts/_hashicorp_mdx/` is a helper package so logic is unit-testable without a
> node/bun runtime; the entry point stays `scripts/hashicorp_mdx_normalize.py` per the
> one-shot convention. No changes to `src/docline/` (production integration is out of scope).

## Decomposition (feature → tasks; groups A–E)

Backlogit hierarchy here is feature → task (tasks nest directly under the covering feature,
matching existing repo features such as 070-F). Logical groups A–E are carried as labels.

### Group A — Selection layer (code)

- **A.T1 — Product classifier (versioned vs unversioned + exclusions).**
  Files: `scripts/_hashicorp_mdx/selection.py`. Classify the 24 top-level dirs into 20
  versioned products + 4 unversioned (`hcp-docs`, `terraform-docs-common`,
  `validated-designs`, `well-architected-framework`); exclude top-level `global/partials`
  and per-product non-version dirs (`terraform/templates`, `vault/global`) and any
  non-product dir. Source of the versioned/unversioned split is an explicit product map
  mirroring `productConfig.mjs` `versionedDocs`.
  **AC:** given the corpus root, returns exactly the 20 versioned + 4 unversioned products;
  `global`, `partials`, per-product `templates`/`global` are excluded; unit-tested against a
  synthetic fixture tree. Size S / Complexity low.

- **A.T2 — Latest-version selector (semver port of gather-version-metadata rules).**
  Files: `scripts/_hashicorp_mdx/selection.py`. Port the `isLatest` algorithm: coerce
  `vX.Y.x` via a `.x`-aware normalization, sort by semver descending, handle
  release-stage-in-parentheses (`x.y.z (beta)`) so a beta is not chosen as latest when a
  stable exists, and fall back to alphabetical for all-non-semver products
  (terraform-enterprise `202507-1`). Validated against a checked-in expected-latest table.
  **AC:** `vault → v2.x` (not v1.21.x), `terraform → v1.16.x`, `terraform-enterprise →
  202507-1`, `terraform-policy` beta handled, unversioned → placeholder; table-driven unit
  tests pass. Size M / Complexity medium.

### Group B — Normalization engine (code)

- **B.T1 — Parser scaffold: frontmatter + fenced-code + placeholder protection.**
  Files: `scripts/_hashicorp_mdx/normalize.py`. Split and preserve YAML frontmatter
  verbatim (incl. the auto-generated metadata block); mask fenced code blocks and literal
  placeholders `<TYPE>`/`<PATH>`/`<VALUE>` so they are never treated as MDX; provide a
  transform pipeline seam the B.T2/B.T3 transforms plug into.
  **AC:** fenced code and `<TYPE>`/`<PATH>`/`<VALUE>` round-trip unchanged; frontmatter
  preserved byte-for-byte; unit tests cover a doc with all three protections. Size S /
  Complexity medium.

- **B.T2 — Callout/admonition transforms.**
  Files: `scripts/_hashicorp_mdx/normalize.py`. Deterministically transform `Note`,
  `Warning`, `Tip`, `Highlight`, `EnterpriseAlert`, `HCPCallout` into standard markdown
  (blockquote-based admonitions). Depends on B.T1.
  **AC:** each of the 6 constructs maps to a documented deterministic markdown form;
  per-construct unit tests with golden output; nested/inline content preserved. Size S /
  Complexity low.

- **B.T3 — Tabs / CodeTabs / CodeBlockConfig / VideoEmbed transforms.**
  Files: `scripts/_hashicorp_mdx/normalize.py`. Transform `Tabs`/`Tab` → headed sections;
  `CodeTabs` (JS-like `tabs` array) → sequential labeled code blocks; unwrap
  `CodeBlockConfig`; `VideoEmbed` → markdown link. Depends on B.T1.
  **AC:** nested tabs flatten deterministically; the JS `tabs` array is parsed into labeled
  fenced blocks; `CodeBlockConfig` wrapper removed while inner code preserved; `VideoEmbed`
  becomes a link; per-construct golden unit tests. Size M / Complexity medium.

### Group C — Orchestration + containment (code)

- **C.T1 — Normalize-on-copy orchestrator.**
  Files: `scripts/hashicorp_mdx_normalize.py`. For each selected product/latest-version,
  walk content, and for each `.mdx`: read → normalize (Group B) → write `.md` at the
  mirrored dest path (streaming; NOT materialize-then-normalize). Skip fragment sources
  (`global/partials`, per-product partials). Decide asset handling (copy `.png/.jpg/.json`
  as-is or skip per a documented rule). Depends on A.T1, A.T2, B.T1–B.T3.
  **AC:** `.mdx` inputs produce `.md` outputs with the same relative path minus extension;
  normalization occurs in-flight (no intermediate `.mdx` materialized at dest); partials are
  not emitted as standalone docs; asset rule documented and applied. Size M / Complexity
  medium.

- **C.T2 — CLI surface + dry-run/execute + containment guard + JSON plan report.**
  Files: `scripts/hashicorp_mdx_normalize.py`. Args: `--source`, `--dest`, `--execute`
  (default dry-run), `--report`. Dry-run performs zero writes and emits a JSON plan
  (per-product selected version, file counts, planned dest paths, unhandled-construct tally)
  to stdout. Containment guard rejects any resolved write path outside `--dest`. Depends on
  C.T1.
  **AC:** default invocation writes nothing anywhere and prints the JSON plan; `--execute`
  is required to write; a write targeting outside `--dest` is refused with a non-zero exit;
  help documents the exact operator command. Size M / Complexity medium.

### Group D — Tests (tests)

- **D.T1 — Selection unit tests.** Files: `tests/scripts/test_hashicorp_selection.py`,
  fixtures. Cover versioned/unversioned split, vault dual-version, TFE date fallback, beta.
  Depends on A.T1, A.T2. **AC:** table-driven; all edge cases asserted; repo-local tmp only.
  Size S / Complexity low.

- **D.T2 — Normalization unit + golden tests.** Files:
  `tests/scripts/test_hashicorp_normalize.py`, `tests/scripts/fixtures/hashicorp/**`. Golden
  assertions for every construct + fence/placeholder/frontmatter preservation. Depends on
  B.T1–B.T3. **AC:** one golden case per construct; preservation invariants asserted;
  repo-local tmp only. Size M / Complexity low.

- **D.T3 — Full-corpus read-only dry-run integration test + coverage report.**
  Files: `tests/scripts/test_hashicorp_dryrun_corpus.py`. Run the script in dry-run against
  the real external corpus (skip cleanly if corpus path absent), assert exit 0, assert
  **zero writes outside the repo**, and emit the coverage + unhandled-construct report into a
  repo-local path. Depends on C.T1, C.T2. **AC:** dry-run over the real corpus exits 0;
  test asserts no filesystem path outside the repo was written; report enumerates
  per-product selected version + file counts + unhandled constructs; uses repo-local
  basetemp. Size M / Complexity medium.

### Group E — Requirements evidence (docs)

- **E.T1 — Requirements-evidence writeup.** Files:
  `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md`.
  Summarize selection rules, the construct transform table, the unhandled-construct
  inventory from D.T3, containment learnings, and concrete requirements for a first-class
  docline MDX capability (e.g., `.mdx` in `_SUPPORTED_EXTENSIONS`, reader/normalizer seam).
  Depends on D.T3. **AC:** doc references the script + the dry-run report and lists concrete,
  numbered productionization requirements. Size S / Complexity low.

## Dependency graph / execution order

```
A.T1 ─┐
A.T2 ─┼─► C.T1 ─► C.T2 ─► D.T3 ─► E.T1
B.T1 ─┤            
 ├─► B.T2 ─┘
 └─► B.T3 ─┘
A.T1,A.T2 ─► D.T1
B.T1..B.T3 ─► D.T2
```

Suggested order: A.T1, A.T2, B.T1, B.T2, B.T3, D.T1, D.T2, C.T1, C.T2, D.T3, E.T1.

## Plan Hardening (P-006)

**Hardening signals:** interacts with an external filesystem corpus; correctness of
latest-selection has real consequences (vault v2.x vs v1.21.x); MDX parsing has adversarial
edge cases (fenced code, placeholders); a hard containment policy governs writes.

**Risk register + mitigations:**

1. **Containment breach (writing outside the repo).** *Mitigation:* dry-run default (zero
   writes), runtime containment guard bounded to `--dest`, pytest repo-local `--basetemp`,
   and an explicit D.T3 assertion of zero out-of-repo writes. Ship never runs `--execute`
   against the external dest.
2. **Wrong "latest" selected.** *Mitigation:* Python port faithfully mirrors
   `gather-version-metadata.mjs`; checked-in expected-latest table (A.T2/D.T1); full-corpus
   cross-check (D.T3). Compound learning "third-party shape requires live verification"
   applied.
3. **MDX corruption of fenced code / placeholders / frontmatter.** *Mitigation:* B.T1
   protection scaffold with dedicated preservation tests before any construct transform.
4. **Scope creep into production docline.** *Mitigation:* placement in `scripts/`, no edits
   to `src/docline/`, explicit out-of-scope list; `process/docfx_*` used as reference only.
5. **Materialize-then-normalize regression.** *Mitigation:* C.T1 AC requires in-flight
   normalization; no intermediate `.mdx` at dest.
6. **Test run creating OS-temp files (soft containment concern).** *Mitigation:* repo-local
   basetemp requirement in the containment contract and every test AC.

## Verification criteria (feature-level)

- All unit + golden tests pass; full-corpus dry-run exits 0 with zero out-of-repo writes.
- Coverage report enumerates all 24 products, the selected latest version each, and any
  unhandled MDX constructs.
- Requirements-evidence doc committed with concrete productionization requirements.
- The exact operator `--execute` command is documented; no session agent executed it.

## Out of scope

Production docline MDX integration; changes to `_SUPPORTED_EXTENSIONS`/readers/ELT; any
write to the external normalized destination by a session agent; node/bun runtime dependency.
