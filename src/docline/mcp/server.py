"""MCP server adapters for manifest discovery and shared fetch/process operations."""

import copy
from enum import Enum

from pydantic import BaseModel, ConfigDict

from docline.app import execute_fetch, execute_process, get_manifest, get_mcp_manifest
from docline.app_models import (
    FetchRequest,
    FetchResult,
    ManifestTool,
    McpManifestResponse,
    ProcessRequest,
    ProcessResult,
)
from docline.mcp.exceptions import McpTransportError, UnknownToolError
from docline.schema.export import export_base_frontmatter_schema_json

# Protocol versions advertised by both eras (modern first, legacy pinned).
LEGACY_PROTOCOL_VERSION = "2025-11-25"
MODERN_PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_PROTOCOL_VERSIONS = (MODERN_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION)

# Server identity — single source consumed by both initialize and server/discover.
SERVER_NAME = "docline-mcp"
SERVER_VERSION = "0.1.0"

# Tools dispatchable on the untrusted MCP surface (a subset of the shared
# manifest; ``ingest_local_dir`` is excluded — its ``source_path`` has no
# workspace-containment validator).
_CALLABLE_TOOL_NAMES = ("fetch", "process", "export_schema")


class _ExportSchemaArgs(BaseModel):
    """Empty argument model for ``export_schema`` — rejects any non-empty args."""

    model_config = ConfigDict(extra="forbid")


def _omit_workspace_root(schema: dict[str, object]) -> dict[str, object]:
    """Return a deep copy of ``schema`` with the ``workspace_root`` property removed."""
    result = copy.deepcopy(schema)
    props = result.get("properties")
    if isinstance(props, dict):
        props.pop("workspace_root", None)
    required = result.get("required")
    if isinstance(required, list) and "workspace_root" in required:
        required.remove("workspace_root")
    return result


class TransportMode(Enum):
    """Approved MCP transport modes.

    Only stdio transport is approved for docline's MCP surface.
    """

    STDIO = "stdio"


class DoclineMcpServer:
    """Expose manifest discovery plus fetch/process adapters over approved stdio transport."""

    def __init__(self, transport_mode: "TransportMode | str" = TransportMode.STDIO) -> None:
        """Initialize the MCP server with the approved transport mode.

        Accepts either a :class:`TransportMode` enum member or the string
        ``"stdio"`` so that callers using config or environment values can
        pass the mode without constructing the enum directly.

        Args:
            transport_mode: Requested MCP transport configuration. Must resolve
                to :attr:`TransportMode.STDIO` after coercion.

        Raises:
            McpTransportError: If any transport other than stdio is requested.
        """
        if isinstance(transport_mode, str):
            try:
                transport_mode = TransportMode(transport_mode)
            except ValueError as err:
                raise McpTransportError(
                    f"Unsupported MCP transport: {transport_mode!r}. Only stdio is approved."
                ) from err
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

    def export_schema(self) -> str:
        """Return the BaseFrontmatter v1 JSON Schema as a deterministic JSON string.

        Returns:
            A ``sort_keys`` normalized JSON Schema document declaring the
            Draft 2020-12 dialect and the stable docline ``$id``.
        """
        return export_base_frontmatter_schema_json()

    def list_callable_tools(self) -> McpManifestResponse:
        """Return the callable allow-list manifest for the untrusted MCP surface.

        Excludes ``ingest_local_dir`` and removes the ``workspace_root`` property
        from the advertised ``process`` schema (the two sanctioned MCP-only
        parity divergences). This — not :meth:`list_tools` — is the sole tool
        advertise source for the stdio transport.
        """
        tools: list[ManifestTool] = []
        for tool in get_manifest().tools:
            if tool.name not in _CALLABLE_TOOL_NAMES:
                continue
            params = tool.parameters
            if tool.name == "process":
                params = _omit_workspace_root(params)
            tools.append(
                ManifestTool(name=tool.name, description=tool.description, parameters=params)
            )
        return McpManifestResponse(tools=tools)

    def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Dispatch a ``tools/call`` through the static callable allow-list.

        Each allow-list entry is a uniform ``(arguments: dict) -> object``
        adapter — no ``getattr`` dispatch, so dunder/attribute injection is
        impossible and every callable name is explicitly enumerated.

        Args:
            name: The requested tool name.
            arguments: The raw argument dict from the tools/call params.

        Returns:
            The domain result (``FetchResult``/``ProcessResult``/``str``).

        Raises:
            UnknownToolError: When ``name`` is absent from the allow-list.
            ValidationError: When ``arguments`` fail model validation.
        """
        if name == "fetch":
            return self.fetch(arguments)
        if name == "process":
            return self.process(arguments)
        if name == "export_schema":
            _ExportSchemaArgs.model_validate(arguments or {})
            return self.export_schema()
        raise UnknownToolError(f"Unknown or unroutable tool: {name!r}")

    def describe_server(self) -> dict[str, object]:
        """Return the single-source server identity/version/capability descriptor.

        Consumed by both the legacy ``initialize`` and the modern
        ``server/discover`` so the two negotiation entry points cannot drift.
        """
        return {
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
            "protocolVersion": LEGACY_PROTOCOL_VERSION,
            "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        }


def get_manifest_response() -> McpManifestResponse:
    """Return the shared manifest wrapped in the MCP response envelope."""
    return get_mcp_manifest()


SERVER = DoclineMcpServer()
