"""Stdio MCP server protocol, dispatch, security, and dual-era conformance harness.

Authored test-first across the 064-F task chain. Each task appends its scenarios
here; shared framing/driver helpers live at the top of the module.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from docline.app import get_manifest
from docline.mcp.server import SERVER, DoclineMcpServer

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

LEGACY_PROTOCOL_VERSION = "2025-11-25"
MODERN_PROTOCOL_VERSION = "2026-07-28"
MODERN_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
MODERN_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"


def _frame(obj: Any) -> bytes:
    """Encode a JSON-RPC message as a newline-delimited frame."""
    return json.dumps(obj).encode("utf-8") + b"\n"


def _dispatch(message: dict, server: DoclineMcpServer | None = None) -> dict | None:
    """Call the pure dispatch() with the module singleton by default."""
    from docline.mcp.stdio import dispatch

    return dispatch(message, server or SERVER)


class _EofStdin:
    """Non-greedy binary stdin fake that yields all bytes then EOF.

    Exposes ``read1`` only; a greedy ``read`` records and raises so a greedy
    transport cannot pass the liveness/framing tests.
    """

    def __init__(self, data: bytes) -> None:
        self._buf = bytearray(data)
        self.greedy_read_called = False

    def read1(self, size: int = -1) -> bytes:
        if not self._buf:
            return b""
        if size is None or size < 0:
            size = len(self._buf)
        chunk = bytes(self._buf[:size])
        del self._buf[:size]
        return chunk

    def read(self, size: int = -1) -> bytes:  # pragma: no cover - guard
        self.greedy_read_called = True
        raise AssertionError("greedy read() is prohibited; serve() must use read1()")


class _RecordingStdout:
    """Binary stdout fake recording writes and flush events."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.flush_count = 0
        self.frames_at_flush: list[int] = []

    def write(self, data: bytes) -> int:
        self._buf.extend(data)
        return len(data)

    def flush(self) -> None:
        self.flush_count += 1
        self.frames_at_flush.append(self._buf.count(b"\n"))

    def responses(self) -> list[dict]:
        return [json.loads(line) for line in bytes(self._buf).split(b"\n") if line.strip()]


def _drive_serve(
    frames: list[Any],
    server: DoclineMcpServer | None = None,
    timeout: float = 10.0,
) -> list[dict]:
    """Run serve() to completion over ``frames`` (EOF-first) and return responses."""
    from docline.mcp.stdio import serve

    payload = b"".join(
        _frame(f) if not isinstance(f, (bytes, bytearray)) else bytes(f) for f in frames
    )
    stdin = _EofStdin(payload)
    stdout = _RecordingStdout()
    worker = threading.Thread(target=serve, args=(stdin, stdout, server or SERVER))
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), "serve() did not terminate on EOF within timeout"
    return stdout.responses()


class _InteractiveStdin:
    """Interactive non-greedy stdin fake.

    Releases the first frame immediately but withholds each subsequent frame
    until the previous response has been FLUSHED to the paired stdout. ``read1``
    blocks (bounded) while the next frame is gated; a greedy ``read`` is
    prohibited.
    """

    def __init__(self, frames: list[bytes], stdout: _GatedStdout, timeout: float = 5.0) -> None:
        self._frames = frames
        self._stdout = stdout
        self._timeout = timeout
        self._buf = bytearray()
        self._delivered = 0
        self._cond = threading.Condition()
        self.greedy_read_called = False
        stdout.bind(self._cond)
        # Release the first frame immediately.
        self._buf.extend(self._frames[0])
        self._delivered = 1

    def _maybe_release(self) -> None:
        # Release the next frame once flushes >= number of frames already delivered.
        if self._delivered < len(self._frames) and self._stdout.flush_count >= self._delivered:
            self._buf.extend(self._frames[self._delivered])
            self._delivered += 1

    def read1(self, size: int = -1) -> bytes:
        with self._cond:
            deadline_hit = False
            while not self._buf and self._delivered < len(self._frames):
                self._maybe_release()
                if self._buf:
                    break
                if not self._cond.wait(self._timeout):
                    deadline_hit = True
                    break
            if deadline_hit and not self._buf:
                raise AssertionError("read1() blocked past deadline: response was not flushed")
            if not self._buf:
                return b""
            if size is None or size < 0:
                size = len(self._buf)
            chunk = bytes(self._buf[:size])
            del self._buf[:size]
            return chunk

    def read(self, size: int = -1) -> bytes:  # pragma: no cover - guard
        self.greedy_read_called = True
        raise AssertionError("greedy read() is prohibited; serve() must use read1()")


class _GatedStdout(_RecordingStdout):
    """Recording stdout that notifies a bound condition on flush."""

    def __init__(self) -> None:
        super().__init__()
        self._cond: threading.Condition | None = None

    def bind(self, cond: threading.Condition) -> None:
        self._cond = cond

    def flush(self) -> None:
        super().flush()
        if self._cond is not None:
            with self._cond:
                self._cond.notify_all()


# ---------------------------------------------------------------------------
# 064.001-T — Scenario 1: initialize handshake + interactive serve() liveness
# ---------------------------------------------------------------------------


def test_initialize_returns_pinned_version_capabilities_serverinfo() -> None:
    """Legacy initialize returns pinned protocolVersion + capabilities + serverInfo."""
    resp = _dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == LEGACY_PROTOCOL_VERSION
    assert "capabilities" in result
    assert "serverInfo" in result
    assert result["serverInfo"].get("name")


def test_serve_interactive_liveness_non_greedy_read_and_per_frame_flush() -> None:
    """serve() reads non-greedily and flushes after every response so an
    interactive client (send -> await response -> send next, stdin open) never
    deadlocks. Withholds the second frame until the first response is flushed."""
    from docline.mcp.stdio import serve

    frames = [
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    stdout = _GatedStdout()
    stdin = _InteractiveStdin(frames, stdout, timeout=5.0)
    worker = threading.Thread(target=serve, args=(stdin, stdout, SERVER))
    worker.start()
    worker.join(10.0)
    assert not worker.is_alive(), "serve() deadlocked or did not exit on EOF"
    assert stdin.greedy_read_called is False
    responses = stdout.responses()
    assert [r["id"] for r in responses] == [1, 2]
    # Every response frame was flushed (flush count covers both frames).
    assert stdout.flush_count >= 2


# ---------------------------------------------------------------------------
# 064.001-T — Scenario 2: callable discovery/parity + list_tools unchanged
# ---------------------------------------------------------------------------


def _normalize_tool(tool: dict) -> dict:
    """Normalize a tools/list entry to {name, inputSchema} for semantic parity."""
    schema = tool.get("inputSchema", tool.get("parameters"))
    return {"name": tool["name"], "inputSchema": schema}


def test_tools_list_matches_callable_allowlist() -> None:
    """tools/list is derived from list_callable_tools(): semantic parity (name +
    normalized schema) vs the callable-filtered manifest, not the raw 4-tool set."""
    resp = _dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert resp is not None
    advertised = [_normalize_tool(t) for t in resp["result"]["tools"]]
    callable_manifest = SERVER.list_callable_tools().model_dump(by_alias=True)["tools"]
    expected = [_normalize_tool(t) for t in callable_manifest]
    assert advertised == expected
    names = [t["name"] for t in advertised]
    assert names == ["fetch", "process", "export_schema"]
    assert "ingest_local_dir" not in names


def test_callable_process_schema_omits_workspace_root() -> None:
    """The advertised process inputSchema omits workspace_root (H1 divergence)."""
    callable_manifest = SERVER.list_callable_tools().model_dump(by_alias=True)["tools"]
    process = next(t for t in callable_manifest if t["name"] == "process")
    assert "workspace_root" not in process["inputSchema"]["properties"]


def test_list_tools_unchanged_full_manifest() -> None:
    """SERVER.list_tools() still exposes the full four-tool shared manifest."""
    manifest = get_manifest()
    listed = SERVER.list_tools().model_dump(by_alias=True)["tools"]
    assert [t["name"] for t in listed] == [t.name for t in manifest.tools]
    assert len(listed) == 4


def test_transport_advertises_callable_set_only() -> None:
    """Adapter invariant: the transport tools/list == list_callable_tools(), never list_tools()."""
    resp = _dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    advertised_names = [t["name"] for t in resp["result"]["tools"]]
    callable_names = [
        t["name"] for t in SERVER.list_callable_tools().model_dump(by_alias=True)["tools"]
    ]
    list_tools_names = [t["name"] for t in SERVER.list_tools().model_dump(by_alias=True)["tools"]]
    assert advertised_names == callable_names
    assert advertised_names != list_tools_names


# ---------------------------------------------------------------------------
# 064.001-T — Scenario 3: dispatchability of every advertised tool
# ---------------------------------------------------------------------------


def test_every_advertised_tool_is_dispatchable(monkeypatch, tmp_path) -> None:
    """Every advertised MCP tool is invocable via call_tool (no advertise-but-uncallable gap)."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    advertised = [
        t["name"] for t in SERVER.list_callable_tools().model_dump(by_alias=True)["tools"]
    ]
    args_by_tool = {
        "fetch": {"source": "ftp://example.com"},
        "process": {"staging_dir": "staging", "output_dir": "output"},
        "export_schema": {},
    }
    for name in advertised:
        result = SERVER.call_tool(name, args_by_tool[name])
        assert result is not None
