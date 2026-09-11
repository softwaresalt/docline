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
_TFE_DATE_PARSE_RE = re.compile(r"^v(?P<yyyymm>[0-9]{6})-(?P<rev>\d+)$", re.IGNORECASE)
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


def _tfe_date_sort_key(base: str) -> tuple[int, int]:
    """Numeric ``(YYYYMM, revision)`` sort key for a ``vYYYYMM-N`` directory name.

    GROUNDING NOTE (live-corpus correction): the previous implementation
    sorted this group with a plain descending *alphabetical* comparison
    on the raw string (``strip_release_stage(raw)[0].lower()``). That is
    lexical, not numeric: the string ``"v202507-9"`` sorts ABOVE
    ``"v202507-10"`` alphabetically (``"9" > "1"`` at the first
    differing character), even though ``-10`` is the later revision
    numerically. Terraform Enterprise's real ``vYYYYMM-N`` history
    accumulates well past nine same-month revisions, so this bug is a
    live correctness defect, not a synthetic edge case. Parsing both the
    ``YYYYMM`` and revision components as integers and comparing the
    resulting tuple sorts every revision count correctly regardless of
    digit-length, while leaving the deliberate semver-group-sorts-first
    mixed-family rule (see the module docstring's terraform-enterprise
    ``2.0.x`` finding) completely untouched -- this only changes how the
    date-pattern group orders *itself* internally.
    """
    match = _TFE_DATE_PARSE_RE.match(base)
    if not match:
        return (0, 0)
    return (int(match.group("yyyymm")), int(match.group("rev")))


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
       Terraform-Enterprise-date-pattern group (descending NUMERIC sort
       on the parsed ``(YYYYMM, revision)`` pair -- see
       :func:`_tfe_date_sort_key`; a lexical string sort would rank
       ``v202507-9`` above ``v202507-10``), then concatenate
       semver-sortable first -- this reproduces the upstream tool's
       "semver directories are more recent" ordering assumption when a
       product's directories are a mix of both shapes.
    3. Exactly ONE entry is ``is_latest``: the FIRST entry (in the
       combined descending order above) whose release stage is
       ``"stable"``. If no entry is stable at all, the first entry in
       that order (index 0, the highest-sorted candidate regardless of
       release stage) is ``is_latest`` instead.

    GROUNDING NOTE (review-fix cycle 2, P3 correctness finding): the
    previous implementation computed ``is_latest`` with a running
    "latest index" cursor that incremented once per non-stable entry
    and compared it against the current loop index on every iteration.
    That could flag a SECOND entry as latest: once the highest-sorted
    entry was stable (cursor stays at 0, matches index 0), a
    lower-ranked non-stable entry immediately following it would
    increment the cursor to 1 and then find ``idx == cursor`` true
    again at index 1 -- e.g. ``["v3.x" (stable), "v3.x (rc)", "v2.x"]``
    flagged BOTH ``"v3.x"`` and ``"v3.x (rc)"`` as latest. This
    implementation instead computes the single first-stable-or-fallback
    index up front and marks that ONE index true, guaranteeing exactly
    one ``is_latest`` entry whenever the input is non-empty.
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
    nonsemver_group.sort(
        key=lambda raw: _tfe_date_sort_key(strip_release_stage(raw)[0]), reverse=True
    )
    ordered = semver_group + nonsemver_group
    parsed = [(raw, *strip_release_stage(raw)) for raw in ordered]

    latest_index: int | None = next(
        (idx for idx, (_raw, _base, stage) in enumerate(parsed) if stage == "stable"), None
    )
    if latest_index is None and parsed:
        latest_index = 0

    return [
        VersionEntry(
            raw_name=raw,
            clean_version=base,
            release_stage=stage,
            is_latest=idx == latest_index,
        )
        for idx, (raw, base, stage) in enumerate(parsed)
    ]


def select_latest_version(raw_dir_names: Iterable[str]) -> str | None:
    """Return the raw directory name selected as "latest", or ``None`` if empty."""
    entries = list_version_entries(raw_dir_names)
    for entry in entries:
        if entry.is_latest:
            return entry.raw_name
    return None
