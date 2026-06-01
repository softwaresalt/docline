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

    def fetch(self, request: FetchRequest | dict[str, object]) -> FetchResult:
        """Execute a fetch operation via the MCP tool surface.

        Accepts either a pre-validated :class:`~docline.app_models.FetchRequest`
        or a raw dict payload, validating dict inputs at the MCP boundary.

        Args:
            request: Validated fetch parameters or a raw parameter dict.

        Returns:
            The shared fetch result for the requested source.

        Raises:
            ValidationError: If a dict payload fails Pydantic schema validation.
        """
        if isinstance(request, dict):
            request = FetchRequest.model_validate(request)
        return execute_fetch(request)

    def process(self, request: ProcessRequest | dict[str, object]) -> ProcessResult:
        """Execute a processing operation via the MCP tool surface.

        Accepts either a pre-validated :class:`~docline.app_models.ProcessRequest`
        or a raw dict payload, validating dict inputs at the MCP boundary.

        Args:
            request: Validated process parameters or a raw parameter dict.

        Returns:
            The shared process result for the requested staging directory.

        Raises:
            ValidationError: If a dict payload fails Pydantic schema validation.
        """
        if isinstance(request, dict):
            request = ProcessRequest.model_validate(request)
        return execute_process(request)


def get_manifest_response() -> McpManifestResponse:
    """Return the shared manifest wrapped in the MCP response envelope."""
    return get_mcp_manifest()


SERVER = DoclineMcpServer()
