---
type: tuning-report
date: 2026-11-18
generated_at: 2026-11-18T00:02:00Z
gsd_version: "1.6.0"
status: PASS_WITH_WARNINGS
---

# GSD Latest-Source Refresh

## Outcome

Updated the existing `chore/migrate-to-gsd` migration with the current GSD
source checkout and activated the resulting workspace-local runtime through
`docline\.gsd\gsd.exe`.

* Active GSD executable: `.gsd/gsd.exe`
* Active bundle: `.gsd/gsd-assets-v1.6.0.zip`
* Bundle SHA-256: `b170652c9d83786cde8e988ef8d4c9cf47fb7039373383645b2a7ad7d053ebc1`
* Manifest: 124 registered artifacts
* Operator `.gsd/config.yaml` content preserved
* `.env.local` and existing startup scripts preserved
* Backups: `.gsd/backups/2026-11-17/latest-refresh/`

## Applied Improvements

The refresh applied the latest rendered agents, instructions, skills, policies,
prompts, registry, workflow, and script changes. It also restored omitted
full-preset core artifacts:

* `browser-verification` instruction and `browser-automation` skill
* `shipment-documentation-audit` instruction
* Evidence Consistency Reviewer
* `grill-me`
* `gsd-dark-mode` skill and prompt
* `gsd-show-dag-queue` skill and prompt
* guarded `create_checkpoint` command in the backlog integration table
* `Auto-MergeInstall` and `Auto-Tune` elective agents
* `install-harness`, `tune-harness`, `verify-harness`, and
  `workspace-discovery` lifecycle skills
* `/install-harness` and `/tune-harness` prompt entry points

Docline-specific hardenings were retained after the render, including P-018
Copilot gate handling, Python instruction references, pack-aware review search,
single-authority checkpoint resumption, and fail-closed local hook behavior.

## Verification

* `gsd verify-workspace --workspace . --gsd-home .\.gsd --json`: exit 0
* Blockers: 0
* Strict schema blockers: 0
* Unresolved placeholders: 0
* Targeted checks: 12/12 passed
* Checksum drift: 0
* `gsd gate line-endings --json`: exit 0
* Refreshed PowerShell syntax: PASS
* Refreshed shell syntax: PASS
* Adversarial re-review: no HIGH target-installation finding remained after
  remediation; upstream-template drift remains advisory because this task
  changed the consuming docline workspace, not the GSD source repository

## External Integration Warning

The preserved operator configuration still enables `kbdb`, but docline has no
KBDB MCP server registered in `.mcp.json` and
`.kbdb/config/sources.yaml` currently contains no indexed sources. The generated
harness therefore documents the fallback path rather than claiming indexed KBDB
retrieval is active. Provisioning that server and corpus is external to this
GSD reinstall and does not block the refreshed harness from passing its gates.
