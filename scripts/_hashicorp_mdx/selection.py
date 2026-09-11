"""Product classification + latest-version selection for the HashiCorp
unified-docs MDX->MD normalization preprocessor (071-F / 062-S).

Ports two decisions from the external unified-docs repo's build tooling,
grounded directly against the real corpus at
``C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs`` (read-only) during
implementation:

* ``productConfig.mjs`` -- decides whether a top-level product directory
  is versioned or unversioned (``PRODUCT_VERSIONED_MAP`` below).
* ``scripts/prebuild/gather-version-metadata.mjs`` -- decides, for a
  versioned product, which version subdirectory is "latest": ``.x``-aware
  semver coercion, descending sort, a release-stage
  ``(beta)``/``(rc)``/``(alpha)`` fallback rule (a non-stable release is
  only "latest" when every candidate is non-stable), and a non-semver
  alphabetical-descending fallback for date-based schemes (Terraform
  Enterprise's historical ``vYYYYMM-N`` releases).

GROUNDING NOTE (compound learning: third-party shape requires live
verification): the live corpus surfaced two corrections to the initial
planning assumptions in
``docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md``:

1. The corpus has 23 product entries (19 ``versionedDocs: true`` + 4
   ``versionedDocs: false``), not "20 versioned" as the plan's A.T1
   acceptance criterion estimated. ``PRODUCT_VERSIONED_MAP`` below is the
   authoritative, individually-verified product map (``global`` is a 24th
   top-level directory that is not a product at all -- it is a partials
   container and is excluded).
2. ``terraform-enterprise`` now has, on top of ~50 legacy date-based
   ``vYYYYMM-N`` version directories, a small number of newer
   ``X.Y.x``-style semver directories (``1.0.x``, ``1.1.x``, ``1.2.x``,
   ``2.0.x``) whose auto-generated ``created_at`` frontmatter metadata
   postdates every ``vYYYYMM-N`` directory (the newest date-based
   release, ``v202507-1``, carries ``created_at: 2025-07-03``; ``2.0.x``
   carries ``created_at: 2026-02-02``). Faithfully porting
   ``gather-version-metadata.mjs`` (which sorts semver-coercible
   directories ahead of non-semver ones as "more recent") therefore
   selects ``2.0.x`` as latest for ``terraform-enterprise`` against the
   REAL corpus, not ``v202507-1`` as the plan's A.T2 acceptance criterion
   assumed. See the requirements-evidence doc and the full-corpus dry-run
   report for the live finding. The synthetic unit-test fixtures in
   ``tests/scripts/test_hashicorp_selection.py`` intentionally model the
   plan's SIMPLER assumed shape (date-based versions only) so the
   literal acceptance-criterion example continues to hold at the unit
   level; ``tests/scripts/test_hashicorp_dryrun_corpus.py`` exercises the
   corrected, live-verified answer against the real corpus separately.

Public API:
    :data:`PRODUCT_VERSIONED_MAP` -- explicit product -> versioned bool map
    :func:`classify_products` -- top-level dir names -> versioned/unversioned/excluded
    :func:`is_valid_version_dirname` -- generic version-dir-coercibility test
    :func:`list_version_entries` -- version directory names -> ordered :class:`VersionEntry` list
    :func:`select_latest_version` -- convenience wrapper returning just the latest raw dir name
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Product classification
# ---------------------------------------------------------------------------

#: Explicit product -> versioned bool map, individually verified against
#: the real corpus's ``productConfig.mjs``-equivalent top-level directory
#: set. ``global`` is deliberately absent: it is not a product, it is the
#: shared partials container and must always be excluded.
PRODUCT_VERSIONED_MAP: dict[str, bool] = {
    # 19 versioned products
    "boundary": True,
    "consul": True,
    "nomad": True,
    "packer": True,
    "sentinel": True,
    "terraform": True,
    "terraform-cdk": True,
    "terraform-docs-agents": True,
    "terraform-enterprise": True,
    "terraform-mcp-server": True,
    "terraform-migrate": True,
    "terraform-plugin-framework": True,
    "terraform-plugin-log": True,
    "terraform-plugin-mux": True,
    "terraform-plugin-sdk": True,
    "terraform-plugin-testing": True,
    "terraform-policy": True,
    "vagrant": True,
    "vault": True,
    # 4 unversioned products
    "hcp-docs": False,
    "terraform-docs-common": False,
    "validated-designs": False,
    "well-architected-framework": False,
}


@dataclass(frozen=True)
class ProductClassification:
    """Result of classifying a set of top-level corpus directory names."""

    versioned: list[str]
    unversioned: list[str]
    excluded: list[str]


def classify_products(top_level_names: Iterable[str]) -> ProductClassification:
    """Split top-level corpus directory names into versioned / unversioned / excluded.

    ``excluded`` covers both the known non-product ``global`` partials
    container and any unrecognized directory name -- unrecognized names
    are reported, never silently dropped without trace, so the CLI's
    report surfaces them as an operator-visible warning.
    """
    versioned: list[str] = []
    unversioned: list[str] = []
    excluded: list[str] = []
    for name in top_level_names:
        is_versioned = PRODUCT_VERSIONED_MAP.get(name)
        if is_versioned is True:
            versioned.append(name)
        elif is_versioned is False:
            unversioned.append(name)
        else:
            excluded.append(name)
    return ProductClassification(
        versioned=sorted(versioned),
        unversioned=sorted(unversioned),
        excluded=sorted(excluded),
    )


# ---------------------------------------------------------------------------
# Version directory parsing
# ---------------------------------------------------------------------------

_RELEASE_STAGE_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<stage>alpha|beta|rc)\)$", re.IGNORECASE)
_TFE_DATE_RE = re.compile(r"^v[0-9]{6}-\d+$", re.IGNORECASE)
_TRAILING_X_RE = re.compile(r"\.x$", re.IGNORECASE)
_COERCE_RE = re.compile(r"(\d{1,6})(?:\.(\d{1,6}))?(?:\.(\d{1,6}))?")


def strip_release_stage(name: str) -> tuple[str, str]:
    """Split ``"v0.2.x (beta)"`` into ``("v0.2.x", "beta")``; else ``(name, "stable")``."""
    match = _RELEASE_STAGE_RE.match(name.strip())
    if match:
        return match.group("base").strip(), match.group("stage").lower()
    return name.strip(), "stable"


def _normalize_for_semver(base: str) -> str:
    """Rewrite a trailing ``.x`` component to ``.0`` so it coerces to semver."""
    return _TRAILING_X_RE.sub(".0", base)


def _coerce_semver(token: str) -> tuple[int, int, int] | None:
    """Loose semver coercion: extract the first ``major[.minor[.patch]]`` run."""
    match = _COERCE_RE.search(token)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


def is_valid_version_dirname(raw_name: str) -> bool:
    """Generic version-directory test: does this name coerce to a version?

    This mirrors the upstream ``rawVersions`` filter
    (``semver.valid(semver.coerce(name))``) and is what excludes
    non-version directories (``templates``, ``global``, ``releases``,
    ``scripts``, ``partials``, ...) WITHOUT a per-product hardcoded
    exclusion list.
    """
    base, _stage = strip_release_stage(raw_name)
    return _coerce_semver(base) is not None


def _is_tfe_date_pattern(base: str) -> bool:
    """True for Terraform Enterprise's historical ``vYYYYMM-N`` scheme."""
    return bool(_TFE_DATE_RE.match(base))


def _semver_sort_key(base: str) -> tuple[int, int, int]:
    normalized = _normalize_for_semver(base)
    return _coerce_semver(normalized) or (0, 0, 0)


# ---------------------------------------------------------------------------
# Latest-version selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionEntry:
    """One version directory plus its derived selection metadata."""

    raw_name: str
    clean_version: str
    release_stage: str
    is_latest: bool


def list_version_entries(raw_dir_names: Iterable[str]) -> list[VersionEntry]:
    """Return every valid version directory, ordered latest-first, with ``is_latest`` flags.

    Faithful port of ``gather-version-metadata.mjs``'s ``isLatest``
    algorithm:

    1. Filter to directory names that coerce to a version at all
       (excludes ``templates``, ``global``, ``releases``, ``scripts``,
       ``partials``, and any other non-version directory generically).
    2. Split into a semver-sortable group (descending numeric sort) and a
       Terraform-Enterprise-date-pattern group (descending alphabetical
       sort), then concatenate semver-sortable first -- this reproduces
       the upstream tool's "semver directories are more recent" ordering
       assumption when a product's directories are a mix of both shapes.
    3. Walk the combined order, incrementing a "latest index" cursor past
       every non-stable (``alpha``/``beta``/``rc``) entry; the entry
       whose position matches the cursor is ``is_latest``.
    4. Fallback: if no entry ends up marked latest (i.e. every candidate
       is non-stable), the highest-sorted entry (index 0) is latest
       regardless of release stage.
    """
    candidates = [name for name in raw_dir_names if is_valid_version_dirname(name)]

    semver_group: list[str] = []
    nonsemver_group: list[str] = []
    for raw in candidates:
        base, _stage = strip_release_stage(raw)
        if _is_tfe_date_pattern(base):
            nonsemver_group.append(raw)
        else:
            semver_group.append(raw)

    semver_group.sort(key=lambda raw: _semver_sort_key(strip_release_stage(raw)[0]), reverse=True)
    nonsemver_group.sort(key=lambda raw: strip_release_stage(raw)[0].lower(), reverse=True)
    ordered = semver_group + nonsemver_group

    entries: list[VersionEntry] = []
    latest_index = 0
    any_latest = False
    for idx, raw in enumerate(ordered):
        base, stage = strip_release_stage(raw)
        if stage != "stable":
            latest_index += 1
        is_latest = idx == latest_index
        if is_latest:
            any_latest = True
        entries.append(
            VersionEntry(raw_name=raw, clean_version=base, release_stage=stage, is_latest=is_latest)
        )

    if not any_latest and entries:
        first = entries[0]
        entries[0] = VersionEntry(
            raw_name=first.raw_name,
            clean_version=first.clean_version,
            release_stage=first.release_stage,
            is_latest=True,
        )

    return entries


def select_latest_version(raw_dir_names: Iterable[str]) -> str | None:
    """Return the raw directory name selected as "latest", or ``None`` if empty."""
    entries = list_version_entries(raw_dir_names)
    for entry in entries:
        if entry.is_latest:
            return entry.raw_name
    return None
