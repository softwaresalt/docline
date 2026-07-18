---
shipment: 054-S
title: "Closure record — bump artifact GitHub Actions off deprecated Node 20 (058-F)"
status: verified
merge_sha: f8dd323
merged_pr: 161
---

## Scope delivered

Feature `058-F` (shipment `054-S`, from stash `4D06AAD8`) clears the Node.js 20
deprecation warnings observed on the `v0.1.0` Release run. GitHub was forcing the
pinned artifact actions onto Node 24 because their versions still targeted the
deprecated Node 20 runtime.

| Task | Delivered |
|---|---|
| `058.001-T` | `.github/workflows/release.yml` — `actions/upload-artifact` v4.6.2 → **v7.0.1** (`043fb46d…`) and `actions/download-artifact` v4.3.0 → **v8.0.1** (`3e5f45b2…`, both the publish-pypi and github-release jobs). SHA-pinned with `# vX.Y.Z` comments per the workflow security convention. |

`ci.yml` uses no artifact actions (documented no-op audit). `checkout@v6.0.3`,
`setup-uv@v8.2.0`, and `setup-python@v6.2.0` were already on Node 24 and left
untouched.

## Notable behavior change (accepted)

`download-artifact@v8` changes digest mismatches from a warning to a **workflow
failure by default** (configurable via the new `digest-mismatch` input). The
secure `error` default is accepted: upload and both downloads run in the same
workflow, so the digest always matches; a mismatch would indicate a corrupted or
tampered artifact that should block the release rather than publish silently.

## Verification

- Old v4 SHAs absent from `release.yml`; new v7.0.1/v8.0.1 SHAs present
  (upload ×1, download ×2) — an executable pre/post check that fails before the
  edit and passes after.
- `actionlint .github/workflows/release.yml` exits 0; YAML parses.
- Full CI green on the merge (`ruff` lint/format, `pyright`, `pytest`,
  sdist+wheel, ci gate) — the change-detection guard correctly treated the
  workflow edit as code and ran the heavy jobs.
- Copilot review passed clean (no comments) on the merge head.

The workflow is tag-triggered and cannot run on a normal PR, so the final runtime
proof is a clean **next release tag** with no Node 20 annotations.

## Notes

* Plan `docs/plans/2026-07-17-ci-artifact-actions-node24-plan.md` cleared the
  plan-review gate (PASS) after a multi-round Copilot review on the staging PR
  (#160) that corrected an initial over-dismissal of the v8 digest change and
  added the required Constitution Check.
* This change does not affect the already-published `v0.1.0`; it takes effect on
  the next version tag.
