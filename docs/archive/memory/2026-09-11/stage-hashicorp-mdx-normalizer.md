# Stage session memory — HashiCorp MDX normalization preprocessor

- **Session:** stage-hashicorp-mdx-normalizer-2026-09-11
- **Date:** 2026-09-11
- **Agent:** stage
- **Branch:** feat/github-markdown-extension
- **Phase:** complete

## Intake

Operator-delivered feature-shaped request (not a stash entry): build a temporary,
standalone preprocessing script that copies only latest-version HashiCorp products +
unversioned products from the external read-only corpus
`C:\Source\Docs\hashicorp-tf-unified-dev-docs\content`, normalizing `.mdx`→`.md` in-flight,
tested, producing requirements evidence for a future first-class docline MDX feature.

## Containment constraint (session policy)

No session agent writes/modifies/deletes outside `C:\Source\GitHub\docline`. External corpus
is read-only-authorized. `C:\Source\Docs\tf-unified-dev-docs-normalized` MUST NOT be written
this session; operator runs `--execute`.

## Pipeline outcome

- **Tool gate:** ALL_TOOLS_OK (backlogit CLI 1.10.1). INDEX_SYNC_OK. Checkpoints all
  resolved on entry (no recovery). No dark mode.
- **Triage:** feature-shaped; no DEFERRED SCOPE EXPANSION marker; grouping (1.5) skipped.
- **Learnings (1.8):** compound learning `2026-09-09-third-party-api-shape-requires-live-verification`
  applied → mandated full-corpus dry-run cross-check.
- **Deliberation:** `docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md`
  (chose Python semver-port selection + standalone normalization engine, `scripts/` placement).
- **Plan:** `docs/plans/2026-09-11-hashicorp-mdx-normalization-preprocessor-plan.md`
  (Requires plan hardening: yes → hardening section folded in; P-006 satisfied).
- **Plan review:** `docs/plans/...-plan-review.md` — Verdict PASS (attempt 1).
- **Harvest:** feature **071-F** + 11 tasks **071.001-T..071.011-T** (groups A–E), 16
  dependency edges. P-003 chain intact.
- **Sizing degradation:** task WIT defines no structured size/complexity fields (despite
  `features.sizing=true`); recorded size+complexity as labeled prose per degradation policy.
- **Shipment:** **062-S** (queued) — 12 items (071-F + 11 tasks), manifest verified.
- **Stash archival (5.6):** no-op — no stash entries consumed (direct operator intake).

## Handoff to Ship

Claim shipment **062-S**. Build script+tests inside docline, run full-corpus read-only
dry run (zero out-of-repo writes), emit coverage + unhandled-construct report, author
E.T1 evidence doc, document the exact operator `--execute` command. Do NOT run `--execute`
against the external destination.

## Deferred stash (unchanged, not for this session)

D6E758F5 (bug, high), 4C03AE14 (task, low), 6BF410E2, D548B756, DFF8E8E1, EF8503EC,
8E0B4FB5, 0EE542D9 — all belong to 060-S/069-F or 061-S/070-F contexts.
