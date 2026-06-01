"""CLI entrypoint for the docline document ingestion pipeline."""

import argparse
import json
import sys

from docline.app import execute_fetch, execute_process, get_manifest
from docline.app_models import FetchRequest, ProcessRequest


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

    fetch_parser = subcommands.add_parser("fetch", help="Fetch and stage a document source.")
    fetch_parser.add_argument("source", help="URL or file path to fetch.")
    fetch_parser.add_argument("--depth", type=int, default=0, help="Crawl depth for web sources.")
    fetch_parser.add_argument(
        "--output-dir",
        default=".cache/staging",
        help="Staging output directory.",
    )

    process_parser = subcommands.add_parser(
        "process",
        help="Process staged documents into Markdown output.",
    )
    process_parser.add_argument(
        "--staging-dir",
        default=".cache/staging",
        help="Staging input directory.",
    )
    process_parser.add_argument(
        "--output-dir",
        default="output",
        help="Processing output directory.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the docline CLI.

    Supported commands:
    - ``--manifest``: Print the JSON tool manifest and exit 0.
    - ``fetch``: Stage a fetch request and print a JSON result.
    - ``process``: Validate a process request and print a JSON result.
    - Anything else: Prints usage and exits 2.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        Integer exit code (0 = success, 1 = operation failure, 2 = bad args).
    """
    args_list = argv if argv is not None else sys.argv[1:]

    if not args_list:
        print("usage: docline [--manifest | fetch | process]")
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
            request = FetchRequest(
                source=parsed.source,
                depth=parsed.depth,
                output_dir=parsed.output_dir,
            )
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2

        result = execute_fetch(request)
        print(json.dumps(result.model_dump()))
        return 0 if result.success else 1

    if parsed.command == "process":
        try:
            request = ProcessRequest(
                staging_dir=parsed.staging_dir,
                output_dir=parsed.output_dir,
            )
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2

        result = execute_process(request)
        print(json.dumps(result.model_dump()))
        return 0 if result.success else 1

    print("usage: docline [--manifest | fetch | process]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
