---
title: "Closure — final stash follow-ups (crawl scope, HTML fidelity) + release setup"
status: verified
items: [5A27C137, B0A77532, 7AA9FAA0]
merged_prs: [151, 152, 153]
merge_shas: [a05028c, 103a167, 1ae921a]
date: 2026-07-06
---

Cleared the last actionable stash entries and stood up the release pipeline so
docline can publish to PyPI. Three focused PRs, each adversarially reviewed with
Copilot review resolved before merge.

## 5A27C137 — crawl section-scope full prefix (PR #151, `a05028c`)

`crawl._derive_section_scope` scoped to only the first path segment (`/docs/`)
instead of the full start-path directory prefix (`/docs/current/`), so a crawl
of a sub-path followed sibling links into other subsections — during the
PostgreSQL ingest it wandered across ~30 `/docs/<version>/` trees. It now returns
the full directory prefix (directory URL → itself; file URL → parent dir; bare
root / ambiguous extensionless path → no scope). This removes the local
workaround used during the PostgreSQL operational run. 6 new tests, including an
integration crawl proving `/docs/10/` links are not followed from `/docs/current/`.

## B0A77532 — HTML-extraction fidelity follow-ups (PR #152, `103a167`)

Five improvements to fetched-HTML → Markdown fidelity:

- `<dl>/<dt>/<dd>` definition lists render as bold term + description (e.g.
  PostgreSQL parameter lists) instead of flattened text.
- table `colspan`/`rowspan` expand by repeating spanned cells (no data loss).
- `<pre>`/`<code>` with a `language-*`-style class emit a language-tagged fence.
- web sources without a Learn `publish_config` get `docline:canonical_url` = the
  fetched URL.
- `FetchRequest.max_pages` exposes the single-shot crawl page budget.

7 new tests; verified on real PostgreSQL `sql-select.html` (6 definition-list
terms, 72 code fences preserved, canonical_url stamped). A `page_metadata is
None` crash on local-dir ingests was caught by the full suite and guarded.

## 7AA9FAA0 — tag-driven PyPI release workflow (PR #153, `1ae921a`)

`.github/workflows/release.yml` runs on a `v*` tag: quality gates → build (with a
tag-vs-`pyproject` version check) → PyPI publish via Trusted Publishing (OIDC, no
stored token, in a `pypi` GitHub Environment) → GitHub Release with artifacts and
generated notes. Actions are SHA-pinned with precise version comments and
permissions are least-privilege. `ci.yml` dropped its `v*`/`release` triggers so
CI is not duplicated on release. `docs/RELEASING.md` documents the version scheme,
one-time PyPI/environment setup, and the cut-a-release steps.

**First release version: `0.1.0`** — SemVer pre-1.0 for an evolving public
surface; matches `pyproject.toml`. Cut with `git tag v0.1.0 && git push origin v0.1.0`.

## Operator action required before the first release

Register the PyPI Trusted Publisher (owner `softwaresalt`, repo `docline`,
workflow `release.yml`, environment `pypi`) and create the `pypi` GitHub
Environment. Both are PyPI-/GitHub-side and cannot be automated from the repo;
see `docs/RELEASING.md`.

## Backlog state

Queue empty. Remaining stash entries all require external resources (Azure
Foundry credentials, GPU hardware, or specific document corpora) or are
speculative deferrals — none are autonomously actionable.
