"""Tests for MCP transport restrictions."""

import pytest

from docline.mcp.server import SERVER, DoclineMcpServer, TransportMode
from docline.schema.models import DoclineError


def test_stdio_transport_accepted() -> None:
    """DoclineMcpServer accepts the approved stdio transport."""
    server = DoclineMcpServer(TransportMode.STDIO)
    assert isinstance(server, DoclineMcpServer)


def test_transport_mode_stdio_value() -> None:
    """TransportMode exposes the stdio protocol value."""
    assert TransportMode.STDIO.value == "stdio"


def test_non_stdio_string_rejected() -> None:
    """DoclineMcpServer rejects unsupported transport string values."""
    from docline.mcp.exceptions import McpTransportError

    with pytest.raises(McpTransportError):
        DoclineMcpServer(transport_mode="websocket")  # type: ignore[arg-type]


def test_stdio_string_accepted() -> None:
    """DoclineMcpServer accepts the string 'stdio' in place of the enum."""
    server = DoclineMcpServer(transport_mode="stdio")  # type: ignore[arg-type]
    assert server._transport_mode is TransportMode.STDIO


def test_mcp_transport_error_is_docline_error() -> None:
    """McpTransportError is part of the shared Docline error hierarchy."""
    from docline.mcp.exceptions import McpTransportError

    assert issubclass(McpTransportError, DoclineError)


def test_server_default_uses_stdio() -> None:
    """The module singleton is constructed with the stdio transport."""
    assert SERVER._transport_mode is TransportMode.STDIO
