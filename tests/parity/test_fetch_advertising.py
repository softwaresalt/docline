"""fetch tool advertising parity harness (064.018-T, red).

The advertised fetch description must state HTTP(S)-only and must not claim
local file-path support, matching execute_fetch's scheme rejection. Greened by
064.019-T.
"""

from __future__ import annotations

from docline.app import execute_fetch, get_manifest, get_mcp_manifest
from docline.app_models import FetchRequest
from docline.mcp.server import SERVER


def _fetch_description(tools) -> str:
    return next(t for t in tools if t.name == "fetch").description


def test_manifest_fetch_description_states_http_only() -> None:
    """The shared manifest fetch description advertises HTTP(S)-only."""
    desc = _fetch_description(get_manifest().tools)
    assert "HTTP" in desc
    assert "file path" not in desc.lower()


def test_mcp_manifest_fetch_description_states_http_only() -> None:
    """The MCP tools/list fetch description advertises HTTP(S)-only."""
    desc = _fetch_description(get_mcp_manifest().tools)
    assert "HTTP" in desc
    assert "file path" not in desc.lower()


def test_callable_tools_fetch_description_states_http_only() -> None:
    """The callable-surface fetch description advertises HTTP(S)-only."""
    desc = _fetch_description(SERVER.list_callable_tools().tools)
    assert "HTTP" in desc
    assert "file path" not in desc.lower()


def test_advertised_contract_matches_executor_scheme_rejection() -> None:
    """The advertised input contract matches execute_fetch's non-HTTP(S) rejection."""
    result = execute_fetch(FetchRequest(source="ftp://example.com"))
    assert result.success is False
    assert "http" in (result.error or "").lower()
