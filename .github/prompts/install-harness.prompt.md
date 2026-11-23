---
description: "Install a complete agent harness into a target workspace from the global gsd installation"
agent: Auto-MergeInstall
argument-hint: "workspace=<target-path> [preset=starter|standard|full] [primitives=1,2,3,4,5,6,7,8,9,10] [capability_packs=agent-engram,backlogit,kbdb]"
---

# Install Harness

gsd is installed globally and generates harness artifacts into a target workspace. The target workspace receives only the generated output — not the gsd engine itself.

## Inputs

* ${input:workspace}: (Required in CLI environments, auto-detected in editors) Absolute path to the target workspace.
* ${input:preset}: (Optional) Install preset: `starter`, `standard`, or `full`. Defaults to `standard`.
* ${input:primitives}: (Optional) Comma-separated primitive numbers (1-10) to install. Defaults to the selected preset.
* ${input:capability_packs}: (Optional) Comma-separated external-tool capability packs: `agent-engram`, `backlogit`, `kbdb` (legacy `graphtor-docs` is accepted as an alias for `kbdb`). The former internal packs (`browser-verification`, `continuous-learning`, `strict-safety`, `release-observability`, `adversarial-review`) are part of the core harness install set (including their 5 core instruction files, `.github/agents/subagents/adversarial-review.agent.md`, and all remaining core template skills); passing one logs `FOLDED_CORE_PACK` and is ignored as a capability pack.
