---
title: "backlogit features.sizing:true does not guarantee the task WIT defines size/complexity"
date: 2026-09-08
agent: stage
context: harvest / backlog-sizing
tags:
  - backlogit
  - harvest
  - sizing
  - degraded-mode
  - p-012
trigger:
  - "Harvesting tasks and setting structured size/complexity via backlogit update"
  - "Registry advertises features.sizing: true"
---

## Problem

The backlogit registry advertised `features.sizing: true` and `backlogit update` exposed
`--size` / `--complexity` (with `--size-source` / `--size-ruleset-version`). Setting them on a
`task` failed:

```
Error: artifact type "task" does not define a size field: backlogit: validation error
Error: set complexity: ... artifact type "task" does not define a complexity field
```

`features.sizing: true` is a workspace-level capability flag; whether a *specific artifact type*
(here `task`) actually defines the `size`/`complexity` fields is a separate WIT-schema fact. The
two can disagree, and the update help text ("Complexity is task-only planning metadata") can be
misleading for a given workspace's WIT.

## Root cause

The field-definition lives in the workspace WIT/type schema, not in the registry feature flag.
`features.sizing: true` says the tool *supports* sizing; it does not assert that every (or any)
type's schema *declares* the field in this workspace.

## Resolution

1. Do not trust `features.sizing` alone. Before assuming structured sizing, probe once:
   `backlogit update <one-task-id> --size S --size-source agent --size-ruleset-version <v>` and
   read the result. If it validation-errors with "does not define a size field", the type lacks it.
2. Fall back to the two-axis prose contract: embed `Size: <XS|S|M|L|XL> | Complexity:
   <trivial|low|medium|high>` (both enum-validated, never conflated) in the task description, and
   flag the degradation in the Stage/harvest report. This is the same fallback the Stage contract
   prescribes for `features.sizing` absent/false.
3. Do NOT suppress the update's stderr (`*>$null`) during a batch — a suppressed non-zero exit
   hides exactly this validation error and makes a silent no-op look like success. Run visibly or
   check `$LASTEXITCODE`.

## Lesson

Capability flags advertise tool support, not per-type schema. Probe the actual mutation on one
item before batching, and never swallow the exit status of a "field-setting" command — a masked
validation error is indistinguishable from success and leaves the values unrecorded.
