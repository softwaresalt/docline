"""Render local-only HTML viewers for quarantine artifacts."""

import html
import json
from pathlib import Path
from urllib.parse import urlparse

from docline.paths import PathContainmentError, safe_workspace_path
from docline.schema.models import DoclineError


class QuarantineViewerError(DoclineError):
    """Raised when a local quarantine viewer artifact cannot be rendered."""


def _is_remote_artifact_url(artifact_path: str) -> bool:
    """Return whether an artifact reference is a remote HTTP(S) URL."""
    parsed = urlparse(artifact_path)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _validate_local_artifact_path(
    artifact_path: Path | str,
    workspace_root: Path,
) -> Path:
    """Validate that a quarantine artifact path stays inside the workspace."""
    if isinstance(artifact_path, str) and _is_remote_artifact_url(artifact_path):
        raise QuarantineViewerError(
            f"Remote quarantine artifacts are not supported: {artifact_path!r}"
        )

    try:
        resolved = safe_workspace_path(artifact_path, workspace_root)
    except PathContainmentError as err:
        raise QuarantineViewerError(str(err)) from err

    if not resolved.is_file():
        raise QuarantineViewerError(f"Quarantine artifact is not a file: {resolved!s}")
    if resolved.suffix.lower() != ".json":
        raise QuarantineViewerError(f"Quarantine artifact must be a JSON file: {resolved!s}")
    return resolved


def _load_quarantine_artifact(artifact_path: Path) -> dict[str, object]:
    try:
        artifact_text = artifact_path.read_text(encoding="utf-8")
    except OSError as err:
        raise QuarantineViewerError(
            f"Unable to read quarantine artifact {artifact_path!s}"
        ) from err

    try:
        payload = json.loads(artifact_text)
    except json.JSONDecodeError as err:
        raise QuarantineViewerError(
            f"Quarantine artifact is not valid JSON: {artifact_path!s}"
        ) from err

    if not isinstance(payload, dict):
        raise QuarantineViewerError(
            f"Quarantine artifact must decode to a JSON object: {artifact_path!s}"
        )
    return payload


def _build_viewer_html(artifact_path: Path, artifact_payload: dict[str, object]) -> str:
    document_id = html.escape(str(artifact_payload.get("document_id", "unknown")), quote=False)
    rendered_payload = html.escape(
        json.dumps(artifact_payload, indent=2, ensure_ascii=False, sort_keys=True),
        quote=False,
    )
    rendered_artifact_path = html.escape(str(artifact_path), quote=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Quarantine viewer - {document_id}</title>
</head>
<body>
  <main>
    <h1>Quarantine viewer</h1>
    <p>Document ID: {document_id}</p>
    <p>Artifact: {rendered_artifact_path}</p>
    <pre>{rendered_payload}</pre>
  </main>
</body>
</html>
"""


def render_local_quarantine_viewer(
    artifact_path: Path | str,
    output_dir: Path | str,
) -> Path:
    """Render a local-only quarantine artifact viewer.

    Args:
        artifact_path: Path to a quarantine JSON artifact.
        output_dir: Local directory that should receive the viewer.

    Returns:
        Path to the rendered ``index.html`` viewer.

    Raises:
        QuarantineViewerError: If the artifact is remote, unreadable, invalid JSON,
            or the viewer cannot be written.
    """
    workspace_root = Path.cwd()
    resolved_artifact_path = _validate_local_artifact_path(artifact_path, workspace_root)
    try:
        viewer_dir = safe_workspace_path(output_dir, workspace_root)
    except PathContainmentError as err:
        raise QuarantineViewerError(str(err)) from err
    artifact_payload = _load_quarantine_artifact(resolved_artifact_path)
    viewer_html = _build_viewer_html(resolved_artifact_path, artifact_payload)
    viewer_path = viewer_dir / "index.html"

    try:
        viewer_dir.mkdir(parents=True, exist_ok=True)
        viewer_path.write_text(viewer_html, encoding="utf-8")
    except OSError as err:
        raise QuarantineViewerError(f"Unable to write quarantine viewer {viewer_path!s}") from err

    return viewer_path
