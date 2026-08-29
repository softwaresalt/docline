---
type: decided-plan
source_plan: 2026-06-01-restore-copilot-review-requestability-plan.md
consolidated_at: 2026-08-29
status: shipped
---

## Decision Summary

The shipped operational task enabled GitHub Copilot code review for `softwaresalt/docline` so Ship's PR automation could request, poll, and gate Copilot reviews without manual override. The work was configuration-first and intentionally involved no repository code changes.

Verification required a successful Copilot review request on an open PR, a submitted review appearing within the expected window, and elimination of the previous `422 not a collaborator` failure.

## Implementation Units

* Enable Copilot code review in the repository settings
* Verify `gh pr edit <N> --add-reviewer copilot` or MCP review request succeeds
* Confirm a Copilot review appears on the target PR within five minutes
* Record the configuration as an operational prerequisite

## Key Constraints

* No code, schema, or test harness changes
* Low blast radius repository setting only
* Rollback is disabling the setting
* Independent of other shipments and safe to verify against an existing PR

## Rejected Alternatives

* Continue with operator overrides — leaves the automated PR lifecycle below its intended gate standard
* Treat as a code fix — the failure was repository configuration, not application logic
* Add a local test harness — no importable code path changed

## Review Outcome

No appended plan-review findings were present in the source. The plan was accepted as a low-risk operational prerequisite with no hardening requirement.

## Traceability

Full deliberation history archived at docs/archive/plans/2026-06-01-restore-copilot-review-requestability-plan.md

