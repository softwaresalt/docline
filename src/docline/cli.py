"""CLI entrypoint for the docline document ingestion pipeline."""

import json
import sys

from docline.app import get_manifest


def main(argv: list[str] | None = None) -> int:
    """Run the docline CLI.

    Supported commands:
    - ``--manifest``: Print the JSON tool manifest and exit 0.
    - ``fetch``: Stub — prints a message and exits 1.
    - ``process``: Stub — prints a message and exits 1.
    - Anything else: Prints usage and exits 2.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        Integer exit code (0 = success, 1 = not implemented, 2 = bad args).
    """
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        print("usage: docline [--manifest | fetch | process]")
        return 2

    command = args[0]

    if command == "--manifest":
        manifest = get_manifest()
        print(json.dumps(manifest.model_dump(), indent=2))
        return 0

    if command == "fetch":
        print("fetch not yet implemented")
        return 1

    if command == "process":
        print("process not yet implemented")
        return 1

    print("usage: docline [--manifest | fetch | process]")
    return 2
