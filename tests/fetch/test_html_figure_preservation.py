"""Red-first HTML figure preservation tests (010-S F6.T1).

These tests pin the contract that F6.T2 (010.026-T) must satisfy when adding
figure/caption/alt preservation to ``src/docline/fetch/html_extract.py`` and
``src/docline/fetch/html_normalize.py``:

* ``<figure>`` blocks containing ``<img>`` and ``<figcaption>`` must round-trip
  to Markdown as an inline image plus a caption line — neither element may be
  silently dropped by ``strip_dom_noise`` or ``extract_main_content``
* bare ``<img alt="…" src="…">`` outside any figure must render as a Markdown
  image ``![alt](src)`` so the image is preserved in document order
* image ``alt`` attributes (including the deliberately-empty ``alt=""`` used
  for decorative images) must round-trip unchanged
* multiple figures must preserve document order
* ``<img>`` tags with a missing ``alt`` attribute must still emit a
  ``![](src)`` placeholder rather than being silently dropped — operators
  triaging accessibility issues need every image in the output

These assertions are expected to **fail today** because
``_element_to_markdown`` in ``html_extract.py`` has no figure/img/figcaption
handling and falls through to ``el.get_text(...)``, which drops the image
source entirely. F6.T2 lands the figure-aware element handlers that turn these
red tests green.
"""

from __future__ import annotations

import pytest

from docline.fetch.html_extract import (
    HtmlExtractionError,
    extract_main_content,
    strip_dom_noise,
)

# ---------------------------------------------------------------------------
# Fixtures — exercise the figure / img / figcaption shapes we must preserve
# ---------------------------------------------------------------------------

_FIGURE_WITH_CAPTION_HTML = (
    "<html><body><article>"
    "<h1>Diagram-driven page</h1>"
    "<p>Intro paragraph.</p>"
    "<figure>"
    '<img src="https://example.com/diagram.png" alt="System diagram">'
    "<figcaption>Figure 1: Overall system architecture.</figcaption>"
    "</figure>"
    "<p>Closing paragraph.</p>"
    "</article></body></html>"
)

_BARE_IMG_HTML = (
    "<html><body><article>"
    "<h1>Image-only page</h1>"
    '<img src="https://example.com/logo.png" alt="Product logo">'
    "<p>Surrounding text.</p>"
    "</article></body></html>"
)

_DECORATIVE_IMG_HTML = (
    "<html><body><article>"
    "<h1>Decorative image page</h1>"
    '<img src="https://example.com/spacer.png" alt="">'
    "<p>Body text.</p>"
    "</article></body></html>"
)

_MISSING_ALT_HTML = (
    "<html><body><article>"
    "<h1>Missing-alt page</h1>"
    '<img src="https://example.com/no-alt.png">'
    "<p>Body text.</p>"
    "</article></body></html>"
)

_MULTI_FIGURE_HTML = (
    "<html><body><article>"
    "<h1>Multi-figure page</h1>"
    "<figure>"
    '<img src="https://example.com/first.png" alt="First diagram">'
    "<figcaption>First caption.</figcaption>"
    "</figure>"
    "<p>Middle paragraph.</p>"
    "<figure>"
    '<img src="https://example.com/second.png" alt="Second diagram">'
    "<figcaption>Second caption.</figcaption>"
    "</figure>"
    "</article></body></html>"
)


# ---------------------------------------------------------------------------
# Tests — target behavior F6.T2 must satisfy
# ---------------------------------------------------------------------------


def test_strip_dom_noise_preserves_figure_blocks() -> None:
    """``strip_dom_noise`` must keep ``<figure>``/``<img>``/``<figcaption>``."""
    cleaned = strip_dom_noise(_FIGURE_WITH_CAPTION_HTML)
    assert "<figure" in cleaned, "figure element must survive noise stripping"
    assert "<img" in cleaned, "img element must survive noise stripping"
    assert "<figcaption" in cleaned, "figcaption must survive noise stripping"


def test_extract_main_content_emits_markdown_image_for_figure() -> None:
    """Figure ``<img>`` must round-trip to a Markdown image with alt + src."""
    result = extract_main_content(_FIGURE_WITH_CAPTION_HTML)
    assert "![System diagram](https://example.com/diagram.png)" in result, (
        "figure <img> must emit a Markdown image with the alt text and src URL"
    )


def test_extract_main_content_preserves_figcaption_text() -> None:
    """``<figcaption>`` text must remain visible in the output Markdown."""
    result = extract_main_content(_FIGURE_WITH_CAPTION_HTML)
    assert "Figure 1: Overall system architecture." in result


def test_extract_main_content_emits_markdown_image_for_bare_img() -> None:
    """A bare ``<img>`` outside any figure must still render as Markdown image."""
    result = extract_main_content(_BARE_IMG_HTML)
    assert "![Product logo](https://example.com/logo.png)" in result


def test_extract_main_content_preserves_empty_alt_for_decorative_image() -> None:
    """``alt=""`` (decorative) must round-trip as ``![](src)``."""
    result = extract_main_content(_DECORATIVE_IMG_HTML)
    assert "![](https://example.com/spacer.png)" in result, (
        "decorative images must keep empty alt so the round-trip is faithful"
    )


def test_extract_main_content_emits_placeholder_for_missing_alt() -> None:
    """``<img>`` missing ``alt`` must still produce a Markdown image."""
    result = extract_main_content(_MISSING_ALT_HTML)
    assert "https://example.com/no-alt.png" in result, (
        "images without alt must still appear in the output — never silently dropped"
    )
    # Must use Markdown image syntax so downstream linters can flag the
    # accessibility regression rather than treating it as plain text.
    assert "![" in result and "](https://example.com/no-alt.png)" in result


def test_extract_main_content_preserves_multi_figure_document_order() -> None:
    """Multiple figures must round-trip in document order."""
    result = extract_main_content(_MULTI_FIGURE_HTML)
    first_pos = result.find("![First diagram](https://example.com/first.png)")
    second_pos = result.find("![Second diagram](https://example.com/second.png)")
    assert first_pos != -1, "first figure must be present"
    assert second_pos != -1, "second figure must be present"
    assert first_pos < second_pos, "figures must preserve document order"
    first_caption_pos = result.find("First caption.")
    second_caption_pos = result.find("Second caption.")
    assert first_caption_pos != -1 and second_caption_pos != -1
    assert first_caption_pos < second_caption_pos, "captions must follow figure order"


def test_extract_main_content_rejects_empty_html_unchanged() -> None:
    """Regression: empty-input contract from F3 must remain intact."""
    with pytest.raises(HtmlExtractionError):
        extract_main_content("")
