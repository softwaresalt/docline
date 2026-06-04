"""Sink for media (picture) artifacts extracted from source documents.

The ``PictureSink`` protocol decouples media extraction (DOCX image walk,
docling PDF picture rendering) from media persistence (filesystem write
under a per-source media root). The default ``CountingPictureSink`` writes
extracted bytes to ``{media_root}/figure-NNNN.{ext}`` with a monotonic
counter scoped per sink instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


def _ext_for_mime(mime: str, *, override_ext: str | None = None) -> str:
    """Resolve a file extension for ``mime``, falling back to ``.bin`` for unknown types.

    Args:
        mime: MIME type string (``"image/png"`` etc).
        override_ext: Optional explicit extension to use verbatim (with leading dot).
            When provided, takes precedence over the MIME lookup.

    Returns:
        File extension with leading dot.
    """
    if override_ext is not None:
        return override_ext
    return _MIME_TO_EXT.get(mime.lower(), ".bin")


@dataclass(frozen=True)
class MediaReference:
    """A single media artifact emitted from a source document.

    Attributes:
        filename: Sidecar filename relative to the per-source media root
            (e.g. ``"figure-0001.png"``).
        mime: MIME type of the bytes (``"image/png"``, ``"image/jpeg"``).
        data: Image bytes.
    """

    filename: str
    mime: str
    data: bytes


class PictureSink(Protocol):
    """Receives extracted media artifacts and assigns sidecar filenames."""

    def emit(
        self, mime: str, data: bytes, *, ext: str | None = None
    ) -> MediaReference:
        """Persist ``data`` as a media sidecar; return its assigned reference.

        Args:
            mime: MIME type of ``data``.
            data: Raw image bytes.
            ext: Optional explicit extension (with leading dot) to use
                verbatim instead of the MIME-derived default.

        Returns:
            The ``MediaReference`` for the persisted sidecar.
        """
        ...


class CountingPictureSink:
    """Default ``PictureSink`` that writes sequential files to a media root.

    Filenames follow the ``figure-NNNN.{ext}`` convention with a zero-padded
    monotonic counter scoped per sink instance. The media root directory is
    created lazily on the first ``emit`` call so sources with zero media
    artifacts do not leave behind empty directories.
    """

    def __init__(self, media_root: Path) -> None:
        """Construct a sink rooted at ``media_root``.

        Args:
            media_root: Directory where extracted sidecars are written.
                The directory is created on first ``emit``.
        """
        self._media_root = media_root
        self._counter = 0
        self._references: list[MediaReference] = []

    def emit(
        self, mime: str, data: bytes, *, ext: str | None = None
    ) -> MediaReference:
        """Write ``data`` to ``{media_root}/figure-NNNN{ext}`` and return its reference."""
        self._counter += 1
        extension = _ext_for_mime(mime, override_ext=ext)
        filename = f"figure-{self._counter:04d}{extension}"
        self._media_root.mkdir(parents=True, exist_ok=True)
        (self._media_root / filename).write_bytes(data)
        reference = MediaReference(filename=filename, mime=mime, data=data)
        self._references.append(reference)
        return reference

    @property
    def references(self) -> tuple[MediaReference, ...]:
        """Return the ordered tuple of references emitted so far."""
        return tuple(self._references)


__all__ = ["CountingPictureSink", "MediaReference", "PictureSink"]
