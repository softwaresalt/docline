---
artifact_type: operational-closure
shipment_id: 010-S
feature_id: 010-F
title: 010-S Document Ingestion / docline-graphtor ingestion contract alignment operational closure
created_at: 2026-06-03T12:40:00-07:00
author: ship-agent
merge_commit: 3f1226f
pr_number: 19
releasability: READY_WITH_CONDITIONS
---

# 010-S — Operational Closure

## Release readiness summary

Shipment **010-S** (PR [#19](https://github.com/softwaresalt/docline/pull/19),
merge commit `3f1226f`) delivered the docline → graphtor-docs ingestion
contract alignment in a single coordinated release. The work spanned:

- **39 tasks** organized into 8 work blocks (F1 through F8: schema/manifest
  surface, content hashing + POSIX paths, HTML extraction, DOCX adapter,
  PDF adapter (heuristic + docling), assemble heading validation + chunk
  anchors, URL canonicalization + sitemap SSRF, end-to-end real-binary
  parity).
- **3 multi-day Ship sessions** plus 3 sub-sessions (sessions 1-2 in
  2026-06-02, sessions 3-5 in 2026-06-03, plus this closure session 6).
- **~6 600 lines added, ~190 lines removed** across 101 files (per merge
  diffstat).

The releasability evidence in `docs/closure/010-S-runtime-verification.md`
records every required graphtor-docs ingestion contract assertion as PASS
and every P2 advisory from the structured review as verified.

## Strict-safety final records

### PA-1 — `BaseFrontmatter` v1 extension

| Field | Value |
| --- | --- |
| ProposedAction | Extend `BaseFrontmatter` with the five graphtor-docs contract additions (`content_sha256`, `source_path`, `chunk_strategy`, `schema_version`, `docline` namespace) and the `BaseFrontmatter` library reorganization |
| Targets | `src/docline/schema/models.py`, `src/docline/schema/library.py`, `src/docline/schema/export.py`, all docline reader/extractor frontmatter producers |
| ActionRisk | high — public contract surface change, affects all downstream consumers reading docline output |
| Rollback | Revert `3f1226f`; consumers still on v0 frontmatter continue to work because the additions default to safe empty values |
| approval_required | yes |
| ActionResult | **applied** — landed across tasks `010.001-T` through `010.014-T`; PA-1 commit `d18d4d9` finalized the upgrade; runtime verification confirms all five fields populate correctly and `schema_version` default is `"1.0"` |

### PA-2 — POSIX path migration

| Field | Value |
| --- | --- |
| ProposedAction | Normalize `source_path` and other path frontmatter to forward-slash POSIX form across all reader / extractor / assemble paths to guarantee cross-platform consumer parity |
| Targets | `src/docline/paths.py` (new `posixify_path` helper), `src/docline/process/assemble.py`, `src/docline/fetch/html_extract.py`, `src/docline/elt/execute.py`, all readers |
| ActionRisk | high — touches every path-emitting surface, regression would break cross-platform consumers |
| Rollback | Revert `3f1226f`; consumers running on POSIX hosts were unaffected even pre-fix; Windows hosts revert to backslash form (the bug being fixed) |
| approval_required | yes |
| ActionResult | **applied** — PA-2 commit `fc9e2ca` finalized the migration; runtime live probe confirms Windows `docs\sub\file.md` round-trips to `docs/sub/file.md` in the YAML frontmatter |

## P2 advisories honored

The structured review (`docs/closure/010-S-review.md`) raised three P2
advisories. All three are honored in shipped code:

1. **`defusedxml` for DOCX XML parsing (010.015)** — `src/docline/readers/docx.py`
   imports `defusedxml.ElementTree.fromstring` and `defusedxml.ElementTree.ParseError`
   for both `word/document.xml` and `word/numbering.xml`, protecting against
   XXE attacks. `defusedxml` is declared as a runtime dependency in
   `pyproject.toml`.

2. **JSON Schema `$schema` + `$id` in export (010.005)** — `docline export-schema`
   output declares `"$schema": "https://json-schema.org/draft/2020-12/schema"`
   and `"$id": "https://docline.softwaresalt.dev/schema/base-frontmatter/v1.json"`
   so downstream tools can pin the dialect and identify the contract version.

3. **SSRF defense-in-depth (010.030)** — `src/docline/fetch/sitemap.py::validate_sitemap_url`
   applies six layered checks: scheme allowlist, hostname metadata blocklist,
   IP literal classification, DNS resolution, per-address `ipaddress`
   classification (private / loopback / link-local / multicast / reserved),
   and an explicit cloud-metadata IP rejection. Six dedicated unit tests
   plus a live probe confirm the layered defense.

## Downstream impact note

docline now emits `schema_version: "1.0"` per the cross-tool contract specified
in `docs/design-docs/graphtor-docs-ingestion-contract.md`. graphtor-docs
consumers reading docline output as of `3f1226f` receive all five v1 fields:

- `content_sha256` — SHA-256 hex digest over the assembled Markdown body bytes
- `source_path` — project-relative POSIX path of the source artifact
- `chunk_strategy` — chunk-boundary strategy identifier (defaults to `h1-h2-h3`)
- `schema_version` — semantic version of the frontmatter contract (`"1.0"`)
- `docline` — optional namespace dict for docline-only metadata (intentionally
  NOT promoted to top-level fields, so docline-internal metadata cannot leak
  into the shared contract surface)

Consumer-side validation work and the consumer perspective on this contract
are tracked in the graphtor-docs repository; cross-link both `docs/closure/`
records when graphtor-docs lands its corresponding consumer release.

## Rollback plan

| Step | Command | Notes |
| --- | --- | --- |
| 1 | `git revert -m 1 3f1226f` | Single-commit revert of the merge; preserves history |
| 2 | `git push origin main` | Publish revert; downstream consumers see prior v0 frontmatter on next ingest |
| 3 | none | docline emits fresh frontmatter each run; no data migration to roll back |

Estimated rollback time: **5 minutes** (no migrations, no schema persistence,
no consumer-coupled state).

## Monitoring

| Surface | Current monitoring | Recommendation |
| --- | --- | --- |
| CI quality gates | none (no GitHub Actions workflow configured) | Add a workflow that runs `ruff format --check`, `ruff check`, `pyright src/`, and `pytest` on every push and PR — tracked as new stash item below |
| Schema drift | none | Future: emit a checksum of the JSON Schema export in a workflow, fail PR if it changes without bumping `schema_version` |
| Downstream consumer regression | none | Coordinate with graphtor-docs to subscribe a consumer-side smoke test against docline output samples |

## Validation window

The 010-S release is considered observed-good at `3f1226f`. Any
production-relevant regression should land as a follow-up shipment that cites
this closure document and updates `schema_version` if the contract changes.

Validation owner: project maintainer (single-maintainer project; same owner as
the merge approval gate).

## Outstanding follow-ups

### Existing stash entries

| Stash ID | Kind | Priority | Summary |
| --- | --- | --- | --- |
| CE758832 | bug | low | Windows pytest `tmp_path` `PermissionError` noise — `_pytest/pathlib.py:176` `WinError 5: Access is denied` on `C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>`. Blocks ~95 reader / process tests on long-running Windows sessions but does not affect test logic. Workaround: close shells and clear temp manually |

### New stash entries created this session

| Title | Kind | Priority | Rationale |
| --- | --- | --- | --- |
| Add GitHub Actions CI workflow for docline (ruff, pyright, pytest, build) | task | high | Greenfield project still has no CI; 010-S landed 100 tests but every push relies on the maintainer running gates locally. Workflow should run on Linux runners to dodge the Windows `tmp_path` issue |

## Compound learnings to capture

(Recommended for the `compound` skill when invoked at session end.)

1. **Multi-session Ship pattern for large shipments** — 39-task shipments
   need ~3 working sessions plus closure overhead; per-session task budget
   capped at 20 (constitution stop condition) forces the split. Document
   the explicit `session-N-resume-prompt.md` handoff pattern as the canonical
   continuation mechanism.

2. **Lifecycle slip recovery** — Queue / archive divergence (task `done` but
   queue file still present) is recoverable via `git checkout HEAD -- <queue file>`
   followed by the canonical `backlogit move` → `track-commit` → `archive_item`
   sequence. Two slips happened in this shipment; the recovery procedure was
   identical and reliable both times.

3. **GitHub Copilot re-request dedup quirk** — Programmatic
   `gh api repos/.../requested_reviewers -X POST` returns `201 Created` but no
   timeline event is produced when Copilot has already submitted a review at
   any prior SHA on the PR, even if HEAD has moved. The operator-side workaround
   (re-request via the PR UI) is the only known unstick. Document this in the
   `pr-lifecycle` skill or in `.github/instructions/github-pr-automation.instructions.md`
   §1.1 so the next Ship session does not block at §1.9 Check 2 waiting on a
   stale review that will never refresh programmatically.

4. **Conventional commit scope drift** — Two commits in this shipment used
   `chore(backlog):` instead of an allowed scope (`core`, `cli`, `mcp`,
   `fetch`, `process`, `schema`, `docs`). Ship self-check should validate the
   scope against `.github/instructions/commit-message.instructions.md` before
   `git commit`.

## Releasability outcome

**`READY_WITH_CONDITIONS`** — 010-S is operationally released to `main` at
`3f1226f`. The two follow-up conditions are non-blocking:

1. Windows `tmp_path` noise (CE758832) does not affect production behavior;
   tracked for ergonomics.
2. GitHub Actions CI workflow gap is a project-level chore, not a 010-S
   regression risk.

Closure complete. The post-merge closure PR will archive `010-F` and `010-S`
and land this document plus `docs/closure/010-S-runtime-verification.md` on
`main`.
