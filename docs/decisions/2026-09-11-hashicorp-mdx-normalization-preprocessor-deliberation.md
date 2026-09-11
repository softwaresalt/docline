# Deliberation: Temporary HashiCorp unified-docs MDX→MD normalization preprocessor

- **Date:** 2026-09-11
- **Stage session:** stage-hashicorp-mdx-normalizer-2026-09-11
- **Shape:** feature-shaped (operator-delivered, not a stash entry)
- **Kind:** feature (temporary tooling that produces requirements evidence for a future
  first-class docline MDX capability)
- **Branch context:** `feat/github-markdown-extension` (clean, tracks origin)
- **Escalation route (resolved fresh this session):** claude-opus-4.8 / anthropic / high

## Problem frame

The operator wants a **temporary, standalone preprocessing script** that:

1. Reads the external read-only corpus
   `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`.
2. Selectively copies **only the latest-version** directory of each versioned HashiCorp
   product **plus all unversioned products**.
3. **Normalizes `.mdx` → standard `.md` during the copy** (normalize-on-copy, streaming;
   NOT materialize-then-normalize).
4. Is tested.
5. Ultimately preprocesses content into
   `C:\Source\Docs\tf-unified-dev-docs-normalized`.
6. Becomes **requirements evidence** for a future first-class docline MDX feature.

### Hard containment constraint (session policy)

All agents in this CLI session **MUST NOT create, modify, or delete outside**
`C:\Source\GitHub\docline`. The external corpus may be **read** (operator-authorized),
but `C:\Source\Docs\tf-unified-dev-docs-normalized` **MUST NOT be written by this
session**. Therefore:

- Stage produces only planning/backlog artifacts inside docline (this file, the plan, the
  review record, backlog items).
- Ship builds the script + tests **inside docline**, runs a **read-only, zero-external-write
  dry run** against the real corpus, and **leaves the exact operator command** that
  produces the external output. The **operator** (not a session agent) runs `--execute`.

## Investigation findings (grounding evidence)

### Docline current state

- `src/docline/app.py` `_SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".html", ".htm", ".md",
  ".markdown", ".txt"}` — **`.mdx` is not supported**. `DEFAULT_LOCAL_INCLUDE_PATTERNS`
  globs `**/*.md` and `**/*.markdown` only.
- **Prior art already in-repo** for construct normalization: `src/docline/process/
  docfx_normalize.py`, `docfx_tabs.py`, `docfx_includes.py`, plus `ast_lint.py`,
  `toc_parser.py`, `canonical_url.py` (strips `.md`/`.markdown` suffixes).
- **Script convention exists**: one-shot analysis scripts live in `scripts/`
  (e.g. `scripts/spike_h1_corpus_analysis.py` — structured JSON to stdout, table to
  stderr) and are tested under `tests/scripts/` (e.g. `test_load_test.py`). The temporary
  preprocessor fits this convention exactly.
- Python 3.12 (cpython-312 bytecode present); pytest test runner.

### External corpus layout facts

- 24 top-level dirs. Versioned products carry `vX.Y.x` dirs; **non-version** sibling dirs
  exist and must be excluded: top-level `global/partials`, per-product `templates`
  (terraform) and `global` (vault).
- **Latest-selection is NOT a naive sort.** `scripts/prebuild/gather-version-metadata.mjs`
  computes `isLatest` per product using `semver.coerce` + a `.x` normalization, a
  release-stage-in-parentheses rule (`x.y.z (beta)`), and a non-semver alphabetical
  fallback. Confirmed edge cases:
  - `vault`: dirs include both `v1.21.x` **and** `v2.x` → latest is **v2.x** (numeric,
    not lexical).
  - `terraform`: latest **v1.16.x** (with a non-version `templates` sibling to skip).
  - `terraform-enterprise`: date-based `202507-1` (non-semver fallback path).
  - `terraform-policy`: `v0.2.x (beta)` → beta release-stage handling.
- Unversioned products (`versionedDocs: false` in `productConfig.mjs`, placeholder
  `v0.0.x`): `hcp-docs`, `terraform-docs-common`, `validated-designs`,
  `well-architected-framework`.
- `productConfig.mjs` is the **version source of truth** (`versionedDocs` flag +
  `semverCoerce`); `gather-version-metadata.mjs` is the selection algorithm.
- Content files are `.mdx` (386 under `terraform/v1.16.x`) plus assets (`.png/.jpg/.json`).
  Frontmatter is YAML with an auto-generated metadata block that must be preserved.

### MDX constructs in scope

`Tabs`/`Tab`, `Note`, `Warning`, `Tip`, `Highlight`, `CodeBlockConfig`, `CodeTabs` (with a
JS-like `tabs` array), `EnterpriseAlert`, `HCPCallout`, `VideoEmbed`. **Invariants:**
literal placeholders `<TYPE>`, `<PATH>`, `<VALUE>` must remain **unchanged**; fenced code
must **never** be parsed as MDX; YAML frontmatter preserved verbatim.

### Relevant compound learning

`docs/compound/2026-09-09-third-party-api-shape-requires-live-verification.md` — external
data shape must be verified against the live source, not assumed. Reinforces the mandatory
**full-corpus read-only dry-run validation** task and cross-checking latest-selection
against the real corpus.

## Options considered

### Latest-version selection strategy

- **Option A — Shell out to node** to run the external repo's own
  `gather-version-metadata.mjs` and consume its JSON.
  - Pro: authoritative, zero drift. Con: adds a node/bun runtime dependency to a Python
    tool; the `.mjs` exports a function (no CLI), needs a wrapper; brittle across
    environments; harder to unit test deterministically.
- **Option B — Python port of the gather rules** (`semver.coerce` equivalent + `.x`
  normalize + beta-parentheses + non-semver date fallback), validated against a
  checked-in expected-latest fixture table derived from the corpus + `productConfig`.
  - Pro: self-contained in docline, deterministic, unit-testable, no external runtime.
    Con: must mirror the external algorithm faithfully (mitigated by the fixture table
    + full-corpus cross-check).
- **Option C — Static embedded latest-version manifest** (hardcode the known-latest dirs).
  - Pro: trivial. Con: silently wrong when the corpus updates; poor requirements evidence.

**Chosen: Option B**, with a full-corpus dry-run cross-check (Option A kept as an optional
validation oracle, not a runtime dependency). Rationale: containment-friendly (all Python,
all in-repo), deterministic and testable, and the produced selection logic is itself the
requirements evidence for how a first-class feature should pick versions.

### Normalization approach

- **Option A — Reuse `process/docfx_*` modules directly.** Con: those target DocFX, not
  HashiCorp MDX; coupling a throwaway script to production internals risks scope creep and
  a P-010/YAGNI violation. Kept as **reference prior art only**.
- **Option B — Standalone normalization engine in the script** with a construct-by-construct
  transform table, protecting fenced code + placeholders + frontmatter.
  - **Chosen.** Surgical, isolated, disposable; its transform table + unhandled-construct
    inventory is the concrete requirements evidence.

### Placement

- **Chosen:** `scripts/` (one-shot convention) + `tests/scripts/`. Not `src/docline/`
  (would imply production integration, which is explicitly out of scope).

## Scope decisions

- **In scope:** standalone temporary preprocessing script + tests; latest-only + unversioned
  selection; streaming MDX→MD normalization; dry-run(default)/execute modes with a
  containment guard; full-corpus read-only dry-run validation; a requirements-evidence
  writeup.
- **Out of scope (explicit):** any production docline MDX integration (no change to
  `_SUPPORTED_EXTENSIONS`, readers, or the ELT pipeline); no writing to the external
  normalized destination by any session agent; no node/bun runtime dependency.

## What "done" looks like

A reviewed plan and a queued backlogit shipment that lets Ship: build the script + tests
inside docline, run a full-corpus read-only dry run proving zero external writes, emit a
coverage + unhandled-construct report, author the requirements-evidence doc, and document
the exact operator `--execute` command — without ever writing outside the repo.

## Open questions (non-blocking; resolved by the dry-run evidence)

1. Exact target markdown rendering for each construct (blockquote vs. admonition syntax) —
   decided per-construct in B-group tasks; the dry-run inventory validates coverage.
2. Whether any latest dir is empty/`pages`-style legacy layout (noted in `productConfig`
   TODOs) — surfaced by the dry-run report, not a planning blocker.

## Operator confirmation

Operator delivered this as a bounded temporary tooling chore/feature with explicit scope
guardrails; deliberation confirms the feature framing and the surgical decomposition below.
