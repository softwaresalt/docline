---
title: "CI artifact actions to Node 24"
type: plan
slug: ci-artifact-actions-node24
created: 2026-07-17
status: ready
scope: ops/ci
---

## Problem

The `v0.1.0` Release run logged Node.js 20 deprecation warnings: GitHub is
forcing `actions/upload-artifact` and `actions/download-artifact` onto Node 24
because the pinned versions still target the deprecated Node 20 runtime. The
release still succeeds, but the annotations are noise and the runtime will be
removed in a future GitHub Actions update.

## Findings (repo-grounded)

* The artifact actions appear **only** in `.github/workflows/release.yml`:
  * line 86 — `actions/upload-artifact@…  # v4.6.2`
  * line 105 — `actions/download-artifact@…  # v4.3.0`
  * line 120 — `actions/download-artifact@…  # v4.3.0`
* `.github/workflows/ci.yml` uses **no** artifact actions — the "audit ci.yml"
  item resolves to a no-op confirmation.
* Other actions (`checkout@v6.0.3`, `setup-uv@v8.2.0`, `setup-python@v6.2.0`)
  were **not** flagged — already on Node 24; leave them.
* Current Node-24-targeting releases: `upload-artifact v7.0.1`,
  `download-artifact v8.0.1`.

## Approach

Bump the three artifact-action pins in `release.yml` to the current
Node-24-targeting releases, keeping the SHA-pin + `# vX.Y.Z` comment convention:

* `upload-artifact` → `v7.0.1` (resolve to its commit SHA)
* `download-artifact` → `v8.0.1` (resolve to its commit SHA, both lines)

Verify the v4→v7 (upload) and v4→v8 (download) major bumps against the
single-named-artifact contract used here (name `dist`, downloaded **by name**):

* `download-artifact@v5` — path change affects single downloads **by ID** only;
  we download by name, so this does not apply.
* `download-artifact@v8` — **digest-mismatch now fails the run by default**
  (previously a warning; configurable via the new `digest-mismatch` input). This
  applies to every download, including our `dist` artifact. Because the upload
  and both downloads run in the same workflow, the digest always matches, so no
  spurious failure is expected — and the secure `error` default is desirable (it
  surfaces a corrupted/tampered artifact instead of publishing it). Accept the
  default; do **not** set `digest-mismatch: warn`.
* `download-artifact@v8` also migrated to ESM (transparent to callers) and skips
  decompression for non-zip downloads; our `dist` artifact is a zip, so the
  default behavior is unchanged.
* `upload-artifact@v7` — the immutable-artifact / unique-name model (introduced
  in v4) is unchanged for our single `dist` upload.

## Verification

Tag-driven `release.yml` is exercised only on a version tag, so it cannot run on
a normal PR. Verify by:

1. `actionlint` / YAML sanity (the workflow parses).
2. Confirming the three pins resolve to valid SHAs for the stated tags.
3. On the **next** release tag, confirm the Node 20 deprecation annotations are
   gone from the Release run.

## Constitution Check

| Principle | Assessment |
|---|---|
| I. Safety-First Python | N/A — no Python changes. The release job's `ruff`/`pyright`/`pytest` gates still run ahead of build/publish and are unaffected. |
| II. Test-First (NON-NEGOTIABLE) | Applies, but no `pytest`-style harness can attach to a tag-triggered workflow with no importable code path. The red→green intent is honored by an **executable pre/post check**: assert the old v4 pins (`ea165f8d…` upload, `d3f86a1…` download) are gone and the `v7.0.1`/`v8.0.1` SHAs present — this fails before the edit and passes after. Supplemented by `actionlint` parse and a clean next-tag Release run with no Node 20 annotations as runtime proof (see Verification). No production code is added that would need unit coverage. |
| III / IV. Workspace isolation & CLI containment | Change confined to `.github/workflows/release.yml`; no writes outside the repo tree. |
| V. Structured Observability | Net-positive — removes deprecation noise and makes artifact-integrity failures explicit (digest mismatch → hard error). |
| VI. Single Responsibility | No new dependencies; bumps existing action pins only. |
| VII. Destructive-command approval | None — no destructive commands involved. |
| VIII. Safety modes | Not required; low blast radius, config-only, cannot affect a build until the next tag. |
| IX. Git-friendly persistence | YAML workflow edit; SHA-pinned with `# vX.Y.Z` comments. |
| XI. Merge-commit policy | The PR merges via a merge commit per policy. |

**Rollback:** revert the pin bump (single commit). The change cannot affect a
build until the next version tag is cut. No principle conflicts; the one accepted
behavior change — `download-artifact@v8`'s secure digest-mismatch default — aligns
with Principle V.

## Plan Review

**Gate decision: PASS** — no P0/P1/P2 findings. Reviewed against the plan-review
personas before staging (recorded here to satisfy the harvest review gate).

| Persona | Assessment |
|---|---|
| Constitution Reviewer | `## Constitution Check` present and accurate. Test-First non-applicability, workflow safety/rollback, observability, and merge-commit policy all addressed. No violations. |
| Python Reviewer | N/A — no Python; no type signatures or error-handling surface. |
| Scope Boundary Auditor | Tight scope: three action pins in `release.yml` plus a documented no-op `ci.yml` audit. No scope creep or YAGNI. |
| Learnings Researcher | No conflicting or superseding learning found in `docs/compound/` (searched action-pinning / workflow terms). SHA-pin convention upheld. |
| Architecture Strategist | No architectural impact; CI-config only. |
| Security Lens Reviewer | SHA-pinning preserved; adopts `download-artifact@v8`'s secure `digest-mismatch: error` default — net-positive for supply-chain integrity. No secrets touched. |

**P3 (advisory):** consider a periodic (e.g. quarterly) action-version audit so
pinned actions do not drift onto deprecated runtimes again. Not blocking; captured
as awareness only.

Runtime verification and rollback are covered under Verification and Risk above.
No runtime or closure gaps for a tag-triggered, config-only change.

## Risk

Low. CI-config-only, no application code. Rollback = revert the pin bump. The
change cannot affect a build until the next tag is cut. The only behavioral shift
is `download-artifact@v8`'s digest-mismatch → error default, accepted as a secure
default (in-run upload/download digests always match).
