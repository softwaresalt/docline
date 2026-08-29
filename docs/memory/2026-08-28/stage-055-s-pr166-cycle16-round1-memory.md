---
type: session-memory
agent: stage
date: 2026-08-28
shipment: 055-S
feature: 064-F
pr: 166
cycle: cycle-16 round cycle-1
head: 845686a56a47855f564d9b20aa2638ebd9667c32
---

# Stage session — PR #166 cycle-16 round-1 (HEAD 845686a)

Planning/backlog/docs reconciliation only. No production or test source touched. Shipment `055-S`
unchanged at 37 members; no new tasks. Two clusters (four unresolved Copilot findings) closed after a
two-model, multi-persona adversarial review.

## Findings closed

- **H7 byte semantics** — comment 3885775394 on `064.017-T`, comment 3885775424 on `064.016-T`.
  `len(body_bytes)` is not a raw-wire count: `urllib`/`http.client` strips HTTP transfer framing
  (chunk-size lines, trailers) and headers before `HTTPResponse.read()` returns, and does not
  content-decode (`gzip` stays compressed). The budget bounds **entity-body bytes**, not wire bytes.
- **Legacy era routing** — comment 3885775403 on `064.022-T`, comment 3885775415 on `064.021-T`.
  Using per-request `_meta` presence as the era discriminator misroutes retained `2025-11-25` clients
  that carry ancillary `_meta` (e.g. `_meta.progressToken`) to the modern validator and rejects them.

## Decisions and resolution

### Cluster 1 — re-scope to entity-body bytes (simpler reliable option, no wire accounting)

Chose the reviewer's simpler option: re-scope the invariant to **entity-body bytes** (the undecoded
response-content bytes returned by `HTTPResponse.read()`, transfer framing and headers excluded,
before charset decoding). Rationale: the DoS surface is memory + `output_dir` staging, which
entity-body bytes bound; docline cannot count raw wire bytes without a bespoke transport. No new task.

- `body_byte_count` narrowed to completed-terminal-`FetchResponse` observability only (not the
  enforcement source; does not record failed/retried/intermediate responses).
- Softened "crossing byte pulled from the socket" to "`HTTPResponse.read()` returns at most one
  entity-body byte beyond the allowance".
- Kept the non-ASCII/invalid-byte tests; reframed them to prove only that enforcement is below charset
  decoding (resists a decode/re-encode undercount), NOT chunk-framing/header coverage.
- Added an accepted-residual `## Risks` bullet: the budget does not bound headers, transfer framing,
  raw socket bandwidth, parser CPU, or exact post-decode memory/disk.

### Cluster 2 — discriminator = namespaced modern negotiation member

Re-keyed the discriminator to the **presence** (key membership, not truthiness) of a namespaced modern
negotiation member — canonically `io.modelcontextprotocol/protocolVersion`, equivalently
`io.modelcontextprotocol/clientCapabilities` — plus the modern-only `server/discover` rule; otherwise
honor the established per-process legacy latch; reject pre-`initialize`. Precedence: a modern member
wins even after a legacy latch. Keying on either member avoids misrouting a version-less-but-
capabilities-bearing modern request to legacy (both members are modern-namespaced, absent from legacy
clients — no legacy false positive).

- `064.021-T` scenario (b): +3 parametrized rows (count stays 3) — post-init ancillary-`_meta`→legacy;
  pre-init ancillary-`_meta`→reject (not the modern `-32602` path); modern-wins-after-latch.
- `064.020-T` scenario (c): +present-but-malformed-`protocolVersion` axis (member present → modern
  validator → `-32602`/`-32022`, never legacy fallthrough) proving key-membership semantics.
- Green attribution: protocolVersion-keyed discriminator delivered by `064.022-T`; latch-dependent
  rows RED at authoring, green at `064.023-T` (owns the per-process legacy latch).

## Files modified

- `docs/plans/2026-08-27-mcp-stdio-server-plan.md` — §H7 item 3, design summary, Selected numeric
  limits (`MAX_RESPONSE_BYTES` + `MAX_TOTAL_FETCH_BYTES` boundaries), Verification, Rollback, Protocol
  Era Model routing bullet + method-map note, new `## Risks` residual bullet, new cycle-16 round-1
  remediation section.
- `.backlogit/queue/064-F.md` — H7 DoD entity-body qualifier; era-routing DoD discriminator.
- `.backlogit/queue/064.016-T.md`, `064.017-T.md`, `064.024-T.md` — entity-body re-scope.
- `.backlogit/queue/064.020-T.md`, `064.021-T.md`, `064.022-T.md`, `064.023-T.md` — discriminator +
  parametrized rows + green attribution.
- `docs/decisions/2026-08-27-mcp-stdio-server-deliberation.md` — era-routing discriminator.
- `.backlogit/memories.json` — `stage-2026-08-27-darkfactory-stash-sweep` record: `body_byte_count`
  entity-body wording + era-classifier discriminator wording.

## Adversarial outcome

Two models (Claude Opus 4.8 + GPT-5.6 Sol), multi-persona (Correctness, Security, Scope,
Protocol-Compat). Both verdicts: approaches sound, no blocking defects. Folded-in refinements: drop
the "network/real transfer" overclaim; qualify bare "raw" as undecoded; record the entity-body
residual; add the pre-init ancillary-`_meta` reject + modern-wins rows; key on either modern member;
correct green attribution. Confirmed sound: "entity-body bytes" is the correct term; no memory/disk
DoS hole from the re-scope; no new task; `055-S` unchanged.

## Constraints honored

Not pushed; no PR actions; Ship not invoked; `055-S` queued/unclaimed. Production source unchanged.
Did not stage/edit/revert the operator's pre-existing working-tree changes to `.autoharness/config.yaml`,
`.github/agents/_orchestrator.agent.md`, `.github/agents/_ship.agent.md`, or `.gitignore`.

## Next steps

Push the branch and re-run Copilot review on the four threads; expect the entity-body re-scope and the
protocolVersion-keyed discriminator to resolve them. Ship remains the owner of shipment execution.
