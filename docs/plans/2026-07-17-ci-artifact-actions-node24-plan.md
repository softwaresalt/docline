---
type: plan
slug: ci-artifact-actions-node24
created: 2026-07-17
status: draft
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

Verify the v4→v7 (upload) and v4→v8 (download) major bumps don't change the
single-named-artifact upload/download contract used here (name `dist`, default
path). No matrix/merge behavior is involved, so the breaking changes around
artifact immutability/merging do not apply.

## Verification

Tag-driven `release.yml` is exercised only on a version tag, so it cannot run on
a normal PR. Verify by:

1. `actionlint` / YAML sanity (the workflow parses).
2. Confirming the three pins resolve to valid SHAs for the stated tags.
3. On the **next** release tag, confirm the Node 20 deprecation annotations are
   gone from the Release run.

## Risk

Low. CI-config-only, no application code. Rollback = revert the pin bump. The
change cannot affect a build until the next tag is cut.
