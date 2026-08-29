---
type: decided-plan
source_plan: 2026-07-17-ci-artifact-actions-node24-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped CI maintenance work removed GitHub Actions Node 20 deprecation warnings from the release workflow by bumping artifact action pins to Node-24-targeting releases while preserving SHA pinning and version comments. Only `.github/workflows/release.yml` needed changes; `ci.yml` had no artifact actions and remained a documented no-op audit result.

The plan accepted `download-artifact@v8`'s secure `digest-mismatch: error` default because uploads and downloads happen within the same workflow and a mismatch should fail rather than publish corrupted artifacts.

## Implementation Units

* Bump `actions/upload-artifact` in `release.yml` to `v7.0.1` and its resolved SHA
* Bump both `actions/download-artifact` uses in `release.yml` to `v8.0.1` and its resolved SHA
* Preserve SHA-pin plus `# vX.Y.Z` comment convention
* Verify major-version behavior against the single named `dist` artifact downloaded by name
* Confirm `ci.yml` contains no artifact actions

## Key Constraints

* Leave unrelated actions alone because they were already not flagged
* Keep artifact names and workflow contract unchanged
* Do not set `digest-mismatch: warn`; accept the secure error default
* Normal PRs cannot exercise tag-only release workflow, so verification is static plus next-release runtime confirmation
* Rollback is reverting the pin bump

## Rejected Alternatives

* Ignore the warnings until GitHub removes Node 20 — rejected because future runtime removal would break releases
* Update all actions opportunistically — rejected as scope creep because only artifact actions were flagged
* Downgrade digest mismatch to warning — rejected because failing on corrupted or tampered artifacts is desirable
* Add a pytest harness — rejected because the change is CI configuration, not Python behavior

## Review Outcome

Plan review passed with no P0/P1/P2 findings. The only advisory was to consider periodic action-version audits so pinned workflow actions do not drift onto deprecated runtimes again.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-07-17-ci-artifact-actions-node24-plan.md

