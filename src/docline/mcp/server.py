"""Minimal MCP manifest adapter for shared docline operations."""

from enum import Enum

from docline.app import execute_fetch, execute_process, get_mcp_manifest
from docline.app_models import (
    FetchRequest,
    FetchResult,
    McpManifestResponse,
    ProcessRequest,
    ProcessResult,
)
from docline.mcp.exceptions import McpTransportError


class TransportMode(Enum):
    """Approved MCP transport modes.

    Only stdio transport is approved for docline's MCP surface.
    """

    STDIO = "stdio"


class DoclineMcpServer:
    """Minimal MCP server surface for manifest discovery."""

    def __init__(self, transport_mode: TransportMode = TransportMode.STDIO) -> None:
        """Initialize the MCP server with the approved transport mode.

        Args:
            transport_mode: Requested MCP transport configuration.

        Raises:
            McpTransportError: If any transport other than stdio is requested.
        """
        if transport_mode is not TransportMode.STDIO:
            raise McpTransportError(
                f"Unsupported MCP transport: {transport_mode!r}. Only stdio is approved."
            )
        self._transport_mode = transport_mode

    def list_tools(self) -> McpManifestResponse:
        """Return the shared manifest in the MCP ``tools/list`` envelope."""
        return get_mcp_manifest()

    def fetch(self, request: FetchRequest) -> FetchResult:
        """Execute a fetch operation via the MCP tool surface.

        Args:
            request: Validated fetch parameters from the MCP caller.

        Returns:
            The shared fetch result for the requested source.
        """
        return execute_fetch(request)

    def process(self, request: ProcessRequest) -> ProcessResult:
        """Execute a processing operation via the MCP tool surface.

        Args:
            request: Validated process parameters from the MCP caller.

        Returns:
            The shared process result for the requested staging directory.
        """
        return execute_process(request)


def get_manifest_response() -> McpManifestResponse:
    """Return the shared manifest wrapped in the MCP response envelope."""
    return get_mcp_manifest()


SERVER = DoclineMcpServer()
