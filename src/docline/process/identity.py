"""Document identity stubs for the processing pipeline."""

from uuid import NAMESPACE_URL, UUID, uuid5

from docline.types import SourceInput, SourceKind


def canonical_source_key(source_input: SourceInput) -> str:
    """Return a stable canonical source key for a staged input.

    Args:
        source_input: Classified staged source input.

    Returns:
        Stable canonical source key.
    """
    raw = (
        source_input.raw.replace("\\", "/")
        if source_input.kind in (SourceKind.FILE, SourceKind.TRANSCRIPT)
        else source_input.raw
    )
    return f"{source_input.kind.value}:{raw}"


def derive_document_uuid(source_input: SourceInput) -> UUID:
    """Return a deterministic UUID for a staged input.

    Args:
        source_input: Classified staged source input.

    Returns:
        Deterministic document UUID.
    """
    return uuid5(NAMESPACE_URL, canonical_source_key(source_input))


__all__ = ["canonical_source_key", "derive_document_uuid"]
