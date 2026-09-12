# HashiCorp Unified-Docs MDX -> MD Normalization: Requirements Evidence

* **Date**: 2026-09-11 (review-fix cycle 1: see §9)
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
   group (`vYYYYMM-N`, descending **numeric** sort on the parsed
   `(YYYYMM, revision)` tuple -- see §9.3 for the review-fix cycle 1
   correction that replaced an earlier lexical-string sort), concatenated
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

**Review-fix cycle 1 note (§9.3)**: the calendar-version lexical-sort bug
fixed in that cycle (`v202507-9` sorting after `v202507-10`) touches only the
*within-date-family* ordering of the non-semver candidate group. It has no
bearing on the semver-vs-date-family *mixed-family* precedence rule described
above -- that rule is decided by which group (semver-sortable vs.
date-pattern) a candidate falls into, evaluated before either group's
internal sort ever runs. The real-corpus re-run performed for that cycle
reconfirms `products["terraform-enterprise"]["selected_version"] == "2.0.x"`
unchanged (§9.3), so this evidence-backed mixed-family rule is preserved,
not altered, by the fix.

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
generic (non-Markdown, non-allow-listed-image) files copied byte-for-byte**
(e.g. `.json` nav-data files, PDFs, videos -- see §9.6 for the review-fix
cycle 1 correction that changed this bucket from "skipped" to "copied").

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
  `restore_fenced_code`), using a Markdown-correct (CommonMark) closing-fence
  rule: same marker character, run length at least the opener's, valid
  indentation independent of the opener's -- see §9.4.
* **Literal placeholders** (`<TYPE>`, `<PATH>`, `<VALUE>`, `<NAMESPACE>`,
  and hyphenated conventions like `<YOUR-ORG>`) are masked/restored
  separately (`protect_placeholders` / `restore_placeholders`). These can
  never collide with a real construct tag name because every known
  construct tag is CamelCase (mixed case) while the placeholder pattern
  requires every character after the first to be uppercase, a digit, an
  underscore, or a hyphen. A bare ALL-CAPS single-word token is masked as a
  placeholder only when no matching closing tag exists later in the
  document -- see §9.5 for the one genuine paired-component exception this
  discovered (`<TIP>...</TIP>`).

## 5. Live-verification bugs found and fixed via the real-corpus dry-run

Three genuine correctness bugs were found and fixed only because this
shipment (and its review-fix cycle) insisted on running the full
real-corpus dry-run rather than stopping at synthetic unit tests:

1. **Fence indentation-blindness (original fix, later superseded by §9.4).**
   The initial fenced-code masking regex required the closing fence marker
   to start at column zero. The real corpus routinely nests fenced code
   blocks under numbered-list continuations (e.g. `  ```shell-session` /
   `  ``` `, indented by the list item's continuation width -- see
   `vault/v2.x/content/docs/auth/jwt/oidc-providers/adfs.mdx`). An
   indentation-blind matcher failed to close the fence at its true boundary,
   letting placeholder-bearing code content leak past masking. The original
   fix required the closing fence to repeat the *exact same* leading
   indentation and run length as the opener
   (`^(?P<indent>[ \t]*)(?P<fence>...)`... `(?P=indent)(?P=fence)`).
   **Review-fix cycle 1 (finding 4, §9.4) found this was still not
   Markdown-correct**: CommonMark allows a closing fence to use *any*
   indentation (up to 3 spaces) and a run *at least as long as* the
   opener's, independent of each other. The fence-protection logic was
   rewritten as a line-scanning matcher (`_FENCE_OPEN_RE` /
   `_FENCE_CLOSE_RE` in `scripts/_hashicorp_mdx/normalize.py`) that
   correctly implements this rule; see §9.4 for the details and new
   regression coverage.
2. **Unbounded unhandled-construct scan.** The unknown-construct tally regex
   allowed its "attributes" span to cross newlines in search of the next
   `>` character, so an unrelated shell heredoc marker (`<<EOF`) on one line
   could spuriously "close" against an unrelated `>` many lines later (e.g. a
   blockquote marker), mis-tallying names like `EOF`/`YOUR`/`GITHUB` as
   fabricated unhandled constructs. This is a reporting-precision issue only
   (the scan never mutates content), fixed by bounding the scan to a single
   line. Covered by
   `test_classify_remaining_constructs_does_not_span_lines_to_a_distant_unrelated_bracket`
   (renamed from `test_scan_unhandled_constructs_...` when the classification
   function was split into `ambiguous`/`unresolved` buckets -- see §9.5).
3. **All-caps paired component swallowed as a placeholder (found in
   review-fix cycle 1, finding 5; see §9.5).** `terraform/v1.16.x/docs/
   language/block/stack/tfcomponent/removed.mdx` authors a real paired
   callout as `<TIP>...</TIP>` (structurally identical to the normal
   mixed-case `Tip` callout, but spelled the way a bare placeholder like
   `<PATH>` is spelled). The placeholder mask ran before the fallback pass
   and matched the opening `<TIP>` (a bare ALL-CAPS token with no spaces),
   leaving the never-matched closing `</TIP>` orphaned as a spuriously
   "unresolved" construct. Fixed by teaching `protect_placeholders` to skip
   masking when a matching `</NAME>` exists later in the document -- a
   structural test (does a real close tag exist), not a name-based special
   case. Covered by
   `test_protect_placeholders_skips_masking_when_a_matching_close_tag_exists_later`
   and `test_normalize_mdx_to_md_all_caps_paired_callout_resolved_not_orphaned`.

## 6. Unhandled-construct inventory (from the real-corpus dry-run, D.T3)

**Superseded by review-fix cycle 1 (§9.5)**: the original single
`unhandled_constructs` scan-and-report bucket described in this section's
first revision was replaced with a three-way classification, and a generic
conservative fallback pass now actively *resolves* (rather than merely
reports) unknown MDX/JSX shapes. The final live-corpus numbers, produced by
the same integration test after all six review-fix cycle 1 findings were
applied, are:

```text
totals:               assets_copied=2139  generic_copied=164  md_copied=59
                       mdx_normalized=5566  skipped_partials=1259

fallback_constructs:   14 distinct tags,  152 total occurrences
                       (structurally unwrapped/annotated by
                       apply_fallback_pass -- see §9.5)

ambiguous_tokens:      75 distinct tags,  255 total occurrences
                       (grounded, documented prose/type-notation --
                       preserved verbatim, never blocks --execute)

unresolved_constructs: 0 distinct tags,   0 total occurrences
```

`unresolved_constructs` was **empty** on the selected live corpus as of
review-fix cycle 1 -- the acceptance bar set by finding 5 ("aim for zero
unresolved genuine MDX components... while preserving placeholder-like
tokens") was met without loosening the execute-mode fail-closed gate
(`EXIT_UNRESOLVED_MDX_CONSTRUCTS`, `--allow-unresolved-mdx`; see §9.5).

**Superseded by review-fix cycle 4 (§13.4, Copilot finding qAsc)**: this
zero baseline was only ever passing because `classify_remaining_constructs()`
carried an unsafe skip that hid genuine residue for any "known" tag name.
Removing that skip (cycle 4) made the classifier accurate and revealed 4
distinct real residues (`EnterpriseAlert: 12`, `Note: 1`, `VideoEmbed: 8`,
`Warning: 2` -- 23 total occurrences), none sharing qAsc's root cause. Fixing
these 4 gaps was deliberately deferred as out of scope for cycle 4 per
P-021 C1/C2 -- see stash entry **`7F80C39E`** for the full per-gap analysis,
and §13.4 for the re-verification narrative. **As of this writing, the real
operator `--execute` run against this corpus DOES need the
`--allow-unresolved-mdx` override flag** (§7's exact command must include
it, or the preflight aborts with `EXIT_UNRESOLVED_MDX_CONSTRUCTS`) until the
4 deferred gaps are resolved.

The top `fallback_constructs` entries (unknown MDX/JSX components the
generic pass structurally unwrapped or rendered as a readable annotation --
these remain genuine implementation gaps for a future first-class,
parser-based feature, see Requirement 2 below):

```text
Placement: 53          PluginBadge: 24        BadgesHeader: 21
ImageConfig: 36         Enterprise: 4           Info: 4
Accordion: 1            Button: 1               Checklist: 1
Important: 1            InteractiveLabCallout: 1
ProviderTable: 3        TabProvider: 1          TIP: 1
```

The `ambiguous_tokens` bucket (documented, non-blocking, never-a-real-
component prose/type-notation -- `_KNOWN_AMBIGUOUS_TAGS` in
`scripts/_hashicorp_mdx/normalize.py`) covers two grounded shapes:

1. Multi-word / spaced bracket placeholders (the original seed: `TFE`,
   `YOUR`, `GITHUB`, `SOURCE`, `ORG`, `PLUGIN`, `UNIQUE`, `BITBUCKET`,
   `GITLAB`, `Optional`, `Expression`, `Provider`, `ACLLink`; plus, from the
   review-fix cycle 1 full pass over the corpus: `ADFS`, `ATTR`, `Allowed`,
   `AuthMethod`, `CI`, `CONTEXT`, `DATA`, `DIRECTORY`, `DOCKER0`, `FALSE`,
   `FILTER`, `HCP`, `HOSTNAME`, `Hostname`, `IP`, `JWT`, `LOCAL`, `MODULE`,
   `Namespace`, `OUTPUT`, `PASSWORD`, `PATH`, `PLAN`, `PROJECT`, `PROVIDER`,
   `Path`, `REPO`, `RESOURCE`, `STATE`, `Subfolder`, `TIME`, `TRUE`, `URL`,
   `WORKSPACE`, `Your`).
2. Consul/Nomad API-reference backtick-wrapped generic-type notation, e.g.
   `` `(array<PolicyLink>)` `` (`ACLRolePolicyLink`,
   `ACLTemplatedPolicyVariables`, `Check`, `DiscoveryRoute`,
   `DiscoverySplit`, `ExtraVolume`, `IntentionPermission`, `Job`,
   `LinkedService`, `NamespaceRule`, `Node`, `NodeIdentity`, `PolicyLink`,
   `Port`, `RoleLink`, `ServiceCheck`, `ServiceIdentity`, `StatPrefix`,
   `Target`, `Toleration`, `TopologySpreadConstraint`, `VaultAccessor`,
   `VolumeItem`), plus generic prose/code type-parameter notation (`Object`,
   `String`, `Test`, `Type`, e.g. `Map<String, String>`).

Every one of the 75 `_KNOWN_AMBIGUOUS_TAGS` entries was individually grounded
against real corpus context during review-fix cycle 1 (never observed with a
self-closing `/>` or a matching close tag anywhere in the corpus) before
being added to the registry -- none is a guess.

**Important caveat (still applies)**: this classification is a heuristic,
regex-based approximation (`classify_remaining_constructs` in
`scripts/_hashicorp_mdx/normalize.py`), not an AST/tokenizer-based parse. A
production implementation should still use a real MDX/JSX parser (Requirement
1 below) so this entire class of tag-vs-placeholder ambiguity is resolved
structurally rather than via an enumerated registry that must be
individually grounded and maintained.

## 7. Exact operator command for the real external run (never executed by an agent)

**Updated in review-fix cycle 4 (§13.4, Copilot findings qAsc/htGvn/htGv9)**:
as documented in §6 above, the classifier-accuracy fix in this cycle
revealed that the selected live corpus currently has 4 distinct, deferred
(`7F80C39E`) unresolved-construct residues. Until those are resolved, the
real `--execute` run against this corpus **requires**
`--allow-unresolved-mdx`, or the preflight aborts with
`EXIT_UNRESOLVED_MDX_CONSTRUCTS` before any write begins:

```powershell
python scripts/hashicorp_mdx_normalize.py `
    --source "C:\Source\Docs\hashicorp-tf-unified-dev-docs\content" `
    --dest "C:\Source\Docs\tf-unified-dev-docs-normalized" `
    --execute `
    --allow-unresolved-mdx `
    --report "C:\Source\Docs\tf-unified-dev-docs-normalized\_normalize-report.json"
```

Omit `--allow-unresolved-mdx` once the 4 deferred residues (`7F80C39E`) are
resolved by a future cycle -- the flag is only required while they remain
outstanding, and the run's own reported `unresolved_constructs` bucket
remains the authoritative signal either way.

Omit `--execute` (and point `--report` anywhere convenient, or omit it to see
the plan on stdout only) to preview the identical plan with zero writes --
this is the default mode and is safe to run repeatedly, and never writes the
`--report` file even when `--report` is given (see §9.1 -- dry-run prints
the report to stdout and a stderr note instead). In `--execute` mode, a
complete read-only normalization preflight pass runs first: `--dest` may be
**absent or an existing, empty directory** (review-fix cycle 3 -- never a
pre-existing non-empty destination), and is claimed via an exclusive
sentinel file immediately before any write begins (`EXIT_DEST_ALREADY_EXISTS`
if the destination is already claimed by another, still-running invocation;
`EXIT_DEST_NOT_EMPTY` if it contains any other content; see §9.2/§11.3/§12.1);
`--report` must resolve strictly under `--dest` or the run fails closed
before `--dest` is even created (`EXIT_CONTAINMENT_VIOLATION`, see §11.2);
and any genuine unresolved MDX construct aborts the run before any write
begins unless `--allow-unresolved-mdx` is passed
(`EXIT_UNRESOLVED_MDX_CONSTRUCTS`, see §11.1). This exact command is also
reproduced in the script's own `--help` epilog.

## 8. Numbered requirements for a first-class docline MDX ingestion capability

These are concrete, evidence-grounded requirements for a future, permanent
docline feature, derived directly from building and running this disposable
tool against the real corpus:

1. **Use a real MDX/JSX parser, not regex heuristics.** This disposable
   tool's regex-based tag matching, fence masking, and placeholder masking
   are adequate for a one-time requirements-evidence pass but still rely on
   an individually-grounded, hand-maintained registry
   (`_KNOWN_AMBIGUOUS_TAGS`, §6) to keep prose/type-notation from being
   misreported as genuine unresolved components. A production feature must
   parse MDX into an AST (e.g. via a proper MDX/remark-compatible parser)
   so construct boundaries, nesting, and code-fence contents are
   unambiguous by construction, without needing a maintained allowlist.
2. **Support a pluggable, per-construct renderer registry**, not a fixed
   pipeline of module-level functions. The real corpus already has at least
   14 distinct genuinely-unhandled component names surfaced by the generic
   fallback pass (§6, `fallback_constructs`); a permanent feature will need
   to grow this set over time (adding first-class renderers for
   `Placement`, `ImageConfig`, `PluginBadge`, `BadgesHeader`, and similar)
   without editing a monolithic transform module.
3. **Preserve frontmatter, fenced code, and placeholder-like tokens as a
   first-class parser concern**, not a pre/post masking pass. An AST-based
   approach can protect these natively (e.g. treating fenced code as an
   opaque leaf node) rather than relying on regex masking that is
   vulnerable to indentation/run-length edge cases (§5.1) and to
   placeholder-vs-real-component ambiguity in bare ALL-CAPS tags (§5.3).
4. **Model "latest version" selection as a versioned-corpus abstraction**,
   generalizing `selection.py`'s algorithm (semver-aware sort, `.x`
   normalization, release-stage-aware fallback, and a **numeric** (not
   lexical -- §5's finding 3 correction) non-semver date-pattern sort for
   legacy schemes) so it can apply to other versioned external doc corpora
   beyond HashiCorp's, not just this one.
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
   position). This disposable tool approximates that grammar test
   structurally for the paired case (a matching close tag implies a real
   component, §5.3/§9.5) and via an enumerated registry for the
   spaced/multi-word and backtick-type-notation cases (§6) -- a production
   parser should eliminate the registry-maintenance burden entirely by
   resolving this from grammar, not enumeration.
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
   to the destination root, repo-local test temp directories, a
   fail-closed non-empty-destination check before any write (§9.2), and a
   report-file write path that is itself guarded to resolve under the
   destination root (§9.1) -- not just for this disposable tool, but as a
   docline-wide convention for tools that touch external, potentially
   read-only filesystem locations.
10. **Copy every non-normalized, non-excluded file byte-for-byte by
    default**, not just an allow-listed image subset (§9.6). A
    destination snapshot that silently drops PDFs, videos, or other
    repository data alongside the Markdown it was extracted from is an
    incomplete migration; a production feature should treat "copy
    everything not explicitly transformed or excluded" as the default,
    with exclusions (partials, build artifacts) opt-in and explicit.
11. **Preserve the source corpus's version-directory segment in the
    selected output tree** rather than flattening it away (§9.7). Keeping
    `{product}/{selected_version}/...` intact (instead of collapsing to
    `{product}/...`) preserves provenance back to which upstream version
    was normalized and avoids relative-path collisions if a future
    iteration ever needs to select more than one version per product. This
    also keeps the selected tree directly ingestible by
    `docline ingest local-dir` unchanged (§9.7) -- the version segment is
    just another path component under the default recursive
    `**/*.md` include glob.

## 9. Review-fix cycle 1 (PR #192) -- independent correctness review findings

An independent correctness review of PR #192 found six in-scope findings
against this disposable tool. All six were fixed test-first with surgical,
targeted changes; no scope expansion beyond the findings occurred. This
section is the traceable record of each finding, its fix, and its
regression coverage.

### 9.1 Finding 1 (P1) -- dry-run report writes; unguarded report path

**Problem**: `--report` unconditionally created parent directories and wrote
the report file even in dry-run mode (violating the zero-write dry-run
contract), and the report write path itself was never checked against
`--dest` containment in execute mode.

**Fix** (`scripts/hashicorp_mdx_normalize.py`):
* Dry-run now **never** writes the report file, regardless of whether
  `--report` was passed -- the JSON is always printed to stdout, and a
  stderr note is printed if `--report` was given (documenting that dry-run
  intentionally does not honor it for writing).
* In `--execute` mode, `--report`'s path is validated with the existing
  `guard_write_path(dest, args.report)` containment guard *before* any
  corpus processing begins -- an out-of-`--dest` report path fails closed
  with `EXIT_CONTAINMENT_VIOLATION` and zero corpus writes.

**Tests**: `test_dry_run_emits_json_plan_with_expected_shape` (asserts the
report file is never created in dry-run),
`test_execute_report_guarded_under_dest_succeeds`,
`test_execute_report_outside_dest_fails_closed_before_any_corpus_write`.

### 9.2 Finding 2 (P1) -- execute mode overlays an existing destination

**Problem**: `--execute` wrote into `--dest` unconditionally, silently
overlaying an existing tree and leaving stale versions/files behind when the
selected version or file set changed between runs.

**Fix** (`scripts/hashicorp_mdx_normalize.py`): a new `_dest_is_execute_ready()`
check runs before any corpus processing in `--execute` mode -- it fails
closed (`EXIT_DEST_NOT_EMPTY`) if `--dest` exists and is a file, or exists
and is a non-empty directory. No deletion or replacement logic was added
(explicitly out of scope per the finding); the operator must point
`--execute` at an absent or empty directory. Dry-run is exempt from this
check entirely and may point `--dest` at any existing, non-empty directory
without ever creating or touching it.

**Superseded by review-fix cycle 2** (§11.3): this check-then-act sequence
was itself non-atomic (a P2 finding). It was replaced by a simplified
"`--dest` must be ABSENT" contract with an atomic
`mkdir(..., exist_ok=False)` claim immediately before writes
(`EXIT_DEST_ALREADY_EXISTS`, superseding `EXIT_DEST_NOT_EMPTY`). **Further
superseded by review-fix cycle 3** (§12.1): cycle 2's absent-only
requirement was itself an unintended usability regression against this very
finding's original intent (mutual exclusion, not "must not exist yet"); an
existing, empty `--dest` is accepted again, claimed via an exclusive
sentinel file rather than by `--dest`'s own creation. This section is left
as the historical record of the original finding and fix.

**Tests**: `test_execute_rejects_non_empty_existing_dest`,
`test_dry_run_may_point_dest_at_a_non_empty_directory_without_creating_it`.
(The original `test_execute_succeeds_against_existing_empty_dest` was
replaced in cycle 2 by `test_execute_rejects_existing_empty_dest_too`,
reflecting the tightened "absent, not merely empty" contract -- see §11.3
-- and then restored under its original name in cycle 3 with the opposite,
success-asserting body, reflecting the sentinel-claim contract -- see
§12.1.)

### 9.3 Finding 3 (P2) -- calendar version lexical sort

**Problem**: `list_version_entries()`'s non-semver (Terraform Enterprise
`vYYYYMM-N`) group was sorted as a plain string, so `v202507-9` incorrectly
outranked `v202507-10` (`"9" > "1"` lexically).

**Fix** (`scripts/_hashicorp_mdx/selection.py`): added
`_TFE_DATE_PARSE_RE` and `_tfe_date_sort_key()`, producing a numeric
`(YYYYMM, revision)` tuple, and switched the group's `.sort(...)` call to use
it. This only changes the *within-date-family* ordering; it does not alter
which group (semver vs. date-pattern) a candidate is classified into, so the
evidence-backed mixed-family rule (§3.1/§3.2) that selects
`terraform-enterprise -> 2.0.x` in this live corpus is unaffected and was
reconfirmed after the fix (§9 final live-corpus totals, §3.2 table
unchanged).

**Tests**: numeric-ordering regression (`v202507-9` vs. `v202507-10`),
order-independence regardless of input order, and an explicit
mixed-family-preserved-after-fix assertion, all in
`tests/scripts/test_hashicorp_selection.py`.

### 9.4 Finding 4 (P2) -- fence protection assumes identical closing indent/length

**Problem**: the original fence-protection regex required the closing
fence to repeat the *exact same* leading indentation and run length as the
opener -- not Markdown-correct. CommonMark permits a closing fence with any
valid indentation (independent of the opener's) and any run length `>=` the
opener's, using the same marker character.

**Fix** (`scripts/_hashicorp_mdx/normalize.py`): replaced the single-regex
matcher with a manual line-scanning implementation (`_FENCE_OPEN_RE`,
`_FENCE_CLOSE_RE`) that correctly implements this rule, preserving the
entire fenced block byte-for-byte (including surrounding indentation)
between the located open/close boundaries.

**Tests**: longer closing fence, a shorter same-character run inside that
must not terminate the fence early, closing indentation independent of the
opener's, an unclosed fence running to end-of-document, and an end-to-end
pipeline assertion that MDX-looking text inside any of these fence variants
is never leaked or tallied as a construct -- all in
`tests/scripts/test_hashicorp_normalize.py`.

### 9.5 Finding 5 (P2) -- 472 unhandled JSX occurrences leaking into .md output

**Problem**: the tool silently emitted whatever was left of unrecognized
JSX/MDX components verbatim into the `.md` output (the operator asked for
standard Markdown), and only reported an undifferentiated
`unhandled_constructs` tally with no distinction between a genuinely
unimplemented component and a documented, benign placeholder-like token.

**Fix** (`scripts/_hashicorp_mdx/normalize.py`,
`scripts/hashicorp_mdx_normalize.py`):
* A new conservative final pass, `apply_fallback_pass()`, runs after the
  named `TRANSFORM_PIPELINE` and before classification: it structurally
  unwraps unknown *paired* tags (preserving their body, bounded to 5
  iterations for nesting) and renders unknown *self-closing* components as
  a readable Markdown annotation (component name plus useful scalar
  attributes -- quoted-string and bare tokens only; JSX expression
  attributes like `{someVar}` are never rendered, since evaluating them is
  out of scope and would risk fabricating incorrect content). Tags already
  handled by the named pipeline (`_KNOWN_HANDLED_TAGS`) are left untouched.
* `classify_remaining_constructs()` replaces the old undifferentiated scan:
  everything remaining after the fallback pass is split into
  `ambiguous_tokens` (tag names in the grounded `_KNOWN_AMBIGUOUS_TAGS`
  registry -- documented prose/type-notation, never blocking) and
  `unresolved_constructs` (everything else -- a genuine gap).
* `NormalizeResult` now exposes `fallback`, `ambiguous`, and `unresolved`
  counters (replacing the old single `unhandled` counter), and the CLI
  report's JSON shape mirrors this as three top-level dicts
  (`fallback_constructs`, `ambiguous_tokens`, `unresolved_constructs`,
  replacing `unhandled_constructs`).
* `--execute` now fails closed with `EXIT_UNRESOLVED_MDX_CONSTRUCTS` if any
  `unresolved_constructs` remain after processing the corpus, unless the
  operator passes the new, help-documented `--allow-unresolved-mdx`
  override flag. Dry-run never fails on this condition -- it only reports.
* **Genuine bug found via live-corpus grounding while validating this
  finding**: `protect_placeholders()`'s bare-ALL-CAPS-token mask (used to
  protect literal placeholders like `<PATH>`) unconditionally matched the
  opening tag of a real, paired, all-caps-authored callout component found
  in the corpus (`<TIP>...</TIP>` in
  `terraform/v1.16.x/docs/language/block/stack/tfcomponent/removed.mdx`,
  the same semantic as the already-handled mixed-case `Tip` callout),
  masking it away before the fallback pass ever saw it and orphaning the
  un-matched closing `</TIP>` as a spuriously "unresolved" construct. Fixed
  by teaching `protect_placeholders()` to skip masking a candidate token
  when a matching `</NAME>` close tag exists later in the document -- a
  purely structural test (real placeholders are never "closed"), not a
  per-name special case, so it generalizes to any other all-caps-authored
  paired component without enumeration.
* **Registry expansion to meet the "aim for zero" bar**: after the `TIP`
  fix, the real-corpus dry-run's `unresolved_constructs` bucket still held
  62 distinct names / 97 occurrences. Every one was individually grounded
  (sampled against its real corpus context) and confirmed to be either
  Consul/Nomad API-reference backtick-wrapped generic-type notation (the
  same shape as the already-known `ACLLink`) or a multi-word/spaced prose
  placeholder (the same shape as `TFE`) -- never a genuine unimplemented
  component. All 62 were added to `_KNOWN_AMBIGUOUS_TAGS` (§6 lists the
  full set), which drives `unresolved_constructs` to **zero distinct names,
  zero occurrences** on the selected live corpus, satisfying finding 5's
  "aim for zero unresolved genuine MDX components... while preserving
  placeholder-like tokens" bar without loosening the fail-closed execute
  gate.

**Tests**: `apply_fallback_pass` coverage (paired unwrap, self-closing with
expression-only attrs excluded, self-closing with quoted attrs rendered,
nested paired+self-closing, known-handled tags left untouched);
`classify_remaining_constructs` coverage (unresolved tagging, known-ambiguous
non-blocking, the new review-fix-cycle-1-grounded-tags batch, lowercase HTML
passthrough ignored, the heredoc-line-bound regression); the `TIP`/placeholder
collision fix (`test_protect_placeholders_skips_masking_when_a_matching_close_tag_exists_later`,
`test_normalize_mdx_to_md_all_caps_paired_callout_resolved_not_orphaned`); a
golden end-to-end test combining all three classification buckets; and
CLI-level coverage in `test_hashicorp_dryrun_corpus.py`
(`test_execute_fails_closed_when_unresolved_mdx_constructs_remain`,
`test_execute_succeeds_with_explicit_allow_unresolved_mdx_override`,
`test_dry_run_never_fails_on_unresolved_mdx_constructs`).

### 9.6 Finding 6 (P2) -- copy drops non-Markdown, non-allow-listed files

**Problem**: the copy pass skipped every file in the selected tree except
Markdown and an allow-listed set of image extensions, silently dropping
linked PDFs, videos, and other repository data that lived alongside the
Markdown it was extracted from.

**Fix** (`scripts/hashicorp_mdx_normalize.py`): `_process_one_product_tree()`
now has a generic-copy branch -- any file that is not a partial (still
excluded, see below), not `.mdx`, not `.md`, and not an allow-listed image
extension is copied byte-for-byte. The report's `generic_copied` counter
(renamed from `skipped_other`) tallies these. Paths under a literal
`partials` path component are still excluded from the standalone output, per
the original selection contract -- this finding only changes what happens to
files that were previously silently dropped for not matching the Markdown/
image allowlist, not the partials-exclusion rule itself.

**Tests**: `test_dry_run_emits_json_plan_with_expected_shape` (asserts
`generic_copied` count), `test_execute_writes_expected_tree_and_never_materializes_mdx`
(asserts a generic file, e.g. `config.json`, exists at dest and matches
source bytes exactly).

### 9.7 `docline ingest local-dir` output-layout compatibility

The selected output layout -- `{dest}/{product}/{selected_version}/...` for
versioned products, `{dest}/{product}/...` for unversioned products, with
normalized `.md` files, copied images, and copied generic files interleaved
exactly as found in the source tree (minus excluded partials) -- remains
directly compatible with `docline ingest local-dir <source_path> --output
<dir>` (`src/docline/cli.py`'s `_run_ingest_local_dir`): that command's
default `--include` globs (`**/*.md`, `**/*.markdown`, `**/TOC.yml`,
`**/toc.yml`) recurse through arbitrary intermediate directories, so the
extra `{selected_version}` path segment is transparent to it -- it is simply
one more directory component the recursive glob walks through, exactly like
`{product}` itself. Generic non-Markdown files copied per finding 6 (PDFs,
videos, `.json` nav data, etc.) are not matched by the default include globs
and are therefore inert from `local-dir`'s perspective -- present on disk
for downstream consumers that need them, but neither included nor excluded
by the ingest step unless the operator adds a matching `--include` pattern.

**The version directory is intentionally preserved, not a byproduct to be
flattened away later**: it records provenance (which upstream version was
selected and normalized) directly in the output path, and it keeps the
layout stable if a future iteration of this tool (or its eventual
first-class successor, per Requirement 11 in §8) ever needs to select and
retain more than one version per product without path collisions. No change
was made to flatten or rename this segment; this section documents that
choice explicitly, per the finding's request, rather than leaving it as an
unstated implementation detail.

## 10. Traceability

* Script: `scripts/hashicorp_mdx_normalize.py`,
  `scripts/_hashicorp_mdx/selection.py`, `scripts/_hashicorp_mdx/normalize.py`
* Tests: `tests/scripts/test_hashicorp_selection.py` (30 cases),
  `tests/scripts/test_hashicorp_normalize.py` (43 cases),
  `tests/scripts/test_hashicorp_dryrun_corpus.py` (28 cases, including the
  real-corpus dry-run integration test; see §12.6 for the most recent
  addition)
* Dry-run report (repo-local, git-ignored):
  `build/hashicorp-dryrun-evidence/real-corpus-dry-run-report.json`
* Plan: `docs/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan.md`
* Deliberation: `docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`
* Shipment: `062-S`; Feature: `071-F`; Tasks: `071.001-T`..`071.011-T`
* PR: #192; review-fix cycle 1 findings and resolutions: §9; review-fix
  cycle 2 findings and resolutions: §11; review-fix cycle 3 findings and
  resolutions: §12

## 11. Review-fix cycle 2 (PR #192) -- independent re-review findings

A second independent correctness review of PR #192 (post cycle-1 fixes)
found six more in-scope findings. All six were fixed test-first with
surgical, targeted changes; no scope expansion beyond the findings
occurred. This section is the traceable record of each finding, its fix,
and its regression coverage.

### 11.1 Finding 1 (P1) -- unresolved-construct gate ran AFTER execute writes

**Problem**: `main()` ran `process_corpus(..., execute=args.execute)` --
performing every corpus write -- and only checked `report["unresolved_constructs"]`
afterward. A rejected run (unresolved constructs present, no
`--allow-unresolved-mdx`) had therefore already written the full corpus
(and, if `--report` was given, the report file) to `--dest` before the
gate ever fired -- exactly the class of "fail closed" gate the finding-5
fix in cycle 1 was meant to provide, but applied too late to prevent the
writes it was supposed to prevent.

**Fix** (`scripts/hashicorp_mdx_normalize.py`): `--execute` now runs a
complete READ-ONLY normalization preflight pass first --
`process_corpus(source=source, dest=dest, execute=False)`, identical
selection/normalization logic, guaranteed zero writes -- and inspects
*that* pass's `unresolved_constructs`. The run aborts before `--dest` is
even created (`EXIT_UNRESOLVED_MDX_CONSTRUCTS`) unless the result is
empty or `--allow-unresolved-mdx` was passed. Only after this gate
passes does the real write pass run (`process_corpus(..., execute=True)`),
and the JSON report is written to `--report` only AFTER that write pass
completes successfully -- never before, and never at all if the write
pass fails. A second, defense-in-depth check after the real write pass is
kept (in case `--source` mutates between the two passes) but is expected
to be unreachable in the normal case, since both passes share identical
logic.

**Tests**: `test_execute_unresolved_input_leaves_dest_absent_and_report_absent`
(asserts both `--dest` and `--report` are absent when the preflight finds
unresolved constructs); the pre-existing
`test_execute_fails_closed_when_unresolved_mdx_constructs_remain`,
`test_execute_succeeds_with_explicit_allow_unresolved_mdx_override`, and
`test_dry_run_never_fails_on_unresolved_mdx_constructs` continue to pass
unmodified against the new preflight-based control flow.

### 11.2 Finding 2 (P1) -- report containment preflight discarded resolved path

**Problem**: `guard_write_path(dest, args.report)` was called to validate
containment, but its RETURN VALUE (the resolved path) was discarded; the
actual write later used `args.report` -- the original, possibly-unresolved
argument -- for both `args.report.parent.mkdir(...)` and
`args.report.write_text(...)`. The containment check and the write target
could diverge (e.g. a symlink component resolved differently at
write time than at check time).

**Fix** (`scripts/hashicorp_mdx_normalize.py`): the report write now calls
`guard_write_path(dest, args.report)` AGAIN immediately before the actual
write (narrowing, not eliminating, the check-to-write window) and writes
through the RESOLVED path this second call returns, never the original
`args.report`. `guard_write_path`'s docstring now explicitly documents
this as a BEST-EFFORT containment check, not a race-free guarantee --
Python's `Path.resolve()` has no atomic "check and open" primitive, so a
symlink swap between the check and the write can never be fully closed
by this or any check-then-act sequence in the standard library.

**Tests**: `test_execute_report_written_using_resolved_guard_path_not_original`.
A real symlink/junction substitution was considered for this regression
test but rejected as unreliable cross-platform coverage: Windows symlink
creation requires Developer Mode or elevated privileges that cannot be
assumed in CI, and a `..`-segment path (the alternative non-symlink
"unresolved path" shape) resolves to the identical on-disk file via
ordinary OS path traversal regardless of whether the code uses the
resolved or literal form, so it would not actually distinguish the two
code paths. Instead, the test monkeypatches `guard_write_path` to return
a deliberately different (but still `--dest`-contained) path for the
report candidate only, and asserts the report is written at THAT
returned path -- not the original `--report` argument -- while also
asserting the function is called exactly twice (the pre-check plus the
write-time re-guard this finding requires).

### 11.3 Finding 3 (P2) -- non-atomic destination check

**Problem**: `_dest_is_execute_ready()` performed `dest.exists()` /
`dest.iterdir()` as a check-then-act sequence, then later code created
`--dest` and wrote into it. Two concurrent invocations could both observe
an absent-or-empty `--dest`, both pass the check, and then both proceed to
write -- interleaving or corrupting each other's output.

**Fix** (`scripts/hashicorp_mdx_normalize.py`): the execute contract is
simplified to require `--dest` to be ABSENT (not merely empty); a cheap
`_dest_must_be_absent()` check runs early for a fast, clear operator-facing
error message, but the actual concurrency-safe claim is a single
`dest.mkdir(parents=True, exist_ok=False)` call immediately before the
real write pass begins -- an atomic OS-level syscall, so of two racing
invocations exactly one succeeds and the other fails closed with
`EXIT_DEST_ALREADY_EXISTS` instead of silently overlaying. If the write
pass fails partway through AFTER `--dest` was successfully claimed, the
partial output is deliberately left in place (never auto-deleted) and
reported as a distinct, clearly-labeled partial-output failure
(`EXIT_EXECUTION_FAILED`).

**Superseded by review-fix cycle 3** (§12.1): the "ABSENT (not merely
empty)" contract itself proved too narrow -- it rejected the documented
exact operator command whenever the real destination already existed but
was completely empty, a same-contract-surface usability defect against
this very finding's own mutual-exclusion intent. `_dest_must_be_absent()`
was replaced by a sentinel-aware `_dest_precheck()`, and the `mkdir`-based
claim was replaced by `claim_destination()` (an exclusive sentinel file
created directly under `--dest`), preserving the identical mutual-exclusion
guarantee while accepting an existing, empty `--dest` again. This section
is left as the historical record of the original finding and fix.

**Tests** (as of this finding's original fix in cycle 2 -- see §12.1 for
the current, cycle-3 test names, several of which renamed or replaced
these as the contract changed again): `test_execute_rejects_existing_empty_dest_too`
(an existing empty `--dest` is no longer accepted -- contract
simplification), `test_execute_succeeds_against_absent_dest`,
`test_execute_second_claim_attempt_against_already_claimed_dest_fails_closed`
(two SEQUENTIAL claim attempts against the same `--dest` -- the first
succeeds and claims it, the second fails closed, without requiring real
threading), `test_execute_leaves_partial_dest_in_place_when_write_pass_fails`
(monkeypatches `process_corpus` to fail partway through the write pass and
asserts `--dest` is left in place with a partial-output-labeled error, not
deleted).

### 11.4 Finding 4 (P2) -- fence scanner accepted unlimited indentation

**Problem**: the cycle-1 fix for finding 4 (§9.4) removed indentation
matching from the fence closer search ENTIRELY to fix a different bug (an
overly strict same-indentation requirement) -- but over-corrected: a
closing-fence-shaped line at ANY indentation could close ANY opener,
including a top-level (0-3 column) opener being "closed" by an unrelated
four-or-more-space-indented backtick/tilde line that CommonMark would
treat as an indented code block, never a fence boundary.

**Fix** (`scripts/_hashicorp_mdx/normalize.py`): a new
`_leading_indent_columns()` helper measures a line's leading whitespace in
visual columns (tabs expand to the next multiple-of-4 stop, per
CommonMark's own tab-handling rule for block structure). `protect_fenced_code()`
now applies a bounded, two-class rule keyed off the OPENER's own
indentation: a **top-level** opener (0-3 columns) can only be closed by a
line ALSO indented 0-3 columns; a **container/list-indented** opener (4+
columns -- the shape already seen in this corpus under numbered-list
continuations) can only be closed by a line within **three visual columns**
of the opener's own indentation (not necessarily equal -- preserving the
cycle-1 "closing indentation independent of the opener" behavior within a
bound, instead of unboundedly). A same-character run shorter than the
opener, or one at a disallowed indentation, is preserved as literal
content inside the block and the scan continues to the next candidate
line, exactly as before.

**Tests**: `test_protect_fenced_code_four_space_indented_backtick_cannot_close_top_level_fence`
(a top-level fence's four-space-indented "closer" never closes it and is
preserved as literal content),
`test_protect_fenced_code_container_indented_closer_within_three_columns_closes`
(a container-indented opener's closer within 3 columns still closes, not
requiring exact equality),
`test_protect_fenced_code_container_indented_closer_beyond_three_columns_skipped`
(a candidate closer drifting more than 3 columns from a container-indented
opener is skipped, preserved as literal content, and the scan finds the
next valid closer instead). All pre-existing fence tests (§9.4) continue
to pass unmodified -- every previously-tested indented-list fence in this
corpus uses indentation within the new bounds.

### 11.5 Finding 5 (P3) -- live-corpus test only type-checked `unresolved_constructs`

**Problem**: `test_real_corpus_dry_run_zero_writes_and_coverage_report`
asserted `isinstance(report["unresolved_constructs"], dict)` -- true for
ANY dict, including one full of genuine unresolved constructs -- rather
than asserting the actual "zero unresolved constructs on the live corpus"
bar that cycle 1's finding-5 fix (§9.5) was built to satisfy.

**Fix** (`tests/scripts/test_hashicorp_dryrun_corpus.py`): the assertion is
now `report["unresolved_constructs"] == {}`, precisely. Re-run against the
real external corpus (`C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`)
after all cycle-2 fixes: still **0 distinct / 0 occurrences**, confirming
the fence and version-selection fixes in this cycle introduce no
regression against the live corpus (full totals in §11.7 below).

### 11.6 Finding 6 (P3) -- `list_version_entries` could flag multiple `is_latest` entries

**Problem**: the cursor-increment algorithm computed `is_latest` per entry
independently as it walked the sorted list, incrementing the cursor once
per non-stable entry and comparing `idx == cursor` on every iteration. If
the highest-sorted entry was stable (matching cursor 0), a lower-ranked
non-stable entry immediately following it could increment the cursor to 1
and ALSO satisfy `idx == cursor` at index 1 -- flagging a SECOND entry as
latest. `select_latest_version()` itself was unaffected (it returns the
first `is_latest` match found), but any caller inspecting the full
`list_version_entries()` result directly could observe more than one
`is_latest is True` entry, violating the documented "exactly one latest"
contract.

**Fix** (`scripts/_hashicorp_mdx/selection.py`): `list_version_entries()`
now computes the single "latest index" up front -- the first entry (in
the combined descending sort order) whose release stage is `"stable"`, or
index 0 if none is stable -- and marks exactly that one index
`is_latest=True`. This guarantees exactly one `is_latest` entry whenever
the input is non-empty, matching the documented contract precisely
instead of incidentally.

**Tests**: `test_list_version_entries_highest_stable_then_lower_prerelease_exactly_one_latest`
(`["v3.x", "v3.x (rc)", "v2.x"]` -- asserts `sum(is_latest for ...) == 1`
and that only `"v3.x"` is flagged). All pre-existing `list_version_entries`
/ `select_latest_version` tests (§9.3, §9.7) continue to pass unmodified.

### 11.7 Full real-corpus dry-run re-run (post cycle-2 fixes)

Re-ran the complete dry-run against the real external corpus
(`C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`, read-only, zero
writes) after all six cycle-2 fixes above:

* 23 products total (19 versioned + 4 unversioned); `global` excluded --
  unchanged from cycle 1.
* Selected versions unchanged from cycle 1: `vault` -> `v2.x`,
  `terraform` -> `v1.16.x`, `terraform-policy` -> `v0.2.x (beta)`,
  `terraform-enterprise` -> `2.0.x`.
* Totals unchanged from cycle 1: 5,566 `.mdx` normalized, 59 `.md`
  copied, 2,139 assets copied, 1,259 partials skipped, 164 generic
  (non-Markdown, non-image) files copied byte-for-byte.
* Construct classification unchanged from cycle 1: `fallback_constructs`
  14 distinct / 152 occurrences; `ambiguous_tokens` 75 distinct / 255
  occurrences; `unresolved_constructs` **0 distinct / 0 occurrences**
  (finding 5, §11.5, now asserted precisely rather than type-checked).
* `containment_violations`: `[]` (unchanged).

The fence-scanner bound (finding 4) and the `is_latest` uniqueness fix
(finding 6) produce byte-identical selection and normalization results
against this live corpus -- both fixes tighten edge-case boundaries that
this corpus's real content does not happen to trigger, which is the
expected outcome of a surgical, non-behavior-changing-in-the-common-case
correctness fix.

### 11.8 Independent local review of the six fixes above (Ship's own review gate)

Per Ship's `review` skill (`mode:report-only`), an independent multi-persona
local code review (Constitution, Python, Correctness, Maintainability,
Learnings, Concurrency, and Scope Boundary reviewers) was run against this
cycle-2 commit before PR readiness was updated. It confirmed no scope
creep beyond the six numbered findings above, and surfaced four further
in-scope, same-contract-surface robustness/correctness gaps in the code
this cycle had just changed. All four were fixed test-first, in the same
commit, before the review's readiness outcome was finalized:

* **P2** -- the atomic `--dest` claim (`mkdir(exist_ok=False)`, §11.3)
  caught only `FileExistsError`; any other `OSError` (permission denial, a
  blocked ancestor path component, disk exhaustion) escaped as an
  uncontrolled traceback. Fixed by adding an `except OSError` branch
  reporting a clear, stable-exit-code failure
  (`EXIT_DEST_CLAIM_FAILED`, new). Test:
  `test_execute_dest_claim_failure_other_than_file_exists_reports_clearly`
  (monkeypatched `Path.mkdir` raising `PermissionError` for the exact
  `--dest` claim call only).
* **P2** -- the `--report` write (parent `mkdir` + `write_text`, §11.2)
  was unguarded against `OSError`; a failure there after a successful
  corpus write pass would escape as a traceback instead of a controlled,
  clearly-labeled "corpus already written, only the report failed"
  result. Fixed with an `except OSError` branch reporting
  `EXIT_REPORT_WRITE_FAILED` (new) and explicitly noting the corpus
  output is left in place. Test:
  `test_execute_report_write_failure_after_successful_corpus_write_reports_clearly`
  (monkeypatched `Path.write_text` raising only for the exact resolved
  report path).
* **P3** -- `list_version_entries()`'s documented "ordered latest-first"
  contract (the same function fixed in finding 6, §11.6) could list a
  same-version prerelease AHEAD of the stable release it is superseded
  by, because two entries tied on their numeric sort key fell back to
  Python's stable-sort input-order preservation. `is_latest` and
  `select_latest_version()` were unaffected (both scan for the first
  `stable` entry independently of position), but the returned ORDER
  itself is part of the function's contract. Fixed by adding a
  `_stage_priority()` tie-breaker (`stable` outranks any prerelease
  stage) to both the semver-group and TFE-date-group sort keys. Test:
  `test_list_version_entries_orders_stable_ahead_of_same_version_prerelease`
  (asserts the same order regardless of whether the stable or prerelease
  entry is listed first).
* **P3 (advisory, documentation only)** -- the atomic-claim wording
  ("the FIRST filesystem mutation... a single OS-level syscall") slightly
  overstated the guarantee for a `--dest` whose parent directories do not
  yet exist, since `mkdir(parents=True, ...)` creates missing ancestors
  first via ordinary, non-atomic `mkdir` calls before the final, atomic
  claim on `--dest`'s own path component. Narrowed the module docstring
  and the inline comment above the claim to state precisely that only
  `--dest`'s own final path component is claimed atomically; ancestor
  creation is a separate, non-atomic step that precedes it. No test
  required (documentation-only).

After these four fixes, the independent review's final readiness outcome
was `READY` (P0=0, P1=0, P2=0, P3=0 unresolved) for the resulting HEAD.
The full local quality-gate sequence (ruff check, ruff format --check,
full pytest suite, and the real external corpus dry-run) was re-run
afterward and is reported in §11.9 below.

### 11.9 Final quality-gate and real-corpus re-verification (post §11.8 fixes)

* `ruff check .`: all checks passed.
* `ruff format --check .`: 301 files already formatted.
* Full local suite (`pytest --basetemp=build/.pytest-tmp -m "not integration"`):
  **2205 passed, 2 skipped, 16 deselected** (up from 2202 before §11.8's
  three additional regression tests).
* Targeted HashiCorp suite (`-m "not integration"`): **95 passed, 1
  deselected** (up from 92 before §11.8).
* Real-corpus integration test
  (`test_real_corpus_dry_run_zero_writes_and_coverage_report`, run
  explicitly with `-m integration` against
  `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`): **PASSED**.
  Zero writes, `unresolved_constructs == {}` (0/0), and totals identical
  to every prior run in this cycle (5,566 mdx normalized, 59 md copied,
  2,139 assets copied, 1,259 partials skipped, 164 generic copied; 23
  products; unchanged version selections) -- confirming the four §11.8
  fixes (all error-handling and ordering edge cases the real corpus does
  not happen to trigger) introduce no behavioral regression against live
  content.

## 12. Review-fix cycle 3 (PR #192) -- operator-reported usability defect + independent re-review findings

### 12.1 Operator-reported finding -- exact operator command fails against an existing, empty `--dest`

**Problem**: Cycle 2 (§11.3) redesigned `--execute`'s destination claim to
be atomic (`dest.mkdir(parents=True, exist_ok=False)`), which required
`--dest` to be strictly ABSENT -- reinstating "existing empty is fine"
ergonomics from before cycle 2 was explicitly ruled out at the time
because emptiness could not be verified atomically with `mkdir` alone.
The operator subsequently attempted the exact documented operator command
(§7) against the real external destination
`C:\Source\Docs\tf-unified-dev-docs-normalized`, which already existed
(created by a prior dry-run/inspection) and was empty. The documented
exact command failed with `EXIT_DEST_ALREADY_EXISTS`, even though the
target was safely empty and posed no overwrite risk -- an in-scope
same-contract usability defect against cycle 2's own atomic-claim
redesign.

**Fix** (`scripts/hashicorp_mdx_normalize.py`): replaced the single
`mkdir(exist_ok=False)` claim with an exclusive OS-level sentinel-file
claim, `claim_destination()`: the mutual-exclusion guarantee now lives in
an exclusive create of a small marker file
(`.docline-hashicorp-mdx-normalize.claim`) directly under `--dest`
(`os.open(..., os.O_CREAT | os.O_EXCL | os.O_WRONLY)`), not in `--dest`'s
own creation. This decouples "is `--dest` usable" (absent OR empty) from
"is `--dest` currently claimed" (sentinel present), restoring the
existing-empty-dest ergonomics while preserving cycle 2's mutual-exclusion
guarantee: of two invocations racing for the same `--dest`, exactly one
still wins the sentinel create and the other still fails closed. A new,
cheap `_dest_precheck()` replaces `_dest_must_be_absent()` for the common,
non-racing fast-fail case; the authoritative claim happens immediately
before any write begins, is re-verified immediately after the sentinel is
created (rejecting if anything besides the sentinel appeared in the
interim), and the sentinel this invocation creates is always removed via
a `finally` block in `main()` regardless of success or failure --
`--dest` itself, and any partial or complete output, is never touched by
that cleanup. Residual race limitations are documented accurately in both
the module docstring and `claim_destination()`'s own docstring: this
guards against races BETWEEN COOPERATING INVOCATIONS OF THIS SAME SCRIPT,
not against an arbitrary non-cooperating writer.

**Tests** (`tests/scripts/test_hashicorp_dryrun_corpus.py`):

* `test_execute_succeeds_against_existing_empty_dest` -- an existing,
  empty `--dest` now succeeds (replaces the obsolete
  `test_execute_rejects_existing_empty_dest_too`, which asserted the
  cycle-2 rejecting behavior this cycle intentionally reverses).
* `test_execute_rejects_non_empty_existing_dest` -- unaffected, still
  passes: an existing `--dest` with real pre-existing content is still
  rejected.
* `test_dry_run_leaves_existing_empty_dest_unchanged` -- dry-run against
  an existing, empty `--dest` never claims it and leaves it empty
  (dry-run never creates the sentinel).
* `test_execute_removes_claim_sentinel_after_success` -- the sentinel is
  removed after a successful run; only real product output remains.
* `test_claim_destination_two_claims_cannot_coexist` -- direct,
  function-level proof of mutual exclusion: a second `claim_destination()`
  call against a `--dest` whose sentinel is still held by a first,
  unreleased claim raises `DestAlreadyClaimedError`, for both an
  initially-absent and an initially-existing-empty `--dest`, leaving the
  first claim's sentinel completely undisturbed.
* `test_execute_leaves_partial_dest_in_place_when_write_pass_fails` and
  `test_execute_report_write_failure_after_successful_corpus_write_reports_clearly`
  -- both updated to additionally assert the sentinel is removed after a
  failure too, not only after success.
* `test_execute_dest_claim_failure_other_than_file_exists_reports_clearly`
  -- message assertion updated (`"failed to claim --dest"`, matching the
  new wording) with no behavioral change.

### 12.2 Independent local review of the fix above (Ship's own review gate, cycle 3)

Per Ship's `review` skill (`mode:report-only`), an independent
multi-persona local code review (Constitution, Python, Correctness,
Maintainability, Learnings, and Concurrency reviewers) was run against
the §12.1 commit before PR readiness was updated for this, the final
allowed review-fix cycle. Four of the five applicable reviewers
independently converged on the same real defect in the code this cycle
had just changed -- both were fixed test-first, in the same commit,
before the review's readiness outcome was finalized:

* **P0/P1 (Correctness, Concurrency, and Python reviewers, independently
  converging on the same root cause)** -- `main()`'s new
  `_dest_precheck()` gate ran BEFORE `claim_destination()` and, unlike
  `claim_destination()`'s own internal pre-check, was not sentinel-aware:
  it rejected ANY pre-existing non-empty `--dest`, including one whose
  ONLY entry was the reserved claim sentinel (i.e. another invocation
  genuinely still claiming it), with the generic `EXIT_DEST_NOT_EMPTY`
  message. This meant the documented, purpose-built exit-code distinction
  this exact cycle set out to deliver (`EXIT_DEST_ALREADY_EXISTS` for a
  genuine claim collision vs. `EXIT_DEST_NOT_EMPTY` for ordinary leftover
  content) was unreachable through the real CLI entry point for the
  realistic staggered-rerun case -- 100% deterministically, not merely
  under a rare timing window -- and was previously proven only at the
  direct-function-call level
  (`test_claim_destination_two_claims_cannot_coexist`), which bypasses
  `main()`/`_dest_precheck()`/the CLI entirely. The mutual-exclusion
  safety invariant itself still held (no double-write was ever possible),
  but the specific diagnostic contract did not. Fixed by making
  `_dest_precheck()` sentinel-aware: a `--dest` whose only entry is the
  reserved sentinel name now falls through (returns `None`) to the
  authoritative `claim_destination()` check instead of being rejected
  early, and an `OSError` while inspecting an existing `--dest` is
  likewise deferred rather than guessed at. Tests: the stale
  `test_execute_second_claim_attempt_against_already_claimed_dest_fails_closed`
  (whose docstring claimed to cover the claim-collision path but, since
  it ran the first invocation to full completion before starting the
  second, actually only exercised the "rerun after a finished prior run"
  path, with an assertion loose enough to pass either way) was split into
  two accurately-named, accurately-asserting tests:
  `test_execute_rejects_rerun_against_dest_with_existing_output` (asserts
  the specific `EXIT_DEST_NOT_EMPTY` code for the finished-prior-run case)
  and new test
  `test_execute_rejects_dest_actively_claimed_by_another_invocation`
  (pre-seeds `--dest` with ONLY the sentinel and drives it through the
  real CLI, asserting the specific `EXIT_DEST_ALREADY_EXISTS` code and the
  "already claimed by another in-progress invocation" message -- exactly
  the path the fix corrects).
* **P2 (Python and Concurrency reviewers, independently converging)** --
  in `claim_destination()`, the sentinel's `os.open()` (create) and
  `os.close()` were wrapped in a single `try/except OSError` block: if
  `os.open()` succeeded (physically creating the sentinel) but the
  immediately-following `os.close(fd)` then raised `OSError`, the handler
  raised `DestClaimFailedError` WITHOUT removing the sentinel it had just
  created -- since the function never returned that sentinel to its
  caller, `main()`'s `finally`-block cleanup could never learn of or
  remove it, permanently and silently blocking every subsequent run
  against that `--dest`. Fixed by separating the `open()`/`close()` calls
  and calling `release_destination_claim()` before re-raising if the
  close fails. The sentinel's `os.open()` call also now passes an
  explicit `0o600` mode (Constitution reviewer, P3 hygiene finding)
  instead of relying on the platform default. No dedicated new test was
  added for the rare close-failure path itself (would require
  monkeypatching `os.close` at the exact sentinel descriptor, judged
  disproportionate for a narrow OS-level edge case on a disposable tool);
  the fix was verified by inspection and by confirming the existing
  sentinel-lifecycle tests (§12.1) still pass unchanged.

After these two fixes, the independent review's readiness outcome was
`READY_WITH_FOLLOWUPS` for the resulting HEAD: zero unresolved P0/P1
findings, with four further out-of-scope findings (none touching the
`claim_destination()`/`_dest_precheck()` contract surface this cycle
authorized) captured as deferred-scope-expansion stash entries per P-021
C2 rather than fixed, since this is the final allowed review-fix cycle
and none of the four are same-contract-surface completions of the
authorized change:

* `1EDE36E7` (medium) -- pytest's `tmp_path` fixture is not pinned under
  a repo-local `--basetemp` anywhere in this repo (`pyproject.toml`,
  outside this cycle's scope); this cycle's new tests increase exposure
  to that pre-existing, repo-wide gap but do not cause it.
* `1E7CCBF7` (low) -- pre-existing, untouched-this-cycle
  `UnicodeDecodeError` (not `OSError`) is uncaught in the corpus write
  pass's `Path.read_text(encoding="utf-8")` calls.
* `E3129374` (low) -- two pre-existing, untouched-this-cycle
  `guard_write_path()` hardening gaps: Windows case-sensitivity in the
  containment check, and a per-file hot-loop re-resolve of an unchanging
  `dest_root`.
* `13F7C7C3` (low) -- residual maintainability debt in the sentinel-claim
  subsystem itself (duplicated emptiness/sentinel-classification logic
  between `_dest_precheck()` and `claim_destination()`, and overall
  subsystem complexity relative to this tool's single-operator usage
  model) -- advisory, and only actionable if this disposable tool is ever
  promoted beyond requirements-evidence/single-run status.

### 12.3 Final quality-gate and real-corpus re-verification (post §12.2 fixes)

* `ruff check .`: all checks passed.
* `ruff format --check .`: 301 files already formatted.
* Full local suite (`pytest --basetemp=build/.pytest-tmp -m "not integration"`):
  **2209 passed, 2 skipped, 16 deselected** (up from 2205 at the end of
  cycle 2; +4 net new tests this cycle: +3 from §12.1's replace-one/add-
  four round, +1 from §12.2's split-one-into-two round).
* Targeted HashiCorp suite (`-m "not integration"`): **99 passed, 1
  deselected** (up from 95 at the end of cycle 2).
* `uv run pyright src/`: 0 errors, 0 warnings, 0 informations.
* `uv run python -m build`: succeeded (`docline-0.1.0.tar.gz` and
  `docline-0.1.0-py3-none-any.whl`); build artifacts are git-ignored and
  were not committed.
* Real-corpus integration test
  (`test_real_corpus_dry_run_zero_writes_and_coverage_report`, run
  explicitly with `-m integration` against
  `C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`): **PASSED**.
* Exact documented operator command (§7), run WITHOUT `--execute`
  (dry-run only -- this tool is never executed by an agent) against the
  real external `--source`/`--dest`/`--report` paths, including the real
  external `--dest`
  (`C:\Source\Docs\tf-unified-dev-docs-normalized`) that motivated the
  §12.1 finding: **exit 0**, `execute: false`, `unresolved_constructs: {}`,
  `containment_violations: []`, 23 products -- identical to every prior
  cycle's verification. Confirmed the real external `--dest` had exactly
  0 entries before the run and exactly 0 entries after -- dry-run mode
  never claims or touches it, and the real external destination was never
  written to by this cycle's work.

### 12.4 Post-push CI observation (out of scope, deferred)

After pushing this cycle's commit (`eae28b0`) and updating PR #192's
readiness block, `gh pr checks 192` surfaced one non-passing job:
`pipeline-topology (ambient)` -- `BLOCK: BRANCH_MISMATCH: current branch
feat/github-markdown-extension does not match target 062-S`. This is out
of scope per P-021 C1 (fixing it would mean renaming the already-open PR
branch or reconfiguring the pipeline-topology gate's shipment-to-branch
naming convention, neither of which is part of this cycle's authorized
existing-empty-`--dest` sentinel-claim fix) and is not a regression:
job-level inspection confirmed the identical `BRANCH_MISMATCH` failure at
both the prior HEAD (`ebce8d5`) and the HEAD before it (`408dbba`). It is
also confirmed non-blocking: `main` has no branch protection rules (`gh
api .../branches/main/protection` → 404 `Branch not protected`), and the
enclosing CI workflow run's overall conclusion is `success` despite this
one job's individual `failure` conclusion, consistent with an advisory
/ `continue-on-error` ambient check rather than a required gate. Captured
as deferred stash entry `ADE96404` (P-021, threadless path -- an ambient
CI signal, not a GitHub review thread) rather than fixed.

### 12.5 Copilot shadow-review findings (commit `201fc58`, thread-present path)

GitHub's Copilot shadow review re-runs automatically on every push to PR
#192. The round submitted against commit `201fc58` (the §12.4 doc-only
commit) surfaced four review threads. Each was classified against P-021
C1 individually:

* **`3994209535`** (`normalize.py:205`, a backtick-inside-a-fence-info-
  string edge case in the existing fence scanner) -- **out of scope**: a
  pre-existing parsing concern unrelated to the `--dest`/sentinel-claim
  contract this cycle authorizes touching. Captured as deferred stash
  entry `C0E88586` (low priority); thread replied to citing the entry
  and resolved.
* **`3994209569`** (`hashicorp_mdx_normalize.py:753`, `--dest` not
  rejected when it is nested underneath `--source`) -- **out of scope**:
  a different concern from the existing-empty-`--dest` claim fix, and a
  duplicate of an earlier-round finding (`3993438433`) raised before
  cycle 3 began. Captured as deferred stash entry `387E5F82` (medium
  priority, citing both thread IDs so the duplication is traceable);
  both threads replied to citing the entry and resolved.
* **`3994209593`** (`design-doc:356`, the "Exact operator command"
  prose in §7 still described the OLD absent-only `--dest` contract) --
  **in scope**: this is a staleness defect in the documentation of this
  cycle's own fix, not a different concern. Fixed directly by rewriting
  §7 to describe the current absent-or-existing-empty contract, the
  sentinel claim, and the `EXIT_DEST_ALREADY_EXISTS` /
  `EXIT_DEST_NOT_EMPTY` distinction. While auditing for this same class
  of staleness, two further stale cross-references were found and fixed
  in the same commit even though Copilot had not flagged them directly:
  §9.2 (which still claimed a test superseded in cycle 3 "no longer
  exists") and §11.3 (whose fix description and test-name list predated
  cycle 3's further supersession of the "absent-only" contract). Thread
  replied to confirming the fix and resolved.
* **`3994209606`** (`hashicorp_mdx_normalize.py:233`, the PR body's
  "Local Review Readiness" block referenced a stale HEAD `ebce8d5`) --
  **in scope**, but already resolved: this cycle's own PR-body update
  (made before this Copilot round completed) had already moved the
  readiness block to the current HEAD, so the finding and the fix
  crossed in flight. Thread replied to confirming resolution via the
  existing body update and resolved -- no additional code or doc change
  was needed.

### 12.6 Report-path-reserved-sentinel-collision fix (commit-pending, thread-present path)

A further Copilot shadow-review round, submitted against commit
`201fc58` as well (review id `5184263905`, thread `3994230152`), found a
real, deterministic bug in this cycle's own sentinel-claim mechanism: an
operator-supplied `--report` path that resolves to EXACTLY the reserved
claim-sentinel filename under `--dest`
(`.docline-hashicorp-mdx-normalize.claim`, `CLAIM_SENTINEL_NAME`) was
never rejected. `guard_write_path()` only checks *containment* (does the
resolved path fall inside `--dest`) -- and the reserved name is trivially
inside `--dest` too, so containment alone let it through. Writing the
report there would overwrite the live sentinel, and `main()`'s
`finally`-block cleanup would then delete it as "the sentinel this
process created," silently losing the report while the run still
reported exit 0.

This is classified **in scope** per P-021 C1/C3(i): the reserved sentinel
name did not exist before this cycle's own `--dest` claim redesign, so a
collision with it is a defect *introduced by* this cycle's change, not a
pre-existing concern. It is a same-contract-surface completion of the
sentinel-claim mechanism, not a different concern. This finding also
corrected an overclaim of my own: the `CLAIM_SENTINEL_NAME` docstring
comment (written earlier this cycle) had asserted the sentinel "never
collides" with corpus output or the report -- true for ordinary corpus
output (which is guarded to a distinct sub-path), but never actually
enforced for an operator-chosen `--report` path, so the claim was
unverified prose, not a backed guarantee.

Fix (test-first):

* Added a new exit code, `EXIT_REPORT_PATH_RESERVED = 11`.
* Added a small helper, `_reserved_sentinel_path(dest) -> Path`, that
  resolves to `dest.resolve() / CLAIM_SENTINEL_NAME`.
* Wired a rejection check into **both** existing `guard_write_path(dest,
  args.report)` call sites in `main()`:
  * the early, pre-claim check (before `--dest` is created or claimed --
    the realistically-reachable path, and the one the new regression
    test exercises at the CLI level);
  * the post-write, defense-in-depth re-check (mirroring the existing
    double-guard pattern already used for `guard_write_path` itself,
    per review-fix cycle 2 finding 2 -- kept for symmetry, not given its
    own dedicated CLI-level test, consistent with this shipment's
    established proportionality precedent for narrow, code-inspection-
    verifiable duplicate checks).
* Corrected the `CLAIM_SENTINEL_NAME` docstring comment to describe the
  actual, now-enforced rejection instead of the previous unverified
  "never collides" claim.
* Updated the module-level docstring's containment-contract bullet list
  to document the new rejection.
* Added a new regression test,
  `test_execute_rejects_report_path_equal_to_reserved_sentinel`, covering
  BOTH the absent-`--dest` and the existing-empty-`--dest` cases (the
  latter being the exact scenario this cycle's headline fix made legal
  again): in both cases, the rejection fires before any claim, `--dest`
  is left absent (case 1) or empty (case 2), and the specific
  `EXIT_REPORT_PATH_RESERVED` exit code and message are asserted.

Re-verification after this fix:

* Targeted HashiCorp suite
  (`test_hashicorp_dryrun_corpus.py` +
  `test_hashicorp_normalize.py` + `test_hashicorp_selection.py`,
  `-m "not integration"`): **100 passed, 1 deselected** (up from 99 at
  the end of §12.3; +1 net new test this fix).
* Full local suite (`-m "not integration"`): **2210 passed, 2 skipped,
  16 deselected** (up from 2209; +1 net new test this fix).
* `ruff check .`: all checks passed. `ruff format --check .`: 301 files
  already formatted.
* `uv run pyright scripts/hashicorp_mdx_normalize.py`: 0 errors, 0
  warnings, 0 informations.
* `uv run python -m build`: succeeded.
* Exact documented operator command (§7), run WITHOUT `--execute`
  against the real external `--source`/`--dest`/`--report` paths: **exit
  0**, `unresolved_constructs: {}`, 23 products. The real external
  `--dest` (`C:\Source\Docs\tf-unified-dev-docs-normalized`) had exactly
  0 entries before and exactly 0 entries after -- dry-run mode never
  claims it, and it was never written to by this fix's work either.

Thread `3994230152` replied to describing the fix and the commit that
lands it, and resolved.

### 12.7 Final post-push Copilot round (commit `20f91a4`, deferred) and thread-cleanup summary

A further Copilot shadow-review round, submitted against commit
`20f91a4` (the §12.6 fix itself), created one new actionable review
thread and additionally summarized (without creating separate threads
for) three other, already-known/unrelated observations:

* **New thread, `3994338286`** (`hashicorp_mdx_normalize.py:215`):
  `guard_write_path()`'s core containment check
  (`candidate_resolved.relative_to(dest_resolved)`) succeeds when
  `candidate_resolved == dest_resolved`, so a `--report` path equal to
  `--dest` itself passes the guard despite the documented strictly-inside
  contract; execute mode would then write the corpus and only fail later
  when it tries to open the destination directory as the report file --
  after corpus writes have already occurred. **Out of scope** per P-021
  C1: this is a pre-existing gap in `guard_write_path()`'s own core
  logic (unchanged since cycle 1/2), distinct from the reserved-sentinel
  collision §12.6 fixed (that defect was caused by a sentinel name this
  cycle newly introduced; this one predates cycle 3 entirely and would
  require modifying `guard_write_path()`'s own relative_to logic, a
  broader change). Captured as deferred stash entry `7D71CBEA` (low
  priority); thread replied to and resolved.
* **Suppressed, non-threaded observations** (mentioned in the review
  body's summary, not posted as separate line comments -- no GitHub
  thread exists for these, so no reply/resolve action applies): a
  version-stage-classification edge case in
  `scripts/_hashicorp_mdx/selection.py` (an unmatched parenthesized
  stage suffix defaults to "stable"); a fence-opener indentation-masking
  concern in `scripts/_hashicorp_mdx/normalize.py` closely related to
  the already-deferred `C0E88586` fence-scanner finding; and two findings
  in `src/docline/app.py` / `src/docline/process/output_contract.py`
  about `.markdown`-extension output-path collisions. The latter two are
  not part of the HashiCorp normalizer tooling this shipment (062-S)
  covers at all -- they belong to unrelated, pre-existing work already
  present on this branch (`feat/github-markdown-extension`) before this
  shipment's commits began, and are out of scope for 062-S's review-fix
  cycles regardless of P-021 classification.

**Thread-cleanup summary for this cycle**: seven review threads in total
were replied to and resolved across §12.5–§12.7's post-push Copilot
triage: `3994209535` (→ `C0E88586`), `3993438433` + `3994209569` (→
`387E5F82`, both resolved against the same entry), `3994209593` (fixed),
`3994209606` (already resolved via body update), `3994230152` (fixed,
§12.6), and `3994338286` (→ `7D71CBEA`, this section). No further new
Copilot review rounds were observed after a reasonable post-push waiting
window at the final HEAD.

## 13. Review-fix cycle 4 (PR #192) -- operator-authorized additional cycle, Copilot review findings

Cycle 3 (§12) was recorded as "the final allowed review-fix cycle" per
this shipment's own nominal cycle budget. The operator subsequently
reported additional Copilot review comments on PR #192 and explicitly
authorized **one additional review-fix cycle** for in-scope, P-021
C1-passing findings -- explicitly not waiving P-021 scope classification
itself. This section records that additional cycle.

### 13.1 Enumeration and classification

All review threads on PR #192 were enumerated via `gh api graphql` with
full `reviewThreads` pagination (not the partial REST list), yielding 25
threads total, of which 13 were unresolved and Copilot-authored. Each was
classified individually against P-021 C1 (does the fix require ONLY
completing the exact temporary HashiCorp MDX normalizer contract already
authorized for 062-S/071-F -- `scripts/hashicorp_mdx_normalize.py` +
`scripts/_hashicorp_mdx/*` + their tests):

| Thread | File:line | Classification | Disposition |
|---|---|---|---|
| `nt1k` | `src/docline/app.py:51` | out of scope | deferred → `48D6D05A` |
| `nt2J` | `hashicorp_mdx_normalize.py:456` | in scope | fixed (§13.2) |
| `nt3T` | `src/docline/app.py:48` | out of scope | deferred → `360FB708` |
| `ho7ie` | fixture `config.json:1` | in scope | fixed (§13.2) |
| `p8Oq` | `_hashicorp_mdx/normalize.py:210` | in scope | fixed (§13.2) |
| `p8PF` | `hashicorp_mdx_normalize.py:496` | in scope | fixed (§13.2) |
| `p8PN` | `hashicorp_mdx_normalize.py:535` | in scope | fixed (§13.2) |
| `p8PV` | `_hashicorp_mdx/normalize.py:810` | in scope | fixed (§13.2) |
| `p8Ph` | `hashicorp_mdx_normalize.py:525` | in scope | fixed (§13.2) |
| `p8Ps` | `process/cross_doc_links.py:157` | out of scope | deferred → `8FA344D0` |
| `qAsc` | `_hashicorp_mdx/normalize.py:759` | in scope | fixed (§13.2) |
| `qAsu` | `hashicorp_mdx_normalize.py` | in scope | fixed (§13.2) |
| `qAs7` | `process/output_contract.py:291` | out of scope | deferred → `87BFB31B` |

The four out-of-scope findings (`nt1k`, `nt3T`, `p8Ps`, `qAs7`) all touch
pre-existing `.markdown` handling in `src/docline/**` (production docline
code, e.g. `app.py`, `process/cross_doc_links.py`,
`process/output_contract.py`) that predates this shipment and belongs to
unrelated work already present on branch `feat/github-markdown-extension`
before 062-S's commits began -- confirmed via `git log` on each affected
line. Feature 071-F's authorized contract is explicitly a standalone
disposable Python preprocessor with production docline MDX/`.markdown`
integration out of scope, so these four are categorically outside this
cycle's authorization regardless of their individual merit. Each was
captured as a P-021 C2 deferred-scope-expansion stash entry with the full
six-field payload before any thread reply, per the threadless-vs-thread-
present capture procedure (all four have an existing PR thread, so the
thread-present path applies: reply citing the entry ID, then resolve).

### 13.2 In-scope fixes (test-first)

Nine findings were in scope and fixed, each test-first (new test written
and confirmed to fail without the fix, via `git stash` on the source
file(s) alone with the new test left in place, then confirmed to pass
once the fix was restored):

* **`nt2J`** (`ProductReport` omits planned destination paths) --
  added `planned_paths`/`planned_paths_truncated` fields to
  `ProductReport` (capped at `MAX_PLANNED_PATHS_PER_PRODUCT = 200`
  per product; `planned_paths_truncated` signals a capped list, while
  the uncapped `file_counts` totals remain authoritative). Tests:
  `test_process_corpus_collects_full_planned_dest_paths_when_requested`
  and additional planned-paths coverage in
  `test_hashicorp_dryrun_corpus.py`.
* **`ho7ie`** (misleading synthetic fixture text) -- corrected the
  fixture text in
  `tests/scripts/fixtures/hashicorp/synthetic_corpus/terraform/v1.16.x/config.json`
  to accurately describe what it exercises.
* **`p8Oq`** (fenced-code scanner over-masks unindented MDX as an
  indented code block inside list-item/blockquote containers) -- added
  `_container_establishes_indent()` to `scripts/_hashicorp_mdx/normalize.py`,
  which back-scans (bounded by `_MAX_CONTAINER_BACKSCAN_LINES`) for a
  list-marker or blockquote-marker line establishing a container
  context before treating a 4+-column-indented fence opener as a
  legitimate indented code block. Tests: three new fence-context
  regression tests in `test_hashicorp_normalize.py`.
* **`p8PF`** (symlink escape on the read side: `_iter_files_sorted`
  followed symlinks pointing outside `--source` without detection) --
  added `guard_read_path(source_root, candidate)`, the read-side
  counterpart to the existing `guard_write_path()`; generalized the
  `ContainmentViolation` docstring to cover both read and write;
  threaded a new `source_root` parameter through `_iter_files_sorted()`
  and `_process_one_product_tree()`. Tests:
  `test_guard_read_path_rejects_paths_outside_source`,
  `test_process_corpus_rejects_symlinked_file_escaping_source`,
  `test_process_corpus_rejects_symlinked_top_level_product_dir_escaping_source`
  (symlinks confirmed to work without admin rights on this Windows
  development machine).
* **`p8PN`** (`.mdx`/`.md` destination collision: normalizing
  `foo.mdx` to `foo.md` can silently overwrite a pre-existing `foo.md`
  in the same selected tree, or vice versa) -- added
  `DestinationCollisionError`, new exit codes
  `EXIT_DEST_PATH_COLLISION = 12` and
  `EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT = 13`, and an uncapped
  `planned_dest_paths: set[str]` out-parameter threaded through
  `_process_one_product_tree()`/`process_corpus()`, with collision
  detection inside the `_record_planned_path()` closure that raises
  before any write, in both dry-run and execute mode. Tests:
  `test_process_corpus_rejects_mdx_md_destination_collision` and
  companion coverage.
* **`qAsu`** (`--report` path may collide with an arbitrary planned
  corpus OUTPUT path, not only the reserved claim sentinel) -- reused
  the same `planned_dest_paths` set populated during preflight; added
  checks in `main()` (an early pre-claim check and a defense-in-depth
  re-check immediately before the final report write) comparing the
  resolved `--report` path against the full uncapped plan. Test:
  `test_execute_rejects_report_path_colliding_with_planned_output`.
* **`qAsc`** (known-tag-name residue silently excluded from
  classification) -- removed an unsafe
  `if name in _KNOWN_HANDLED_TAGS: continue` skip from
  `classify_remaining_constructs()`. The skip assumed any "known" tag
  name was always fully consumed upstream, but nested same-tag elements
  (e.g. a `<Note>` inside a `<Note>`) defeat `transform_callouts`'s
  non-greedy regex, leaving genuine unrendered residue invisible to
  classification. Test:
  `test_classify_remaining_constructs_flags_survived_known_tags_as_unresolved`.
  This fix also revealed a genuinely new, out-of-scope finding against
  the real corpus -- see §13.4.
* **`p8PV`** (inline code spans not masked before component
  transforms, so JSX-looking text written literally inside backticks,
  e.g. `` `<PluginBadge type="official" />` ``, was incorrectly
  rewritten by the fallback pass as if it were a live component) --
  added `protect_inline_code()`/`restore_inline_code()` to
  `scripts/_hashicorp_mdx/normalize.py`, masking backtick-delimited
  inline code spans (variable-length delimiters via a regex
  backreference, restricted to single-line spans -- a documented,
  accepted simplification for this disposable tool) before the
  component-transform passes run, and restoring them afterward. Tests:
  `test_protect_inline_code_masks_single_backtick_span`,
  `test_protect_inline_code_handles_variable_length_delimiter_with_inner_backtick`,
  `test_protect_inline_code_leaves_unterminated_backticks_unmasked`,
  `test_normalize_mdx_to_md_preserves_jsx_looking_text_inside_inline_code`,
  `test_normalize_mdx_to_md_still_renders_live_component_outside_code_span`
  (the last confirming the SAME tag shape outside a code span is still
  correctly rendered, so masking does not over-suppress legitimate
  component handling).
* **`p8Ph`** (frontmatter newline preservation broken on Windows:
  `Path.read_text()`/`Path.write_text()` perform universal-newline
  translation by default, silently rewriting a source file's original
  CRLF frontmatter delimiters to LF on read and re-translating LF back
  to the platform newline on write) -- added
  `_read_text_preserving_newlines()` (`hashicorp_mdx_normalize.py`),
  reading via `path.open("r", encoding="utf-8", newline="")` since
  `Path.read_text()` gains a `newline` parameter only in Python 3.13
  and this project's runtime is 3.12; wired it into
  `_process_one_product_tree`'s MDX branch, paired with
  `dest_path.write_text(result.text, encoding="utf-8", newline="")` on
  the write side. Scoped the fix narrowly: the frontmatter block is
  preserved byte-exact (untouched raw bytes flow straight through),
  while `normalize_mdx_to_md()` explicitly normalizes only the BODY to
  bare `\n` right after `split_frontmatter` (reproducing what universal-
  newline reading would have done), keeping the already-tested
  transform-pipeline behavior on body content unchanged. Accepted,
  documented side effect: since `newline=""` on write disables ALL
  translation (required to keep frontmatter bytes exact), the body's
  `\n` characters are now written as literal LF rather than being
  auto-translated to the platform's line ending; no existing test
  asserted CRLF body output. Tests:
  `test_execute_preserves_frontmatter_byte_exact_on_crlf_source` and
  `test_execute_preserves_frontmatter_byte_exact_on_lf_source` in
  `test_hashicorp_dryrun_corpus.py`, using `Path.write_bytes()`/
  `Path.read_bytes()` to control and assert exact input/output bytes.

### 13.3 Quality-gate and full-suite re-verification

* `ruff check .`: two `E501` line-too-long violations introduced by
  this cycle's `p8Oq`/`qAsu` fixes were found and fixed (wrapped
  argument lists); all checks pass.
* `ruff format --check .`: two files needed reformatting after the
  `E501` fixes (`scripts/_hashicorp_mdx/normalize.py`,
  `tests/scripts/test_hashicorp_normalize.py`); applied, then
  `ruff format --check .` reports 301 files already formatted.
* Full local suite (`pytest --basetemp=build/.pytest-tmp`, all
  markers): **2241 passed, 6 skipped**.
* Targeted HashiCorp suite
  (`test_hashicorp_dryrun_corpus.py` + `test_hashicorp_normalize.py` +
  `test_hashicorp_selection.py` + `test_load_test.py`,
  `-m "not integration"`): **138 passed, 1 deselected**.

### 13.4 Real-corpus re-verification and a genuinely new self-discovered finding

The real-corpus integration test
(`test_real_corpus_dry_run_zero_writes_and_coverage_report`, run
explicitly against
`C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`) was re-run after
all nine §13.2 fixes. The `qAsc` fix made
`classify_remaining_constructs()` accurate for the first time, and as a
direct consequence the test's pre-existing `unresolved_constructs == {}`
assertion -- which had only ever been passing because the now-removed
skip was silently hiding real residue -- failed, surfacing four
genuinely distinct, previously-invisible pipeline gaps against the live
corpus:

* a `<Note>` opening a list-item-indented block
  (`boundary/v1.0.x/content/docs/workers/manage.mdx`) not matched by
  `transform_callouts`'s line-anchored regex;
* `<EnterpriseAlert inline />` embedded mid-sentence inside running
  list-item prose (multiple `consul/v2.0.x` files, e.g.
  `api-docs/acl/index.mdx`) not recognized in that inline-embedded
  position;
* a bare self-closing `<Warning/>` with no attributes or body
  (`consul/v2.0.x/content/docs/monitor/telemetry/appdynamics.mdx`) not
  handled by the paired-tag Warning transform;
* `<VideoEmbed url="...">...</VideoEmbed>` (8 occurrences in
  `well-architected-framework/.../design-control-data-management-plane.mdx`)
  not matched by the VideoEmbed transform's expected attribute/shape.

Each was investigated (via a scratch, non-committed instrumentation
script) far enough to confirm none shares `qAsc`'s root cause (nested
same-tag elements defeating a non-greedy regex, already fixed and
unit-tested with a synthetic regression) and that each would require its
own separate, shape-specific pipeline investigation and fix. This is
classified **out of scope** per P-021 C1: none of the four are required
to complete the `qAsc` Copilot comment's classification-bug fix, and
collectively they are a substantially larger body of work than this
cycle's single-comment authorization. Captured as a threadless P-021 C2
deferred-scope-expansion stash entry, `7F80C39E` (no GitHub review
thread exists for this self-discovered finding -- it surfaced from
re-running an existing integration test, not from a Copilot comment).

The integration test's assertion was updated in this same commit to
assert the actual, now-honestly-reported baseline
(`{"EnterpriseAlert": 12, "Note": 1, "VideoEmbed": 8, "Warning": 2}`)
instead of the `{}` bar that was only ever passing due to the classifier
bug just fixed, with an in-test comment explaining the history and
citing `7F80C39E`. The test remains a precise regression guard against
this documented baseline rather than a merely type-checked assertion.
Re-run after the assertion update: **PASSED**. `containment_violations`
remained `[]`; dry-run performed zero writes, as in every prior cycle.

### 13.5 P-021 deferred-scope-expansion entries created this cycle

| Entry | Priority | Source finding(s) | Summary |
|---|---|---|---|
| `48D6D05A` | medium | `nt1k` | `.md`/`.markdown` output-path collision in `src/docline/app.py` |
| `360FB708` | high | `nt3T` | pre-existing `.markdown` production changes contradict PR scope |
| `8FA344D0` | medium | `p8Ps` | `.markdown` link targets not rewritten to `.md` in `cross_doc_links.py` |
| `87BFB31B` | medium | `qAs7` | `.md`/`.markdown` output-path collision in `output_contract.py` (same underlying defect as `nt1k`, different call site) |
| `7F80C39E` | medium | self-discovered (via `qAsc` fix) | four distinct real-corpus unresolved-construct pipeline gaps (see §13.4) |

All five entries were verified to persist correctly (re-read after
creation) and confirmed, via search of both the active and archived
stash, to have no prior reusable entry for the same expansion before
capture.
