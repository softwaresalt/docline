---
title: "Deliberation - Restore Copilot Review Requestability"
stash_id: "4BC95A72"
kind: chore
status: decided
decided_at: "2026-06-01"
---

# Deliberation: Restore Copilot Review Requestability

## Problem Statement

Since shipment 001-S (PR #2), Copilot review requests have failed with:

* `gh pr edit <N> --add-reviewer copilot` → `'copilot' not found`
* REST API request for `copilot-pull-request-reviewer` → `422 not a collaborator`

This means the `github-pr-automation.instructions.md` §1.1–§1.9 defense-in-depth
review workflow cannot function. Every subsequent shipment has merged either with
a stale Copilot review or under operator override.

## Root Cause Analysis

GitHub Copilot code review must be explicitly enabled per-repository. When the
feature is not enabled or the bot is not added as a collaborator/reviewer, review
requests fail. The repository `softwaresalt/docline` does not currently have the
Copilot reviewer bot configured.

## Options

### Option A: Enable GitHub Copilot Code Review (Recommended)

1. Navigate to repository Settings → Code review → Copilot
2. Enable "Copilot code review" for the repository
3. Verify by requesting a review on an open PR

**Pros**: Restores the full automated review pipeline; zero code changes required.
**Cons**: Requires repository admin access; operator action.

### Option B: Remove Copilot Review Dependency

Remove Copilot review from the automation workflow and rely on manual review only.

**Pros**: No external configuration dependency.
**Cons**: Loses automated review coverage; violates the intent of §1.9 defense-in-depth.

## Decision

**Option A selected.** The Copilot reviewer is a core part of the PR automation
pipeline. Restoring it is a repository configuration task — no source code changes
needed. A verification task will confirm the fix works on the next PR.

## Covering Chore Scope

* Enable Copilot code review in repository settings
* Verify requestability on a live PR (can use the next shipment's PR or a test PR)
* Document the configuration requirement in the repository knowledge base

## Out of Scope

* Changing the `github-pr-automation.instructions.md` workflow
* Modifying Ship agent behavior — the instructions already handle the timeout/halt case
