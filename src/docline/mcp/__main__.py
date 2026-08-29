"""Console entry point and module bootstrap for the docline stdio MCP server.

Exposes ``main`` for the ``docline-mcp`` console script and for
``python -m docline.mcp``. Constructs a :class:`~docline.mcp.server.DoclineMcpServer`
in the approved stdio transport mode and runs the read/dispatch/write loop.

The §H8 external-PDF-engine opt-in is a SERVER-SIDE, startup-only, fail-closed
control resolved here exactly once — from the ``DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES``
environment variable (enabled only for the raw exact token ``"1"``) or the
``--allow-external-pdf-engine`` flag — and threaded into a fresh server instance. It
is never derived from request data and never mutates the module-level ``SERVER``.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from typing import cast

from docline.mcp.server import DoclineMcpServer, TransportMode
from docline.mcp.stdio import serve

_ENV_OPTIN = "DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES"


def _resolve_external_opt_in(argv: list[str] | None = None) -> bool:
    """Resolve the §H8 external-engine opt-in fail-closed (raw exact token / CLI flag).

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        ``True`` only when the ``--allow-external-pdf-engine`` flag is present OR
        the ``DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES`` env var equals the raw exact
        token ``"1"`` (no strip/trim, no case-fold, no truthy coercion); ``False``
        otherwise (including unset and any padded ``"1"``).
    """
    parser = argparse.ArgumentParser(
        prog="docline-mcp",
        description="Run the docline stdio MCP server.",
    )
    parser.add_argument(
        "--allow-external-pdf-engine",
        action="store_true",
        help=(
            "Enable external, credential/network-bearing PDF engines (mistral_ocr) "
            "on the MCP surface. Delegates paid external OCR calls and workspace-PDF "
            "upload to the connected client — enable only for trusted local clients."
        ),
    )
    args = parser.parse_args(argv)
    env_enabled = os.environ.get(_ENV_OPTIN) == "1"
    return bool(args.allow_external_pdf_engine) or env_enabled


def main() -> int:
    """Construct the stdio MCP server and run the transport loop until EOF.

    Returns:
        The :func:`~docline.mcp.stdio.serve` exit code (``0`` on clean EOF).
    """
    external_pdf_engines_enabled = _resolve_external_opt_in()
    server = DoclineMcpServer(
        TransportMode.STDIO,
        external_pdf_engines_enabled=external_pdf_engines_enabled,
    )
    stdin = cast(io.BufferedReader, sys.stdin.buffer)
    stdout = cast(io.BufferedWriter, sys.stdout.buffer)
    return serve(stdin, stdout, server=server)


if __name__ == "__main__":
    raise SystemExit(main())
