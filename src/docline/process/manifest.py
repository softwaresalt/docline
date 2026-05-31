"""Manifest update stubs for ingestion output tracking."""

import json
import os
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from docline.paths import safe_workspace_path

_OMITTED_ENTRY_KEYS = frozenset({"relationships"})


def update_manifest_index(
    output_root: Path, manifest_name: str, entry: Mapping[str, object]
) -> Path:
    """Atomically update the ingestion manifest with a new document entry.

    Args:
        output_root: Workspace-contained output root.
        manifest_name: Relative manifest filename within the output root.
        entry: Manifest entry to persist.

    Returns:
        Path to the updated manifest file.
    """
    path = safe_workspace_path(manifest_name, output_root)
    if path.exists():
        manifest_data = json.loads(path.read_text(encoding="utf-8"))
        documents = list(manifest_data.get("documents", []))
    else:
        documents = []

    documents.append({key: value for key, value in entry.items() if key not in _OMITTED_ENTRY_KEYS})
    payload = {"documents": documents}

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            with suppress(OSError):
                temp_path.unlink()

    return path


__all__ = ["update_manifest_index"]
