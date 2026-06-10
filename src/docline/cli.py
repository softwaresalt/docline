"""CLI entrypoint for the docline document ingestion pipeline."""

import argparse
import json
import sys
from pathlib import Path

from docline.app import execute_process, get_manifest
from docline.app_models import ProcessRequest
from docline.elt.orchestrate import orchestrate_fetch
from docline.paths import PathContainmentError, safe_workspace_path
from docline.quarantine_viewer import QuarantineViewerError, render_local_quarantine_viewer
from docline.schema.export import export_base_frontmatter_schema_json
from docline.schema.models import DoclineError


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="docline",
        description="Document ingestion and normalization pipeline",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Print the JSON tool manifest and exit.",
    )
    subcommands = parser.add_subparsers(dest="command")

    fetch_parser = subcommands.add_parser(
        "fetch",
        help="Fetch and stage document sources configured in .elt/config.",
    )
    fetch_parser.add_argument(
        "--config-dir",
        default=".elt/config",
        help="ELT config directory containing YAML source definitions.",
    )
    fetch_parser.add_argument(
        "--staging-dir",
        default=".elt/staging",
        help="Staging output directory for fetched sources.",
    )
    fetch_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually fetch content (default: plan-only staging job creation).",
    )

    process_parser = subcommands.add_parser(
        "process",
        help="Process staged documents into Markdown output.",
    )
    process_parser.add_argument(
        "--staging-dir",
        default=".elt/staging",
        help="Staging input directory.",
    )
    process_parser.add_argument(
        "--output-dir",
        default="output",
        help="Processing output directory.",
    )
    process_parser.add_argument(
        "--allow-heading-disorder",
        action="store_true",
        default=False,
        help=(
            "Bypass H1->H2->H3 heading hierarchy validation during Markdown "
            "assembly. Defaults to enforcing graphtor-docs chunk-boundary parentage."
        ),
    )
    process_parser.add_argument(
        "--pdf-engine",
        choices=("auto", "docling", "heuristic"),
        default="auto",
        help=(
            "PDF layout extractor selection. 'auto' (default) uses docling "
            "when the optional docline[pdf] extras are installed and falls "
            "back to the heuristic extractor otherwise. 'docling' opts in "
            "explicitly (errors if not installed). 'heuristic' uses the "
            "built-in extractor."
        ),
    )
    process_parser.add_argument(
        "--pdf-mode",
        choices=("auto", "triage"),
        default="auto",
        help=(
            "PDF processing pipeline mode. 'auto' (default) is the existing "
            "split-and-throttle batch pipeline. 'triage' runs the heuristic "
            "engine across the whole document, scores each page for fidelity "
            "loss, and re-runs only flagged pages through docling — typically "
            "6-8x faster on long technical PDFs with mostly clean prose. "
            "Orthogonal to --pdf-engine."
        ),
    )

    quarantine_viewer_parser = subcommands.add_parser(
        "quarantine-viewer",
        help="Render a local HTML viewer for a quarantine artifact.",
    )
    quarantine_viewer_parser.add_argument(
        "artifact",
        help="Path to the quarantine JSON artifact to render.",
    )
    quarantine_viewer_parser.add_argument(
        "--output-dir",
        default="quarantine-viewer",
        help="Workspace-local output directory for the rendered viewer.",
    )

    subcommands.add_parser(
        "export-schema",
        help="Print the JSON Schema for the BaseFrontmatter v1 contract.",
    )

    ingest_parser = subcommands.add_parser(
        "ingest",
        help="One-shot fetch+process for an already-cloned local source.",
    )
    ingest_subcommands = ingest_parser.add_subparsers(dest="ingest_kind", required=True)
    local_dir_parser = ingest_subcommands.add_parser(
        "local-dir",
        help=(
            "Ingest a local directory of markdown content end-to-end. "
            "Functionally mirrors a `type: local` ManifestLocalSource YAML "
            "entry but lets the operator skip writing a YAML config first."
        ),
    )
    local_dir_parser.add_argument(
        "source_path",
        help="Path to the source directory (e.g. a cloned docs repo).",
    )
    local_dir_parser.add_argument(
        "--output",
        required=True,
        help="Output directory for processed Markdown.",
    )
    local_dir_parser.add_argument(
        "--include",
        action="append",
        default=None,
        help=(
            "Glob pattern (relative to source_path) of files to include. "
            "Repeatable. Defaults to ['**/*.md'] when omitted."
        ),
    )
    local_dir_parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Glob pattern (relative to source_path) of files to exclude. Repeatable.",
    )
    local_dir_parser.add_argument(
        "--staging-dir",
        default=None,
        help=(
            "Workspace-relative staging directory. Defaults to a tempdir under "
            "the workspace .elt/staging/ingest-<job-id>/ that is removed after "
            "processing unless --keep-staging is passed."
        ),
    )
    local_dir_parser.add_argument(
        "--keep-staging",
        action="store_true",
        default=False,
        help="Retain the staging directory after process completes (debug aid).",
    )
    local_dir_parser.add_argument(
        "--allow-heading-disorder",
        action="store_true",
        default=False,
        help="Passthrough to docline process (see `docline process --help`).",
    )
    local_dir_parser.add_argument(
        "--pdf-engine",
        choices=("auto", "docling", "heuristic"),
        default="auto",
        help="Passthrough to docline process (see `docline process --help`).",
    )
    local_dir_parser.add_argument(
        "--pdf-mode",
        choices=("auto", "triage"),
        default="auto",
        help="Passthrough to docline process (see `docline process --help`).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the docline CLI.

    Supported commands:
    - ``--manifest``: Print the JSON tool manifest and exit 0.
    - ``fetch``: Stage a fetch request and print a JSON result.
    - ``process``: Validate a process request and print a JSON result.
    - ``quarantine-viewer``: Render a local quarantine viewer artifact.
    - Anything else: Prints usage and exits 2.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        Integer exit code (0 = success, 1 = operation failure, 2 = bad args).
    """
    args_list = argv if argv is not None else sys.argv[1:]

    if not args_list:
        print("usage: docline [--manifest | fetch | process | quarantine-viewer | export-schema]")
        return 2

    parser = _build_parser()

    try:
        parsed = parser.parse_args(args_list)
    except SystemExit as err:
        return int(err.code) if err.code is not None else 2

    if parsed.manifest and parsed.command is not None:
        try:
            parser.error("--manifest cannot be used with a subcommand")
        except SystemExit as err:
            return int(err.code) if err.code is not None else 2

    if parsed.manifest:
        manifest = get_manifest()
        print(json.dumps(manifest.model_dump(), indent=2))
        return 0

    if parsed.command == "fetch":
        try:
            config_dir = safe_workspace_path(parsed.config_dir, Path.cwd())
            safe_workspace_path(parsed.staging_dir, Path.cwd())
        except PathContainmentError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1

        if not config_dir.exists():
            print(f"error: ELT config directory not found: {parsed.config_dir}", file=sys.stderr)
            return 1
        if not config_dir.is_dir():
            print(
                f"error: ELT config directory is not a directory: {parsed.config_dir}",
                file=sys.stderr,
            )
            return 1

        try:
            if getattr(parsed, "execute", False):
                from docline.elt.execute import execute_elt_fetch as _exec

                jobs = _exec(config_dir, parsed.staging_dir, workspace_root=Path.cwd())
            else:
                jobs = orchestrate_fetch(config_dir, parsed.staging_dir, workspace_root=Path.cwd())
        except DoclineError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1

        if not jobs:
            print(
                f"error: ELT config directory contains no source configs: {parsed.config_dir}",
                file=sys.stderr,
            )
            return 1

        print(json.dumps([job.model_dump(mode="json") for job in jobs]))
        return 0

    if parsed.command == "process":
        try:
            request = ProcessRequest(
                staging_dir=parsed.staging_dir,
                output_dir=parsed.output_dir,
                allow_heading_disorder=parsed.allow_heading_disorder,
                pdf_engine=parsed.pdf_engine,
                pdf_mode=parsed.pdf_mode,
            )
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2

        result = execute_process(request)
        print(json.dumps(result.model_dump()))
        return 0 if result.success else 1

    if parsed.command == "quarantine-viewer":
        try:
            viewer_path = render_local_quarantine_viewer(
                artifact_path=parsed.artifact,
                output_dir=parsed.output_dir,
            )
        except QuarantineViewerError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        print(json.dumps({"viewer_path": str(viewer_path)}))
        return 0

    if parsed.command == "export-schema":
        print(export_base_frontmatter_schema_json())
        return 0

    if parsed.command == "ingest":
        return _run_ingest(parsed)

    print(
        "usage: docline [--manifest | fetch | process | quarantine-viewer | export-schema | ingest]"
    )
    return 2


def _run_ingest(parsed: argparse.Namespace) -> int:
    """Dispatch the `docline ingest <kind>` subcommand family.

    Currently supports ``local-dir``; future kinds (``git-url``,
    ``manifest-file``) plug in here.
    """
    if parsed.ingest_kind == "local-dir":
        return _run_ingest_local_dir(parsed)
    print(f"error: unknown ingest kind: {parsed.ingest_kind!r}", file=sys.stderr)
    return 2


def _run_ingest_local_dir(parsed: argparse.Namespace) -> int:
    """Run the one-shot `docline ingest local-dir <path> --output <dir>` flow.

    Functionally mirrors the YAML manifest flow: builds a
    ``ManifestLocalSource(type="local", id=<derived>, path=<path>,
    include=<include>, exclude=<exclude>)`` in memory, runs the standard
    fetch via ``execute_source_configs``, then runs the standard
    ``execute_process`` against the resulting staging directory. Cleans
    up the staging directory after process completes unless
    ``--keep-staging`` is set.
    """
    import hashlib
    import shutil

    from docline.elt.execute import execute_source_configs
    from docline.elt.manifest_models import ManifestLocalSource

    source_path = Path(parsed.source_path)
    if not source_path.exists():
        print(f"error: source path does not exist: {parsed.source_path}", file=sys.stderr)
        return 1
    if not source_path.is_dir():
        print(
            f"error: source path is not a directory: {parsed.source_path}",
            file=sys.stderr,
        )
        return 1

    output_path = Path(parsed.output).resolve()

    source_resolved = source_path.resolve()
    source_id = source_resolved.name or "ingest-source"
    # Default include also captures TOC.yml so the T2 manifest emitter can
    # derive authorial ingest order. .yml files are filtered out by the
    # process pipeline's _SUPPORTED_EXTENSIONS check.
    include = parsed.include or ["**/*.md", "**/TOC.yml", "**/toc.yml"]
    exclude = parsed.exclude or []

    # Resolve staging dir. When the operator did not specify one, allocate
    # a temp dir inside the workspace so safe_workspace_path stays happy and
    # we can remove it after process completes.
    workspace = Path.cwd().resolve()
    cleanup_staging = not parsed.keep_staging
    if parsed.staging_dir is not None:
        staging_path = Path(parsed.staging_dir).resolve()
        if not staging_path.is_relative_to(workspace):
            print(
                f"error: --staging-dir {parsed.staging_dir!r} must resolve inside "
                f"the workspace ({workspace}); provide a workspace-relative path "
                "or an absolute path under the workspace root.",
                file=sys.stderr,
            )
            return 1
        staging_path.mkdir(parents=True, exist_ok=True)
        staging_dir_arg = str(staging_path.relative_to(workspace).as_posix())
    else:
        digest = hashlib.sha256(str(source_resolved).encode("utf-8")).hexdigest()[:12]
        staging_path = workspace / ".elt" / "staging" / f"ingest-{digest}"
        staging_path.mkdir(parents=True, exist_ok=True)
        staging_dir_arg = str(staging_path.relative_to(workspace).as_posix())

    if not output_path.is_relative_to(workspace):
        print(
            f"error: --output {parsed.output!r} must resolve inside the workspace "
            f"({workspace}); provide a workspace-relative path or an absolute path "
            "under the workspace root.",
            file=sys.stderr,
        )
        return 1
    # Create the output dir only AFTER both containment checks pass so we
    # never leave an empty directory behind on a rejected request
    # (Constitution Principle III — workspace isolation).
    output_path.mkdir(parents=True, exist_ok=True)
    output_dir_arg = str(output_path.relative_to(workspace).as_posix())

    config = ManifestLocalSource(
        type="local",
        id=source_id,
        path=str(source_resolved),
        include=include,
        exclude=exclude,
    )

    try:
        execute_source_configs([config], staging_dir_arg, workspace_root=workspace)

        try:
            process_request = ProcessRequest(
                staging_dir=staging_dir_arg,
                output_dir=output_dir_arg,
                allow_heading_disorder=parsed.allow_heading_disorder,
                pdf_engine=parsed.pdf_engine,
                pdf_mode=parsed.pdf_mode,
            )
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2

        result = execute_process(process_request)
        print(json.dumps(result.model_dump()))
        return 0 if result.success else 1
    except DoclineError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        if cleanup_staging and staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
