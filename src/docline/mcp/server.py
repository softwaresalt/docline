"""Minimal MCP manifest adapter for shared docline operations."""

from docline.app import get_mcp_manifest
from docline.app_models import McpManifestResponse


class DoclineMcpServer:
    """Minimal MCP server surface for manifest discovery."""

    def list_tools(self) -> McpManifestResponse:
        """Return the shared manifest in the MCP ``tools/list`` envelope."""
        return get_mcp_manifest()


def get_manifest_response() -> McpManifestResponse:
    """Return the shared manifest wrapped in the MCP response envelope."""
    return get_mcp_manifest()


SERVER = DoclineMcpServer()
