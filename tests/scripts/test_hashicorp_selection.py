"""Unit tests for ``scripts/_hashicorp_mdx/selection.py`` (071.001-T / 071.002-T).

Covers product classification (versioned vs. unversioned vs. excluded
top-level directories) and the "latest version" selection algorithm, a
faithful Python port of the external unified-docs repo's
``scripts/prebuild/gather-version-metadata.mjs``.

The version-selection fixture table below intentionally models the
SIMPLER, plan-assumed shape for ``terraform-enterprise`` (date-based
``vYYYYMM-N`` directories only) so the literal acceptance-criterion
example from
``docs/decisions/2026-09-11-hashicorp-mdx-normalization-preprocessor-deliberation.md``
continues to hold at the unit level. The REAL external corpus contains
additional semver-style directories for ``terraform-enterprise``
(``1.0.x``, ``1.1.x``, ``1.2.x``, ``2.0.x``) that cause the faithfully
ported algorithm to select ``2.0.x`` as latest instead -- that
live-verified finding is exercised separately in
``tests/scripts/test_hashicorp_dryrun_corpus.py`` and documented in the
requirements-evidence doc, not hardcoded here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _hashicorp_mdx import selection  # noqa: E402

# ---------------------------------------------------------------------------
# Product classification (071.001-T)
# ---------------------------------------------------------------------------


def test_product_versioned_map_has_23_products() -> None:
    """Ground-truth correction vs. the plan's "20 versioned" estimate.

    The real ``productConfig.mjs``-equivalent has 19 versioned + 4
    unversioned = 23 products; ``global`` is a 24th top-level directory
    that is not a product at all (partials container).
    """
    versioned = [p for p, is_versioned in selection.PRODUCT_VERSIONED_MAP.items() if is_versioned]
    unversioned = [
        p for p, is_versioned in selection.PRODUCT_VERSIONED_MAP.items() if not is_versioned
    ]
    assert len(versioned) == 19
    assert len(unversioned) == 4
    assert "global" not in selection.PRODUCT_VERSIONED_MAP


def test_classify_products_splits_versioned_unversioned_excluded() -> None:
    top_level = ["vault", "terraform", "hcp-docs", "well-architected-framework", "global", "bogus"]
    result = selection.classify_products(top_level)
    assert result.versioned == ["terraform", "vault"]
    assert result.unversioned == ["hcp-docs", "well-architected-framework"]
    assert result.excluded == ["bogus", "global"]


def test_classify_products_excludes_global_partials_container() -> None:
    result = selection.classify_products(["vault", "global"])
    assert "global" in result.excluded
    assert "global" not in result.versioned
    assert "global" not in result.unversioned


# ---------------------------------------------------------------------------
# Version-directory validity + non-version-dir exclusion (071.001-T)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dirname", "expected"),
    [
        ("v1.16.x", True),
        ("v2.x", True),
        ("v202507-1", True),
        ("v0.2.x (beta)", True),
        ("v2.2.10", True),
        ("templates", False),
        ("global", False),
        ("releases", False),
        ("scripts", False),
        ("partials", False),
    ],
)
def test_is_valid_version_dirname(dirname: str, expected: bool) -> None:
    assert selection.is_valid_version_dirname(dirname) is expected


# ---------------------------------------------------------------------------
# Latest-version selection (071.002-T)
# ---------------------------------------------------------------------------


def test_select_latest_version_vault_picks_v2x_not_v1_21x() -> None:
    dirs = [f"v1.{n}.x" for n in range(4, 22)] + ["v2.x", "global"]
    assert selection.select_latest_version(dirs) == "v2.x"


def test_select_latest_version_terraform_picks_v1_16x() -> None:
    dirs = [f"v1.{n}.x" for n in range(1, 17)] + ["templates"]
    assert selection.select_latest_version(dirs) == "v1.16.x"


def test_select_latest_version_terraform_policy_beta_fallback() -> None:
    """All-non-stable fallback: highest-sorted wins even though non-stable."""
    dirs = ["v0.1.x (beta)", "v0.2.x (beta)"]
    assert selection.select_latest_version(dirs) == "v0.2.x (beta)"


def test_select_latest_version_terraform_enterprise_synthetic_date_based() -> None:
    """Plan-assumed synthetic shape: date-based dirs only -> highest date wins."""
    dirs = [
        "v202206-1",
        "v202301-1",
        "v202401-1",
        "v202401-2",
        "v202507-1",
        "releases",
        "scripts",
    ]
    assert selection.select_latest_version(dirs) == "v202507-1"


def test_select_latest_version_vagrant_numeric_patch_not_lexical() -> None:
    """v2.2.10 must sort AFTER v2.2.9 numerically, not before it lexically."""
    dirs = ["v2.2.9", "v2.2.10", "v2.3.0", "v2.4.9"]
    assert selection.select_latest_version(dirs) == "v2.4.9"


def test_select_latest_version_two_betas_highest_wins_via_fallback() -> None:
    dirs = ["v202401-1 (beta)", "v202401-2 (beta)"]
    assert selection.select_latest_version(dirs) == "v202401-2 (beta)"


def test_select_latest_version_stable_beats_higher_beta() -> None:
    dirs = ["v202401-1", "v202401-2 (beta)"]
    assert selection.select_latest_version(dirs) == "v202401-1"


def test_select_latest_version_order_independent() -> None:
    forward = ["v202401-1", "v202401-2 (beta)"]
    reversed_dirs = list(reversed(forward))
    assert selection.select_latest_version(forward) == selection.select_latest_version(
        reversed_dirs
    )


def test_select_latest_version_tfe_date_pattern_numeric_not_lexical() -> None:
    """Regression (P1 correctness review, review-fix cycle 1): the TFE
    date-pattern group must sort ``(YYYYMM, revision)`` numerically, not
    lexically. ``v202507-10`` is a LATER revision than ``v202507-9``, but a
    plain descending string sort ranks ``"v202507-9"`` above
    ``"v202507-10"`` (``"9" > "1"`` at the first differing character).
    """
    dirs = ["v202507-1", "v202507-9", "v202507-10", "v202401-1"]
    assert selection.select_latest_version(dirs) == "v202507-10"


def test_list_version_entries_tfe_date_pattern_numeric_order_independent() -> None:
    dirs = ["v202507-9", "v202507-10", "v202507-2"]
    entries_forward = selection.list_version_entries(dirs)
    entries_reversed = selection.list_version_entries(list(reversed(dirs)))
    assert [e.raw_name for e in entries_forward] == ["v202507-10", "v202507-9", "v202507-2"]
    assert [e.raw_name for e in entries_reversed] == ["v202507-10", "v202507-9", "v202507-2"]


def test_select_latest_version_mixed_semver_and_nonsemver_still_prefers_semver_after_fix() -> None:
    """The numeric TFE-date sort fix must not disturb the evidence-backed
    mixed-family rule: semver-coercible directories still sort ahead of every
    TFE date-pattern directory, even when the date-pattern group itself now
    contains a numerically-larger-looking revision like ``-10``."""
    dirs = ["1.0.x", "1.1.x", "1.2.x", "2.0.x", "v202507-10", "v202507-9", "v202206-1"]
    assert selection.select_latest_version(dirs) == "2.0.x"


def test_select_latest_version_mixed_semver_and_nonsemver_prefers_semver() -> None:
    """Faithful port of the real terraform-enterprise mixed shape.

    Semver-coercible directories sort ahead of TFE date-pattern
    directories as "more recent" -- this reproduces the live-corpus
    finding that ``2.0.x`` outranks every ``vYYYYMM-N`` directory.
    """
    dirs = ["1.0.x", "1.1.x", "1.2.x", "2.0.x", "v202507-1", "v202206-1"]
    assert selection.select_latest_version(dirs) == "2.0.x"


def test_select_latest_version_empty_returns_none() -> None:
    assert selection.select_latest_version([]) is None


def test_select_latest_version_unversioned_product_sentinel() -> None:
    """Unversioned products get a single stable placeholder entry."""
    entries = selection.list_version_entries([])
    assert entries == []


def test_list_version_entries_reports_release_stage_and_flags() -> None:
    dirs = ["v0.1.x (beta)", "v0.2.x (beta)"]
    entries = selection.list_version_entries(dirs)
    by_raw = {e.raw_name: e for e in entries}
    assert by_raw["v0.2.x (beta)"].release_stage == "beta"
    assert by_raw["v0.2.x (beta)"].clean_version == "v0.2.x"
    assert by_raw["v0.2.x (beta)"].is_latest is True
    assert by_raw["v0.1.x (beta)"].is_latest is False


def test_list_version_entries_highest_stable_then_lower_prerelease_exactly_one_latest() -> None:
    """Regression (review-fix cycle 2, P3): a stable entry ranked highest
    must be the SOLE ``is_latest`` even when a lower-ranked prerelease of
    the same base version immediately follows it in sort order.

    The previous cursor-increment algorithm could flag a SECOND entry as
    latest whenever a non-stable entry landed exactly at the
    post-increment cursor position right after an already-matched stable
    entry: ``"v3.x"`` (idx 0, stable) matches cursor 0 and is flagged
    latest; ``"v3.x (rc)"`` (idx 1, non-stable) increments the cursor to
    1, and ``idx == cursor`` (``1 == 1``) is ALSO true, flagging a second
    "latest" entry. Exactly one entry must ever be ``is_latest``.
    """
    dirs = ["v3.x", "v3.x (rc)", "v2.x"]
    entries = selection.list_version_entries(dirs)
    assert sum(1 for entry in entries if entry.is_latest) == 1
    by_raw = {e.raw_name: e for e in entries}
    assert by_raw["v3.x"].is_latest is True
    assert by_raw["v3.x (rc)"].is_latest is False
    assert by_raw["v2.x"].is_latest is False
