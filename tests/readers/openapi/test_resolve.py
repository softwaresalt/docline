"""Tests for external/split-file $ref containment resolution (053.001-T / T1)."""

from pathlib import Path

import pytest

from docline.paths import PathContainmentError
from docline.readers.openapi.errors import OpenApiRefError
from docline.readers.openapi.resolve import (
    CorpusRefLinker,
    is_url_ref,
    resolve_contained_ref_file,
    split_external_ref,
)


def test_split_external_ref() -> None:
    assert split_external_ref("definitions.json#/definitions/X") == (
        "definitions.json",
        "#/definitions/X",
    )
    assert split_external_ref("#/components/schemas/X") == ("", "#/components/schemas/X")
    assert split_external_ref("./a.json") == ("./a.json", "")


def test_is_url_ref() -> None:
    assert is_url_ref("https://host/spec.json#/x") is True
    assert is_url_ref("http://host/spec.json") is True
    assert is_url_ref("./definitions.json#/x") is False
    assert is_url_ref("../common/definitions.json#/x") is False


def test_resolve_same_dir(tmp_path: Path) -> None:
    """A same-directory external ref resolves to the sibling file within the root."""
    (tmp_path / "admin").mkdir()
    target = tmp_path / "admin" / "definitions.json"
    target.write_text("{}", encoding="utf-8")
    resolved = resolve_contained_ref_file(
        "./definitions.json#/definitions/X",
        referring_dir=tmp_path / "admin",
        corpus_root=tmp_path,
    )
    assert resolved == target.resolve()


def test_resolve_parent_dir_within_root(tmp_path: Path) -> None:
    """A ../common ref (legitimate in-corpus cross-dir) resolves within the root."""
    (tmp_path / "admin").mkdir()
    (tmp_path / "common").mkdir()
    target = tmp_path / "common" / "definitions.json"
    target.write_text("{}", encoding="utf-8")
    resolved = resolve_contained_ref_file(
        "../common/definitions.json#/definitions/ErrorResponse",
        referring_dir=tmp_path / "admin",
        corpus_root=tmp_path,
    )
    assert resolved == target.resolve()


def test_resolve_escape_above_root_raises(tmp_path: Path) -> None:
    """A ref escaping above the corpus root raises PathContainmentError."""
    (tmp_path / "admin").mkdir()
    with pytest.raises(PathContainmentError):
        resolve_contained_ref_file(
            "../../../etc/passwd.json#/definitions/X",
            referring_dir=tmp_path / "admin",
            corpus_root=tmp_path,
        )


def test_resolve_url_ref_denied(tmp_path: Path) -> None:
    """A URL-valued ref is denied (SSRF) and never fetched."""
    with pytest.raises(OpenApiRefError):
        resolve_contained_ref_file(
            "https://evil.example.com/spec.json#/definitions/X",
            referring_dir=tmp_path / "admin",
            corpus_root=tmp_path,
        )


def test_resolve_absolute_ref_denied(tmp_path: Path) -> None:
    """An absolute-path ref is denied."""
    with pytest.raises(PathContainmentError):
        resolve_contained_ref_file(
            "/etc/passwd.json#/definitions/X",
            referring_dir=tmp_path / "admin",
            corpus_root=tmp_path,
        )


def test_resolve_local_ref_is_not_external(tmp_path: Path) -> None:
    """A purely local (#/...) ref is not an external file ref."""
    with pytest.raises(OpenApiRefError):
        resolve_contained_ref_file(
            "#/components/schemas/X",
            referring_dir=tmp_path / "admin",
            corpus_root=tmp_path,
        )


def _corpus(tmp_path: Path) -> Path:
    """Build a two-file corpus: svc/swagger.json + svc/types.json (+ common)."""
    (tmp_path / "svc").mkdir()
    (tmp_path / "common").mkdir()
    (tmp_path / "svc" / "swagger.json").write_text('{"swagger":"2.0"}', encoding="utf-8")
    (tmp_path / "svc" / "types.json").write_text(
        '{"swagger":"2.0","definitions":{"Widget":{"type":"object"}}}', encoding="utf-8"
    )
    (tmp_path / "common" / "errors.json").write_text(
        '{"swagger":"2.0","definitions":{"ErrorResponse":{"type":"object"}}}',
        encoding="utf-8",
    )
    return tmp_path


def test_corpus_linker_local_ref(tmp_path: Path) -> None:
    """A local schema ref links to a sibling schema doc (same as the single-file default)."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    href = linker.link_for("#/components/schemas/Foo", from_dir="svc/swagger/operations")
    assert href == "../schemas/Foo.md"


def test_corpus_linker_same_dir_external_ref(tmp_path: Path) -> None:
    """A same-dir external ref links across files to the target's schema doc."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    href = linker.link_for("./types.json#/definitions/Widget", from_dir="svc/swagger/operations")
    assert href == "../../types/schemas/Widget.md"


def test_corpus_linker_parent_dir_external_ref(tmp_path: Path) -> None:
    """A ../common external ref links across directories, contained in the corpus."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    href = linker.link_for(
        "../common/errors.json#/definitions/ErrorResponse",
        from_dir="svc/swagger/operations",
    )
    assert href == "../../../common/errors/schemas/ErrorResponse.md"


def test_corpus_linker_missing_target_schema_no_link(tmp_path: Path) -> None:
    """A ref to a schema absent from the target file yields no link (no dangling)."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    assert (
        linker.link_for("./types.json#/definitions/Ghost", from_dir="svc/swagger/operations")
        is None
    )


def test_corpus_linker_url_and_escape_yield_no_link(tmp_path: Path) -> None:
    """Denied refs (URL, escape) yield no link rather than raising, so rendering continues."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    assert (
        linker.link_for(
            "https://x/spec.json#/definitions/Widget", from_dir="svc/swagger/operations"
        )
        is None
    )
    assert (
        linker.link_for(
            "../../../etc/passwd.json#/definitions/X", from_dir="svc/swagger/operations"
        )
        is None
    )


def test_corpus_linker_example_ref_no_link(tmp_path: Path) -> None:
    """An example ref (non-schema fragment / no fragment) yields no link."""
    root = _corpus(tmp_path)
    linker = CorpusRefLinker(referring_path=root / "svc" / "swagger.json", corpus_root=root)
    assert linker.link_for("./examples/Sample.json", from_dir="svc/swagger/operations") is None


def test_corpus_linker_mutual_cross_file_refs_terminate(tmp_path: Path) -> None:
    """Mutual A<->B cross-file refs both resolve to one-hop links (no recursion/hang)."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "a.json").write_text(
        '{"swagger":"2.0","definitions":{"A":{"properties":'
        '{"b":{"$ref":"../b/b.json#/definitions/B"}}}}}',
        encoding="utf-8",
    )
    (tmp_path / "b" / "b.json").write_text(
        '{"swagger":"2.0","definitions":{"B":{"properties":'
        '{"a":{"$ref":"../a/a.json#/definitions/A"}}}}}',
        encoding="utf-8",
    )
    linker_a = CorpusRefLinker(referring_path=tmp_path / "a" / "a.json", corpus_root=tmp_path)
    linker_b = CorpusRefLinker(referring_path=tmp_path / "b" / "b.json", corpus_root=tmp_path)
    assert (
        linker_a.link_for("../b/b.json#/definitions/B", from_dir="a/a/schemas")
        == "../../../b/b/schemas/B.md"
    )
    assert (
        linker_b.link_for("../a/a.json#/definitions/A", from_dir="b/b/schemas")
        == "../../../a/a/schemas/A.md"
    )
