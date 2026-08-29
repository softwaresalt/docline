---
type: session-memory
date: 2026-07-04
agent: orchestrator (Stage + Ship inline)
shipment: 049-S
feature: 047-F
---

# Session memory — 049-S CI cost reduction

## Outcome

Staged and shipped feature `047-F` (shipment `049-S`): cost guards for
`.github/workflows/ci.yml` — harvested from the operator's `3CFD945D` stash.

## Task completed

- `047.001-T` — `paths-ignore` (restore-ready) + PR-title `if:` guards on
  `test`/`build` + an always-reporting `ci-gate` aggregate job. Merge SHA
  `cd56682` (PR #130).

## Key decision / review learning

- Job-level `if:` skips report "skipped", which a **required** branch-protection
  check treats as not-successful → would block `chore:`/`docs:` PRs. Fixed with a
  `ci-gate` aggregate job (`if: always()`, `needs` all jobs) that always reports;
  require it instead of the guarded jobs. (Copilot review catch on PR #130.)
- Ops/config work is verified by YAML validity + workflow conventions, not
  red-green TDD.

## Session context

- This closes a long multi-shipment session: 044-S closure, 045-S, 046-S, the
  agent model-routing tune, 047-S (graphtor spike + canonical_url v1), the
  canonical_url v2 arc (045-F spike → learnings → plan → adversarial review →
  046-F/048-S), and 049-S (this).
- **backlogit MCP was down the entire session** ("Transport closed"); every
  backlog op used the CLI (`C:\Tools\backlogit.exe`). A daemon restart before the
  next session would restore MCP.
- `read_powershell` tool unavailable — long commands redirected output to files.

## Open / next

- Deferred canonical_url v2 follow-ups: nosql `~/`-breadcrumb fallback,
  redirect-map emission (graphtor contract), monikers.
- graphtor Option B feature spec handed to the graphtor agent.
- Parked `.gitignore`/`uv.lock` still uncommitted per operator.
- Non-Mistral stash remainder: `A3E6D72C`, `4CB606D5`, `3048007A`, `935F2694`,
  `7AA9FAA0`, `F8E142A1`. Mistral (`E32FAF6F`, `F4167E69`, `B26003B0`) blocked on
  Foundry.
