"""Tests for ``docline.process.canonical_url`` (task 044.001-T)."""

from __future__ import annotations

from typing import Any

import pytest

_CONFIG: dict[str, Any] = {
    "docsets_to_publish": [
        {"docset_name": "fabric", "build_source_folder": "docs", "url_path_prefix": "/fabric"},
        {
            "docset_name": "pbi",
            "build_source_folder": "powerbi-docs",
            "url_path_prefix": "/power-bi",
        },
    ]
}


@pytest.mark.parametrize(
    "source_rel_path,expected",
    [
        ("docs/admin/foo.md", "/fabric/admin/foo"),
        ("docs/admin/index.md", "/fabric/admin"),
        ("docs/index.md", "/fabric"),
        ("powerbi-docs/create/report.md", "/power-bi/create/report"),
        ("docs/Admin/Foo.md", "/fabric/admin/foo"),  # canonical URLs are lowercase
    ],
)
def test_derive_canonical_url_maps_docset_paths(source_rel_path: str, expected: str) -> None:
    from docline.process.canonical_url import derive_canonical_url

    assert derive_canonical_url(_CONFIG, source_rel_path) == expected


def test_derive_canonical_url_returns_none_for_unmatched_path() -> None:
    from docline.process.canonical_url import derive_canonical_url

    assert derive_canonical_url(_CONFIG, "other/thing.md") is None


def test_derive_canonical_url_returns_none_when_prefix_missing() -> None:
    from docline.process.canonical_url import derive_canonical_url

    cfg = {"docsets_to_publish": [{"docset_name": "x", "build_source_folder": "docs"}]}
    assert derive_canonical_url(cfg, "docs/a.md") is None


def test_derive_canonical_url_longest_build_source_folder_wins() -> None:
    from docline.process.canonical_url import derive_canonical_url

    cfg = {
        "docsets_to_publish": [
            {"docset_name": "outer", "build_source_folder": "docs", "url_path_prefix": "/outer"},
            {
                "docset_name": "inner",
                "build_source_folder": "docs/sub",
                "url_path_prefix": "/inner",
            },
        ]
    }
    assert derive_canonical_url(cfg, "docs/sub/page.md") == "/inner/page"
    assert derive_canonical_url(cfg, "docs/top.md") == "/outer/top"


def test_derive_canonical_url_handles_backslash_paths() -> None:
    from docline.process.canonical_url import derive_canonical_url

    assert derive_canonical_url(_CONFIG, "docs\\admin\\foo.md") == "/fabric/admin/foo"


def test_derive_canonical_url_empty_config_is_none() -> None:
    from docline.process.canonical_url import derive_canonical_url

    assert derive_canonical_url({}, "docs/a.md") is None


def test_derive_canonical_url_longest_match_without_prefix_returns_none() -> None:
    """A more-specific docset without a prefix must yield None, not a wrong prefix."""
    from docline.process.canonical_url import derive_canonical_url

    cfg = {
        "docsets_to_publish": [
            {"docset_name": "inner", "build_source_folder": "docs/sub"},  # no url_path_prefix
            {"docset_name": "outer", "build_source_folder": "docs", "url_path_prefix": "/outer"},
        ]
    }
    # docs/sub/page.md's most-specific docset lacks a prefix -> None (not /outer/sub/page).
    assert derive_canonical_url(cfg, "docs/sub/page.md") is None
    # A path outside the prefix-less docset still resolves via the outer docset.
    assert derive_canonical_url(cfg, "docs/top.md") == "/outer/top"


# --- 046.001-T: breadcrumb-path prefix derivation + optional prefix map ------


def _docfx(breadcrumb: str | None) -> dict:
    gm = {"breadcrumb_path": breadcrumb} if breadcrumb is not None else {}
    return {"build": {"globalMetadata": gm}}


def test_derive_url_prefix_from_absolute_breadcrumb() -> None:
    from docline.process.canonical_url import derive_url_prefix

    assert derive_url_prefix(_docfx("/dax/breadcrumb/toc.json")) == "/dax"
    assert derive_url_prefix(_docfx("/azure/bread/toc.json")) == "/azure"
    assert derive_url_prefix(_docfx("/powerquery-m/breadcrumb/toc.json")) == "/powerquery-m"


def test_derive_url_prefix_relative_or_missing_is_none() -> None:
    from docline.process.canonical_url import derive_url_prefix

    assert derive_url_prefix(_docfx("~/breadcrumb/cosmos-db/toc.yml")) is None
    assert derive_url_prefix(_docfx(None)) is None
    assert derive_url_prefix({}) is None


def test_derive_canonical_url_uses_prefix_map_when_no_url_path_prefix() -> None:
    from docline.process.canonical_url import derive_canonical_url

    cfg = {"docsets_to_publish": [{"docset_name": "fabric", "build_source_folder": "docs"}]}
    assert derive_canonical_url(cfg, "docs/admin/foo.md", prefixes={"docs": "/fabric"}) == (
        "/fabric/admin/foo"
    )
    # No prefix map and no url_path_prefix -> None (exact v1 behavior).
    assert derive_canonical_url(cfg, "docs/admin/foo.md") is None


def test_url_path_prefix_wins_over_prefix_map() -> None:
    from docline.process.canonical_url import derive_canonical_url

    cfg = {"docsets_to_publish": [{"build_source_folder": "docs", "url_path_prefix": "/cfg"}]}
    assert derive_canonical_url(cfg, "docs/a.md", prefixes={"docs": "/breadcrumb"}) == "/cfg/a"
