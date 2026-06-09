"""Tests for TOC.yml parser (024.004-T / 026-S T4)."""

from __future__ import annotations

from pathlib import Path


def test_parse_toc_flat_list(tmp_path: Path) -> None:
    """A flat list of {name, href} entries produces an ordered list of hrefs."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text(
        "- name: First\n"
        "  href: first.md\n"
        "- name: Second\n"
        "  href: second.md\n"
        "- name: Third\n"
        "  href: third.md\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert [e["href"] for e in entries] == ["first.md", "second.md", "third.md"]


def test_parse_toc_nested_items(tmp_path: Path) -> None:
    """Nested ``items: [...]`` lists flatten into the order they appear."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text(
        "- name: Section 1\n"
        "  items:\n"
        "    - name: A\n"
        "      href: a.md\n"
        "    - name: B\n"
        "      href: b.md\n"
        "- name: Section 2\n"
        "  items:\n"
        "    - name: C\n"
        "      href: c.md\n"
        "- name: Top D\n"
        "  href: d.md\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert [e["href"] for e in entries] == ["a.md", "b.md", "c.md", "d.md"]


def test_parse_toc_depth_tracking(tmp_path: Path) -> None:
    """Each entry has a depth field reflecting nesting level (0 for top-level)."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text(
        "- name: Top\n"
        "  href: top.md\n"
        "- name: Group\n"
        "  items:\n"
        "    - name: Child\n"
        "      href: child.md\n"
        "    - name: Subgroup\n"
        "      items:\n"
        "        - name: Grandchild\n"
        "          href: grand.md\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    by_href = {e["href"]: e for e in entries}
    assert by_href["top.md"]["depth"] == 0
    assert by_href["child.md"]["depth"] == 1
    assert by_href["grand.md"]["depth"] == 2


def test_parse_toc_resolves_relative_hrefs(tmp_path: Path) -> None:
    """``href: ../other-dir/doc.md`` paths resolve relative to TOC.yml's location."""
    from docline.process.toc_parser import parse_toc

    (tmp_path / "subdir").mkdir()
    toc_yml = tmp_path / "subdir" / "TOC.yml"
    toc_yml.write_text(
        "- name: Sibling\n  href: sibling.md\n- name: Cross\n  href: ../other/across.md\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    target_paths = sorted(e["target_path"] for e in entries)
    assert target_paths == ["other/across.md", "subdir/sibling.md"]


def test_parse_toc_skips_non_md_hrefs(tmp_path: Path) -> None:
    """Entries with hrefs that are not .md files (e.g., index.yml) are skipped."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text(
        "- name: Landing\n"
        "  href: index.yml\n"
        "- name: First doc\n"
        "  href: first.md\n"
        "- name: External\n"
        "  href: https://example.com\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert [e["href"] for e in entries] == ["first.md"]


def test_parse_toc_entry_without_href_still_walks_items(tmp_path: Path) -> None:
    """A group node with no href but with items[] still walks its children."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text(
        "- name: Group only\n  items:\n    - name: Child\n      href: child.md\n",
        encoding="utf-8",
    )
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert [e["href"] for e in entries] == ["child.md"]


def test_parse_toc_handles_empty_file(tmp_path: Path) -> None:
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text("", encoding="utf-8")
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert entries == []


def test_parse_toc_handles_malformed_yaml_gracefully(tmp_path: Path) -> None:
    """Malformed YAML returns [] and does not raise."""
    from docline.process.toc_parser import parse_toc

    toc_yml = tmp_path / "TOC.yml"
    toc_yml.write_text("- not: balanced\n  : weird\n  ---broken\n", encoding="utf-8")
    entries = parse_toc(toc_yml, base_dir=tmp_path)
    assert entries == []


def test_merge_toc_files_lexicographic(tmp_path: Path) -> None:
    """When multiple TOC.yml files exist, merge them in lexicographic subdir order."""
    from docline.process.toc_parser import merge_toc_files

    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "TOC.yml").write_text("- name: A\n  href: a.md\n", encoding="utf-8")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "TOC.yml").write_text("- name: B\n  href: b.md\n", encoding="utf-8")
    (tmp_path / "TOC.yml").write_text("- name: Root\n  href: root.md\n", encoding="utf-8")

    merged = merge_toc_files(
        [
            tmp_path / "TOC.yml",
            tmp_path / "alpha" / "TOC.yml",
            tmp_path / "beta" / "TOC.yml",
        ],
        base_dir=tmp_path,
    )
    paths = [e["target_path"] for e in merged]
    # Root TOC entries first, then alpha (lexicographic), then beta
    assert paths == ["root.md", "alpha/a.md", "beta/b.md"]
