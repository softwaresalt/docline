---
type: session-memory
date: 2026-08-31
agent: ship
context: autoharness v1.5.0 merge-install
pr: 181
merge_commit: acec71acd0d9003b641d4f1bd5bfbcd83b5c4d1e
status: shipped
---

# autoharness v1.5.0 merge-install — session memory

## Outcome

PR #181 merged to `main` as merge commit `acec71a` (P-009 verified: 2 parents, all 7
branch commits preserved individually — no squash, no rebase).

## Commits shipped

| Commit | Content |
|---|---|
| `a6342b5` | Preserve operator's pre-install edits as a baseline before any harness write |
| `60854bc` | autoharness v1.0.0 → v1.5.0 merge-install (99 artifacts) |
| `fe93b3a` | `feature-flow-dark.prompt.md` under explicit P-017 operator opt-in (→103) |
| `079d937` | 14 round-1 Copilot review fixes |
| `dea1db4` | 13 round-2 fixes (1 declined with schema evidence) |
| `e789f60` | 2 round-3 fixes — PowerShell hooks fail-closed on repo-root discovery |
| `c910478` | Enable `continuous-learning` + `release-observability` packs (→108) |

## Final harness state

* **108 artifacts**, install preset `full`, autoharness **1.5.0**
* **7 capability packs**: `agent-engram`, `backlogit`, `strict-safety`, `graphtor-docs`,
  `adversarial-review`, `continuous-learning`, `release-observability`
  * plus the `capability-pack-enforcement` coordinator (auto-installed because two
    retrieval-enforced packs are active)
  * `browser-verification` explicitly declined by the operator
  * `agent-intercom` not installed (opt-in add-on; never a preset default in v1.5.0)
* `verify-workspace` on merged `main`: **0 blockers, 0 strict schema blockers**

## Decisions and rationale

* **Left residual `agent-intercom` prose in place.** 133 guarded lines exist across foundation
  docs and agents. The guards make them inert, and stripping them would flip artifacts to
  `user-modified` and be reverted by the next tune. See the compound learning on guarded
  overlay prose.
* **Left `config.yaml` / `workspace-profile.yaml` manifest checksums stale.** Probed and proved
  their `user-modified` status predates this session (already drifted at `e789f60`).
  Re-baselining would strip the protection guarding the operator's model-routing
  customizations.
* **Left edited artifacts as `user-modified` deliberately.** That status is what stops a future
  `tune-harness` from silently reverting the review fixes.
* **Declined 2 of 30 Copilot findings**, each with empirical evidence rather than opinion
  (see "Verification-first" below).
* **Restored `"MD025": true`** in `.markdownlint.json` — the merge-install had weakened it,
  which was my own regression against the operator's baseline.

## Verification-first discipline — four errors caught

Every claim was proven before acting on it. This caught two bad review findings and two of
my own wrong assumptions:

1. **Round-1 #2** (`release_lock.ps1` symlink concern) — disproved with a symlink probe: the
   OS resolves symlinks during path lookup, so lexical and physical paths reach the same
   inode. Reported as *declined*, not as a fix.
2. **Round-2 #9** (add the topology gate to `pre_push_gates`) — applying it produced a hard
   schema blocker: that field is enum-restricted to
   `['test','lint','format','typecheck','build']`. Reverted and declined with the schema as
   evidence.
3. **My CRLF assumption** — probing proved installed artifacts are LF and manifest checksums
   are raw-byte hashes. Caught pre-write; would otherwise have produced 5 wrong checksums.
4. **My manifest-key assumption** — the `verify-workspace` JSON uses `unresolved` /
   `warning_instances` / `checksum_scan`, not the names I first guessed. The initial probe
   returned misleading zeros.

## Review cycle

Rounds 1–3 produced 30 threads (28 fixed, 2 declined with evidence). Rounds 4 and 5 returned
**zero new findings**. All 30 threads replied to and resolved programmatically via
`gh api graphql`. §1.9 pre-merge gate: all 3 checks PASS on final HEAD `c910478`. CI 8/8 green.

## Environment gotchas worth remembering

* `ruff` / `pytest` are not on PATH — use `.\.venv\Scripts\`. `uv run` fails here with a TLS
  `HandshakeFailure` to `files.pythonhosted.org`. `pyright` is CI-only.
* Inline `python -c` with nested quotes breaks in PowerShell, and PowerShell has no heredoc —
  always write a real `.py` file. `.autoharness/staging/` is gitignored, so probe scripts
  there never dirty the tree.
* `bash` is WSL: needs `/mnt/c/...` paths, and repo `.sh` files are CRLF.
* Copilot's GraphQL login is `copilot-pull-request-reviewer` (**no** `[bot]` suffix); the REST
  API uses the `[bot]` form.
* Git hooks are P-019 opt-in — scripts ship to `scripts/` but nothing is wired into
  `.git/hooks`, so they never block a commit unless the operator installs them.

## Known residuals (accepted, out of scope)

* 10 pre-existing MD041 violations in upstream skill templates. The 3 new skills match the
  identical pattern found in **14 of 25** already-installed skills — template-consistent, not
  a regression. Repo-wide markdownlint is not run in CI.
* 2 benign portability warnings in `_orchestrator.agent.md`.
* 14 known unresolved placeholders; 1 skipped artifact (`workspace-profile.yaml`, generated
  rather than template-rendered).
* 2 `ambiguous` migration proposals for `start.ps1` / `start.sh` — the verifier deliberately
  downgraded these to avoid discarding unrecognized core-content edits on refresh.

## Next steps

* Branch `chore/autoharness-merge-install-2026-08-31` still exists on the remote; delete it
  when convenient (left in place rather than auto-deleting).
* Consider wiring the opt-in pre-commit / pre-push hooks via a single dispatcher if local
  gating is wanted — the harness ships both markdownlint and pipeline-topology hooks that
  must be chained rather than overwrite one another.
* The upstream MD041 skill-template defect is worth reporting to autoharness rather than
  patching downstream.
