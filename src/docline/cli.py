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

    print("usage: docline [--manifest | fetch | process | quarantine-viewer | export-schema]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
