---
type: session-memory
date: 2026-08-28
agent: Stage
session: PR #166 H8 round cycle-3 — Finding A + Finding B closure
head: d402b103986008906ddacc1daf4fb91f0cedae19
branch: chore/stage-055-s
---

# Stage session — PR #166 cycle-16 (Finding A id-less notification + Finding B sitemap CGNAT)

## Objective

Operator-directed FULL Stage pass (planning/backlog/docs only, no production source) closing two
unresolved PR #166 Copilot findings via further decomposition + four-persona adversarial review
instead of an ordinary fourth fix.

## Findings closed

### Finding A — id-less ≠ automatically a notification (thread PRRT_kwDOSsAX4c6dXgJo, comment 3885656380, plan ~L259)

- Established an explicit ORDERING INVARIANT: request-shape validation over `{root, jsonrpc, method,
  id-type}` runs BEFORE the id-absent notification-suppression branch in the single shared `dispatch()`.
  An absent id yields silence ONLY for an OTHERWISE-VALID request (object root, jsonrpc "2.0", present
  non-empty-string method); a malformed id-less payload returns -32600 / id:null, never suppression.
- Correctness-review closure folded in: unified `method` predicate (present+string+non-empty) in both
  the shape guard and notification precondition; id-absence by KEY MEMBERSHIP not truthiness (present
  id:0/id:"" → normal echoed response); -32600 echoes a valid present id on a non-id defect, id:null
  only for absent/malformed/non-finite id; shape-guard field-set locked (params post-suppression);
  array-root → single -32600 (no batching) rationale recorded.
- NO new 064 task: added as parametrized rows to existing scenarios; scenario count stays 3; impl is a
  clause-ordering guarantee in the existing dispatch() guard (≤4-function / <3-file budget intact);
  width isolated. 055-S stays 37 members, order unchanged.

### Finding B — sitemap CGNAT gap had no backlog item (thread PRRT_kwDOSsAX4c6dXgJs, comment 3885656388, plan ~L2722)

- Root cause: `sitemap._is_unsafe_address` (src/docline/fetch/sitemap.py:173-189) rejects via six
  ipaddress flags only; CGNAT 100.64.0.0/10 (RFC 6598) sets none on Python 3.12.x.
- Created REAL queued high-priority security item OUTSIDE 055-S: feature 065-F + red 065.001-T →
  green 065.002-T, new shipment 056-S, related_to 064-F (non-blocking), plan + deliberation docs.
- 055-S does NOT block (Security verdict, independently traced): validate_sitemap_url/_is_unsafe_address
  has ZERO production callers (live crawl path = url_policy.validate_crawl_url; robots uses
  RobotFileParser.can_fetch, never discover_sitemaps_from_robots) → dormant defense-in-depth. §H6
  (in 055-S, touches url_policy.py/http.py) re-implements the classifier with an independent explicit
  CGNAT check → live path CGNAT-complete without the sitemap helper. 055-S scope NOT expanded.
- SSRF classifier drift (Security P3 + Architecture P2): CGNAT literal duplicated across url_policy +
  sitemap post-merge. Coverage matrix recorded in the deliberation; consolidation (Option B) filed as
  stash 87F2C06D (kind=feature, priority=medium). Activation-condition edge on 065-F: any future
  shipment wiring sitemap discovery into the crawl MUST depend on 065-F.

## Adversarial review outcome (4 personas)

- Correctness: reconciliation substantially correct; 2 P2 precision fixes folded in (empty-method
  predicate, id-membership-not-truthiness) + spec advisories.
- Security: VERDICT 055-S MUST NOT block; create separate item (done). Confidence high.
- Scope: no new 064 task necessary (9/10); Finding B red+green + separate shipment correct (8/10);
  055-S isolation verified 37 items (10/10).
- Architecture: 065-F independent of 064-F (9/10, disjoint files, no merge conflict); separate
  shipment 056-S justified (8/10); related_to non-blocking correct (8/10); DAG acyclic; 056-S is the
  correct next shipment id (the review-prompt hypothetical 066-S was never materialized).

## Files touched

- Plan: docs/plans/2026-08-27-mcp-stdio-server-plan.md (dispatch docstring, request-shape section,
  cycle-9 record, Risks Finding-B bullet, top cycle summary, new ### Cycle-16 note)
- Backlog edited: .backlogit/queue/064-F.md, 064.002-T.md, 064.005-T.md, 064.021-T.md
- Backlog new: .backlogit/queue/065-F.md, 065.001-T.md, 065.002-T.md, 056-S.md
- Docs new: docs/plans/2026-08-28-sitemap-cgnat-ssrf-gap-plan.md,
  docs/decisions/2026-08-28-sitemap-cgnat-ssrf-gap-deliberation.md
- Stash: 87F2C06D (SSRF classifier consolidation follow-up)

## Validation

- backlogit sync: 408 artifacts, 0 parse_failures.
- doctor: 168 issues, ALL pre-existing archived_from_self_ref (archive 031-040); none on 064/065/055-S/056-S.
- 065.002-T depends_on 065.001-T (red-before-green); 065-F chain has 0 blocking deps outside itself (acyclic, independent).
- 055-S = 37 members (unchanged order); 056-S = 3 members, parent-first [065-F, 065.001-T, 065.002-T].

## Guardrails honored

- No production source edited. NOT pushed; no PR actions; Ship not invoked; 055-S queued/unclaimed.
- Forbidden files NOT staged/edited: .autoharness/config.yaml, .github/agents/_orchestrator.agent.md,
  .github/agents/_ship.agent.md, .gitignore (carry only pre-existing unstaged changes).

## ActionRisk / ActionResult

- ProposedAction: reconcile plan/backlog/docs for Finding A + create Finding B security work item.
  ActionRisk: low (planning artifacts only, no code, no push). ActionResult: applied (committed;
  not pushed).

## Next steps

- Ship claims 055-S (unchanged, 37 members) and 056-S (sitemap CGNAT) independently.
- Future: harvest stash 87F2C06D (SSRF classifier consolidation) when prioritized.
