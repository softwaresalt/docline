---
title: "Closure: 057-S SSRF canonical classifier + sitemap validated-IP pinning"
date: 2026-08-29
shipment: 057-S
feature: 066-F
pr: 173
merge_commit: b89c902460700128fc71b0d33046b1210e2fb5d4
status: closed
---

## Scope delivered

Shipment 057-S closed feature 066-F, consuming stash entries 87F2C06D, 0A56B201, and 0A56B202.

| Task | Width | Commit | Outcome |
|---|---|---|---|
| 066.001-T | tests | `1ea21c9` | Class-parity red harness (observed 8 failures) |
| 066.007-T | config | `33754b2` | `requires-python >= 3.12.4` + regenerated `uv.lock` |
| 066.002-T | src | `62dfbcd` | Consolidated onto one canonical predicate; added `fec0::/10` |
| 066.003-T | tests | `b7ea8a4` | Metadata-gate red harness (observed 9 failures) |
| 066.004-T | src | `39f9e7e` | Metadata IPs compared post parse + normalization |
| 066.005-T | tests | `f355b07` | Pinned-sink red harness (observed 11 failures) |
| 066.006-T | src | `9fa95a0` | `fetch_sitemap` routes through the pinned HTTP sink |

Review-driven follow-ups on the same branch:

| Commit | Origin | Change |
|---|---|---|
| `a654ffd` | Correctness reviewer P1 | `is_private_host` delegates to the canonical predicate; dropped redundant `sitemap.__all__` re-export |
| `d78aca9` | Copilot review | Red harness for preflight event-loop and deadline invariants |
| `ee4f6d4` | Copilot review | Preflight runs off the event loop, bounded by and charged against `timeout_seconds` |
| `3007afd` | Copilot review | Repaired duplicated docstring block; trimmed the hanging-resolver sleep |

## Security outcome

The three defects that motivated the shipment are closed:

* **87F2C06D** — one canonical classifier. `sitemap` owns no predicate; `is_private_host` no
  longer holds a third divergent copy. Drift on this predicate is now structurally impossible
  without deleting the delegation-identity test.
* **0A56B202** — metadata membership compares parsed `ipaddress` objects after IPv4-mapped
  normalization, so `::ffff:169.254.169.254` and expanded/uppercase IPv6 spellings hit the gate.
* **0A56B201** — `fetch_sitemap` is the single authoritative retrieval path. The
  validate-then-return-hostname window is gone; `validate_sitemap_url` is documented as a
  non-authoritative preflight.

The CVE-2024-4032 mitigation is the runtime floor, not a wholesale prefix reject, so the
documented globally-reachable exceptions stay reachable.

## Adversarial review

Four reviewers on diverse models. No P0. One P1 (third divergent classifier in
`is_private_host`) found by the Correctness reviewer and fixed in `a654ffd`. Architecture and
Scope independently converged on the `__all__` re-export, fixed in the same commit. Copilot
raised three further valid findings across three review cycles, all fixed and each thread
resolved after a reply carrying the fix SHA.

## Runtime verification (post-merge, on `b89c902`)

Executed against merged `origin/main`:

```text
runtime python 3.12.10, floor satisfied (>= 3.12.4)

rejected classes    private, loopback, link-local, multicast, reserved, unspecified,
                    CGNAT, ULA, site-local fec0::/10, metadata v4/v6/mapped,
                    unparseable  -> all unsafe=True
over-block guard    192.0.0.9, 192.0.0.10, 2001:1::1, 2001:1::2, 2001:3::1,
                    2001:4:112::1, 2001:20::1, 2001:30::1 -> all unsafe=False
delegation          sitemap.is_unsafe_resolved_address is url_policy's  -> True
duplicates removed  _is_unsafe_address/_METADATA_IPS/_CGNAT_NETWORK      -> absent
is_private_host     fec0::1 -> True, 100.64.0.1 -> True

TOCTOU rebinding    public at validation, private at connect -> CrawlUrlRejectedError
connections opened  [] (none)
preflight deadline  0.52s against a 0.5s budget with a hanging resolver
fetch_sitemap in __all__ -> True
```

## Gates

`ruff check`, `pyright src/`, `pytest` (1978 passed, 17 skipped), `ruff format --check`,
`python -m build`, and `uv lock --check` all clean locally; all seven CI jobs green on the
merged HEAD.

## Risk record

Per `.github/instructions/strict-safety.instructions.md`.

### ProposedAction

* **summary** — Consolidate SSRF unsafe-address classification onto a single canonical predicate,
  fix the cloud-metadata membership gate to compare parsed addresses after normalization, and
  close the sitemap validate-then-return-hostname TOCTOU by routing retrieval through the
  address-pinned HTTP sink. Raise the interpreter floor so the corrected CPython `ipaddress`
  tables back the flag checks.
* **targets** —
  * `src/docline/fetch/url_policy.py` (canonical classifier, metadata set, `is_private_host`)
  * `src/docline/fetch/sitemap.py` (duplicate predicate removed, `fetch_sitemap` added)
  * `tests/fetch/` (three new harness modules, one existing module repointed)
  * `pyproject.toml`, `uv.lock` (runtime floor)
  * Runtime surface: the outbound fetch path used by crawl and sitemap retrieval.
* **change_kind** — local edit to a security boundary, plus a config change (dependency-resolution
  floor). No migration, no data change, no rollout or external call.
* **rollback** — revert merge commit `b89c902`. Single-domain, no data or config migration, and
  the live crawl path is behavior-preserving, so revert risk is low.
* **approval_required** — yes. Two gates applied:
  1. *Merge approval* — the operator granted merge approval for 057-S in the dispatching
     instruction, scoped to this shipment.
  2. *Merge-strategy compliance* — verified before merging that the repository permits merge
     commits only (`allow_merge_commit: true`, `allow_squash_merge: false`,
     `allow_rebase_merge: false`), satisfying Principle XI / P-009.

### ActionRisk

**high** — security boundary on a fail-closed SSRF classifier. Not `destructive`: no deletion of
data or config, and the change is revertible by a single commit revert.

### ActionResult

**applied.** Merged as merge commit `b89c902` after four-persona adversarial review (no P0; one P1
fixed in `a654ffd`), three Copilot review cycles with every thread resolved, all local gates and
7/7 CI jobs green, and post-merge runtime verification of the class table, the CVE over-block
guard, rebinding rejection, and the preflight deadline. Approval evidence: operator merge grant
plus the pre-merge repository merge-strategy check recorded above.

### Approval path evidence

| Gate | Evidence |
|---|---|
| Adversarial review | 4 reviewers, diverse models; no P0; P1 fixed in `a654ffd` |
| Bot review | 3 Copilot cycles on PR #173; final review covers HEAD `3007afd`; 3/3 threads resolved |
| CI | 7/7 jobs green on the merged HEAD |
| Merge strategy | Verified merge-commit-only before merging (P-009) |
| Operator | Merge approval granted for 057-S; 058-S explicitly not claimed |

## Follow-up debt

* The Security reviewer noted a P3 advisory: `fetch_sitemap` resolves twice (advisory preflight
  plus the authoritative resolve inside `fetch_page`). Not a TOCTOU — the second resolution is
  the one that pins — but it doubles resolver load per call. The Architecture reviewer raised
  the same point as P2, suggesting the preflight be reduced to scheme/host/IP-literal checks
  with resolution left solely to `fetch_page`. Worth a future stash entry; deliberately not
  actioned here to hold shipment scope.
* The pre-existing YAGNI debt stands: `validate_sitemap_url` still has no live `src/` callers.
  The harness pins the invariant so a future wiring inherits it.
