---
title: "Source-key credential sanitization on ELT error/persistence paths"
date: 2026-09-12
agent: stage
kind: implementation-plan
source: docs/decisions/2026-09-12-source-key-credential-sanitization.md
stash_id: D6E758F5
covering_release_unit: chore
revision: R3
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

> **Revision R3** — revised after Copilot review on PR #194 (thread `PRRT_kwDOSsAX4c6hzYmm`).
> The R2 scheme-anchored string parse could not reliably resolve the manifest_url ambiguity:
> `ManifestUrlSource.id` is an unrestricted `str` (`src/docline/elt/manifest_models.py:65`) and the
> composed key is `manifest_url:<id>:<url>:<options>` (`src/docline/elt/source_keys.py:32-40`), so an
> `id` containing `http://`/`https://` defeats the "first scheme after prefix" anchor. The sanitizer
> contract is changed to **consume the typed `SourceConfig`** — sanitize `config.url` and recompose
> the key via the existing builder grammar (`_build_crawl_source_key`) — removing all string-parse
> ambiguity. `job_id` still hashes the raw `build_source_key(config)` (determinism invariant
> unchanged). The decision doc and tasks 072.001-T/072.002-T/072.003-T are updated to match.

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
| Correctly isolate the URL for BOTH web_crawl and manifest_url | Sanitize the typed `config.url` and recompose via `_build_crawl_source_key`; no string parse (Unit 1) |
| Do not change `job_id` determinism | Keep `make_job_id(source_key)` on raw key; sanitize only metadata/log (Unit 3) |
| No credential in `metadata.source` or ERROR log (incl. traceback) | Route both sinks through helper; assert against `caplog.text` (Units 2, 3) |
| Redaction observed before production change | Author failing redaction test first (Unit 2 before Unit 3) |
| Non-crawl keys unchanged (github_repo deferred) | Prefix-restricted pass-through + tests (Unit 1) |

## Constitution Check

Mapped against `.github/instructions/constitution.instructions.md` (actual principle names):

- **I. Safety-First Python:** satisfied — pure helper + call-site swap; reuses the vetted
  `sanitize_source()` primitive; no unsafe constructs.
- **II. Test-First Development (NON-NEGOTIABLE):** satisfied — the failing redaction test (Unit 2)
  precedes production wiring (Unit 3); each unit is single-domain and within the 2-hour rule.
- **III. Workspace Isolation and Security Boundaries:** central purpose — remove the credential
  leak from logs (incl. traceback) and persisted `metadata.json`; verified against full
  `caplog.text` and the written file.
- **IV. CLI Workspace Containment (NON-NEGOTIABLE):** n/a — no path/containment change.
- **V. Structured Observability:** preserved — ERROR log keeps `source_key`/`job_id` context in
  sanitized form and retains `exc_info` (traceback kept, not dropped).
- **VI. Single Responsibility:** satisfied — dedicated `sanitize_source_key()`; `sanitize_source()`
  semantics untouched.
- **VII. Destructive Command Approval (NON-NEGOTIABLE):** n/a — no destructive/irreversible step;
  historical `metadata.json` not rewritten.
- **VIII. Explicit Safety Modes:** applied — strict-safety enabled; plan hardened (see `## Plan
  Hardening`).
- **IX. Git-Friendly Persistence:** n/a — no schema/serialization change.
- **Determinism (Technical Constraint):** `job_id` raw-key hashing invariant pinned by an explicit
  raw-key recomputation assertion (Unit 2) plus the parity characterization (Unit 3).

## Implementation Units

### Unit 1 — Add `sanitize_source_key()` + shared option-key constant (code; test-first)
- **Changes:**
  1. Add a module-level constant co-located with `_crawl_option_parts`, e.g.
     `_CRAWL_OPTION_KEYS = ("depth", "max_pages", "domain_lock", "rate_limit_ms")`, and refactor
     `_crawl_option_parts` to reference it (single source of truth for option-key tokens).
  2. Add `sanitize_source_key(config: SourceConfig) -> str` in `src/docline/elt/source_keys.py`
     that consumes the **typed config** (not the composed key string):
     - For the two leak-scoped crawl configs (`WebCrawlSource`, `ManifestUrlSource`), sanitize the
       typed `config.url` via the existing public `sanitize_source()` (import from
       `docline.fetch.staging`; reuse — do not duplicate `_CREDENTIAL_PARAM_PREFIXES`), then
       **recompose** the key through the same `_build_crawl_source_key(prefix, sanitized_url, ...)`
       path that `build_source_key` uses, so the sanitized key is grammar-identical to the raw key
       except for the URL segment. This is immune to the `manifest_url:<id>:<url>` ambiguity even
       when `<id>` itself contains a URL scheme, because no composed string is parsed.
     - For ALL other config types (`LocalFileSource`, `GitHubRepoSource`, `ManifestLocalSource`,
       `ManifestGitSource`) return `build_source_key(config)` **byte-identical** (github_repo token
       handling is DEFERRED, not implemented here).
     - Keep `_build_crawl_source_key` (and its `_CRAWL_OPTION_KEYS`-based option construction) as
       the single builder grammar reused by both `build_source_key` and the sanitizer, so there is
       no separate parse grammar to drift and no option-suffix peel is needed. Add
       `sanitize_source_key` to `__all__`; update the module docstring to reflect the added
       safe-representation role.
- **Files:** `src/docline/elt/source_keys.py`, `tests/elt/test_source_keys.py` (new).
- **Tests (<= 3 scenarios):** (1) `web_crawl:` key with userinfo + `?token=SECRET` + options ->
  token + userinfo ABSENT, prefix + option suffixes preserved; (2) a `ManifestUrlSource` whose
  `id` itself contains `http://` and whose `url` carries `?token=SECRET` -> token ABSENT and the
  recomposed key preserves the correct prefix/id/options (proves the typed-config recompose is
  immune to scheme-in-id — the exact case the R2 string parse could not handle); (3) non-crawl
  configs (`GitHubRepoSource`, `LocalFileSource`) returned byte-identical AND an empty-option
  credentialed `WebCrawlSource` sanitized.
- **Posture:** test-first. Reuses vetted `sanitize_source` without altering it.

### Unit 2 — Author failing redaction test (tests; test-first RED)
- **Changes:** Update `test_url_fetch_failure_logs_source_key_and_job_id` in
  `tests/elt/test_elt_real_execution.py` to encode the redaction contract BEFORE the call-site
  is wired: (a) keep asserting `job_id in record.message` and `exc_info is not None`; (b) assert
  the persisted `metadata.source` equals `sanitize_source_key(config)`; (c) add a
  credential-bearing crawl URL (userinfo + `?token=SECRET`) and assert the literal `SECRET` /
  userinfo substrings are ABSENT from `caplog.text` (the FULL rendered record incl. traceback)
  AND from the written `metadata.json` text — the injected crawl failure MUST raise an exception
  whose message embeds the credentialed `config.url` (e.g. an error carrying `start_url`), so the
  `caplog.text` traceback assertion is a genuine RED and is NOT vacuously satisfied by a URL-free
  message like `OSError("Network down")`; (d) assert `job_id == make_job_id(build_source_key(config))`
  recomputed independently from the raw credentialed key — this pin, NOT the credential-free parity
  test, is the raw-hash oracle: an impl that hashes the SANITIZED key MUST fail this assertion.
- **Files:** `tests/elt/test_elt_real_execution.py`.
- **Tests:** the updated test itself; authored to FAIL (RED) against current code.
- **Posture:** test-first RED — locks redaction + traceback + determinism contract before wiring.

### Unit 3 — Wire the call-site to green (code; GREEN)
- **Changes:** In `_execute_single_source`, set
  `metadata = SourceMetadata(source=sanitize_source_key(config), ...)` and change the
  `_log.exception(...)` argument from `source_key` to `sanitize_source_key(config)`. Keep
  `job_id = make_job_id(source_key)` on the raw key. If Unit 2's `caplog.text` assertion reveals
  the `exc_info` traceback re-leaks the raw URL (a crawl exception embedding `config.url`), close
  it within this same ERROR sink by SCRUBBING the raw URL out of the logged exception (sanitize or
  wrap the exception message so the rendered traceback carries no credential). Do NOT drop
  `exc_info`: Unit 2 keeps asserting `exc_info is not None`, so the traceback MUST remain present
  but credential-free. Bounded to this file and this ERROR path (still D6E758F5 scope).
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
- **Typed-config consumption + builder recompose (R3)** — sanitizes the typed `config.url` and
  recomposes via `_build_crawl_source_key`, eliminating the manifest_url positional no-op and ALL
  scheme-in-id / colon-in-id string-parse ambiguity (no composed string is parsed); keeps
  github_repo out of scope (deferred).
- **Shared `_CRAWL_OPTION_KEYS` constant** — single source of truth for option-key tokens in the
  builder (`_crawl_option_parts`); the sanitizer reuses the builder rather than re-parsing, so no
  separate parse grammar exists to drift.
- **Sanitize representation, not the hashed key** — only way to satisfy both "no leak" and
  "job_id determinism" simultaneously.

## Risks and Caveats

- **Risk (eliminated by the R3 typed-config contract):** the R2 string-parse risks — manifest_url
  URL mis-isolation, an `id` containing `http(s)://` defeating the scheme anchor, and a URL
  path/query `:key=` colliding with the option-suffix grammar — no longer apply: the sanitizer
  consumes the typed `config.url` and recomposes via `_build_crawl_source_key`, so no composed
  string is parsed and there is no option-suffix peel. **Residual:** `sanitize_source()`
  URL-sanitization semantics still apply to the isolated `config.url` (userinfo + credential query
  params) and are covered by the Unit 1 scenarios (incl. an uppercase-scheme URL).
- **Risk:** `exc_info` traceback re-leaks the URL. **Mitigation:** Unit 2 asserts absence against
  `caplog.text` (full record incl. traceback), forcing Unit 3 to close the traceback path.
- **Risk:** silently changing `job_id`. **Mitigation:** determinism assertion + parity test.
- **Documented residual (NOT fixed here, holds scope):** `_CREDENTIAL_PARAM_PREFIXES` omits
  `password`/`pwd`/`passwd`/`client_secret`/`refresh_token`/`code`, and `_sanitize_url` does not
  redact path-embedded secrets. Expanding that shared list would alter the 059-S WARNING-path
  sanitizer too, widening blast radius beyond D6E758F5 -> **deferred** and recorded as a P-021
  watch; carried to closure as a known partial-redaction limitation.
- **Documented residual — parallel default-fetch sink (NOT fixed here, holds scope):** the
  non-`--execute` `docline fetch` path (`orchestrate_fetch` -> `create_staging_job`,
  `src/docline/fetch/staging.py:161`) has the IDENTICAL `sanitize_source()` no-op leak, persisting
  the raw credentialed key to `metadata.json` and stdout (`cli.py:381`). This shipment fixes only
  `_execute_single_source` per strict D6E758F5 scope -> **deferred**, captured as stash **0F1A653C**
  (high). Surfaced by the Stage adversarial multi-model review (2026-09-12).
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

## Adversarial Multi-Model Review (Stage, pre-staging-PR gate 2)

Operator requires, before every PR, BOTH (1) standard multi-persona review and (2) explicit
adversarial multi-model review. Gate (1) = plan-review rounds 1–2 above (FAIL -> PASS). Gate (2)
recorded here: Stage-owned adversarial review of the exact local staging diff `origin/main..HEAD`
(reviewed HEAD `bd93a406`, pre-remediation).

- **Reviewers (independent models/providers, parallel):** Anthropic `claude-opus-4.8`, OpenAI
  `gpt-5.6-sol`, Google `gemini-3.8-flash`, xAI `grok-4.6`. Verdicts: 3 BLOCK, 1 PASS. All
  findings adjudicated by Stage against the actual source (`source_keys.py`, `staging.py`,
  `execute.py`, `orchestrate.py`, tests) before disposition.
- **Consensus findings resolved in Stage-owned artifacts (this diff):**
  - P1 — unacknowledged second live leak sink (`orchestrate_fetch`/`create_staging_job` default
    `docline fetch` path). VERIFIED against source. Disposition: closure claims scoped to
    `_execute_single_source`; sink captured as deferral stash `0F1A653C` (NOT triaged into 063-S).
  - P1 — determinism test net too weak (parity test uses a credential-free URL). Disposition:
    Unit 2 AC(d) strengthened to an independent raw-key `make_job_id` recomputation oracle.
  - P1 — traceback re-leak under-specified + Unit 2/Unit 3 `exc_info` contradiction. Disposition:
    Unit 3 mandates SCRUB (keep `exc_info`); Unit 2 requires a credentialed-URL-bearing exception.
  - P2 — decision `P-021 Deferral Watch` said "None" vs plan/memory. Disposition: reconciled;
    three deferrals captured as stash `0F1A653C`/`79BF0AEC`/`06A59B1D`.
  - P2 — `## Constitution Check` mapped invented principle names. Disposition: remapped to the
    actual constitution (I Safety-First Python … VII Destructive Approval …).
  - P3 — stale "splits a prefixed key" (decision Option B), sub-epic prose, 063-S EOF blank line,
    archive `harvested_artifact_id`, scheme-in-id/uppercase robustness. Disposition: all fixed.
- **Residual after remediation:** the three captured deferrals (`0F1A653C` high, `79BF0AEC`,
  `06A59B1D`) remain out-of-scope for 063-S by operator P-017 scope freeze; no P0/P1 remain in the
  staged artifacts. Gate (2): PASS.
