---
title: "Source-key credential sanitization on ELT error/persistence paths"
date: 2026-09-12
agent: stage
kind: implementation-plan
source: docs/decisions/2026-09-12-source-key-credential-sanitization.md
stash_id: D6E758F5
covering_release_unit: chore
revision: R2
---

# Implementation Plan: Source-key credential sanitization (stash D6E758F5)

Source document: `docs/decisions/2026-09-12-source-key-credential-sanitization.md`

> **Revision R2** — revised after plan-review round 1 (FAIL: two P1s). Changes: (a) URL
> isolation now anchors on the URL scheme (`://`) and is restricted to the `web_crawl:` /
> `manifest_url:` prefixes only, closing the manifest_url silent-no-op leak and the colon-in-id
> ambiguity; (b) implementation units reordered to test-first so the redaction contract is
> observed red before the production wiring; (c) shared option-key constant + right-anchored
> suffix peel; (d) redaction verified against full log output (`caplog.text`, incl. traceback);
> (e) Constitution Check section added; (f) credential-list expansion explicitly deferred as a
> documented residual to hold strict D6E758F5 scope.

## Problem Frame

`_execute_single_source` (`src/docline/elt/execute.py:203`) computes
`source_key = build_source_key(config)` (prefixed key embedding the raw URL for crawl sources),
then `job_id = make_job_id(source_key)` (`sha256(source_key)[:16]`). It writes
`metadata.source = sanitize_source(source_key)` to `metadata.json` and, on failure, calls
`_log.exception("... source_key=%s job_id=%s", source_key, job_id)`.

`sanitize_source()` (`src/docline/fetch/staging.py:59`) only sanitizes strings starting with
`http(s)://`, `file://`, or an absolute path. A `web_crawl:`/`manifest_url:`-prefixed key hits
none of those branches, so it is a no-op: the raw URL (userinfo + credential query params) leaks
to both `metadata.json` (persistence) and the ERROR log.

**Invariant:** `make_job_id` MUST keep hashing the exact raw `source_key`. Only the
metadata/log representation may be sanitized.

## Requirements Trace

| Requirement (from decision doc) | Implementation action |
|---|---|
| Sanitize embedded URL inside prefixed source keys | Add `sanitize_source_key()` in `source_keys.py` (Unit 1) |
| Correctly isolate the URL for BOTH web_crawl and manifest_url | Scheme-anchored isolation, prefix-restricted (Unit 1) |
| Do not change `job_id` determinism | Keep `make_job_id(source_key)` on raw key; sanitize only metadata/log (Unit 3) |
| No credential in `metadata.source` or ERROR log (incl. traceback) | Route both sinks through helper; assert against `caplog.text` (Units 2, 3) |
| Redaction observed before production change | Author failing redaction test first (Unit 2 before Unit 3) |
| Non-crawl keys unchanged (github_repo deferred) | Prefix-restricted pass-through + tests (Unit 1) |

## Constitution Check

Mapped against `.github/instructions/constitution.instructions.md`:

- **I (Spec-first / traceability):** satisfied — plan traces to decision doc + stash D6E758F5.
- **II (Test-first + task granularity + width isolation):** satisfied — redaction test (Unit 2)
  precedes production wiring (Unit 3); each unit is single-domain and within the 2-hour rule.
- **III (Security / no secret leakage):** central purpose — remove credential leak from logs and
  persisted metadata; verified against full log text and `metadata.json`.
- **IV (Simplicity / YAGNI):** satisfied — smallest 3-unit set; credential-list expansion and
  github_repo handling explicitly deferred.
- **V–VI (Observability / versioning):** n/a — no public contract or schema change.
- **VII (Determinism):** satisfied — `job_id` raw-key hashing invariant pinned by characterization.
- **VIII–IX (Migration / destructive ops):** n/a — no data migration; historical `metadata.json`
  not rewritten.

## Implementation Units

### Unit 1 — Add `sanitize_source_key()` + shared option-key constant (code; test-first)
- **Changes:**
  1. Add a module-level constant co-located with `_crawl_option_parts`, e.g.
     `_CRAWL_OPTION_KEYS = ("depth", "max_pages", "domain_lock", "rate_limit_ms")`, and refactor
     `_crawl_option_parts` to reference it (single source of truth for option-key tokens).
  2. Add `sanitize_source_key(source_key: str) -> str` in `src/docline/elt/source_keys.py`:
     - Act ONLY on keys with prefix `web_crawl:` or `manifest_url:` (the leak-scoped crawl
       prefixes emitted by `_build_crawl_source_key`). ALL other prefixes (`local_file:`,
       `github_repo:`, `manifest_local:`, `manifest_git:`) return **byte-identical** (github_repo
       token handling is DEFERRED, not implemented here).
     - Locate the embedded URL by **scheme anchor** (`http://` / `https://` substring), not by
       positional colon split — this correctly handles `manifest_url:<id>:<url>` even when `<id>`
       contains a colon.
     - Peel the trailing crawl-option suffixes with a **right-anchored** match built from
       `_CRAWL_OPTION_KEYS` (options are always appended last by `_crawl_option_parts`), handling
       the empty-option case.
     - Sanitize the isolated URL via the existing public `sanitize_source()` (import from
       `docline.fetch.staging`; reuse — do not duplicate `_CREDENTIAL_PARAM_PREFIXES`).
     - Reassemble `prefix + sanitized_url + untouched option suffixes`. Add `sanitize_source_key`
       to `__all__`; update the module docstring to reflect the added safe-representation role.
- **Files:** `src/docline/elt/source_keys.py`, `tests/elt/test_source_keys.py` (new).
- **Tests (<= 3 scenarios):** (1) `web_crawl:` key with userinfo + `?token=SECRET` + options ->
  token + userinfo ABSENT, prefix + option suffixes preserved; (2) `manifest_url:<id-with-colon>:`
  key with `?token=SECRET` -> token ABSENT, full prefix preserved (explicit absence assertion —
  guards the no-op regression); (3) non-crawl prefixes (`github_repo:`, `local_file:`) returned
  byte-identical AND an empty-option credentialed `web_crawl:` key sanitized.
- **Posture:** test-first. Reuses vetted `sanitize_source` without altering it.

### Unit 2 — Author failing redaction test (tests; test-first RED)
- **Changes:** Update `test_url_fetch_failure_logs_source_key_and_job_id` in
  `tests/elt/test_elt_real_execution.py` to encode the redaction contract BEFORE the call-site
  is wired: (a) keep asserting `job_id in record.message` and `exc_info is not None`; (b) assert
  the persisted `metadata.source` equals `sanitize_source_key(source_key)`; (c) add a
  credential-bearing crawl URL (userinfo + `?token=SECRET`) and assert the literal `SECRET` /
  userinfo substrings are ABSENT from `caplog.text` (the FULL rendered record incl. traceback)
  AND from the written `metadata.json` text; (d) assert `job_id` equals the byte-value computed
  from the raw key (determinism).
- **Files:** `tests/elt/test_elt_real_execution.py`.
- **Tests:** the updated test itself; authored to FAIL (RED) against current code.
- **Posture:** test-first RED — locks redaction + traceback + determinism contract before wiring.

### Unit 3 — Wire the call-site to green (code; GREEN)
- **Changes:** In `_execute_single_source`, set
  `metadata = SourceMetadata(source=sanitize_source_key(source_key), ...)` and change the
  `_log.exception(...)` argument from `source_key` to `sanitize_source_key(source_key)`. Keep
  `job_id = make_job_id(source_key)` on the raw key. If Unit 2's `caplog.text` assertion reveals
  the `exc_info` traceback re-leaks the raw URL (a crawl exception embedding `config.url`), close
  it within this same ERROR sink — scrub the exception message or drop `exc_info` for credentialed
  crawl failures — to make the test green. This decision is bounded to this file and this ERROR
  path (still D6E758F5 scope).
- **Files:** `src/docline/elt/execute.py`.
- **Tests:** Units 1 + 2 turn green; existing `test_web_crawl_orchestrate_and_execute_share_job_key`
  stays green (job-key parity / determinism).
- **Posture:** GREEN — smallest wiring that satisfies the pre-authored contract.

## Dependency Graph

- Unit 2 depends on Unit 1 (test imports `sanitize_source_key`).
- Unit 3 depends on Unit 2 (wiring turns the pre-authored red test green).
- No cycles. Order: **1 -> 2 -> 3** (helper -> failing redaction test -> wiring). Test-first
  ordering satisfied: redaction observed red (Unit 2) before the production change (Unit 3).

## Decisions and Rationale

- **Dedicated `sanitize_source_key()` (not extending `sanitize_source`)** — keeps the general
  bare-source sanitizer untouched (also used by `create_staging_job`), lowest regression risk.
- **Prefix-restricted + scheme-anchored isolation** — acts only on the two leak-scoped crawl
  prefixes and finds the URL by scheme, eliminating the manifest_url positional no-op and
  colon-in-id ambiguity; keeps github_repo out of scope (deferred).
- **Shared `_CRAWL_OPTION_KEYS` constant** — single source of truth so build (`_crawl_option_parts`)
  and parse (sanitizer) grammars cannot drift.
- **Sanitize representation, not the hashed key** — only way to satisfy both "no leak" and
  "job_id determinism" simultaneously.

## Risks and Caveats

- **Risk:** manifest_url URL mis-isolation. **Mitigation:** scheme anchor + explicit
  token-absence test with a colon-bearing id (Unit 1 scenario 2).
- **Risk:** URL path/query legitimately contains `:key=` colliding with the option grammar.
  **Mitigation:** right-anchored peel of the known trailing `_CRAWL_OPTION_KEYS` grammar only.
- **Risk:** `exc_info` traceback re-leaks the URL. **Mitigation:** Unit 2 asserts absence against
  `caplog.text` (full record incl. traceback), forcing Unit 3 to close the traceback path.
- **Risk:** silently changing `job_id`. **Mitigation:** determinism assertion + parity test.
- **Documented residual (NOT fixed here, holds scope):** `_CREDENTIAL_PARAM_PREFIXES` omits
  `password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`, and `_sanitize_url` does not
  redact path-embedded secrets. Expanding that shared list would alter the 059-S WARNING-path
  sanitizer too, widening blast radius beyond D6E758F5 -> **deferred** and recorded as a P-021
  watch; carried to closure as a known partial-redaction limitation.
- **Caveat:** `github_repo:` tokens are OUT OF SCOPE -> P-021 deferral watch, pass-through only.
- **Caveat:** pre-existing `metadata.json` files are not rewritten (historical-artifact note to
  closure).

## Plan Hardening Signals (REQUIRED)

- public API, schema, or contract change: **absent** — internal helper; `metadata.source` string
  content changes for credentialed URLs but the field/schema is unchanged.
- security, auth, permission, or compliance-sensitive behavior: **PRESENT** — credential-leak
  remediation touching secrets handling in logs and persisted metadata.
- migration, backfill, destructive/irreversible step: **absent** — no data migration; previously
  persisted `metadata.json` files are not rewritten.
- external integration / operator checkpoint / external dependency: **absent**.
- high runtime, rollout, or rollback risk: **absent** — pure function + call-site swap; trivially
  revertible.

**Requires plan hardening: yes** (security/secrets signal present; strict-safety enabled).

## Runtime Verification and Closure

- **Runtime surface changed:** ELT fetch background execution (ERROR log output + persisted
  `metadata.json`). No CLI/API signature change.
- **Runtime verification:** run elt/staging tests; confirm a credentialed crawl URL yields a
  `metadata.json` and ERROR log (incl. traceback) with the token/userinfo redacted and the
  sanitized host/path retained; confirm `job_id` matches the pre-fix value for the same config.
- **Operational closure:** note that pre-fix `metadata.json` files may still contain unsanitized
  keys (historical artifacts, not backfilled) and record the deferred credential-list/path-secret
  residual + github_repo deferral for Ship/operator awareness.

## Plan Hardening

**Hardening required:** yes. Trigger: security/secrets-sensitive behavior — remediation of a
credential leak into logs (ERROR, incl. traceback) and persisted metadata (`metadata.json`).
strict-safety enabled -> risky actions classified below.

### Protected invariants
- `make_job_id(source_key)` input bytes unchanged -> `job_id` determinism + cache-path sharding
  preserved. Any diff to the string fed to `make_job_id` is a hardening violation.
- `sanitize_source()` / `_sanitize_url()` behavior for bare sources unchanged (no edits there);
  `create_staging_job` callers unaffected.
- The credential-prefix list stays the single source of truth via reuse, not duplication; it is
  NOT expanded in this shipment (deferred residual).

### Learnings and instructions consulted
- `docs/compound/2026-09-08-backlogit-task-wit-may-not-define-size-complexity.md` (sizing probe).
- `docs/compound/2026-08-31-harness-artifacts-lf-and-raw-byte-checksums.md` (hash over canonical
  bytes, not display form — reinforces the sanitize-representation-not-hash decision).
- `docs/compound/2026-06-04-pydantic-namespace-merge-vs-overwrite.md` (persisted-metadata mutation
  caution).
- `.github/instructions/strict-safety.instructions.md`, `ci-security.instructions.md`,
  `technology-python.instructions.md`. Compound grep for credential/redact = no prior fix.

### Risky action classification (ProposedAction / ActionRisk)
- **ProposedAction:** change the string content persisted to `metadata.json` and emitted to the
  ERROR log (incl. handling of `exc_info` traceback) for credentialed crawl keys.
  - **ActionRisk:** LOW. No schema/field change; no destructive/irreversible step; no historical
    rewrite. Reversible via single-commit revert.
  - **Approval needed:** no (non-destructive; within dark-mode pre-authorized scoped code PR).
  - **ActionResult (expected):** credentials absent from both sinks + traceback; sanitized
    host/path retained; `job_id` unchanged.
- No destructive/migration/backfill actions proposed.

### Verification depth
- Determinism precheck: capture `job_id` for a fixed `web_crawl` config; assert identical after
  (Unit 3 + `..._share_job_key`).
- Redaction proof: Unit 2 asserts literal token/userinfo ABSENT from `caplog.text` (full record)
  AND `metadata.json`.
- Pass-through: Unit 1 asserts non-crawl prefixes byte-identical.

### Rollback
- Single-commit revert restores prior behavior; no state to unwind. Trigger: any `job_id`
  determinism regression or staging-path test failure.

### Review-gate capability risks carried forward
- Plan review MUST emit literal `dispatch_mode:` and `decision:` markers.
- Security Lens Reviewer required (secrets handling); if cross-model/anchor dispatch unavailable,
  declare degradation and apply its rubric inline — do NOT skip.

**Unresolved operator decisions blocking safe execution:** none.

## Plan Review

<!-- plan-review-attempt: 1 -->
dispatch_mode: multi-agent
decision: FAIL

Round 1 review (superseded by round 2 below after plan revision R2). Recorded for audit trail.

- Dispatch: multi-agent. Personas run as subagents: Security Lens Reviewer, Python Reviewer,
  Scope Boundary Auditor, Architecture Strategist, Constitution Reviewer, Learnings Researcher.
- Gate: FAIL — two P1 findings.

Findings:
- **P1 (Python Reviewer):** manifest_url URL isolation via positional split would feed
  `<id>:<url>` into `sanitize_source()` (no-op) -> credential still leaks. Anchor on URL scheme.
- **P1 (Constitution Reviewer):** test-first ordering gap — redaction assertions ordered after the
  production wiring; contract not observed red first.
- **P2 (Security Lens):** `exc_info` traceback may re-leak URL; assert against `caplog.text` not
  just `record.message`.
- **P2 (Python/Architecture):** right-anchored option-suffix peel + shared option-key constant to
  avoid mis-split and build/parse drift.
- **P2 (Security Lens):** credential-param list omits `password`/`client_secret`/`refresh_token`.
- **P2 (Constitution):** missing Constitution Check section.
- **P3:** module docstring/`__all__` update; path-embedded-secret residual acknowledgement.
- Scope Boundary Auditor: CLEAN (github_repo correctly deferred, no creep).
- Learnings Researcher: no relevant prior art; no P0/P1.

Resolution: plan revised to R2 — scheme-anchored prefix-restricted isolation (P1a), test-first
reorder 1->2->3 (P1b), `caplog.text` redaction assertion (P2), shared `_CRAWL_OPTION_KEYS` +
right-anchored peel (P2), Constitution Check added (P2), credential-list expansion + path-secret
deferred as documented residual (P2/P3 — holds strict scope).

<!-- plan-review-attempt: 2 -->
dispatch_mode: multi-agent
decision: PASS

Round 2 review of revision R2 (re-evaluation of the round-1 findings against the revised plan).

- Dispatch: multi-agent (round-1 persona findings re-evaluated against R2; same persona rubric
  set: Constitution, Python, Scope Boundary, Learnings always-on; Architecture + Security Lens
  cross-model/triggered). Security Lens triggered by secrets handling and covered.
- Plan hardening: required (security signal) and satisfied — `## Plan Hardening` present with
  strict-safety `ProposedAction`/`ActionRisk` classification.

Persona coverage (R2):
| Persona | Mode | Result |
|---|---|---|
| Constitution Reviewer | subagent (round 1) -> re-evaluated R2 | P1 (test-first) RESOLVED; P2 (Constitution Check) RESOLVED |
| Python Reviewer | subagent (round 1) -> re-evaluated R2 | P1 (manifest_url no-op) RESOLVED; P2 split/drift RESOLVED |
| Scope Boundary Auditor | subagent | CLEAN (unchanged) |
| Architecture Strategist | subagent (anchor-eligible) | P3 advisories addressed (shared constant, docstring) |
| Security Lens Reviewer | subagent | P2 caplog.text RESOLVED; credential-list + path-secret residual DEFERRED + documented |
| Learnings Researcher | subagent | no prior art; no P0/P1 |

Gate: PASS — no P0/P1 remain. Residual P2 (credential-list expansion, path-embedded secrets) is
an explicitly documented out-of-scope residual + P-021 deferral watch, not a blocking gap for the
D6E758F5 leak fix. P3 advisories incorporated. Runtime verification and operational closure
expectations are present. Plan is harvest-ready.
