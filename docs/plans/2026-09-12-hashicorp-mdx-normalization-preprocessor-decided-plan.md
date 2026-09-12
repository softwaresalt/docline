# Decided Plan: Temporary HashiCorp unified-docs MDX→MD normalization preprocessor

- **Date decided**: 2026-09-11 (plan review attempt 1, verdict PASS)
- **Compacted**: 2026-09-12 (post-merge closure, shipment `062-S` / feature `071-F`, PR #192)
- **Source deliberation**: `docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`
- **Owner of execution**: Ship
- **Original plan + review**: `docs/archive/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan.md`,
  `docs/archive/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan-review.md`

## Final decision

Build a standalone, disposable Python preprocessor inside `docline` (never inside
`src/docline/`) that selectively copies the latest-version directory of each versioned
HashiCorp product plus all unversioned products from an external read-only corpus,
normalizing `.mdx -> .md` in-flight during copy, and captures the resulting coverage +
unhandled-construct inventory as requirements evidence for a future first-class docline
MDX ingestion feature.

## Containment contract (NON-NEGOTIABLE, honored throughout execution)

- Read-only access to the external corpus only. No session agent writes, modifies, or
  deletes anything outside the repo. The real external destination is never written by
  an agent — dry-run is the default (zero writes), `--execute` is operator-only, and the
  exact operator command is documented rather than run.
- Tests use a repo-local pytest `--basetemp` (never the OS temp dir).
- A runtime containment guard rejects any resolved write path outside `--dest`.

## Delivered files

| Path | Purpose |
|---|---|
| `scripts/hashicorp_mdx_normalize.py` | CLI orchestrator: containment-guarded writes, dry-run/execute, JSON report |
| `scripts/_hashicorp_mdx/selection.py` | Product classification + latest-version selection (semver port) |
| `scripts/_hashicorp_mdx/normalize.py` | MDX→MD transform pipeline (frontmatter/fence/placeholder protection + construct transforms) |
| `tests/scripts/test_hashicorp_{selection,normalize,dryrun_corpus}.py` | Unit + golden + full-corpus integration tests |
| `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md` | Requirements-evidence writeup (selection findings, construct table, unhandled-construct inventory, numbered productionization requirements) |

No `src/docline/` file was touched by this feature's own scope.

## Key implementation decisions that survived review

* **Python semver port of the source repo's `gather-version-metadata.mjs`**, validated
  against a checked-in expected-latest table plus a full-corpus live cross-check — a naive
  sort was rejected because latest-version selection has real edge cases (`vault -> v2.x`
  not `v1.21.x`; date-string fallback for `terraform-enterprise`; beta-stage exclusion).
* **Streaming normalize-on-copy** (never materialize-then-normalize): `.mdx -> .md`
  transforms happen in-flight per file.
* **Protection scaffold before construct transforms**: frontmatter/fenced-code/placeholder
  protection (B.T1) is sequenced strictly before callout/Tabs/CodeTabs/VideoEmbed
  transforms (B.T2/B.T3), so protected regions are never corrupted by a later transform.
* **Dry-run-by-default CLI surface**, `--execute` required to write, containment guard
  bounded to `--dest`.
* **Exclusive sentinel-file destination claim** (`os.O_CREAT | os.O_EXCL`), superseding an
  initial `mkdir(exist_ok=False)` design once live operator use revealed a legitimately
  pre-existing, empty `--dest` cannot be distinguished from a concurrently-claimed one by
  existence alone. See `docs/compound/2026-09-12-exclusive-destination-claim-needs-sentinel-not-mkdir.md`.

## Risks accepted (from the plan's hardening register) and how they resolved

1. **Containment breach** — mitigated by dry-run default + containment guard + repo-local
   basetemp + explicit zero-out-of-repo-writes test assertion. No breach occurred across
   any session; the real external `--dest` was confirmed 0 entries before and after every
   run.
2. **Wrong "latest" selected** — mitigated by the semver port + expected-latest table +
   full-corpus cross-check. Live verification found and corrected discrepancies vs. the
   plan's original assumptions (`terraform-enterprise` had newer semver-style directories).
3. **MDX corruption of fenced code/placeholders/frontmatter** — mitigated by the B.T1
   protection scaffold; no regressions found across 4 review-fix cycles (cycle 4 was an
   operator-authorized additional cycle beyond the original 3-cycle budget — see
   Verification outcome below).
4. **Scope creep into production docline** — held throughout; confirmed zero `src/docline/`
   changes attributable to this feature at closure.
5. **Materialize-then-normalize regression** — did not occur; C.T1's in-flight requirement
   held.
6. **OS-temp test writes** — did not occur; repo-local basetemp used throughout.

## Verification outcome

All acceptance criteria met. Full-corpus dry-run: 23 products (19 versioned + 4
unversioned), zero out-of-repo writes across every session. Cycle 4's classifier fix
(see the sentinel-file compound learning cross-reference above) revealed the corpus's
honest final `unresolved_constructs` baseline is **not empty** —
`{"EnterpriseAlert": 12, "Note": 1, "VideoEmbed": 8, "Warning": 2}` (4 distinct pipeline
gaps, deferred as stash `7F80C39E` per P-021 C1) — so the documented operator `--execute`
command requires `--allow-unresolved-mdx` until those residues are separately resolved.
Requirements-evidence doc committed with numbered productionization requirements. Full
detail:
`docs/closure/2026-09-12-hashicorp-mdx-normalization-preprocessor-runtime-verification.md`
and `docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md`
§12-13.

## Out of scope (unchanged from the original plan, held throughout)

Production docline MDX integration; changes to `_SUPPORTED_EXTENSIONS`/readers/ELT; any
write to the external normalized destination by a session agent; node/bun runtime
dependency.
