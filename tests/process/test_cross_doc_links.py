"""Tests for cross-doc .md link resolver (024.003-T / 026-S T3)."""

from __future__ import annotations

from pathlib import Path


def test_resolve_links_finds_intra_corpus_md_link() -> None:
    """[text](other-doc.md) MUST be collected as a cross_doc_link."""
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "See [Other](other-doc.md) for details."
    out_body, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/this.md"))

    assert len(links) == 1
    link = links[0]
    assert link["target_path"] == "docs/other-doc.md"
    assert link["link_text"] == "Other"
    assert link["anchor"] is None
    # Body text preserved
    assert "[Other]" in out_body


def test_resolve_links_resolves_relative_path() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "[Up](../shared/common.md) and [Same dir](sibling.md)"
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/sub/here.md"))

    target_paths = sorted(link["target_path"] for link in links)
    assert target_paths == ["docs/shared/common.md", "docs/sub/sibling.md"]


def test_resolve_links_captures_anchor() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "[Section](other.md#sub-section)"
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/here.md"))

    assert len(links) == 1
    assert links[0]["target_path"] == "docs/other.md"
    assert links[0]["anchor"] == "sub-section"
    assert links[0]["link_text"] == "Section"


def test_resolve_links_skips_external_links() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = (
        "External: [Microsoft](https://microsoft.com)\n"
        "Mailto: [Email](mailto:a@b.com)\n"
        "FTP: [Files](ftp://example.com/files)\n"
    )
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/here.md"))
    assert links == []


def test_resolve_links_skips_media_links() -> None:
    """[alt](./media/image.png) — image asset references, not cross-doc."""
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "![Diagram](media/diagram.png) and [Same](./media/other.png)"
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/here.md"))
    assert links == []


def test_resolve_links_skips_anchor_only_links() -> None:
    """[link](#fragment) — same-page anchors are not cross-doc."""
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "Jump to [section](#my-section)"
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/here.md"))
    assert links == []


def test_resolve_links_multiple_per_body() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = (
        "See [A](a.md), [B](sub/b.md), and [C](../c.md#anchor).\n"
        "Also [external](https://x.com) (skipped).\n"
    )
    _, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/sub/here.md"))
    target_paths = sorted(link["target_path"] for link in links)
    assert target_paths == ["docs/c.md", "docs/sub/a.md", "docs/sub/sub/b.md"]


def test_resolve_links_empty_body() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    out, links = resolve_cross_doc_links("", current_rel_path=Path("docs/here.md"))
    assert out == ""
    assert links == []


def test_resolve_links_handles_md_with_no_links() -> None:
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "# Heading\n\nParagraph with no links at all.\n"
    out, links = resolve_cross_doc_links(body, current_rel_path=Path("docs/here.md"))
    assert out == body
    assert links == []


def test_resolve_links_deduplicates_when_requested() -> None:
    """The same target referenced multiple times appears once per dedup option."""
    from docline.process.cross_doc_links import resolve_cross_doc_links

    body = "[A](a.md) and [A again](a.md) and [different anchor](a.md#sec)"
    _, links = resolve_cross_doc_links(
        body, current_rel_path=Path("docs/here.md"), deduplicate=True
    )
    # Dedup is by (target_path, anchor) tuple
    keys = {(link["target_path"], link["anchor"]) for link in links}
    assert keys == {("docs/a.md", None), ("docs/a.md", "sec")}
