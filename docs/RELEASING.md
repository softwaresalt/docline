# Releasing docline

docline publishes to [PyPI](https://pypi.org/p/docline) through a tag-driven
GitHub Actions pipeline (`.github/workflows/release.yml`). This document covers
the version scheme, the one-time setup, and the steps to cut a release.

## Version scheme

docline follows [Semantic Versioning](https://semver.org/). The version lives
in `pyproject.toml` (`[project] version`).

The first public release is **`0.1.0`**. A `0.x` series signals that the public
API (CLI flags, MCP tool contract, frontmatter schema) may still evolve between
minor versions; breaking changes bump the minor while the major stays `0`. Once
the surface is considered stable, cut `1.0.0`.

## One-time setup

Both steps below are configured once by a repository administrator before the
first release.

### 1. PyPI Trusted Publisher

The pipeline authenticates to PyPI with OIDC (Trusted Publishing) — no API token
is stored in the repository. Register the publisher on PyPI:

1. Sign in to PyPI and open **Your projects → docline → Settings → Publishing**
   (or, for the very first release before the project exists, **Account
   settings → Publishing → Add a pending publisher**).
2. Add a **GitHub** trusted publisher with:
   - Owner: `softwaresalt`
   - Repository: `docline`
   - Workflow name: `release.yml`
   - Environment: `pypi`

If Trusted Publishing is unavailable, the alternative is a scoped PyPI API token
stored as a repository secret and consumed by `pypa/gh-action-pypi-publish`;
Trusted Publishing is preferred because it removes long-lived credentials.

### 2. `pypi` GitHub Environment

Create a GitHub Environment named `pypi` (**Settings → Environments → New
environment**). The `publish-pypi` job runs in this environment; add required
reviewers or a deployment-branch rule here if you want a manual approval gate
before each publish.

## Cutting a release

1. Ensure `main` is green and up to date.
2. Set the release version in `pyproject.toml` if it needs to change, commit it
   through the normal PR flow, and merge to `main`.
3. Tag the release commit and push the tag:

   ```bash
   git switch main && git pull
   git tag v0.1.0
   git push origin v0.1.0
   ```

The tag push triggers `release.yml`, which:

1. **gate** — runs `ruff check`, `ruff format --check`, `pyright src/`, and
   `pytest`.
2. **build** — verifies the tag matches the `pyproject.toml` version, then
   builds the sdist and wheel with `python -m build`.
3. **publish-pypi** — publishes the artifacts to PyPI via Trusted Publishing.
4. **github-release** — creates a GitHub Release for the tag with the artifacts
   attached and auto-generated notes.

The tag (`vX.Y.Z`) and the `pyproject.toml` version (`X.Y.Z`) must match; the
build job fails fast otherwise, so a mistagged release never publishes.

## Verifying a release

After the workflow completes:

- Confirm the version appears on <https://pypi.org/p/docline>.
- Confirm the GitHub Release was created under **Releases**.
- Smoke-test the install: `pip install docline==X.Y.Z && docline --manifest`.
