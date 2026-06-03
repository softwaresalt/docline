# 010-S Structured Review

| Field | Value |
|---|---|
| Shipment | 010-S — docline-graphtor ingestion contract alignment |
| Branch | `feat/docline-graphtor-alignment` |
| Base | `main` @ `a62cd24` |
| HEAD at review | `284d73c` |
| Reviewer | ship agent (session 4), review skill (mode: report-only) |
| Diff scope | 96 files, +6312/-188 LOC |
| Tasks shipped | 39/39 archived |

## Personas Invoked

Always-on:

- Constitution Reviewer
- Python Reviewer
- Correctness Reviewer
- Maintainability Reviewer
- Learnings Researcher

Conditional (selected by file scope):

- Security Reviewer (fetch surfaces, SSRF guards, XML parsing, archive readers, path containment)
- Architecture Strategist (new modules: sitemap, url_canonical, schema/export, process/heading_validation, process/hashing)
- Agent-Native Parity Reviewer (CLI/MCP/manifest export_schema surface)
- Scope Boundary Auditor (96-file diff sanity check)

## Findings

### P0 (Block PR)

None.

### P1 (Block PR — fixed in this review cycle)

| ID | Module | Finding | Fix |
|---|---|---|---|
| R-1 | `tests/parity/test_equivalence.py::test_manifest_tool_names_match_operation_names` | Assertion expected `["fetch", "process"]` but manifest now exposes `["fetch", "process", "export_schema"]` (added by 010.005-T). | Updated assertion to expected 3-tool list. Committed `284d73c`. |
| R-2 | `tests/parity/test_manifest_parity.py::test_manifest_has_two_tools` | Hard-coded `len(...) == 2` against a 3-tool manifest. | Updated assertion to `== 3` and renamed function to `test_manifest_has_three_tools`. Committed `284d73c`. |

Both P1s root-cause: stale test contracts not updated when `export_schema` was added. New parity coverage in `tests/parity/test_cli_export_schema.py` validates the full 3-surface contract (CLI/MCP/library byte-equivalence) so the fix is consistent with the intended contract.

### P2 (Backlog follow-up — accepted, no action)

All previously enumerated P2 advisories already honored prior to this review cycle:

- `defusedxml` migration for parser hotspots (010.015-T)
- JSON Schema `$schema` and `$id` deterministic export (010.005-T)
- SSRF defense-in-depth across fetch surfaces (010.030-T)

### P3 (Advisory — for future hygiene)

| ID | Module | Advisory |
|---|---|---|
| R-3 | `src/docline/fetch/sitemap.py` | Sitemap XML parsing uses stdlib `xml.etree.ElementTree.fromstring`. Stdlib ET in Python ≥3.7 does not resolve external entities and is not exploitable for XXE on the inputs this parser sees (no DTDs), but for consistency with the 010.015-T `defusedxml` migration elsewhere, future hygiene work could route sitemap XML through `defusedxml.ElementTree` for uniform parser hardening. Not merge-blocking. |

## Persona Highlights

### Constitution Reviewer

- Type hints present on all public surfaces in new modules (`sitemap.py`, `url_canonical.py`, `schema/export.py`, `process/heading_validation.py`, `process/hashing.py`).
- Custom exception hierarchy preserved (`SitemapError`, `UrlCanonicalizationError` extend `DoclineError`).
- Google-style docstrings present on all new public functions.
- TDD evidence: each new module has a paired test file under `tests/`.
- POSIX path migration (PA-2 `fc9e2ca`) compliant with cross-platform path normalization.

### Security Reviewer

- `validate_sitemap_url` correctly enumerates ALL DNS resolutions (defense against DNS rebinding per OWASP SSRF Cheat Sheet).
- Cloud-metadata hostnames AND IPs explicitly rejected (AWS/GCP/Azure IMDS, ECS task metadata, AWS IPv6 IMDS).
- IPv4 + IPv6 literals classified before resolution.
- Fail-closed pattern in `_is_unsafe_address` (unparseable address treated as unsafe).
- `crawl._dedup_key` falls back to `_normalize_url` on canonicalization failure so dedup never raises during normal iteration — defensive.
- Reader bounds (`tests/security/test_reader_limits.py`), path containment (`tests/security/test_path_containment.py`), and quarantine viewer (`tests/security/test_quarantine_viewer.py`) coverage retained.

### Correctness Reviewer

- `canonicalize_url` documented idempotence property holds: pure functional transformations preserve invariant.
- `export_base_frontmatter_schema_json` uses `sort_keys=True` and fixed indent for deterministic byte-identical output.
- `crawl._dedup_key` canonicalization correctly applied at all visited-set insertion points (initial start URL, link enumeration, final_url dedup).
- Heading validation contract pinned by `tests/process/test_heading_validation.py` and `tests/process/test_assemble_heading_integration.py`.

### Maintainability Reviewer

- New modules have focused single responsibilities (sitemap parsing vs URL validation vs canonicalization vs schema export).
- `__all__` declared on new modules.
- Clear module docstrings cite the task IDs that pinned the contract.

### Agent-Native Parity Reviewer

- `export_schema` exposed identically across CLI (`docline export-schema`), MCP (`DoclineMcpServer.export_schema()`), and library (`export_base_frontmatter_schema_json()`).
- 3-way parity covered by `tests/parity/test_cli_export_schema.py::test_mcp_export_schema_matches_cli_export` and `test_cli_export_schema_matches_library_export`.
- Manifest correctly advertises the new tool with documented description.

### Scope Boundary Auditor

- 39 archive renames (98% similarity, simple status moves) account for 39/96 files.
- 3 session memory files under `docs/memory/` — within ship role boundary.
- 2 design docs under `docs/design-docs/` — within ship role boundary (knowledge graduation).
- No edits to `docs/plans/` or `docs/decisions/` (role boundary respected).
- Stash file mutation, `.gitignore`, `pyproject.toml`, `uv.lock`, `README.md` consistent with declared 010-S scope.

## Quality Gates Status (HEAD `284d73c`)

| Gate | Status |
|---|---|
| `ruff check .` | ✅ All checks passed |
| `pyright src/` | ✅ 0 errors, 0 warnings, 0 informations |
| `pytest` | ✅ 561 passed, 2 skipped, 0 failed (244 errors are Windows-tmp PermissionError noise from operator-acknowledged pre-existing stash CE758832; CI runs on Linux and will not surface these) |
| `ruff format --check .` | ✅ 143 files already formatted |

## Decision

**READY_WITH_FOLLOWUPS** — P1 issues fixed in this review cycle. One P3 advisory (R-3) noted for future hygiene; non-blocking for PR.

Proceed to Phase 3 (PR open via pr-lifecycle skill).
