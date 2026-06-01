---
title: "Closure - 005-S CLI and MCP parity"
shipment: "005-S"
branch: "feat/005-cli-mcp-parity"
pr: "12"
merge_commit: "160153ac56851b69dd97c2a07cf1129543ddbdea"
merged_at: "2026-06-01T17:44:35Z"
status: "merged-shipped"
---

## Outcome

Shipment `005-S` is merged and shipped. PR `#12` merged to `main` at
`2026-06-01T17:44:35Z` with merge commit
`160153ac56851b69dd97c2a07cf1129543ddbdea`.

## Final shipped scope

| Change | Surface | Final state |
|---|---|---|
| Stdio-only MCP transport enforcement | `src/docline/mcp/server.py`, `src/docline/mcp/exceptions.py`, `tests/parity/test_mcp_transport.py` | MCP server rejects non-stdio transport values while still accepting string-backed stdio configuration |
| CLI fetch and process adapters | `src/docline/cli.py`, `tests/parity/test_cli_adapters.py` | CLI routes fetch and process through parity-oriented adapters with validated standalone manifest behavior |
| MCP fetch and process adapters | `src/docline/app.py`, `src/docline/app_models.py`, `src/docline/mcp/server.py`, `tests/parity/test_mcp_adapters.py`, `tests/parity/test_app_services.py` | MCP surface exposes fetch and process adapters aligned with the shared application service layer |
| Cross-interface parity verification | `tests/parity/test_manifest_parity.py`, `tests/parity/test_envelope_parity.py`, `tests/parity/test_equivalence.py` | Manifest, envelope, and result equivalence checks guard CLI/MCP behavior parity |

## Review and merge disposition

* Existing Copilot review threads were resolved before merge
* GitHub still showed `REVIEW_REQUIRED` because the latest Copilot review covered stale commit `6d4a7bf4dc348e6587d2e58112916058b04618b7` rather than current HEAD `822280072fa2a58f7deed1e8fcbffb5905ca2a3c`
* Re-requesting Copilot review was unavailable in this environment because `gh pr edit 12 --add-reviewer copilot` returned `'copilot' not found`
* Merge proceeded under the explicit operator-approved administrator-merge override for shipment `005-S`

### Risky action record

* ProposedAction: merge PR `#12` with `--merge --admin`
* ActionRisk: high
* Approval path: explicit operator approval
* ActionResult: applied

## Verification

See the runtime verification report:
[`2026-06-01-005-s-cli-mcp-parity-runtime-verification.md`](2026-06-01-005-s-cli-mcp-parity-runtime-verification.md).

Final gates before closure:

* `python -m py_compile src/docline/__init__.py` -> exit `0`
* `ruff check .` -> passed
* `pyright src/` -> `0` errors
* `pytest` -> `424` collected, exit `0`
* `ruff format --check .` -> passed

## Archival state

* `backlogit shipment ship 005-S --sha 160153ac...` succeeded
* Archived IDs: `005-F`, `005-S`, `005.001-T`, `005.002-T`, `005.003-T`,
  `005.004-T`, `005.005-T`
* `backlogit sync` succeeded after archival

## Operational closure

* Readiness: READY
* Deployment path: merge-only release via `main`
* Validation window: next normal development cycle on `main`
* Owner: operator / repository maintainer
* Monitoring and rollback: rely on the documented quality gates and revert merge commit `160153ac56851b69dd97c2a07cf1129543ddbdea` if CLI/MCP parity regresses
* Closure PR `#13` is open from `post-merge/005-cli-mcp-parity`
* Closure PR Copilot review request via `gh pr edit 13 --add-reviewer copilot` did not succeed in this environment and still requires separate operator approval before merge
* No shipment-local follow-up backlog items were identified during closure

## Knowledge graduation

* The shipped change is implementation-facing and does not require new architecture or design-document updates
* No additional source-artifact cleanup was required for `005-F`
* No `008-S` intake content was incorporated into this closure
