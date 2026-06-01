"""Exceptions for MCP-specific docline behavior."""

from docline.schema.models import DoclineError


class McpTransportError(DoclineError):
    """Raised when the MCP server is configured with an unsupported transport."""
