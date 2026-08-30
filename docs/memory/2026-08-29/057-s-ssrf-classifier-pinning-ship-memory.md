---
title: "Session memory: shipping 057-S SSRF classifier + pinning"
date: 2026-08-29
agent: ship
shipment: 057-S
status: complete
---

## Outcome

Shipment 057-S shipped end to end in dark-factory mode: seven tasks built with observed
red-before-green TDD, four-persona adversarial review, three Copilot review cycles, merged via
merge commit `b89c902`, runtime-verified post-merge, and archived with traceability.

## Task IDs completed

`066.001-T`, `066.007-T`, `066.002-T`, `066.003-T`, `066.004-T`, `066.005-T`, `066.006-T`, and
parent feature `066-F`. All archived under shipment `057-S`.

## Files modified

* `src/docline/fetch/url_policy.py` — canonical classifier; `_SITE_LOCAL_NETWORK`; metadata set
  as parsed objects compared post-normalization; `is_private_host` delegates.
* `src/docline/fetch/sitemap.py` — duplicate predicate and constants deleted; `fetch_sitemap`
  added; `validate_sitemap_url` redocumented as a non-authoritative preflight.
* `tests/fetch/test_ssrf_address_parity.py`, `tests/fetch/test_ssrf_metadata_gate.py`,
  `tests/fetch/test_sitemap_pinned_sink.py` — new.
* `tests/fetch/test_sitemap.py` — repointed off the deleted private symbol.
* `pyproject.toml`, `uv.lock` — runtime floor.

## Decisions and rationale

* **CVE-2024-4032 handled by runtime floor, not prefix rejection.** The affected prefixes retain
  globally-reachable exceptions; a blanket reject would break valid destinations. Verified
  empirically that all eight exception literals classify as `is_global` under 3.12.10.
* **Width-isolation deviation accepted in `62dfbcd`.** That src-only task also touched
  `tests/fetch/test_sitemap.py` because it deleted the private symbol the test imported. Leaving
  it broken would have made the next red-harness commit uncompilable. The Scope auditor reviewed
  this explicitly and judged it minimal and correct.
* **Preflight deadline test measures inside the event loop.** The abandoned resolver thread is
  not cancellable and `asyncio.run` joins it at shutdown, so measuring around `asyncio.run` timed
  loop teardown rather than the deadline. This mirrors a property already documented for
  `fetch_page`.

## Failed approaches

* `uv sync` in the fresh worktree could not complete — repeated TLS `HandshakeFailure` against
  `files.pythonhosted.org` across ~45 retry attempts, both online and `--offline`. **Workaround
  that worked**: borrow the fully-synced sibling worktree interpreter
  (`...a4875141.../worktree-055s/.venv/Scripts/python.exe`) and override `PYTHONPATH` to this
  worktree's `src`. Verified the override takes precedence over the sibling's editable install
  before trusting any result.
* Local `ruff` 0.16.4 reported 11 pre-existing docs files as unformatted; CI pins 0.15.15. Used
  the primary worktree's `.venv\Scripts\ruff.exe` (0.15.15) as a read-only tool runner to match
  CI exactly. `uvx ruff@0.15.15` also failed on the same network issue.
* First attempt at `backlogit move ... --status done` was rejected: the lifecycle hook requires
  `queued -> active -> done`.

## Open questions

* Double DNS resolution in `fetch_sitemap` (Security P3 / Architecture P2). Candidate stash
  entry: reduce `validate_sitemap_url` to scheme/host/IP-literal checks and leave resolution
  solely to `fetch_page`.

## Next steps

058-S is queued and explicitly **not** claimed this session.
