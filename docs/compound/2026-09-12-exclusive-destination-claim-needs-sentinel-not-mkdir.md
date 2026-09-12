---
title: "Exclusive destination-claim for CLI tools needs a sentinel file, not mkdir(exist_ok=False)"
date: 2026-09-12
agent: ship
context: cli-tooling
tags:
  - cli-safety
  - mutual-exclusion
  - filesystem-claims
  - destructive-operation-guards
  - review-fix-cycle
trigger:
  - "Designing a CLI tool's mutual-exclusion guard for a shared, operator-specified output destination"
  - "A `--dest`/`--output` guard uses `mkdir(exist_ok=False)` (or similar 'absent-only' directory creation) to detect a concurrent invocation"
  - "An operator reports the documented exact command fails against a destination that legitimately already exists (e.g. from a prior read-only inspection)"
---

## Problem

Shipment 062-S's HashiCorp MDX normalization preprocessor (`scripts/hashicorp_mdx_normalize.py`)
needed a mutual-exclusion guard so two concurrent `--execute` invocations against the same
`--dest` could never interleave writes. The first design used `Path.mkdir(dest, parents=True,
exist_ok=False)` as the claim primitive: if the directory already existed, the `mkdir` call
raised and the invocation aborted, correctly preventing two concurrent claims.

This design was self-consistent, passed all of its own unit tests, and passed local adversarial
review — but it silently assumed `--dest` would always be either fully absent (the common case in
tests and fixtures) or non-empty-and-rejected. In real operator use, the destination had already
been created (empty) by a prior read-only inspection before the operator ran the documented
`--execute` command. `mkdir(exist_ok=False)` unconditionally rejects an *already-existing* empty
directory exactly the same as a concurrently-claimed one — it cannot distinguish "safe to use" from
"already claimed" when the directory pre-exists for any reason. The operator's exact, documented
command failed against their own real destination.

## Root cause

`mkdir(exist_ok=False)` conflates two different questions into one signal: "does this path already
exist" and "is this path currently claimed by another invocation". Existence alone is not evidence
of a live concurrent claim — a destination can pre-exist for entirely benign reasons (an earlier
read-only pass, an operator-created empty scratch directory, a resumed session) while still being
perfectly safe to use.

## Resolution

Replaced the absent-only `mkdir` guard with an **exclusive OS-level sentinel-file claim**:
`os.open(str(sentinel_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)` inside the destination
directory, released via an explicit `os.close()` + delete after the run completes (success or
failure). This separates the two questions cleanly:

* **`--dest` may be absent OR existing-and-empty** — both are accepted; only an existing
  **non-empty**, unclaimed destination is rejected (`EXIT_DEST_NOT_EMPTY`).
* **The sentinel file itself is the sole claim signal** — `O_CREAT | O_EXCL` atomically fails if
  and only if another invocation's sentinel is already present, which is the actual concurrency
  condition the guard exists to detect. Two concurrent claims against the same `--dest` still
  cannot coexist; an existing-empty `--dest` from unrelated prior activity is no longer conflated
  with an active claim.

Two follow-on review findings sharpened the same pattern further and are worth generalizing:

1. **Every path that checks "is this in use" must be claim-aware, not just the claim/release
   pair itself.** A separate destination-emptiness precheck (`_dest_precheck()`) ran *before* the
   claim and was not sentinel-aware, so a destination actively claimed by another live invocation
   was rejected with the generic "not empty" error instead of the specific "already claimed" one.
   Any precheck that runs ahead of the actual claim needs to recognize the claim's own sentinel as
   an expected, non-error condition, or it re-introduces the same conflation the claim was built to
   resolve.
2. **A reserved sentinel filename can collide with an unrelated, operator-controlled output path.**
   This tool also accepts an operator `--report` path; if that path happened to resolve to the
   exact reserved sentinel filename inside `--dest`, it passed containment validation (trivially
   "inside `--dest`") but was silently overwritten/lost by the claim-release cleanup at the end of
   the run — a real, deterministic bug in the new mechanism's own blind spot, not a hypothetical
   edge case. Any newly introduced reserved/internal filename inside a shared operator-writable
   directory needs an explicit collision check against every other operator-supplied path that
   resolves into that same directory, at both the pre-claim and post-write guard points — not just
   a comment asserting the collision "never happens".

## Lesson

When a CLI tool needs a mutual-exclusion guard over a shared filesystem destination, do not use
existence-based directory creation (`mkdir(exist_ok=False)`) as the claim primitive unless the
destination is *guaranteed* to never legitimately pre-exist. Use a dedicated, exclusively-created
sentinel file (`O_CREAT | O_EXCL`) as the sole claim signal instead, so "does the destination
exist" and "is the destination currently claimed" remain two independently answerable questions.
Once such a sentinel is introduced, audit every other code path that (a) runs ahead of the claim
and inspects the same directory, and (b) accepts any other operator-supplied path that could
resolve into that same directory — both are common, easily-missed blind spots for a
newly-introduced reserved name.
