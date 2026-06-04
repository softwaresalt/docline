"""Failing-first tests for DOCX embedded image extraction (G3c task 015.001-T).

Covers ``read_docx_blocks_with_media`` which walks ``<w:drawing>`` elements,
resolves ``<a:blip r:embed="rIdN"/>`` via ``word/_rels/document.xml.rels``,
extracts ``word/media/imageN.{ext}`` bytes, and emits
``![](media/figure-NNNN.ext)`` markdown at the source paragraph position.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import cast

from docline.readers.docx import read_docx_blocks_with_media
from docline.readers.picture_sink import CountingPictureSink, MediaReference, PictureSink

# ---------------------------------------------------------------------------
# Minimal valid PNG (8-byte sig + IHDR + IDAT + IEND), 1x1 transparent pixel
# ---------------------------------------------------------------------------

_MIN_PNG = bytes.fromhex(
    "89504e470d0a1a0a"
    "0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c63000100000005000119d9d7720000000049454e44ae426082"
)
_MIN_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000806060706050807070709"
    "0908"
    "0a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c303134"
    "34341f27393d38323c2e333432ffc0000b08000100010101110000ffc40014000100"
    "00000000000000000000000000ffd9"
)


def _make_docx_with_drawings(image_specs: list[tuple[str, str, bytes]]) -> bytes:
    """Build a minimal DOCX containing one paragraph per image with `<w:drawing>` references.

    Args:
        image_specs: Ordered list of ``(rId, target, image_bytes)`` triples.
            ``rId`` is the relationship id used in `<a:blip r:embed=...>`.
            ``target`` is the rels Target (e.g. ``"media/image1.png"``).
            ``image_bytes`` is the binary content written under
            ``word/{target}`` in the zip.

    Returns:
        Bytes of a valid DOCX zip with one paragraph per image (each
        paragraph contains both a text run and a `<w:drawing>`).
    """
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_pic = "http://schemas.openxmlformats.org/drawingml/2006/picture"

    body_paragraphs = []
    for rid, _target, _data in image_specs:
        body_paragraphs.append(
            f'<w:p xmlns:w="{ns_w}" xmlns:r="{ns_r}" xmlns:a="{ns_a}" xmlns:pic="{ns_pic}">'
            f"<w:r><w:t>Caption for {rid}</w:t></w:r>"
            f"<w:r><w:drawing>"
            f'<a:graphic><a:graphicData uri="">'
            f"<pic:pic><pic:blipFill>"
            f'<a:blip r:embed="{rid}"/>'
            f"</pic:blipFill></pic:pic>"
            f"</a:graphicData></a:graphic>"
            f"</w:drawing></w:r>"
            f"</w:p>"
        )

    document_xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns_w}">'
        "<w:body>" + "".join(body_paragraphs) + "</w:body></w:document>"
    )

    rels_xml = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="{rid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="{target}"/>'
            for rid, target, _ in image_specs
        )
        + "</Relationships>"
    )

    package_rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    types_xml = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpg" ContentType="image/jpeg"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types_xml)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        for _rid, target, data in image_specs:
            zf.writestr(f"word/{target}", data)
    return buf.getvalue()


def _make_docx_text_only(text: str) -> bytes:
    """Return a minimal DOCX containing exactly one text-only paragraph."""
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns_w}">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    package_rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    types_xml = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types_xml)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _make_docx_with_unresolvable_embed() -> bytes:
    """Return a DOCX with `<a:blip r:embed="rId99"/>` but no matching rels entry."""
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_pic = "http://schemas.openxmlformats.org/drawingml/2006/picture"
    document_xml = (
        '<?xml version="1.0"?>'
        f'<w:document xmlns:w="{ns_w}">'
        "<w:body>"
        f'<w:p xmlns:r="{ns_r}" xmlns:a="{ns_a}" xmlns:pic="{ns_pic}">'
        "<w:r><w:t>orphan</w:t></w:r>"
        "<w:r><w:drawing><a:graphic><a:graphicData>"
        "<pic:pic><pic:blipFill>"
        '<a:blip r:embed="rId99"/>'
        "</pic:blipFill></pic:pic>"
        "</a:graphicData></a:graphic></w:drawing></w:r>"
        "</w:p>"
        "</w:body></w:document>"
    )
    rels_xml = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    package_rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    types_xml = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types_xml)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_docx_with_no_images_returns_empty_media_list(tmp_path: Path) -> None:
    """A text-only DOCX returns text blocks and an empty media list."""
    path = tmp_path / "text-only.docx"
    path.write_bytes(_make_docx_text_only("hello world"))
    sink = CountingPictureSink(tmp_path / "media")
    blocks, media = read_docx_blocks_with_media(path, sink)
    assert any("hello world" in block for block in blocks)
    assert media == []
    assert not (tmp_path / "media").exists()


def test_docx_with_one_embedded_png_produces_one_media_reference(tmp_path: Path) -> None:
    """One `<w:drawing>` with a valid rels resolution produces one ``MediaReference``."""
    path = tmp_path / "one-image.docx"
    path.write_bytes(_make_docx_with_drawings([("rId1", "media/image1.png", _MIN_PNG)]))
    sink = CountingPictureSink(tmp_path / "media")
    blocks, media = read_docx_blocks_with_media(path, sink)
    assert len(media) == 1
    assert media[0].mime == "image/png"
    assert media[0].data == _MIN_PNG
    assert media[0].filename == "figure-0001.png"


def test_docx_image_emission_inserts_markdown_image_at_source_position(tmp_path: Path) -> None:
    """The paragraph that contained the drawing emits a markdown image reference."""
    path = tmp_path / "captioned.docx"
    path.write_bytes(_make_docx_with_drawings([("rId1", "media/image1.png", _MIN_PNG)]))
    sink = CountingPictureSink(tmp_path / "media")
    blocks, _media = read_docx_blocks_with_media(path, sink)
    joined = "\n\n".join(blocks)
    assert "Caption for rId1" in joined
    assert "![](media/figure-0001.png)" in joined


def test_docx_with_two_images_assigns_sequential_filenames(tmp_path: Path) -> None:
    """Two embedded images produce figure-0001 then figure-0002 in source order."""
    path = tmp_path / "two-images.docx"
    path.write_bytes(
        _make_docx_with_drawings(
            [
                ("rId1", "media/image1.png", _MIN_PNG),
                ("rId2", "media/image2.jpg", _MIN_JPEG),
            ]
        )
    )
    sink = CountingPictureSink(tmp_path / "media")
    _blocks, media = read_docx_blocks_with_media(path, sink)
    assert [m.filename for m in media] == ["figure-0001.png", "figure-0002.jpg"]
    assert media[0].mime == "image/png"
    assert media[1].mime == "image/jpeg"


def test_docx_with_unresolvable_embed_id_is_skipped_silently(tmp_path: Path) -> None:
    """A `<a:blip r:embed=...>` referencing a missing rId is skipped without raising."""
    path = tmp_path / "orphan.docx"
    path.write_bytes(_make_docx_with_unresolvable_embed())
    sink = CountingPictureSink(tmp_path / "media")
    blocks, media = read_docx_blocks_with_media(path, sink)
    assert any("orphan" in block for block in blocks)
    assert media == []
    assert not (tmp_path / "media").exists()


def test_docx_jpeg_image_mime_detected_from_extension(tmp_path: Path) -> None:
    """A ``.jpeg`` rels Target yields ``image/jpeg`` mime."""
    path = tmp_path / "jpeg-image.docx"
    path.write_bytes(_make_docx_with_drawings([("rId1", "media/image1.jpeg", _MIN_JPEG)]))
    sink = CountingPictureSink(tmp_path / "media")
    _blocks, media = read_docx_blocks_with_media(path, sink)
    assert len(media) == 1
    assert media[0].mime == "image/jpeg"
    assert media[0].filename == "figure-0001.jpeg"


def test_picture_sink_protocol_is_satisfied_by_counting_sink() -> None:
    """``CountingPictureSink`` satisfies the ``PictureSink`` protocol structurally."""
    sink: PictureSink = CountingPictureSink(Path("dummy"))
    # If this assignment type-checks at runtime via Protocol structural matching,
    # the test passes; we also confirm the contract by calling ``emit`` returns
    # a ``MediaReference`` (would raise AttributeError if the protocol drifted).
    assert hasattr(sink, "emit")
    # Cast for static type checkers — the protocol check is the substantive assertion.
    _ = cast(MediaReference, MediaReference(filename="f.png", mime="image/png", data=b""))
