---
title: "Capability-pack overlay prose is woven unconditionally and guarded, not gated at install"
date: 2026-08-31
agent: ship
context: autoharness-harness
tags:
  - autoharness
  - capability-packs
  - overlays
  - merge-install
  - cross-references
trigger:
  - "You find prose for a capability pack that was never installed and want to strip it"
  - "You are asked to remove a capability pack from the installed list"
  - "AGENTS.md references an instruction file that does not exist on disk"
  - "You are adding a capability pack to an existing autoharness installation"
---

## Problem

Two symptoms that look unrelated are actually the same underlying design:

1. `agent-intercom` was never installed in this workspace, yet **133 lines** of intercom
   prose existed across `AGENTS.md`, `copilot-instructions.md`, `_stage`, `_ship`, and
   several skills. It looked like a botched install leaving residue behind.
2. `continuous-learning` and `release-observability` were *also* not installed, yet
   `AGENTS.md` already carried their overlay sections — and those sections
   **cross-referenced instruction files that did not exist on disk**.

## Root cause

The upstream autoharness templates carry the prose for **every** capability pack
regardless of which packs the composition selects. Each block is wrapped in a
conditional guard:

```text
When the workspace enabled the <pack> capability pack:
```

Install-time pack selection controls which **instruction files and skills** get written —
it does not strip guarded prose from the shared foundation templates.

## Resolution

The correct action is opposite in each direction:

* **Pack not installed, prose present** → leave it alone. The guard makes it inert. Stripping
  it flips those artifacts to `user-modified` in the manifest, and the next `tune-harness`
  re-renders from the template and puts it right back. Confirm the guard is present, then
  do nothing.
* **Prose present, instruction file missing** → this is a real defect: a dangling
  cross-reference. Installing the pack repairs it. Verify with a targeted scan that every
  pack referenced in foundation docs has its `.github/instructions/<pack>.instructions.md`
  on disk.

## Lesson

Do not infer installed-pack state from prose presence — read `.autoharness/config.yaml`
`capability_packs` and the manifest's `capability_pack_overlays`, which are the authoritative
records and agree with each other. Guarded prose for an absent pack is expected and harmless;
a *reference* to an absent pack's instruction file is a genuine broken link. Check which of
the two you actually have before editing anything.
