"""Exceptions for MCP-specific docline behavior."""

from docline.schema.models import DoclineError


class McpTransportError(DoclineError):
    """Raised when the MCP server is configured with an unsupported transport."""


class UnknownToolError(DoclineError):
    """Raised when a tools/call names a tool absent from the callable allow-list."""


class ExternalEngineNotAllowedError(DoclineError):
    """Raised when a client requests a non-allow-list PDF engine without the server opt-in."""
