---
description: "Autoharness 1.6.0 tuning report and multi-model adversarial verification for docline"
recorded_at: "2026-10-26T00:00:01Z"
autoharness_version: "1.6.0"
---

# Harness Tuning Report — 2026-10-26

## Drift Summary

* Breaking changes: 2 (`_ship.agent.md` unresolved `{{VARIABLE}}` placeholder on re-render; erroneously registered `.github/policies/policy-proposal.md` with 13 unresolved placeholders)
* Degrading changes: 45 (3 schema-contract upgrades, 1 retired `agent-intercom` profile cleanup, 18 skill frontmatter `name:` backfills, 20 agent/subagent `model_routing` + `context_tier` frontmatter refreshes, 1 `backlog-registry.yaml` hook CLI surface update, 2 `ambiguous` startup-script manual-review proposals)
* Growth opportunities: 2 (`file-lock` realpath containment + capability-token ownership upgrade; `compound-refresh` hygiene candidates)
* Cosmetic adjustments: 1 (`ci.yml` and `workspace-profile.yaml` pinned `autoharness==1.6.0` alignment)

## Composition

* Installed primary stack pack: `mcp-server`
* Current primary stack pack: `mcp-server`
* Installed stack packs: `["cli-tool", "mcp-server"]`
* Current stack packs: `["cli-tool", "mcp-server"]`
* Installed layers: `["foundation", "instructions", "workflow", "review", "runtime", "backlog", "knowledge", "overlays"]`
* Recommended layers: `["foundation", "instructions", "workflow", "review", "runtime", "backlog", "knowledge", "overlays"]`
* Enabled capability packs: `["agent-engram", "backlogit", "strict-safety", "graphtor-docs", "adversarial-review", "continuous-learning", "release-observability"]`

## Checksum Scan

* Checked manifest artifacts (initial): 110
* Missing installed artifacts: 0
* User-modified artifacts (initial): 19 (`.autoharness/config.yaml` operator model-routing update + 18 artifacts hardened during PR #181 review-fix commits `fe93b3a..e789f60`)
* Ignored artifacts: 0
* Post-tune manifest artifacts: 109 (107 `unchanged`, 2 `user-modified` / `ambiguous` startup scripts `start.ps1` and `start.sh` intentionally preserved for operator review)

## Learning Signals

* Compound patterns detected: 1 (`backlogit` shipment-closure, worktree, and CLI fallback cluster across 8 entries in `docs/compound/`, now codified in 1.6.0 `shipment-reconcile`, `backlogit.instructions.md`, and `backlog-registry.yaml`; 2 entries flagged as `compound-refresh` hygiene candidates: `2026-07-17-backlogit-ship-gate-needs-active-to-done.md` missing YAML frontmatter and `2026-08-30-ship-shipment-deadlocks-in-worktree.md` superseded by `2026-09-09-shipment-ship-primary-workspace-vs-safe-close-fallback.md`)
* Promotion-ready instincts: 0 (3 candidate instincts in `.autoharness/continuous-learning/instincts/2026-09-09-060-s-instincts.md` each at `evidence_count: 1`, below `promotion_threshold: 3`)
* Recurring closure findings: 0 (` operational-closure/SKILL.md` upgraded to the canonical `docs/closure/{shipment_id}-{feature_id}-post-merge-closure.md` contract)
* Policy-gap candidates detected: 0
* Learning-driven proposals generated: 1 (`TUNE-010`, advisory `compound-refresh` pass)

## Proposed Changes (Ordered by Priority)

### P0 — Breaking

1. **[TUNE-001]** (`source: structural-drift`, `status: applied`) — Deregister `.github/policies/policy-proposal.md` from `harness-manifest.yaml` `artifacts[]` and wrap its template example in a fenced code block so `verify-workspace` and template-variable sweeps observe zero unresolved `{{...}}` placeholders.
2. **[TUNE-002]** (`source: structural-drift`, `status: applied`) — Bind `VARIABLE: "<VARIABLE>"` in `harness-manifest.yaml` `variables_used` so `.github/agents/_ship.agent.md` renders with zero unresolved `{{VARIABLE}}` placeholders.

### P1 — Degrading

1. **[TUNE-003]** (`source: schema-contract`, `proposal_id: upgrade-config-contract-1.1.0-to-1.2.0` / `1.2.0-to-1.3.0`, `status: applied`) — Upgrade `.autoharness/config.yaml` from `schema_version: "1.1.0"` to `"1.3.0"`, preserve operator `model_routing` edits (`claude-haiku-5.5`, `claude-sonnet-5.5`, `gemini-4-argon`, `gpt-6.1-sol`, `context_tier: "long_context"`), add `stage.escalation` (`gpt-6.1-sol` / `openai` / `high` / `long_context`) to resolve `ESCALATION_DEGRADED` same-route collision with `stage`, and add empty `escalation`, `routes: {}`, and `bindings: {}` blocks.
2. **[TUNE-004]** (`source: schema-contract`, `proposal_id: upgrade-profile-contract-1.0.0-to-1.1.0` & `remove-retired-capability-pack`, `status: applied`) — Upgrade `.autoharness/workspace-profile.yaml` from `schema_version: "1.0.0"` to `"1.1.0"`, remove the retired `agent_intercom` block, update `ci.autoharness_install_command` to `pip install autoharness==1.6.0`, and record `drift_report`.
3. **[TUNE-005]** (`source: schema-contract`, `proposal_id: upgrade-manifest-contract-1.0.0-to-1.1.0`, `status: applied`) — Upgrade `.autoharness/harness-manifest.yaml` from `schema_version: "1.0.0"` to `"1.1.0"` and `autoharness_version: "1.6.0"`, sync authoritative route variables, and refresh artifact checksums.
4. **[TUNE-006]** (`source: schema-contract`, `contract: frontmatter-conformity`, `status: applied`) — Re-render 18 skill files under `.github/skills/*/SKILL.md` from 1.6.0 templates to add required `name:` frontmatter keys and 1.6.0 protocol updates (including `operational-closure` source artifact cleanup and `pr-lifecycle` session-output reports while preserving PR #181 `MD025` and `iterative-experiment` enhancements).
5. **[TUNE-007]** (`source: schema-contract`, `contract: model-routing`, `status: applied`) — Refresh `model_family`, `model_provider`, `reasoning_effort`, and `context_tier` frontmatter across all 3 pipeline agents (`_orchestrator`, `_stage`, `_ship`) and all 17 subagents under `.github/agents/subagents/`, plus 1.6.0 `context_tier` invocation routing, H6/H7 reload propagation, and portability fixes.
6. **[TUNE-008]** (`source: structural-drift`, `status: applied`) — Upgrade `.autoharness/backlog-registry.yaml`, `.github/policies/workflow-policies.md`, `AGENTS.md`, `.github/copilot-instructions.md`, and `.github/instructions/*` to 1.6.0 templates (adding `poll_hook_events`/`ack_hook_events` CLI commands, `Dark Factory Visibility Protocol`, P-018 threadless review-body finding disposition, and UTC timestamp rules while preserving PR #181 `applyTo: '**'` fixes).
7. **[TUNE-009]** (`source: schema-contract`, `proposal_id: review-startup-script-ps1-contract` & `review-startup-script-sh-contract`, `status: deferred-manual-review`) — `start.ps1` and `start.sh` are classified as `ambiguous` (`manual_review: true`) because PR #181 (`079d937`) added executable validation (`Get-Command $copilotExe`) and bash 3.2 empty-array expansion (`${copilot_arguments[@]+"${copilot_arguments[@]}"}`) to the core block while 1.6.0 templates added `Set-Location -LiteralPath $PSScriptRoot` / `cd "$script_dir"`. Per `tune-harness` Phase 4.1, `ambiguous` startup scripts are not auto-overwritten and remain surfaced for operator review.

### P2 — Growth

1. **[TUNE-010]** (`source: structural-drift`, `status: applied`) — Upgrade `scripts/acquire_lock.ps1`, `scripts/acquire_lock.sh`, `scripts/release_lock.ps1`, and `scripts/release_lock.sh` to the 1.6.0 realpath containment and capability-token ownership implementation matching `.github/skills/file-lock/SKILL.md` and `.github/instructions/concurrency.instructions.md`.
2. **[TUNE-011]** (`source: learning-driven`, `status: advisory`) — Optional `compound-refresh` follow-up to add YAML frontmatter to `docs/compound/2026-07-17-backlogit-ship-gate-needs-active-to-done.md` and link `docs/compound/2026-08-30-ship-shipment-deadlocks-in-worktree.md` to `2026-09-09-shipment-ship-primary-workspace-vs-safe-close-fallback.md`.

### P3 — Cosmetic

1. **[TUNE-012]** (`source: structural-drift`, `status: applied`) — Update `.github/workflows/ci.yml` `topology-check` job pin from `pip install autoharness==1.5.0` to `pip install autoharness==1.6.0` (verified via `uv run pytest tests/test_ci_workflow_lint.py`, 13/13 passing).

## Adversarial Verification

### Reviewer Dispatch

* Anchor Reviewer (`model_routing.anchor_review`: `openai` / `gpt-6.1-sol`, `high`, `TOOL_OK: anchor-review-model`) — 1 finding
* Reviewer A (Template Fidelity: `google` / `gemini-4-argon`, `high`, `long_context`) — 0 findings
* Reviewer B (Overlay Coherence: `anthropic` / `claude-sonnet-5.5`, `high`, `long_context`) — 2 findings
* Reviewer C (Cross-Reference Integrity: `anthropic` / `claude-haiku-5.5`, `xhigh`, `long_context`) — 4 findings

### Consensus Findings (Ordered by Confidence x Severity)

| # | Confidence | Severity | Domain | File | Issue | Status |
|---|---|---|---|---|---|---|
| 1 | HIGH | MAJOR | `overlay-coherence` | `.github/agents/_ship.agent.md` | Step 4.4 stated `adversarial-review` runs in place of standard review, contradicting `adversarial-review.instructions.md` (run standard review first, escalate and merge findings) | AUTO-FIXED |
| 2 | HIGH | MAJOR | `cross-reference` | `.github/skills/pr-lifecycle/SKILL.md` | Step 2b and Step 5a listed only 4 gate checks and omitted Check 5 (`autoharness gate copilot-review`, P-018 fail-closed gate) | AUTO-FIXED |
| 3 | HIGH | MINOR | `overlay-coherence` | `.github/copilot-instructions.md` | `backlogit` and `continuous-learning` sections omitted `follow .github/instructions/<pack>.instructions.md` pointers | AUTO-FIXED |
| 4 | HIGH | MINOR | `overlay-coherence` | `.github/skills/{observe,learn,evolve}/SKILL.md` | Skills omitted explicit pointer to `.github/instructions/continuous-learning.instructions.md` | AUTO-FIXED |
| 5 | HIGH | MINOR | `cross-reference` | `AGENTS.md` | Development Workflow item 4 listed P-001/P-009/P-014/P-016/P-020 without P-018 | AUTO-FIXED |
| 6 | HIGH | MINOR | `cross-reference` | `.github/policies/workflow-policies.md` | Header version declared `1.0.0` while changelog latest version is `1.39.0` | AUTO-FIXED |
| 7 | MEDIUM | MINOR | `cross-reference` | `.github/prompts/feature-flow-dark.prompt.md` | Step 1 mentions pre-activation `DARK_MODE_PREFLIGHT_BLOCKED` halt token not separately tabulated in `workflow-policies.md` P-017 post-activation visibility table (`auto_fixable: false`) | NEEDS REVIEW |

### Auto-Remediation Summary

* Findings auto-fixed: 6
* Findings requiring manual review: 1 (plus 2 deferred `ambiguous` startup-script contract proposals `start.ps1` and `start.sh`)
* False positives dismissed: 0

### Verification Result: PASS WITH WARNINGS

All deterministic checks (`autoharness verify-workspace` exit code 0: 0 strict schema blockers, 0 blockers, 0 warnings, 0 unresolved placeholders, 62/62 targeted checks PASS) and all HIGH-confidence adversarial findings are resolved.

## Recommendation and Branch Safety Guidance

All pre-modification originals are backed up under `.autoharness/backups/2026-10-26/`. Because the workspace is currently on the default branch (`main`), tune changes have been applied as local uncommitted changes only (never commit or push directly to `main`). To land these updates:

1. Create and switch to a feature branch: `git switch -c chore/autoharness-tune-2026-10-26`
2. Review `git diff` (and optionally merge `Set-Location -LiteralPath $PSScriptRoot` / `cd "$script_dir"` into `start.ps1` and `start.sh` if desired, then refresh their manifest checksums)
3. Open a pull request targeting `main`
