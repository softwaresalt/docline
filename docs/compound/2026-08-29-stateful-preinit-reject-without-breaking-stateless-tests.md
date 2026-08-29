---
title: "Introducing a stateful pre-init reject without breaking existing stateless tests"
date: 2026-08-29
agent: ship
context: tdd-harness-design
tags:
  - tdd
  - mcp
  - dual-era
  - session-state
  - test-drivers
trigger:
  - "Adding a per-connection latch/handshake requirement to a previously stateless dispatch"
  - "Many existing tests send bare requests that a new pre-init gate would now reject"
  - "A pure dispatch() function must gain optional session state"
---

# Introducing a stateful pre-init reject without breaking existing stateless tests

## Problem

The dual-era MCP work added a per-connection legacy latch: requests lacking a modern `_meta`
member sent **before** an `initialize` handshake must be rejected (`-32600`). But dozens of
existing tests drove bare frames (`ping`, `tools/list`, `tools/call`) through `serve()`/`dispatch()`
with no handshake. A naive implementation would have turned ~15 green tests red at once.

## Resolution — three moves

1. **Optional session, backward-compatible default.** `dispatch(message, server, session=None)`.
   When `session is None` (direct unit calls) default to a **legacy-latched** session so every
   existing direct-`dispatch` test keeps passing. `serve()` creates one **unlatched** `_SessionState`
   per connection, so production enforces the pre-init reject.
2. **Auto-latching test drivers.** The shared serve-driving helpers (`_drive_serve`/`_drive_bytes`)
   prepend a legacy `initialize` frame (id `"__latch__"`) and strip its response, so bare-frame
   tests inherit a latched connection unchanged. Dedicated pre-init reject tests opt out with
   `latch=False`.
3. **Forward-compatible red harness.** Author the red harness before the impl, and reference the
   not-yet-existing `_SessionState`/session param **lazily inside test bodies** (not at module top),
   so the red tests fail individually instead of breaking module collection for the whole suite.

## Lesson

When adding connection state to a previously pure dispatcher: make the state an **optional
parameter with a compatibility default**, push the strict (unlatched) behavior into the real
entry point, and absorb the migration in **shared test drivers** rather than editing every test.
Keep new-symbol references lazy in red harnesses so collection stays green while individual tests
go red.
