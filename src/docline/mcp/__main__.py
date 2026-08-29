"""Console entry point and module bootstrap for the docline stdio MCP server.

Exposes ``main`` for the ``docline-mcp`` console script and for
``python -m docline.mcp``. Constructs a :class:`~docline.mcp.server.DoclineMcpServer`
in the approved stdio transport mode (external PDF engines disabled by default —
the §H8 startup opt-in is layered separately) and runs the read/dispatch/write loop.
"""

from __future__ import annotations

import io
import sys
from typing import cast

from docline.mcp.server import DoclineMcpServer, TransportMode
from docline.mcp.stdio import serve


def main() -> int:
    """Construct the stdio MCP server and run the transport loop until EOF.

    Returns:
        The :func:`~docline.mcp.stdio.serve` exit code (``0`` on clean EOF).
    """
    server = DoclineMcpServer(TransportMode.STDIO)
    stdin = cast(io.BufferedReader, sys.stdin.buffer)
    stdout = cast(io.BufferedWriter, sys.stdout.buffer)
    return serve(stdin, stdout, server=server)


if __name__ == "__main__":
    raise SystemExit(main())
