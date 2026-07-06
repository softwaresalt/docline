"""External / split-file ``$ref`` containment resolution (053.001-T / T1).

Resolves a ``file.json#/pointer`` reference to a filesystem path **contained
within the corpus root**, with a hard security boundary:

* URL-valued refs (``http://``, ``https://``, any scheme) are **denied** — never
  fetched (SSRF).
* Absolute-path refs are denied.
* Refs that resolve above the corpus root (``../`` escapes, including via
  symlinks) raise :class:`~docline.paths.PathContainmentError`.

Legitimate in-corpus cross-directory refs (``../common/definitions.json``) are
allowed: the target is normalized and verified to stay under the corpus root,
which is why this cannot use :func:`docline.paths.safe_workspace_path` (that
helper rejects any ``..`` token outright).
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docline.paths import PathContainmentError
from docline.readers.openapi.convert import swagger2_to_openapi3
from docline.readers.openapi.errors import OpenApiError, OpenApiRefError
from docline.readers.openapi.loader import component_name_from_ref, load_spec, slug

_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:", re.ASCII)
# ``$ref`` fragments that address a schema (2.0 ``definitions`` or 3.x components).
_SCHEMA_FRAGMENT_PREFIXES = ("#/definitions/", "#/components/schemas/")


def split_external_ref(ref: str) -> tuple[str, str]:
    """Split a ``$ref`` into ``(file_part, fragment)``.

    ``"a.json#/definitions/X"`` -> ``("a.json", "#/definitions/X")``;
    a purely local ``"#/components/schemas/X"`` -> ``("", "#/components/schemas/X")``;
    a bare file ``"a.json"`` -> ``("a.json", "")``.
    """
    if "#" in ref:
        file_part, fragment = ref.split("#", 1)
        return file_part, "#" + fragment
    return ref, ""


def is_url_ref(ref: str) -> bool:
    """Return ``True`` when *ref* (or its file part) uses a URL scheme."""
    return bool(_URL_RE.match(ref))


def resolve_contained_ref_file(ref: str, *, referring_dir: Path, corpus_root: Path) -> Path:
    """Resolve an external file ``$ref`` to a path contained within *corpus_root*.

    Args:
        ref: The raw ``$ref`` string (e.g. ``./definitions.json#/definitions/X``).
        referring_dir: Absolute directory of the referring spec file. Relative
            file parts resolve against this directory.
        corpus_root: Absolute containment boundary. The resolved target must be
            a descendant of this root.

    Returns:
        The resolved, contained absolute target file path.

    Raises:
        OpenApiRefError: If *ref* is a URL (denied, never fetched) or is not an
            external file ref (no file part).
        PathContainmentError: If the file part is absolute or the resolved target
            escapes *corpus_root* (including via symlink).
    """
    file_part, _ = split_external_ref(ref)
    if not file_part:
        raise OpenApiRefError(f"not an external file $ref: {ref!r}")
    if is_url_ref(file_part):
        raise OpenApiRefError(f"URL $ref denied (SSRF); never fetched: {ref!r}")
    if file_part.startswith(("/", "\\")) or _WINDOWS_DRIVE_RE.match(file_part):
        raise PathContainmentError(f"absolute $ref file is not allowed: {ref!r}")

    root = corpus_root.resolve()
    # ``resolve(strict=False)`` normalizes ``..`` and follows any symlinks, so an
    # escape (direct or via symlink) lands outside root and fails containment.
    resolved = (referring_dir / file_part).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise PathContainmentError(
            f"$ref {ref!r} resolves to {resolved!r}, outside corpus root {root!r}"
        )
    return resolved


def _schema_name_from_fragment(fragment: str) -> str | None:
    """Return the schema name a fragment addresses, or ``None`` for non-schema refs."""
    for prefix in _SCHEMA_FRAGMENT_PREFIXES:
        if fragment.startswith(prefix):
            return component_name_from_ref(fragment)
    return None


class CorpusRefLinker:
    """Maps a ``$ref`` (local or external) to the schema doc it should link to.

    A corpus is a directory tree of spec files; each file produces schema docs at
    ``{file_rel_no_suffix}/schemas/{slug(name)}.md``. Given a referring file and
    the corpus root, :meth:`link_for` resolves a ``$ref`` to a relative Markdown
    href to the target schema doc, applying the T1 containment/URL-deny boundary
    for external refs and verifying the target schema exists (no dangling links).
    Non-schema fragments (parameters/responses/examples) yield ``None``.
    """

    def __init__(self, *, referring_path: Path, corpus_root: Path) -> None:
        """Initialize the linker.

        Args:
            referring_path: Absolute path of the referring spec file.
            corpus_root: Absolute containment boundary (the corpus directory).
        """
        self.corpus_root = corpus_root.resolve()
        self.referring_path = referring_path.resolve()
        self.referring_dir = self.referring_path.parent
        self.referring_basename = (
            self.referring_path.relative_to(self.corpus_root).with_suffix("").as_posix()
        )
        self._schema_cache: dict[Path, Mapping[str, Any] | None] = {}

    def _target_schemas(self, target: Path) -> Mapping[str, Any] | None:
        """Load (and cache) the target file's ``components.schemas`` map.

        Returns ``None`` when the target is not a parseable spec.
        """
        if target not in self._schema_cache:
            spec: dict[str, Any] | None
            try:
                spec = load_spec(target)
                swagger = spec.get("swagger")
                if isinstance(swagger, str) and swagger.startswith("2."):
                    spec = swagger2_to_openapi3(spec)
            except OpenApiError:
                spec = None
            if spec is None:
                self._schema_cache[target] = None
            else:
                components = spec.get("components")
                schemas = components.get("schemas") if isinstance(components, Mapping) else None
                self._schema_cache[target] = schemas if isinstance(schemas, Mapping) else {}
        return self._schema_cache[target]

    def link_for(self, ref: str, *, from_dir: str) -> str | None:
        """Return a relative href to the schema doc *ref* addresses, or ``None``.

        Args:
            ref: The raw ``$ref`` string (local ``#/...`` or external
                ``file.json#/...``).
            from_dir: POSIX directory of the current document relative to the
                corpus root (e.g. ``svc/swagger/operations``).

        Returns:
            A relative Markdown href to the target schema document, or ``None``
            when the ref is not a linkable schema (non-schema fragment, denied
            external, or a target schema that does not exist).
        """
        file_part, fragment = split_external_ref(ref)
        name = _schema_name_from_fragment(fragment)
        if name is None:
            return None

        if not file_part:
            # Local ref: the referring file produces this schema doc.
            target_basename = self.referring_basename
        else:
            try:
                target = resolve_contained_ref_file(
                    ref, referring_dir=self.referring_dir, corpus_root=self.corpus_root
                )
            except (OpenApiRefError, PathContainmentError):
                return None  # URL-denied / escape / non-file → skip, do not raise
            schemas = self._target_schemas(target)
            if schemas is None or name not in schemas:
                return None  # not a spec, or schema absent → no dangling link
            target_basename = target.relative_to(self.corpus_root).with_suffix("").as_posix()

        target_doc = f"{target_basename}/schemas/{slug(name)}.md"
        return posixpath.relpath(target_doc, from_dir)


__all__ = [
    "CorpusRefLinker",
    "is_url_ref",
    "resolve_contained_ref_file",
    "split_external_ref",
]
