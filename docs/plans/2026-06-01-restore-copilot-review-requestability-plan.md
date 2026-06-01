---
title: "Plan - Restore Copilot Review Requestability"
stash_id: "4BC95A72"
source: "docs/decisions/2026-06-01-restore-copilot-review-requestability-deliberation.md"
status: approved
requires_plan_hardening: no
---

# Plan: Restore Copilot Review Requestability

## Objective

Enable GitHub Copilot code review for `softwaresalt/docline` so that the Ship
agent's PR automation workflow (§1.1–§1.9) functions without operator overrides.

## Source

* Stash: `4BC95A72`
* Deliberation: `docs/decisions/2026-06-01-restore-copilot-review-requestability-deliberation.md`
* Evidence: `docs/closure/001-S-backlog-artifact-persistence-prerequisite.md` (§ Review and merge disposition)

## Implementation Units

### Task 1: Enable Copilot Review and Verify

**Scope**: Repository configuration (GitHub Settings UI) + live verification

**Steps**:

1. Navigate to `softwaresalt/docline` → Settings → Code review (or equivalent path)
2. Enable Copilot code review for the repository
3. Verify by requesting Copilot review on the next available open PR:
   * `gh pr edit <N> --add-reviewer copilot` should succeed
   * OR use MCP `request_copilot_review` tool
4. Document the configuration as a prerequisite in operational knowledge

**Acceptance Criteria**:

* `gh pr edit <N> --add-reviewer copilot` returns success (exit 0)
* A Copilot review appears on the target PR within 5 minutes
* No `422 not a collaborator` error from the REST API

**Execution posture**: Configuration-first — no test harness needed (no code changes)

**Estimated effort**: < 30 minutes (well within 2-hour rule)

## Dependencies

* None — this is independent of any code shipment
* Can be verified against PR #14 (006-S) which is currently awaiting review

## Risk Assessment

* **Blast radius**: Low — repository settings change only; no code modification
* **Rollback**: Disable the setting if problematic (instant revert)
* **Requires plan hardening**: No — single-step configuration task

## Constitution Check

* Principle VII (Destructive Command Approval): N/A — no destructive commands
* Principle VIII (Safety Modes): Low risk, no elevated safety mode needed
* Principle II (Test-First): N/A — no production code changes
