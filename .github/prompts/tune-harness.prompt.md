---
description: "Tune an installed agent harness to match current workspace state from the global gsd installation"
agent: Auto-Tune
argument-hint: "workspace=<target-path> [scope=all|instructions|agents|skills|policies|constitution]"
---

# Tune Harness

gsd is installed globally. The tuner reads templates from the global installation and updates only the target workspace's harness artifacts.

## Inputs

* ${input:workspace}: (Required in CLI environments, auto-detected in editors) Absolute path to the target workspace.
* ${input:scope}: (Optional) Scope of tuning: `all`, `instructions`, `agents`, `skills`, `policies`, `constitution`. Defaults to `all`.
