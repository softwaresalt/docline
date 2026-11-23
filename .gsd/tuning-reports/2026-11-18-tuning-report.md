---
type: tuning-report
date: 2026-11-18
analysis_at: "2026-11-18T05:35:14Z"
updated_at: "2026-11-18T08:00:26Z"
status: TUNING_APPLIED_AND_VERIFIED
scope: all
auto_apply: false
gsd_version: "1.6.0"
observed_baseline_head: b6794d9fbe397bc5833f20466464bce518572cba
---

# Harness tuning applied and verified

## Result

**TUNING_APPLIED_AND_VERIFIED.** The operator-approved Phase 4 changes are
applied and Phase 5 verification passes. All work remains **uncommitted** on
`chore/migrate-to-gsd`. No commit, push, PR, branch switch, stash, backlog
migration or application-code change occurred.

The observed baseline revision above is historical, not the commit containing
this report and not a claim of hosted-PR readiness.

| Disposition | Count | Proposal IDs |
|---|---|---|
| Applied | 9 | TUNE-001, TUNE-002, TUNE-003, TUNE-004, TUNE-005, TUNE-007, TUNE-008, TUNE-009, TUNE-012 |
| Deferred | 3 | TUNE-006 by policy; TUNE-011 separate session; TUNE-013 optional |
| Declined | 1 | TUNE-010 duplicate community capability |

Original proposal priorities remain P0=1, P1=6, P2=5, P3=1. These count the
original proposals, not unresolved defects. There are **zero unresolved
blocking findings in the accepted change**.

See [proposals.json](2026-11-18-evidence/proposals.json) for each disposition,
the original issue/action/evidence, approval history and verification outcome.
The original proposal-only report is retained in exact-byte backups.

## Applied changes

| ID | Applied outcome |
|---|---|
| TUNE-001 | Product quality and GSD topology jobs use Windows; metadata-only jobs retain Ubuntu. Pinned Windows GSD/bootstrap verifies executable and bundle hashes before execution, exports PATH and uses explicit Git Bash for the installed topology entrypoint. |
| TUNE-002 | Approved quality commands/probe metadata use `uv run`, including Ship command consistency corrections identified during review. CI and pre-push retain full build evidence, not just compilation smoke checks. |
| TUNE-003 | Python guidance targets the Python 3.12 project environment, pyright and Ruff import rules rather than adding mypy/isort dependencies. |
| TUNE-004 | Installed P-018, Stage recovery, startup, model-routing and required Markdown hardenings are preserved; no blanket re-render. |
| TUNE-005 | Active missing-document/template prerequisites now use installed authorities or self-contained contracts; local taxonomy absence produces `unclassified`, not invented classes. Historical provenance remains historical. |
| TUNE-007 | Profile records Pydantic/custom stdio MCP without unsupported FastAPI or external MCP-SDK claims; parity and runtime validators remain required. |
| TUNE-008 | KBDB remains enabled with provisioned binary/config and accurate degraded-fallback prose; no active corpus/server is claimed. |
| TUNE-009 | Added grounded metadata to the July compound note, linked the later provenance caveat from the August note and repaired the instinct observation pointer. No instinct promotion. |
| TUNE-012 | Manifest KBDB verification prose uses `kbdb`, not the legacy alias. |

TUNE-006 never invokes `backlogit migrate` or writes `.backlogit`.
TUNE-010 installs nothing. TUNE-011 archives nothing. TUNE-013 remains
`deferred-optional`: the expensive job stays Python-only without a new npm
installation on every CI run.

### Windows CI contract

* `expensive` and `topology-check`: `windows-latest`
* `changes` and `ci-gate`: `ubuntu-latest`
* Product steps and GSD bootstrap: explicit PowerShell
* Topology entrypoint: explicit `shell: bash` and
  `bash scripts/ci-topology-check.sh`
* Local execution uses `C:\Program Files\Git\bin\bash.exe`, not WSL Bash
* Existing permissions, immutable action pins, credential handling, aggregation
  and advisory/required topology toggle are preserved

The operator supplied the trusted `v1.6.0` release provenance:
`https://github.com/softwaresalt/GSD/releases/download/v1.6.0`.
The workflow provisions `gsd-windows-amd64.exe` and `gsd-assets.zip` only when
absent, validates the pinned executable/versioned/compatibility bundle bytes,
creates runtime activation metadata when absent and verifies the version.
No release download was performed locally; offline tests used verified copies.

Profile schema 1.1.0 requires `ci.linux_only: true`. It remains a documented
**schema-compatibility sentinel**, not the installed workflow runner policy.
The mixed-runner/bootstrap override is documented for future refreshes.

### Runtime and operator-owned controls

Canonical home resolution selected the workspace-local active bundle
`.gsd/gsd-assets-v1.6.0.zip` through `gsd home`; `GSD_HOME` was unset.
The runtime remains GSD `1.6.0`. No package update or extraction occurred.

Config 1.3.0, profile 1.1.0 and manifest 1.1.0 remain current according to the
native verifier. No migration proposals, unresolved contracts or new-artifact
install candidates remain in its final output.

All explicit model tiers, role routes, escalations, contexts, anchor route,
catalog and bindings are preserved. Startup scripts, Stage recovery,
`.markdownlint.json`, dark-mode prompt and precommit topology hardenings retain
their original bytes. `.gsd/carry-forward.yaml` remains absent and untouched.

## Phase 5 verification

| Check | Result | Evidence |
|---|---|---|
| Required exact-home `verify-workspace --json` | Exit 0 | `final-verifier.json`, `final-verifier-execution.json` |
| Blockers / strict schema blockers / unresolved | 0 / 0 / 0 | Native final verifier |
| Targeted checks | 12/12 `ok: true` | Native `targeted_checks` dictionary |
| Raw-byte manifest checksums | 124/124 `unchanged` | Native `checksum_scan`; no CRLF normalization |
| Warnings / migration proposals | 0 / 0 | Native final verifier |
| `gsd gate line-endings --json` | Exit 0 | Final gate record in `run-validation.json` |
| Markdown lint, all 20 modified live/report Markdown files | Exit 0 | Final execution record in `run-validation.json` |
| Five offline Windows bootstrap cases | All pass; zero network calls | `windows-bootstrap-test-results.json` |
| Git for Windows Bash topology invocation | Exit 0, PASS | `shell-topology-checks.json` |
| PowerShell and Bash syntax checks | Pass | Focused-check records in `run-validation.json` |
| Version-matched profile schema and CI composition | Pass | `ci-profile-checks.json` |

All evidence paths above are under `.gsd/tuning-reports/2026-11-18-evidence/`.
The final verifier stdout is preserved as raw bytes. The earlier failed
post-apply attempt remains historical evidence and is not relabeled successful.

The 12 targeted checks are agent-skill references, backlog registry CLI surface,
backlogit compatibility, capability coordinator, carry-forward configuration,
Copilot focus frontmatter, escalation directive parity, frontmatter conformity,
model-routing escalation and the three pipeline workspace identities.
`native-check-count-proof.json` demonstrates the count; it is separate from the
three schema-contract records.

Application tests/build were not executed as part of this harness-only
verification. No application source or dependency manifest changed. No hosted
GitHub Actions run, browser verification, merge readiness or release closure is
claimed.

## Adversarial Verification

### Reviewer dispatch

The operator-configured routes were used, not inferred parent-model settings.
All reviewers were independent read-only leaf executors.

| Slot | Domain | Model | Initial findings |
|---|---|---|---|
| Anchor | Overlay sanity/correctness | `gpt-6.1-sol`, high | 0 |
| A | Template fidelity | `gemini-4-argon`, high | 2 |
| B | Overlay coherence | `claude-sonnet-5.5`, high | 4 |
| C | Cross-reference integrity | `claude-haiku-5.5`, xhigh | 7 |

Anchor dispatch: **TOOL_OK: anchor-review-model**.
Reviewer B could not execute the bundle CLI in its read/search-only toolset;
template fidelity was independently covered by A and native bundle rendering.
This limitation is recorded, not represented as a successful B-side CLI check.

### Consensus and remediation

The audit covered all 24 modified live artifacts. Confirmed MAJOR findings were
read in the actual files before being classified HIGH and corrected.
Two bounded post-remediation cycles used the same four-model pool, scoped only
to corrected files. The final cycle returned four empty finding arrays.

| Outcome | Reported items |
|---|---|
| Corrected | 9: four MAJOR and five MINOR |
| Open pre-existing MINOR advisories | 4 |
| Unconfirmed observation outside modified scope | 1 |
| Intentional operator-preserved stricter P-018 behavior | 1 |
| Dismissed by schema/count evidence | 2 |

These are 17 reported items including four delta-review observations, not 17
independent root causes. Exact findings, source reviewers, confidence,
same-contract scope decisions and dispositions are in
[adversarial-review.json](2026-11-18-evidence/adversarial-review.json).

Corrections completed the approved contracts only: Ship uv commands and summary
variables, installed Ship/Orchestrator/workflow locators, the accurate intake
item label, a self-contained topology citation and matching local taxonomy/audit
inputs. No new taxonomy classes, policy relaxation or upstream source changes
were introduced.

**Audit result: PASS.** Zero HIGH CRITICAL/MAJOR findings remain in the accepted
change. This is not a claim that every optional/pre-existing observation was
implemented or closed.

### Open advisory observations

* Foundation retrieval summaries could mirror pack exemptions more explicitly
* Condensed AGENTS numbering and constitution enforcement/build-gate summaries
  warrant a separately scoped policy/template consistency decision
* Profile Engram marker provenance still records legacy marker names
* A future `.backlog` migration could revisit its docs-only CI filter

Stage health-check symmetry remains an unconfirmed outside-scope observation;
Stage was explicitly preserved byte-for-byte. The proposed schema-invalid
`markdownlint` pre-push enum addition was dismissed. The stricter local P-018
verdict handling was intentionally retained, not silently weakened.
These observations remain open for operator review; Tune did not close them,
invent backlog tasks or write the forbidden backlog root.

## Recovery and evidence integrity

The earlier offline test mistakenly created hardlinks to release assets,
causing bundle containment failure without changing the pinned bytes.
The operator-approved copy-and-rename swap restored link count 1 for the active
executable, versioned bundle and compatibility bundle with **zero deletions and
zero swap overwrites**. Old linked entries remain preserved under the ignored
test fixture tree. See `link-recovery.json`.

The corrected offline test uses ordinary copies and scoped URL stubs.
Cached/fresh setup and bad-executable, bad-alias and bad-manifest cases all pass.
The executable/bundle digests remain the operator-supplied pinned values.

The newline gate exposed CRLF in generated structured evidence and exact
historical report backups. Evidence was backed up and normalized without
changing JSON payloads; exact historical backups were moved, not rewritten, to
`.gsd/backups/2026-11-18/revision-proposal-20261118T060145Z/`.
PowerShell test-result serialization was corrected to emit LF.
Raw baseline/failure/final verifier captures remain unmodified.

The initial proposal-only verifier automatically wrote 117 staged previews and
reports outside that initial report-only boundary. This was disclosed in the
earlier report. Phase 5 verifier writes are now explicitly authorized and backed
up; staged previews were never copied wholesale over the live hardened harness.

## Backups and changed files

Exact-byte backups remain under `.gsd/backups/2026-11-18/`, including:

* Original affected files, mirrored by relative path
* `verification-resume-072509/` for the blocked checkpoint/staged outputs
* `evidence-line-endings/` and `test-results-newline-fix/`
* `revision-proposal-20261118T060145Z/` for the relocated exact proposal backups
* `review-remediation-0730/` and `review-delta-0744/`

`apply-authorization-backups.json` records the initial backup inventory.
`apply-state.json` lists the 24 modified live files and preserved controls.
`run-validation.json` records the final file/hash inventory, native outcomes,
runtime link counts, reviewer result and proposal consistency checks without
trying to hash itself.

Learning changes remain the bounded two-note/pointer hygiene only. Verifier
learning inputs and prior reports are retained as historical evidence; no weak
instinct was promoted and no dynamic policy was invented.
Compact-context was invoked assessment-only, with all archival deferred under
TUNE-011. KBDB retrieval remains a documented local-fallback limitation.

## Next action

Review the uncommitted diff on `chore/migrate-to-gsd`. No commit, push, PR or
default-branch action is authorized by this completion report.
When the operator chooses a later shipping workflow, preserve the Windows
override, local hardenings and exact-byte backup trail.

Tune again after a major release or architectural change, or on the next
scheduled maintenance pass. GitHub Copilot focus instructions take effect from a
PR's base branch only after merge; the custom-instructions setting remains an
advisory prerequisite, not a local tuning gate.
