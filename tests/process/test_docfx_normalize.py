"""Tests for DocFx container normalizer (024.001-T / 026-S T1)."""

from __future__ import annotations


def test_normalize_image_container_basic() -> None:
    """`:::image type='content' source='X' alt-text='Y':::` becomes `![Y](X)`."""
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        "Para 1.\n\n"
        ':::image type="content" source="media/diagram.png" '
        'alt-text="A diagram showing flow":::\n\n'
        "Para 2.\n"
    )
    out = normalize_docfx_containers(body)
    assert "![A diagram showing flow](media/diagram.png)" in out
    assert ":::image" not in out
    assert "Para 1." in out
    assert "Para 2." in out


def test_normalize_image_container_handles_single_quotes() -> None:
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = ":::image type='content' source='img.png' alt-text='Caption':::"
    out = normalize_docfx_containers(body)
    assert "![Caption](img.png)" in out


def test_normalize_image_container_handles_self_closing_form() -> None:
    """Some DocFx image containers use the self-closing form (no body content)."""
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        ':::image type="content" source="a.png" alt-text="AltA":::\n'
        ':::image type="icon" source="b.png" alt-text="AltB":::\n'
    )
    out = normalize_docfx_containers(body)
    assert "![AltA](a.png)" in out
    assert "![AltB](b.png)" in out


def test_normalize_image_container_handles_block_form_with_long_description() -> None:
    """DocFx image containers can have a long-description body before :::-end."""
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        ':::image type="complex" source="chart.png" alt-text="Chart of values":::\n'
        "This chart shows revenue by quarter from Q1 to Q4.\n"
        ":::image-end:::\n"
    )
    out = normalize_docfx_containers(body)
    # Image becomes standard markdown; long description preserved as paragraph
    assert "![Chart of values](chart.png)" in out
    assert "revenue by quarter" in out
    assert ":::image" not in out


def test_normalize_moniker_strips_wrapper_preserves_content() -> None:
    """`:::moniker range='power-bi-2024'::: ... :::moniker-end:::` becomes the body."""
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        "Before.\n\n"
        ':::moniker range="power-bi-2024"\n'
        "Content for the 2024 moniker.\n"
        "More content.\n"
        ":::moniker-end:::\n\n"
        "After.\n"
    )
    out = normalize_docfx_containers(body)
    assert "Content for the 2024 moniker." in out
    assert "More content." in out
    assert ":::moniker" not in out
    assert "Before." in out
    assert "After." in out


def test_normalize_unknown_container_passes_through() -> None:
    """Containers we don't recognize MUST pass through unchanged so consumers
    that DO understand the syntax can still process them.
    """
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        "Before.\n\n"
        ":::row:::\n"
        ':::column span="2":::\n'
        "Column content.\n"
        ":::column-end:::\n"
        ":::row-end:::\n"
    )
    out = normalize_docfx_containers(body)
    # row/column passed through unchanged
    assert ":::row:::" in out
    assert ":::column" in out
    assert "Column content." in out


def test_normalize_image_alt_text_containing_colon() -> None:
    """Alt-text values may contain colons (e.g., 'Figure 1: Overview').
    The image regex MUST NOT break on attribute values that contain colons.
    """
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = ':::image type="content" source="img.png" alt-text="Figure 1: Overview":::'
    out = normalize_docfx_containers(body)
    assert "![Figure 1: Overview](img.png)" in out
    assert ":::image" not in out


def test_normalize_image_block_form_emits_no_spurious_image() -> None:
    """The block form `:::image:::...:::image-end:::` MUST produce exactly ONE
    image markdown reference, not a spurious extra `![](* )` from
    accidentally matching `:::image-end:::` as an opening tag.
    """
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        ':::image type="complex" source="chart.png" alt-text="Chart caption":::\n'
        "Long description body.\n"
        ":::image-end:::\n"
    )
    out = normalize_docfx_containers(body)
    # Exactly one image markdown reference
    image_count = out.count("![")
    assert image_count == 1, f"expected 1 image ref, got {image_count}; output:\n{out}"
    assert "![Chart caption](chart.png)" in out
    # Spurious empty image ![](* ) MUST NOT appear
    assert "![]()" not in out


def test_normalize_multiple_block_form_images() -> None:
    """Two adjacent block-form images each emit one image reference."""
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = (
        ':::image type="complex" source="a.png" alt-text="A":::\n'
        "Desc A.\n"
        ":::image-end:::\n\n"
        ':::image type="complex" source="b.png" alt-text="B":::\n'
        "Desc B.\n"
        ":::image-end:::\n"
    )
    out = normalize_docfx_containers(body)
    assert out.count("![") == 2
    assert "![A](a.png)" in out
    assert "![B](b.png)" in out
    assert "Desc A." in out
    assert "Desc B." in out


def test_normalize_handles_empty_body() -> None:
    from docline.process.docfx_normalize import normalize_docfx_containers

    assert normalize_docfx_containers("") == ""


def test_normalize_passes_plain_markdown_unchanged() -> None:
    from docline.process.docfx_normalize import normalize_docfx_containers

    body = "# Heading\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```\n"
    out = normalize_docfx_containers(body)
    assert out == body
