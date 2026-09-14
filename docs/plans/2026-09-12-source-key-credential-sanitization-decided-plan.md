# Decided Plan: Source-key credential sanitization on ELT error/persistence paths

- **Date decided**: 2026-09-12 (plan review attempt 2, verdict PASS; final revision R8)
- **Compacted**: 2026-09-13 (post-merge closure, shipment `063-S` / feature `072-F`, PR #199,
  merge commit `3933dfc335e19bcd602bf104e82728268ae83156`)
- **Source stash**: `D6E758F5`
- **Source decision doc**: `docs/decisions/2026-09-12-source-key-credential-sanitization.md`
- **Owner of execution**: Ship
- **Original plan + review**: `docs/archive/plans/2026-09-12-source-key-credential-sanitization-plan.md`

## Final decision (R8, as shipped)

Add a dedicated, total, fail-closed typed-config credential sanitizer
(`sanitize_source_key(config)` / `sanitize_source_id(raw_id)` in
`src/docline/elt/source_keys.py`) and wire it into `_execute_single_source`
(`src/docline/elt/execute.py`) so no credential (URL userinfo, credential query
parameter, at any percent-encoding layer) reaches `metadata.json` or the ERROR
log — including through exception-chain scrubbing of `__cause__`/`__context__`.
`make_job_id`'s hash input remains the raw, unsanitized `source_key` — the
determinism invariant is never touched; only the persisted/logged
*representation* is sanitized.

## Requirements Trace (final)

| Requirement | Implementation |
|---|---|
| Sanitize embedded URL inside prefixed source keys | `sanitize_source_key()`, typed-config consumption + `_build_crawl_source_key` recompose (no string parsing) |
| No credential in the `id` segment (URL-shaped or not) | Marker-gated `sanitize_source_id(config.id)`, independent of URL detection |
| Helper is TOTAL / fail-closed (never raises) | Fail-closed wrapper around `config.url` sanitize; non-throwing marker-gated id scan |
| Credential-free IDs preserved verbatim | `sanitize_source_id` returns raw bytes unless a marker is detected |
| Percent-encoded credential names recognized at every decode layer | Bounded multi-layer `unquote` decode (fixed point or `_MAX_CREDENTIAL_DECODE_LAYERS = 5`), marker match at any layer fails closed |
| `job_id` determinism unchanged | `make_job_id(source_key)` keeps hashing the raw key |
| No credential in `metadata.source` or ERROR log (incl. traceback) | Both sinks routed through the sanitizer; exception message/traceback unconditionally scrubbed |
| Redaction observed before production change | Unit 2 (failing test) authored before Unit 3 (wiring) |
| Every same-sink URL-bearing variant sanitized (`web_crawl`, `manifest_url`, `github_repo`, `manifest_git`) | Unit 1b (`072.004-T`) extends the typed-config sanitizer to git variants; only filesystem-path components (`local_file`, `manifest_local` path) pass through byte-identical |

## Implementation units (final, as shipped)

1. **Unit 1 / `072.001-T`** — `sanitize_source_key()` + `sanitize_source_id()` core helper:
   fail-closed URL sanitize (malformed URL → `<source-url-redacted>`), marker-gated id
   redaction (credential-free verbatim, marker-bearing surgically redacted, unredactable
   marker → `<source-id-redacted>`), bounded multi-layer percent-decode detection
   (`_MAX_CREDENTIAL_DECODE_LAYERS = 5`). Covers `WebCrawlSource`/`ManifestUrlSource`.
2. **Unit 1b / `072.004-T`** — extends the same helper to `GitHubRepoSource`
   (`repo_url`/`branch`/`path_glob`) and `ManifestGitSource` (`id`/`url`/`branch`), and
   marker-gates `ManifestLocalSource.id`; `LocalFileSource` stays byte-identical. Subsumes
   and closes the former `79BF0AEC` github_repo deferral.
3. **Unit 2 / `072.002-T`** — failing redaction test (RED) authored before wiring: asserts
   credential absence from `caplog.text` (full record incl. traceback) and `metadata.json`
   for crawl, manifest, and git-variant credentialed configs; asserts `job_id` recomputed
   independently from the raw key (determinism oracle).
4. **Unit 3 / `072.003-T`** — wires `_execute_single_source` to use
   `sanitize_source_key(config)` for both `metadata.source` and the ERROR log call;
   unconditionally scrubs the exception message and `exc_info` traceback (kept, not
   dropped) for all fetch-failure paths.

Dependency order: `072-F` → `072.001-T` → `072.004-T` → `072.002-T` → `072.003-T` (helper →
git-variant extension → failing test → wiring; no cycles).

## Key decisions that survived review

- Dedicated `sanitize_source_key()`/`sanitize_source_id()` rather than extending the
  general `sanitize_source()` — keeps the widely-reused bare-source sanitizer (also used
  by `create_staging_job`) untouched, minimizing regression blast radius.
- Typed-config consumption + builder recompose (not string parsing) — eliminates the
  `manifest_url:<id>:<url>` ambiguity and all scheme-in-id/colon-in-id parse risk entirely,
  rather than attempting to patch a string-parse approach (R2→R3 pivot).
- Sanitizer is TOTAL and non-throwing by construction (fail-closed to a redacted sentinel
  on any malformed input) because it must be safely callable both before the fetch `try`
  and inside the exception logger without crashing `_execute_single_source` or masking a
  genuine fetch failure (R6).
- Bounded multi-layer percent-decode detection (not a single `unquote` pass) — closes the
  double/multi-layer encoding bypass class definitively, with guaranteed termination
  (`_MAX_CREDENTIAL_DECODE_LAYERS = 5`) rather than an unbounded decode loop (R7→R8 pivot).
- `_CREDENTIAL_PARAM_PREFIXES` vocabulary intentionally NOT expanded in this shipment
  (stays the existing, reused list) to hold strict D6E758F5 scope — expansion is a
  separately deferred residual (`06A59B1D`).
- `job_id = make_job_id(source_key)` always hashes the RAW key — this determinism
  invariant was pinned by an explicit independent-recomputation test oracle (Unit 2) and
  never relaxed across any revision.

## Rejected/superseded approaches (revision history)

The plan went through 8 revisions (R2–R8) as PR review (Stage plan-review rounds 1–2,
Stage adversarial multi-model review, and 5 cycles of Copilot review on PR #195) found
progressively deeper gaps in each prior approach. Superseded approaches, in order:

1. **R1 (rejected, plan-review round 1 FAIL, 2 P1s)**: positional-split string parsing for
   manifest_url isolation — defeated by scheme-in-id ambiguity; test-first ordering was
   also wrong (production wiring before the failing redaction test).
2. **R2→R3 (rejected)**: scheme-anchored string-parse URL isolation — still defeated by an
   `id` containing `http://`/`https://` (the anchor cannot distinguish id-embedded schemes
   from the real URL). Replaced by typed-config consumption + builder recompose (no string
   parsing at all).
3. **R4 (rejected)**: routing `config.id` through the general `sanitize_source()` — a no-op
   for non-URL-form ids (`sanitize_source()` only recognizes URL/absolute-path shapes).
   Replaced by a dedicated marker-gated `sanitize_source_id()`.
4. **R5 (rejected)**: `sanitize_source_id()` still delegated to `sanitize_source()` under
   the hood — inherited its `ValueError`-raising port parse (crash risk) and its
   path/fragment-mangling of credential-free ids (broke the "verbatim" guarantee).
   Replaced by a non-delegating, non-throwing, marker-gated implementation (R6).
5. **R6→R7 (rejected)**: raw-byte marker scan — missed a single-layer percent-encoded
   credential name (`%74oken`). Replaced by a decoded-view scan mirroring `parse_qsl`'s
   single `unquote` pass.
6. **R7→R8 (rejected)**: single-pass `unquote` detection — inherited `parse_qsl`'s
   single-layer blind spot, missing a double-encoded credential name (`%2574oken`).
   Replaced by the final bounded multi-layer decode (fixed point or 5-layer cap, fail
   closed on residual ambiguity).

Round-by-round detail for each rejection (exact PR thread IDs, byte-level examples) is
preserved in the archived original plan
(`docs/archive/plans/2026-09-12-source-key-credential-sanitization-plan.md`) and in the
compacted memory record
(`docs/memory/compacted/2026-09-13-063-s-compacted.md`).

## Review gate outcomes

- **Stage plan-review**: round 1 FAIL (2 P1s: manifest_url no-op risk, test-first ordering
  gap) → plan revised to R2 → round 2 PASS (no P0/P1; residual credential-list-expansion
  P2 explicitly documented as an out-of-scope deferral, not a blocking gap).
- **Stage adversarial multi-model review** (4 independent reviewers: Anthropic, OpenAI,
  Google, xAI): 3 BLOCK / 1 PASS on the initial staged diff → all P1/P2 findings
  adjudicated and resolved (determinism-oracle strengthening, traceback-scrub
  unconditional requirement, Constitution Check remap, deferral-list reconciliation) →
  final verdict PASS, no P0/P1 remaining.
- **Local adversarial review (pre-PR, 3 rounds)** and **PR-review (Copilot, 7 rounds plus
  1 operator-authorized bounded extension)**: see the compacted memory record and the
  post-merge closure narrative (`docs/closure/2026-09-13-sanitize-source-key-elt-error-paths-closure.md`)
  for the full accounting of fixed findings and the 14 deferred P-021 stash entries.

## Residuals held out of scope (unchanged at closure)

- `0F1A653C` (high) — the non-`--execute` default `docline fetch` path
  (`orchestrate_fetch`/`create_staging_job`) has the identical unsanitized-key leak;
  deliberately not fixed here (strict D6E758F5 scope).
- `06A59B1D` (medium) — `_CREDENTIAL_PARAM_PREFIXES` vocabulary expansion
  (password/pwd/passwd/client_secret/refresh_token/code) and path-embedded-secret
  redaction; expanding the shared list would widen blast radius into the unrelated 059-S
  WARNING-path sanitizer.
- `79BF0AEC` — **reconciled/closed**, subsumed by the R8 git-variant same-sink extension
  (Unit 1b); no longer an open residual.
- 12 additional lower-priority/advisory deferrals from local and PR-review cycles (see the
  post-merge closure narrative's Residual Follow-Ups table for the complete, current list).

## Constitution / hardening posture (unchanged at closure)

Security/secrets-sensitive behavior triggered mandatory plan hardening (strict-safety).
Protected invariants: `job_id` hash-input bytes unchanged; `sanitize_source()` semantics
for bare sources untouched; credential-prefix vocabulary not expanded. Risk classification:
LOW (non-destructive, no schema change, single-commit revertible). No unresolved operator
decisions blocked execution at plan-review time.
