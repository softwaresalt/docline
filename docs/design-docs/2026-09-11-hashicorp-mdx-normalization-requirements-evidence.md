# HashiCorp Unified-Docs MDX -> MD Normalization: Requirements Evidence

* **Date**: 2026-09-11
* **Shipment**: 062-S
* **Feature**: 071-F
* **Status**: Requirements evidence for a future first-class docline MDX ingestion capability
* **Script**: `scripts/hashicorp_mdx_normalize.py` (+ `scripts/_hashicorp_mdx/{selection,normalize}.py`)
* **Tests**: `tests/scripts/test_hashicorp_{selection,normalize,dryrun_corpus}.py`
* **Dry-run report**: repo-local, git-ignored, produced by
  `tests/scripts/test_hashicorp_dryrun_corpus.py::test_real_corpus_dry_run_zero_writes_and_coverage_report`
  at `build/hashicorp-dryrun-evidence/real-corpus-dry-run-report.json`

## 1. Purpose and scope boundary

This document captures requirements evidence gathered by building and running a
**temporary, disposable** preprocessor against the real, read-only HashiCorp
unified-docs corpus at `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`. The
script selectively copies only the latest-version directory of every versioned
product (plus all unversioned products), converting `.mdx` to standard `.md`
in-flight, so an operator can produce a normalized corpus snapshot at
`C:\Source\Docs\tf-unified-dev-docs-normalized` for downstream evaluation.

**This tool is not, and will never become, a permanent part of docline.**
`.mdx` is not in docline's `_SUPPORTED_EXTENSIONS`
(`src/docline/app.py`), and this script is intentionally kept outside the
`src/docline` package tree, unregistered as a console entry point, with no
dependency on docline's ingestion pipeline. Its only purpose is to produce the
concrete, live-verified findings below so that a future first-class docline MDX
ingestion feature can be scoped and designed from evidence rather than
assumption.

## 2. Containment contract (honored throughout)

* Every file read for this work was read-only against the operator-provided
  external corpus; nothing outside `C:\Source\GitHub\docline` was ever
  created, modified, or deleted.
* The script defaults to dry-run (zero writes) and requires an explicit
  `--execute` flag to write anything, always guarded to resolve strictly
  inside `--dest` (`guard_write_path` / `ContainmentViolation` in
  `scripts/hashicorp_mdx_normalize.py`).
* The external destination, `C:\Source\Docs\tf-unified-dev-docs-normalized`,
  was **never written** by this agent. Every dry-run and test invocation in
  this shipment used a `--dest` path under a repo-local pytest `tmp_path`
  (itself rooted under a repo-local `--basetemp`, e.g. `build/.pytest-tmp`),
  or, for the real-corpus dry-run, a `tmp_path`-derived directory that was
  asserted to never be created at all (see §5).
* The exact operator command to perform the real external run is documented
  in the script's own `--help` epilog and reproduced in §7 below. It was
  never executed during this work.

## 3. Selection algorithm -- ported and live-verified

`scripts/_hashicorp_mdx/selection.py` is a faithful Python port of the
external unified-docs repo's `scripts/prebuild/gather-version-metadata.mjs`
(traced directly from that file plus its test suite and
`scripts/utils/version-regex.mjs`), covering:

1. **Product classification** (`PRODUCT_VERSIONED_MAP`): an explicit,
   individually-verified map of every top-level product directory to
   `versioned: bool`.
2. **Version-directory validity**: any directory name that coerces to a
   version (after stripping a `(alpha|beta|rc)` release-stage suffix and
   normalizing a trailing `.x` to `.0`) is a candidate; this is a **generic**
   coercibility test, not a per-product hardcoded exclusion list, and it
   naturally excludes non-version directories (`templates`, `global`,
   `releases`, `scripts`, `partials`, ...) for every product without any
   product-specific code.
3. **Latest-version selection**: candidates are split into a semver-sortable
   group (descending numeric sort) and a Terraform-Enterprise-date-pattern
   group (`vYYYYMM-N`, descending alphabetical sort), concatenated
   semver-first, then walked with a release-stage-aware cursor: a
   non-stable (`alpha`/`beta`/`rc`) entry is skipped for "latest" unless
   **every** candidate is non-stable, in which case the highest-sorted entry
   wins regardless of stage.

### 3.1 Live-verified corrections vs. the original plan/deliberation

The plan
(`docs/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan.md`) and
deliberation
(`docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`)
were written from an initial investigation of the corpus. Running the
faithfully-ported algorithm against the full real corpus surfaced two
corrections, consistent with the compound learning that **third-party shape
requires live verification** rather than trusting a planning-time estimate:

1. **Product count**: the plan's task acceptance criteria stated "20
   versioned + 4 unversioned" products. The real corpus has **19 versioned +
   4 unversioned = 23 products** (`global` is a 24th top-level directory that
   is not a product at all -- it is the shared partials container and is
   always excluded). `PRODUCT_VERSIONED_MAP` in `selection.py` is the
   authoritative, individually-verified map; this document records the
   correction rather than silently overriding the task's stated number.
2. **`terraform-enterprise`'s true "latest"**: the plan assumed
   `v202507-1` (the newest of ~50 legacy date-based `vYYYYMM-N`
   directories) was latest. The real corpus *also* contains newer semver-style
   directories -- `1.0.x`, `1.1.x`, `1.2.x`, `2.0.x` -- whose auto-generated
   `created_at` frontmatter metadata postdates every date-based directory
   (`v202507-1` carries `created_at: 2025-07-03`; `2.0.x` carries
   `created_at: 2026-02-02`). Faithfully porting the upstream algorithm (which
   treats semver-coercible directories as more recent than the legacy
   date-based scheme when both are present) selects **`2.0.x`** as latest.
   The full-corpus dry-run confirms this: `products["terraform-enterprise"]
   ["selected_version"] == "2.0.x"`. This is consistent with the product
   having migrated its versioning scheme; the deliberation's investigation did
   not surface the newer semver directories.

Both corrections are exercised as first-class, intentional test cases:
`tests/scripts/test_hashicorp_selection.py` still asserts the plan's
*simpler*, synthetic date-only scenario (`v202507-1` wins when no semver-style
directories are present) as a literal unit-level regression, while
`tests/scripts/test_hashicorp_dryrun_corpus.py`'s real-corpus integration test
asserts the corrected, live-verified `2.0.x` answer against the actual corpus.
Neither the plan's AC nor the real finding was silently discarded.

### 3.2 Other selection findings (all match the plan's assumptions)

| Product | Real corpus directories (abridged) | Selected latest | Matches plan? |
|---|---|---|---|
| `vault` | `v1.4.x`..`v1.21.x`, `v2.x`, `global` (excluded) | `v2.x` | Yes |
| `terraform` | `v1.1.x`..`v1.16.x`, `templates` (excluded) | `v1.16.x` | Yes |
| `terraform-policy` | `v0.1.x (beta)`, `v0.2.x (beta)` (both non-stable) | `v0.2.x (beta)` | Yes -- all-non-stable fallback picks highest-sorted |
| `vagrant` | Exact patch versions `v2.2.9`..`v2.4.9` (no `.x`) | `v2.4.9` | Yes -- true numeric semver compare confirmed (`v2.2.10` sorts after `v2.2.9`, not before it lexically) |
| `consul` / `nomad` | `...`, `v2.0.x`, `global` (excluded) | `v2.0.x` | Yes |

Full per-product selection results from the real-corpus dry-run (23
products, 19 versioned + 4 unversioned):

```text
boundary                    -> v1.0.x
consul                      -> v2.0.x
hcp-docs                    -> (unversioned -- whole tree copied)
nomad                       -> v2.0.x
packer                      -> v1.16.x
sentinel                    -> v0.40.x
terraform                   -> v1.16.x
terraform-cdk               -> v0.21.x
terraform-docs-agents       -> v1.31.x
terraform-docs-common       -> (unversioned -- whole tree copied)
terraform-enterprise        -> 2.0.x            (live-verified correction; see 3.1)
terraform-mcp-server        -> v1.0.x
terraform-migrate           -> v2.0.x
terraform-plugin-framework  -> v1.18.x
terraform-plugin-log        -> v0.10.x
terraform-plugin-mux        -> v0.22.x
terraform-plugin-sdk        -> v2.39.x
terraform-plugin-testing    -> v1.15.x
terraform-policy            -> v0.2.x (beta)
vagrant                     -> v2.4.9
validated-designs           -> (unversioned -- whole tree copied)
vault                       -> v2.x
well-architected-framework  -> (unversioned -- whole tree copied)
```

Corpus-wide file totals from the same dry-run: **5,566 `.mdx` files
normalized**, **59 ordinary `.md` files copied as-is**, **2,139 image/binary
assets copied as-is**, **1,259 files skipped as partials/fragments**, **164
files skipped as neither Markdown nor an allow-listed asset type** (e.g.
`.json` nav-data files).

## 4. Construct transform table (B.T2 / B.T3)

| MDX construct | Real shape observed | Rendering |
|---|---|---|
| `Note` / `Warning` / `Tip` / `Highlight` | Block form, `<Tag title="...">body</Tag>` | Blockquote admonition: `> **{title or tag name}**` + quoted body |
| `EnterpriseAlert` | Mostly self-closing inline (`<EnterpriseAlert inline="true" />`), occasionally block form with a body (found in `partials/alerts/*.mdx` fragment files) | Self-closing -> inline `**(Enterprise-only)**` marker; block form -> blockquote titled "Enterprise Only" |
| `HCPCallout` | Always self-closing, `<HCPCallout product="X" />`, no body | Blockquote: `This content applies to HCP` `` `X` `` |
| `Tabs` / `Tab` | `<Tabs><Tab heading="X" group="Y">...</Tab></Tabs>` | Flattened to a fixed-level `#### {heading}` per tab, in document order; nested `Tabs` flatten identically (documented simplification -- no nesting-aware heading-level inference) |
| `CodeTabs` | Wraps sibling `CodeBlockConfig` children, **not** a JS-array literal as the plan assumed (live-verification correction) | Unwrapped; optional bold caption for its `heading` attribute |
| `CodeBlockConfig` | Wraps a single fenced code block; attrs include `filename`, `heading`, `hideClipboard`, `highlight`, `lineNumbers` | Unwrapped; optional bold caption (`heading` preferred, else `filename`); inner fence preserved exactly |
| `VideoEmbed` | Always self-closing, `<VideoEmbed url="X"/>` | `[Video](url)` |

### 4.1 Preservation invariants (B.T1)

* **Frontmatter** is captured and reattached byte-for-byte
  (`split_frontmatter`), never touched by any transform.
* **Fenced code blocks** are masked to opaque tokens before any transform
  runs and restored verbatim at the very end (`protect_fenced_code` /
  `restore_fenced_code`).
* **Literal placeholders** (`<TYPE>`, `<PATH>`, `<VALUE>`, `<NAMESPACE>`,
  and hyphenated conventions like `<YOUR-ORG>`) are masked/restored
  separately (`protect_placeholders` / `restore_placeholders`). These can
  never collide with a real construct tag name because every known
  construct tag is CamelCase (mixed case) while the placeholder pattern
  requires every character after the first to be uppercase, a digit, an
  underscore, or a hyphen.

## 5. Live-verification bugs found and fixed via the real-corpus dry-run

Two genuine correctness bugs were found and fixed only because this shipment
insisted on running the full real-corpus dry-run rather than stopping at
synthetic unit tests:

1. **Fence indentation-blindness.** The initial fenced-code masking regex
   required the closing fence marker to start at column zero. The real
   corpus routinely nests fenced code blocks under numbered-list
   continuations (e.g. `  ```shell-session` / `  ``` `, indented by the list
   item's continuation width -- see
   `vault/v2.x/content/docs/auth/jwt/oidc-providers/adfs.mdx`). An
   indentation-blind matcher failed to close the fence at its true boundary,
   letting placeholder-bearing code content leak past masking. Fixed by
   capturing the opening fence's leading indentation and requiring the same
   indentation before the closing fence
   (`^(?P<indent>[ \t]*)(?P<fence>...)`... `(?P=indent)(?P=fence)`). Covered
   by `test_protect_and_restore_indented_fenced_code_round_trips_exactly`.
2. **Unbounded unhandled-construct scan.** The unknown-construct tally regex
   allowed its "attributes" span to cross newlines in search of the next
   `>` character, so an unrelated shell heredoc marker (`<<EOF`) on one line
   could spuriously "close" against an unrelated `>` many lines later (e.g. a
   blockquote marker), mis-tallying names like `EOF`/`YOUR`/`GITHUB` as
   fabricated unhandled constructs. This is a reporting-precision issue only
   (the scan never mutates content), fixed by bounding the scan to a single
   line. Covered by
   `test_scan_unhandled_constructs_does_not_span_lines_to_a_distant_unrelated_bracket`.

Both fixes are documented in the corresponding module docstrings/comments in
`scripts/_hashicorp_mdx/normalize.py`, not just here.

## 6. Unhandled-construct inventory (from the real-corpus dry-run, D.T3)

The full-corpus dry-run produced **89 distinct unhandled tag names, 472 total
occurrences** across the entire selected corpus (report generated by
`tests/scripts/test_hashicorp_dryrun_corpus.py::test_real_corpus_dry_run_zero_writes_and_coverage_report`,
persisted at the repo-local, git-ignored
`build/hashicorp-dryrun-evidence/real-corpus-dry-run-report.json`). The most
frequent entries:

```text
ImageConfig: 72        Placement: 53          BadgesHeader: 42
TFE: 39                 YOUR: 26                PluginBadge: 24
Provider: 16            GITHUB: 12               SOURCE: 11
UNIQUE: 11              BITBUCKET: 8             Info: 8
ACLLink: 6              Expression: 6            GITLAB: 6
ORG: 6                  PLUGIN: 6                Optional: 5
```

**Important caveat**: this scan is a heuristic, regex-based approximation
(`scan_unhandled_constructs` in `scripts/_hashicorp_mdx/normalize.py`), not an
AST/tokenizer-based parse. It correctly surfaces genuine unhandled JSX
components this disposable tool does not render (`ImageConfig`, `Placement`,
`BadgesHeader`, `TFE`, `PluginBadge`, `Provider`, `ACLLink`, `Expression`,
`Info`, and dozens more single/double-digit-occurrence
tags) -- these are genuine gaps for a production implementation. It also
still contains a residual mix of placeholder-like false positives (e.g.
`YOUR`, `GITHUB`, `SOURCE`, `ORG`, `PLUGIN`) from bracket conventions this
tool's regex-based placeholder protection does not fully cover (e.g.
placeholders containing a literal space, like `<YOUR DB USERNAME>`). This
caveat is itself a concrete requirement for a production implementation (see
Requirement 6 below): a real MDX/AST-based parser eliminates this entire
class of tag-vs-placeholder ambiguity structurally, rather than needing
heuristic masking passes.

## 7. Exact operator command for the real external run (never executed by an agent)

```powershell
python scripts/hashicorp_mdx_normalize.py `
    --source "C:\Source\Docs\hashicorp-tf-unified-dev-docs\content" `
    --dest "C:\Source\Docs\tf-unified-dev-docs-normalized" `
    --execute `
    --report "C:\Source\Docs\tf-unified-dev-docs-normalized\_normalize-report.json"
```

Omit `--execute` (and point `--report` anywhere convenient, or omit it to see
the plan on stdout only) to preview the identical plan with zero writes --
this is the default mode and is safe to run repeatedly. This exact command is
also reproduced in the script's own `--help` epilog.

## 8. Numbered requirements for a first-class docline MDX ingestion capability

These are concrete, evidence-grounded requirements for a future, permanent
docline feature, derived directly from building and running this disposable
tool against the real corpus:

1. **Use a real MDX/JSX parser, not regex heuristics.** This disposable
   tool's regex-based tag matching, fence masking, and placeholder masking
   are adequate for a one-time requirements-evidence pass but produce known
   false positives/negatives (§5, §6). A production feature must parse MDX
   into an AST (e.g. via a proper MDX/remark-compatible parser) so
   construct boundaries, nesting, and code-fence contents are unambiguous by
   construction.
2. **Support a pluggable, per-construct renderer registry**, not a fixed
   pipeline of module-level functions. The real corpus already has at least
   96 distinct unhandled component names (§6); a permanent feature will
   need to grow this set over time without editing a monolithic transform
   module.
3. **Preserve frontmatter, fenced code, and placeholder-like tokens as a
   first-class parser concern**, not a pre/post masking pass. An AST-based
   approach can protect these natively (e.g. treating fenced code as an
   opaque leaf node) rather than relying on regex masking that is
   vulnerable to indentation and line-span edge cases (§5).
4. **Model "latest version" selection as a versioned-corpus abstraction**,
   generalizing `selection.py`'s algorithm (semver-aware sort, `.x`
   normalization, release-stage-aware fallback, and a non-semver
   date-pattern sort for legacy schemes) so it can apply to other
   versioned external doc corpora beyond HashiCorp's, not just this one.
5. **Treat "latest" as a live, re-verifiable computation, not a cached
   constant.** The `terraform-enterprise` finding (§3.1) demonstrates that
   a versioned corpus's true "latest" directory can change in ways a
   point-in-time investigation misses (e.g. a versioning-scheme migration).
   A production feature should re-run selection against the live source on
   each ingestion, not hardcode a previously-observed answer.
6. **Expect ambiguity between placeholder tokens and JSX components in
   angle-bracket syntax**, and design the parser layer (item 1) to resolve
   it structurally: a real MDX parser distinguishes a JSX element from a
   bare text token like `<YOUR-ORG>` by grammar (JSX requires attributes/
   self-closing syntax or matching close tags in a specific grammar
   position), eliminating the entire class of heuristic tag-name
   false-positives observed in §6.
7. **Support nested `Tabs` with real heading-level inference**, not the
   fixed-H4 flattening this disposable tool uses (§4), if a production
   feature needs faithful heading hierarchy in the destination Markdown.
8. **Persist a machine-readable coverage/telemetry artifact per ingestion
   run** (this disposable tool's JSON report -- per-product selected
   version, file counts, unhandled-construct tally, warnings -- is a
   reasonable starting shape; see `scripts/hashicorp_mdx_normalize.py`'s
   `ReportBuilder`), so ingestion drift and unhandled-construct growth are
   observable over time rather than discovered ad hoc.
9. **Apply the containment discipline demonstrated here as a standing
   pattern** for any future external-corpus ingestion tool: dry-run
   default, explicit `--execute` opt-in, a runtime write-path guard bounded
   to the destination root, and repo-local test temp directories -- not
   just for this disposable tool, but as a docline-wide convention for
   tools that touch external, potentially-read-only filesystem locations.

## 9. Traceability

* Script: `scripts/hashicorp_mdx_normalize.py`,
  `scripts/_hashicorp_mdx/selection.py`, `scripts/_hashicorp_mdx/normalize.py`
* Tests: `tests/scripts/test_hashicorp_selection.py` (25 cases),
  `tests/scripts/test_hashicorp_normalize.py` (25 cases),
  `tests/scripts/test_hashicorp_dryrun_corpus.py` (8 cases, including the
  real-corpus dry-run integration test)
* Dry-run report (repo-local, git-ignored):
  `build/hashicorp-dryrun-evidence/real-corpus-dry-run-report.json`
* Plan: `docs/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan.md`
* Deliberation: `docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`
* Shipment: `062-S`; Feature: `071-F`; Tasks: `071.001-T`..`071.011-T`
