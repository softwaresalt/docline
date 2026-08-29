"""Stdio MCP server protocol, dispatch, security, and dual-era conformance harness.

Authored test-first across the 064-F task chain. Each task appends its scenarios
here; shared framing/driver helpers live at the top of the module.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from docline.app import execute_fetch, execute_process, get_manifest
from docline.app_models import FetchRequest, ProcessRequest
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


# A legacy handshake frame prepended by the drivers so the per-connection legacy
# era latch (064.023-T) is set before subsequent bare frames are dispatched. Its
# response is stripped from the returned list. Dedicated pre-initialize reject
# tests opt out with ``latch=False``.
_LATCH_FRAME = _frame({"jsonrpc": "2.0", "id": "__latch__", "method": "initialize", "params": {}})


def _drive_serve(
    frames: list[Any],
    server: DoclineMcpServer | None = None,
    timeout: float = 10.0,
    latch: bool = True,
) -> list[dict]:
    """Run serve() to completion over ``frames`` (EOF-first) and return responses.

    When ``latch`` is True (default) a legacy ``initialize`` frame is prepended so
    the per-connection legacy era latch is set; its response is dropped so callers
    observe only their own frames' responses.
    """
    from docline.mcp.stdio import serve

    payload = b"".join(
        _frame(f) if not isinstance(f, (bytes, bytearray)) else bytes(f) for f in frames
    )
    if latch:
        payload = _LATCH_FRAME + payload
    stdin = _EofStdin(payload)
    stdout = _RecordingStdout()
    worker = threading.Thread(target=serve, args=(stdin, stdout, server or SERVER))
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), "serve() did not terminate on EOF within timeout"
    responses = stdout.responses()
    if latch:
        # Drop the prepended latch handshake response.
        responses = [r for r in responses if r.get("id") != "__latch__"]
    return responses


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


def _drive_raw(*raw_frames: bytes) -> list[dict]:
    """Drive serve() over raw frame bytes (real parse+dispatch path)."""
    return _drive_serve(list(raw_frames))


def _single(raw: bytes) -> dict:
    """Drive one raw frame and return its single response."""
    responses = _drive_raw(raw)
    assert len(responses) == 1, f"expected one response, got {responses!r}"
    return responses[0]


# ---------------------------------------------------------------------------
# 064.005-T — Scenario 1: tools/call parity + CallToolResult wire shape
# ---------------------------------------------------------------------------


def _is_content_block_list(content: Any) -> bool:
    if not isinstance(content, list) or not content:
        return False
    for block in content:
        if not isinstance(block, dict) or "type" not in block:
            return False
        if block["type"] == "text" and not isinstance(block.get("text"), str):
            return False
    return True


def test_tools_call_export_schema_wire_shape() -> None:
    """export_schema returns a CallToolResult with a text ContentBlock[], not a raw str."""
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "export_schema", "arguments": {}},
        }
    )
    result = resp["result"]
    assert _is_content_block_list(result["content"])
    assert result.get("isError", False) is False
    # The schema text is carried in content, not as a bare string result.
    assert (
        "BaseFrontmatter" in result["content"][0]["text"]
        or "$schema" in result["content"][0]["text"]
    )


def test_tools_call_process_success_wire_shape(monkeypatch, tmp_path) -> None:
    """process success returns CallToolResult with structuredContent mirroring ProcessResult."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "process",
                "arguments": {"staging_dir": "staging", "output_dir": "output"},
            },
        }
    )
    result = resp["result"]
    assert _is_content_block_list(result["content"])
    assert result.get("isError", False) is False
    expected = execute_process(ProcessRequest(staging_dir="staging", output_dir="output"))
    assert result["structuredContent"] == expected.model_dump()


def test_tools_call_fetch_failure_maps_to_iserror() -> None:
    """A validated-but-failed fetch (success=False) maps to isError=true with error in content."""
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"source": "ftp://example.com"}},
        }
    )
    result = resp["result"]
    assert result["isError"] is True
    assert _is_content_block_list(result["content"])
    expected = execute_fetch(FetchRequest(source="ftp://example.com"))
    assert result["structuredContent"] == expected.model_dump()
    # Parity with CLI/app layer.
    assert expected.success is False


# ---------------------------------------------------------------------------
# 064.005-T — Scenario 2: error envelopes (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        b'{"jsonrpc":"2.0","id":1,"method":"ping"\n',  # truncated / invalid JSON
        b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n',  # non-finite token NaN
        b'{"jsonrpc":"2.0","id":Infinity,"method":"ping"}\n',  # Infinity token
        b'{"jsonrpc":"2.0","id":-Infinity,"method":"ping"}\n',  # -Infinity token
    ],
)
def test_parse_error_minus_32700(raw: bytes) -> None:
    """Invalid JSON — including non-finite NaN/Infinity tokens — returns -32700 id:null."""
    resp = _single(raw)
    assert resp["error"]["code"] == -32700
    assert resp["id"] is None


@pytest.mark.parametrize(
    "message,expected_id",
    [
        ([], None),  # non-object root (array)
        (42, None),  # non-object root (number)
        ("s", None),  # non-object root (string)
        (True, None),  # non-object root (bool)
        (None, None),  # non-object root (null)
        ({"id": 5}, 5),  # missing jsonrpc, valid id echoed
        ({"jsonrpc": "1.0", "id": 5, "method": "ping"}, 5),  # bad jsonrpc, id echoed
        ({"jsonrpc": "2.0", "id": 5}, 5),  # missing method, id echoed
        ({"jsonrpc": "2.0", "id": 5, "method": ""}, 5),  # empty method, id echoed
        ({"jsonrpc": "2.0", "id": 5, "method": 7}, 5),  # non-string method, id echoed
        ({"jsonrpc": "2.0", "id": {"x": 1}, "method": "ping"}, None),  # object id
        ({"jsonrpc": "2.0", "id": [1], "method": "ping"}, None),  # array id
        ({"jsonrpc": "2.0", "id": True, "method": "ping"}, None),  # bool id
        ({"jsonrpc": "2.0", "id": None, "method": "ping"}, None),  # null id (present)
        ({"jsonrpc": "2.0", "method": "ping"}, None),  # id-absent malformed? no: valid -> notif
    ],
)
def test_invalid_request_minus_32600(message: Any, expected_id: Any) -> None:
    """Request-shape validation returns -32600 with correct id echo/null semantics."""
    if message == {"jsonrpc": "2.0", "method": "ping"}:
        # Otherwise-valid no-id request is a notification (silent), not -32600.
        responses = _drive_raw(_frame(message))
        assert responses == []
        return
    responses = _drive_raw(_frame(message))
    assert len(responses) == 1
    resp = responses[0]
    assert resp["error"]["code"] == -32600
    assert resp["id"] == expected_id


@pytest.mark.parametrize("literal", [b"1e400", b"-1e400"])
def test_non_finite_numeric_id_minus_32600(literal: bytes) -> None:
    """A finite-overflow numeric id (1e400 -> inf) is rejected -32600 id:null."""
    frame = b'{"jsonrpc":"2.0","id":' + literal + b',"method":"ping"}\n'
    resp = _single(frame)
    assert resp["error"]["code"] == -32600
    assert resp["id"] is None


def test_id_absent_malformed_not_suppressed() -> None:
    """A malformed payload lacking an id returns -32600 id:null (not silence)."""
    resp = _single(b'{"jsonrpc":"2.0"}\n')  # no method, no id
    assert resp["error"]["code"] == -32600
    assert resp["id"] is None


def test_method_not_found_minus_32601() -> None:
    """A well-formed request with an unknown method returns -32601."""
    resp = _single(_frame({"jsonrpc": "2.0", "id": 6, "method": "does/not/exist"}))
    assert resp["error"]["code"] == -32601
    assert resp["id"] == 6


def test_whitespace_method_routes_to_32601() -> None:
    """A whitespace-only method is a valid (present, non-empty) method -> -32601, not -32600."""
    resp = _single(_frame({"jsonrpc": "2.0", "id": 7, "method": "   "}))
    assert resp["error"]["code"] == -32601


def test_invalid_params_minus_32602_export_schema_nonempty_args() -> None:
    """export_schema with non-empty arguments is a -32602 invalid-params envelope."""
    resp = _single(
        _frame(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "export_schema", "arguments": {"unexpected": 1}},
            }
        )
    )
    assert resp["error"]["code"] == -32602


def test_internal_error_minus_32603(monkeypatch) -> None:
    """An unexpected adapter exception degrades to a -32603 internal-error envelope."""

    def _boom(name: str, arguments: dict) -> object:
        raise RuntimeError("unexpected /abs/path/leak")

    monkeypatch.setattr(SERVER, "call_tool", _boom)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"source": "ftp://x"}},
        }
    )
    assert resp["error"]["code"] == -32603
    # No absolute path / traceback leakage in the message.
    assert "/abs/path/leak" not in json.dumps(resp)


# ---------------------------------------------------------------------------
# 064.005-T — Scenario 3: id-less notification silence + id membership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["notifications/initialized", "some/unknown/notification"])
def test_notification_is_silent(method: str) -> None:
    """An otherwise-valid request lacking an id is silent (known AND unknown method)."""
    responses = _drive_raw(_frame({"jsonrpc": "2.0", "method": method}))
    assert responses == []


@pytest.mark.parametrize("id_value", [0, ""])
def test_id_absence_is_by_membership_not_truthiness(id_value: Any) -> None:
    """A present falsy id (0 or "") receives a normal echoed response, never suppression."""
    resp = _single(_frame({"jsonrpc": "2.0", "id": id_value, "method": "ping"}))
    assert resp["id"] == id_value
    assert resp["result"] == {}


# ---------------------------------------------------------------------------
# 064.006-T — Security gates H1-H3
# ---------------------------------------------------------------------------


class _RecordingReadStdin:
    """Non-greedy stdin recording each read1 request size; enforces per-read bound."""

    def __init__(self, data: bytes, chunk_size: int) -> None:
        self._buf = bytearray(data)
        self._chunk_size = chunk_size
        self.read_sizes: list[int] = []

    def read1(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if not self._buf:
            return b""
        assert size is not None and 0 <= size <= self._chunk_size, (
            f"read1 requested {size} bytes; must be bounded by CHUNK_SIZE {self._chunk_size}"
        )
        chunk = bytes(self._buf[:size])
        del self._buf[:size]
        return chunk

    def read(self, size: int = -1) -> bytes:  # pragma: no cover - guard
        raise AssertionError("greedy read() prohibited")


def _drive_bytes(
    payload: bytes, server: DoclineMcpServer | None = None, latch: bool = True
) -> tuple[list[dict], list[int]]:
    """Drive serve() over a raw byte payload using the recording stdin.

    When ``latch`` is True (default) a legacy ``initialize`` frame is prepended so
    the per-connection legacy era latch is set; its response is dropped.
    """
    from docline.mcp.stdio import CHUNK_SIZE, serve

    if latch:
        payload = _LATCH_FRAME + payload
    stdin = _RecordingReadStdin(payload, CHUNK_SIZE)
    stdout = _RecordingStdout()
    worker = threading.Thread(target=serve, args=(stdin, stdout, server or SERVER))
    worker.start()
    worker.join(15.0)
    assert not worker.is_alive(), "serve() did not terminate within timeout"
    responses = stdout.responses()
    if latch:
        responses = [r for r in responses if r.get("id") != "__latch__"]
    return responses, stdin.read_sizes


def _exact_payload_frame(n: int) -> bytes:
    """Build a valid ping JSON frame whose payload is exactly ``n`` bytes, plus newline."""
    base = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"p": ""}}
    base_len = len(json.dumps(base, separators=(",", ":")))
    pad = n - base_len
    assert pad >= 0
    obj = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"p": "a" * pad}}
    payload = json.dumps(obj, separators=(",", ":")).encode("ascii")
    assert len(payload) == n
    return payload + b"\n"


def test_h1_process_workspace_root_escape_rejected(monkeypatch, tmp_path) -> None:
    """H1: process with workspace_root='/' and 'C:\\' rejected -32602, nothing written outside."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    for root in ("/", "C:\\"):
        resp = _dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "process",
                    "arguments": {"staging_dir": "staging", "workspace_root": root},
                },
            }
        )
        assert resp["error"]["code"] == -32602


def test_h2_exact_n_frame_accepted() -> None:
    """H2: a frame of exactly MAX_FRAME_BYTES payload bytes + newline is accepted."""
    from docline.mcp.stdio import MAX_FRAME_BYTES

    payload = _exact_payload_frame(MAX_FRAME_BYTES)
    responses, _ = _drive_bytes(payload)
    assert len(responses) == 1
    assert responses[0]["result"] == {}


def test_h2_n_plus_one_rejected_drained_and_resynced() -> None:
    """H2: payload of MAX_FRAME_BYTES+1 with no newline overflows, then the loop resyncs."""
    from docline.mcp.stdio import MAX_FRAME_BYTES

    oversized = b"a" * (MAX_FRAME_BYTES + 1)  # no newline within cap
    trailing = b"restofframe\n"
    good = _frame({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    responses, read_sizes = _drive_bytes(oversized + trailing + good)
    codes = [r.get("error", {}).get("code") for r in responses if "error" in r]
    assert -32700 in codes  # oversized frame -> parse/framing error envelope
    # The following valid frame is dispatched after resync.
    assert any(r.get("id") == 2 and r.get("result") == {} for r in responses)
    # Bounded memory: no single read requested more than CHUNK_SIZE.
    from docline.mcp.stdio import CHUNK_SIZE

    assert all(s <= CHUNK_SIZE for s in read_sizes)


def test_h2_deeply_nested_array_degrades_and_loop_survives() -> None:
    """H2: a deeply nested JSON array degrades to an error envelope; the loop survives."""
    nested = (b"[" * 4000) + (b"]" * 4000) + b"\n"
    good = _frame({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    responses, _ = _drive_bytes(nested + good)
    assert any("error" in r for r in responses)
    assert any(r.get("id") == 3 and r.get("result") == {} for r in responses)


def test_h2_two_frames_in_single_chunk_both_dispatched() -> None:
    """H2: two complete frames arriving together are both dispatched (carry-over buffer)."""
    a = _frame({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    b = _frame({"jsonrpc": "2.0", "id": 5, "method": "ping"})
    responses, _ = _drive_bytes(a + b)
    assert [r["id"] for r in responses] == [4, 5]


def test_h3_no_absolute_paths_in_envelope(monkeypatch, tmp_path) -> None:
    """H3: a containment/validation failure envelope contains no absolute-path substring."""
    monkeypatch.chdir(tmp_path)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "process", "arguments": {"staging_dir": "../escape"}},
        }
    )
    blob = json.dumps(resp)
    assert str(tmp_path) not in blob
    assert "\\escape" not in blob and "/escape" not in blob


def test_h3_no_absolute_paths_in_iserror_content(monkeypatch, tmp_path) -> None:
    """H3: an isError tool result carries sanitized error text (no absolute paths)."""
    monkeypatch.chdir(tmp_path)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "process", "arguments": {"staging_dir": "nonexistent_dir"}},
        }
    )
    blob = json.dumps(resp.get("result", resp))
    assert str(tmp_path) not in blob


# ---------------------------------------------------------------------------
# 064.007-T — Security gates H4, H5, H6 (literal-IP smoke)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name",
    ["ingest_local_dir", "unknown_tool", "__init__", "__class__", "list_tools"],
)
def test_h4_unknown_or_unrouted_tool_fails_closed(tool_name: str) -> None:
    """H4: unknown/unrouted tool names (dunders, ingest_local_dir) -> -32602, not AttributeError."""
    resp = _single(
        _frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": {}},
            }
        )
    )
    assert resp["error"]["code"] == -32602


def test_h5_stdout_carries_only_jsonrpc_frames(monkeypatch, tmp_path) -> None:
    """H5: stdout carries only well-formed JSON-RPC frames across a process tool call."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    frame = _frame(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "process", "arguments": {"staging_dir": "staging"}},
        }
    )
    from docline.mcp.stdio import serve

    # Prepend a legacy initialize so the per-connection legacy latch is set.
    stdin = _EofStdin(_LATCH_FRAME + frame)
    stdout = _RecordingStdout()
    worker = threading.Thread(target=serve, args=(stdin, stdout, SERVER))
    worker.start()
    worker.join(15.0)
    assert not worker.is_alive()
    # Every non-empty line must be a well-formed JSON-RPC frame.
    for line in bytes(stdout._buf).split(b"\n"):
        if line.strip():
            obj = json.loads(line)
            assert obj["jsonrpc"] == "2.0"


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://169.254.169.254"])
def test_h6_literal_ip_fetch_rejected_end_to_end(url: str, monkeypatch, tmp_path) -> None:
    """H6 literal-IP smoke: tools/call fetch to loopback/metadata is rejected end-to-end."""
    monkeypatch.chdir(tmp_path)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"source": url}},
        }
    )
    result = resp["result"]
    # Rejected: mapped to an isError tool result (validated-but-failed fetch).
    assert result["isError"] is True


# ---------------------------------------------------------------------------
# 064.014-T - MCP untrusted-fetch end-to-end boundary harness
# ---------------------------------------------------------------------------


def test_e2e_ssrf_hostname_resolution_rejected(monkeypatch, tmp_path) -> None:
    """A tools/call fetch whose public hostname resolves to loopback is rejected e2e."""
    import socket

    monkeypatch.chdir(tmp_path)

    def _resolver(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _resolver)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"source": "http://internal.example.com"}},
        }
    )
    assert resp["result"]["isError"] is True


@pytest.mark.parametrize("max_pages", [1001, 5000])
def test_e2e_over_limit_max_pages_rejected_32602(max_pages: int) -> None:
    """An over-limit max_pages is rejected -32602 end-to-end (§H7 item 1)."""
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "fetch",
                "arguments": {"source": "http://example.com", "max_pages": max_pages},
            },
        }
    )
    assert resp["error"]["code"] == -32602


@pytest.mark.parametrize("depth", [65, 100])
def test_e2e_over_limit_depth_rejected_32602(depth: int) -> None:
    """An over-limit depth is rejected -32602 end-to-end (§H7 item 4b)."""
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "fetch",
                "arguments": {"source": "http://example.com", "depth": depth},
            },
        }
    )
    assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# 064.020-T — dual-era discovery + modern-negotiation harness (RED)
# ---------------------------------------------------------------------------

SERVERINFO_META_KEY = "io.modelcontextprotocol/serverInfo"
MODERN_METHODS = ["server/discover", "tools/list", "tools/call"]

_UNSET = object()


def _meta_block(
    version: Any = MODERN_PROTOCOL_VERSION,
    caps: Any = _UNSET,
    include_version: bool = True,
    include_caps: bool = True,
) -> dict:
    """Build a per-request modern _meta block with selectable members."""
    meta: dict[str, Any] = {}
    if include_version:
        meta[MODERN_VERSION_KEY] = version
    if include_caps:
        meta[MODERN_CAPS_KEY] = {} if caps is _UNSET else caps
    return meta


def _modern_msg(method: str, meta: dict, id_: int = 1) -> dict:
    """Build a modern JSON-RPC request carrying _meta inside params."""
    params: dict[str, Any] = {"_meta": meta}
    if method == "tools/call":
        params["name"] = "export_schema"
        params["arguments"] = {}
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}


def test_server_discover_returns_cacheable_discover_result() -> None:
    """server/discover with valid _meta returns a CacheableResult DiscoverResult."""
    resp = _dispatch(_modern_msg("server/discover", _meta_block(caps={"tools": {}})))
    assert resp is not None and "result" in resp, resp
    r = resp["result"]
    assert set(r["supportedVersions"]) == {MODERN_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION}
    assert r["supportedVersions"][0] == MODERN_PROTOCOL_VERSION  # modern first
    assert "capabilities" in r
    assert r["resultType"] == "complete"
    assert isinstance(r["ttlMs"], int) and r["ttlMs"] > 0
    assert isinstance(r["cacheScope"], str) and r["cacheScope"]
    assert r["_meta"][SERVERINFO_META_KEY]["name"]


def test_modern_tools_list_served_statelessly() -> None:
    """A modern tools/list (both _meta members, no handshake) carries the modern envelope."""
    resp = _dispatch(_modern_msg("tools/list", _meta_block()))
    assert resp is not None and "result" in resp, resp
    r = resp["result"]
    assert [t["name"] for t in r["tools"]] == ["fetch", "process", "export_schema"]
    assert r["resultType"] == "complete"
    assert isinstance(r["ttlMs"], int) and r["ttlMs"] > 0
    assert isinstance(r["cacheScope"], str) and r["cacheScope"]
    assert r["_meta"][SERVERINFO_META_KEY]["name"]


@pytest.mark.parametrize("method", MODERN_METHODS)
def test_modern_unsupported_version_minus_32022(method: str) -> None:
    """An unsupported modern _meta protocolVersion returns -32022 with supported+requested."""
    resp = _dispatch(_modern_msg(method, _meta_block(version="1999-01-01")))
    assert resp is not None and "error" in resp, resp
    err = resp["error"]
    assert err["code"] == -32022
    assert LEGACY_PROTOCOL_VERSION in err["data"]["supported"]
    assert MODERN_PROTOCOL_VERSION in err["data"]["supported"]
    assert err["data"]["requested"] == "1999-01-01"


@pytest.mark.parametrize("method", MODERN_METHODS)
@pytest.mark.parametrize(
    "kw",
    [
        {"include_caps": False},  # missing clientCapabilities member
        {"caps": "not-an-object"},  # malformed type (str)
        {"caps": 123},  # malformed type (int)
        {"caps": ["x"]},  # malformed type (list)
    ],
)
def test_modern_missing_or_malformed_caps_minus_32602(method: str, kw: dict) -> None:
    """Missing/malformed clientCapabilities (after a valid version) returns -32602."""
    resp = _dispatch(_modern_msg(method, _meta_block(**kw)))
    assert resp is not None and "error" in resp, resp
    assert resp["error"]["code"] == -32602


@pytest.mark.parametrize("method", MODERN_METHODS)
@pytest.mark.parametrize("bad_version", [123, None, 4.5, ["2026-07-28"], {"v": 1}])
def test_modern_malformed_type_version_minus_32602(method: str, bad_version: Any) -> None:
    """A present-but-malformed-type protocolVersion is modern-classified and -32602."""
    resp = _dispatch(_modern_msg(method, _meta_block(version=bad_version)))
    assert resp is not None and "error" in resp, resp
    # Malformed member type -> -32602, never a legacy fallthrough result and never -32022.
    assert resp["error"]["code"] == -32602


@pytest.mark.parametrize("method", MODERN_METHODS)
def test_modern_version_precedence_over_caps(method: str) -> None:
    """An unsupported version wins over an also-absent clientCapabilities: -32022, not -32602."""
    resp = _dispatch(_modern_msg(method, _meta_block(version="1999-01-01", include_caps=False)))
    assert resp is not None and "error" in resp, resp
    assert resp["error"]["code"] == -32022


# ---------------------------------------------------------------------------
# 064.021-T — legacy-era retention + era-routing harness
# ---------------------------------------------------------------------------


def test_legacy_initialize_handshake_anchor() -> None:
    """Scenario (a) green anchor: the legacy initialize/ping/notifications path is retained."""
    init = _dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
    assert init["protocolVersion"] == LEGACY_PROTOCOL_VERSION
    assert "capabilities" in init and "serverInfo" in init
    assert init["serverInfo"].get("name")
    # notifications/initialized is a silent notification.
    assert _drive_serve([{"jsonrpc": "2.0", "method": "notifications/initialized"}]) == []
    # ping -> {} (legacy-only utility).
    ping = _dispatch({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"]
    assert ping == {}


def test_era_routing_modern_member_served_without_handshake() -> None:
    """Scenario (b)(i): a modern-member request is served modern with no prior initialize."""
    responses = _drive_serve([_modern_msg("tools/list", _meta_block(), id_=1)], latch=False)
    r = responses[0]["result"]
    assert r["resultType"] == "complete"


def test_era_routing_legacy_after_initialize() -> None:
    """Scenario (b)(i): after initialize, a bare (no modern member) request is served legacy."""
    frames = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    responses = _drive_serve(frames, latch=False)
    r2 = next(r for r in responses if r.get("id") == 2)["result"]
    assert "resultType" not in r2  # plain legacy result, not a modern envelope
    assert [t["name"] for t in r2["tools"]] == ["fetch", "process", "export_schema"]


def test_ancillary_meta_after_initialize_stays_legacy() -> None:
    """Scenario (b)(i-a): a retained legacy client's ancillary _meta stays on the legacy path."""
    frames = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {"_meta": {"progressToken": "tok"}},
        },
    ]
    responses = _drive_serve(frames, latch=False)
    r2 = next(r for r in responses if r.get("id") == 2)
    # Not routed to the modern validator and rejected; served as a plain legacy result.
    assert "result" in r2
    assert "resultType" not in r2["result"]


def test_modern_wins_after_legacy_latch() -> None:
    """Scenario (b)(i-b): a modern-member request after a legacy latch is still served modern."""
    frames = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        _modern_msg("tools/list", _meta_block(), id_=2),
    ]
    responses = _drive_serve(frames, latch=False)
    r2 = next(r for r in responses if r.get("id") == 2)["result"]
    assert r2["resultType"] == "complete"


def test_no_drift_initialize_vs_server_discover() -> None:
    """Scenario (b)(ii): initialize and server/discover share one identity source (no drift)."""
    init = _dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
    disc = _dispatch(_modern_msg("server/discover", _meta_block(caps={"tools": {}})))["result"]
    assert init["serverInfo"] == disc["_meta"][SERVERINFO_META_KEY]
    assert init["capabilities"] == disc["capabilities"]
    # Legacy singular protocolVersion is CONTAINED IN modern plural supportedVersions.
    assert init["protocolVersion"] in disc["supportedVersions"]


@pytest.mark.parametrize(
    "frame",
    [
        {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},  # metadata-free
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "export_schema", "arguments": {}},
        },  # metadata-free tools/call
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/list",
            "params": {"_meta": {"progressToken": "tok"}},
        },  # ancillary-_meta-only
        {"jsonrpc": "2.0", "id": 9, "method": "ping"},  # legacy utility pre-latch
    ],
)
def test_pre_initialize_operation_rejected(frame: dict) -> None:
    """Scenario (b)(iii): an op lacking a modern member before init is rejected, not legacy."""
    responses = _drive_serve([frame], latch=False)
    assert len(responses) == 1
    assert "error" in responses[0], responses[0]
    assert responses[0]["error"]["code"] == -32600


def _modern_tools_call(name: str, arguments: dict, id_: int = 1) -> dict:
    """Build a modern (_meta-bearing) tools/call for the named tool."""
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "method": "tools/call",
        "params": {"_meta": _meta_block(), "name": name, "arguments": arguments},
    }


def test_modern_tools_call_h1_workspace_root_rejected(monkeypatch, tmp_path) -> None:
    """Scenario (c): the modern path enforces H1 workspace_root reject identically to legacy."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    resp = _dispatch(
        _modern_tools_call("process", {"staging_dir": "staging", "workspace_root": "/"})
    )
    assert resp["error"]["code"] == -32602


def test_modern_tools_call_success_wraps_calltoolresult(monkeypatch, tmp_path) -> None:
    """Scenario (c): a modern success wraps a valid CallToolResult in the resultType envelope."""
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    r = _dispatch(
        _modern_tools_call("process", {"staging_dir": "staging", "output_dir": "output"})
    )["result"]
    assert r["resultType"] == "complete"
    assert r["_meta"][SERVERINFO_META_KEY]["name"]
    assert _is_content_block_list(r["content"])
    assert r.get("isError", False) is False
    expected = execute_process(ProcessRequest(staging_dir="staging", output_dir="output"))
    assert r["structuredContent"] == expected.model_dump()


def test_modern_tools_call_failure_maps_to_iserror() -> None:
    """Scenario (c): a modern validated-but-failed fetch maps to isError under the envelope."""
    r = _dispatch(_modern_tools_call("fetch", {"source": "ftp://example.com"}))["result"]
    assert r["resultType"] == "complete"
    assert r["isError"] is True
    assert _is_content_block_list(r["content"])


def test_modern_export_schema_wire_shape() -> None:
    """Scenario (c): a modern export_schema returns a ContentBlock[] under the envelope."""
    r = _dispatch(_modern_msg("tools/call", _meta_block()))["result"]
    assert r["resultType"] == "complete"
    assert _is_content_block_list(r["content"])


@pytest.mark.parametrize("bad_id", [{"x": 1}, [1], True])
def test_modern_malformed_id_short_circuits_minus_32600(bad_id: Any) -> None:
    """Scenario (c): request-shape id validation precedes _meta/era for the modern path too."""
    frame = _frame(
        {
            "jsonrpc": "2.0",
            "id": bad_id,
            "method": "tools/call",
            "params": {"_meta": _meta_block(), "name": "export_schema", "arguments": {}},
        }
    )
    resp = _single(frame)
    assert resp["error"]["code"] == -32600
    assert resp["id"] is None
    assert "result" not in resp


def test_modern_malformed_id_unsupported_version_still_32600() -> None:
    """Scenario (c): a malformed id short-circuits even with an unsupported modern version."""
    frame = _frame(
        {
            "jsonrpc": "2.0",
            "id": {"bad": 1},
            "method": "tools/call",
            "params": {"_meta": _meta_block(version="1999-01-01"), "name": "export_schema"},
        }
    )
    resp = _single(frame)
    assert resp["error"]["code"] == -32600
    assert resp["id"] is None


def test_modern_meta_malformed_no_id_returns_32600_not_suppressed() -> None:
    """Scenario (c): a malformed _meta-bearing payload with no id is -32600 id:null, not silent."""
    resp = _single(_frame({"jsonrpc": "2.0", "params": {"_meta": _meta_block()}}))
    assert resp["error"]["code"] == -32600
    assert resp["id"] is None


# ---------------------------------------------------------------------------
# 064.031-T — §H8 external-engine adapter-policy harness (advertise + dispatch)
# ---------------------------------------------------------------------------

_LOCAL_ENGINES = {"auto", "docling", "heuristic"}
_FULL_ENGINES = {"auto", "docling", "heuristic", "mistral_ocr"}


def _process_enum(server: DoclineMcpServer) -> list[str]:
    """Return the advertised process pdf_engine enum from list_callable_tools()."""
    tools = server.list_callable_tools().model_dump(by_alias=True)["tools"]
    process = next(t for t in tools if t["name"] == "process")
    return process["inputSchema"]["properties"]["pdf_engine"]["enum"]


def test_h8_default_server_advertises_only_local_engines() -> None:
    """Scenario (a): a default server omits external engines from the advertised enum."""
    assert set(_process_enum(DoclineMcpServer())) == _LOCAL_ENGINES


def test_h8_optin_server_advertises_full_engine_enum() -> None:
    """Scenario (a): an opt-in server advertises the full shared engine enum."""
    optin = DoclineMcpServer(external_pdf_engines_enabled=True)
    assert set(_process_enum(optin)) == _FULL_ENGINES


def test_h8_default_dispatch_denies_external_engine(monkeypatch, tmp_path) -> None:
    """Scenario (b): the adapter denies a non-allow-list engine before egress on both hops."""
    import docline.readers.mistral as mistral_mod
    from docline.mcp.exceptions import ExternalEngineNotAllowedError

    called = {"n": 0}

    def _sentinel(*_a, **_k):
        called["n"] += 1
        return "should-not-be-reached"

    monkeypatch.setattr(mistral_mod, "read_pdf_mistral", _sentinel)
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    default = DoclineMcpServer()
    with pytest.raises(ExternalEngineNotAllowedError) as excinfo:
        default.call_tool("process", {"staging_dir": "staging", "pdf_engine": "mistral_ocr"})
    assert called["n"] == 0
    msg = str(excinfo.value)
    assert "mistral_ocr" in msg
    # No full-arguments echo, no credential value (§H3 alignment).
    assert "staging" not in msg
    for secret in ("AZURE_AI_FOUNDRY_KEY", "MISTRAL_API_KEY"):
        assert secret not in msg
    # The public process() chokepoint denies identically.
    with pytest.raises(ExternalEngineNotAllowedError):
        default.process({"staging_dir": "staging", "pdf_engine": "mistral_ocr"})
    assert called["n"] == 0


def test_h8_spoofed_enable_flag_in_arguments_still_denied(monkeypatch, tmp_path) -> None:
    """Scenario (b)(i): a client-supplied enable flag can never spoof the instance opt-in."""
    from docline.mcp.exceptions import ExternalEngineNotAllowedError

    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    default = DoclineMcpServer()
    with pytest.raises(ExternalEngineNotAllowedError):
        default.call_tool(
            "process",
            {
                "staging_dir": "staging",
                "pdf_engine": "mistral_ocr",
                "external_pdf_engines_enabled": True,
                "allow_external": True,
            },
        )


def test_h8_ingest_local_dir_not_callable_no_egress_bypass() -> None:
    """Scenario (b)(ii): ingest_local_dir is not in the callable allow-list (H4 fail-closed)."""
    from docline.mcp.exceptions import UnknownToolError

    default = DoclineMcpServer()
    with pytest.raises(UnknownToolError):
        default.call_tool(
            "ingest_local_dir",
            {"source_path": "x", "output": "y", "pdf_engine": "mistral_ocr"},
        )
    advertised = [t["name"] for t in default.list_callable_tools().model_dump()["tools"]]
    assert "ingest_local_dir" not in advertised


def test_h8_optin_dispatch_accepts_external_engine(monkeypatch, tmp_path) -> None:
    """Scenario (c): an opt-in server does NOT raise the gate error (egress stubbed)."""
    import docline.readers.mistral as mistral_mod

    monkeypatch.setattr(mistral_mod, "read_pdf_mistral", lambda *_a, **_k: "")
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    optin = DoclineMcpServer(external_pdf_engines_enabled=True)
    result = optin.call_tool(
        "process",
        {"staging_dir": "staging", "output_dir": "output", "pdf_engine": "mistral_ocr"},
    )
    assert result is not None  # ProcessResult; the gate did not fire


def test_h8_manifest_parity_delta_is_exact() -> None:
    """Scenario (c): CLI manifest + list_tools keep all engines; only list_callable_tools omits."""
    manifest = get_manifest()
    proc = next(t for t in manifest.tools if t.name == "process")
    assert set(proc.parameters["properties"]["pdf_engine"]["enum"]) == _FULL_ENGINES
    default = DoclineMcpServer()
    listed = default.list_tools().model_dump(by_alias=True)["tools"]
    lproc = next(t for t in listed if t["name"] == "process")
    assert "mistral_ocr" in lproc["inputSchema"]["properties"]["pdf_engine"]["enum"]
    assert "mistral_ocr" not in _process_enum(default)


# ---------------------------------------------------------------------------
# 064.033-T — §H8 external-engine transport-mapping harness (dual-era -32602)
# ---------------------------------------------------------------------------


def test_h8_transport_legacy_reject_minus_32602(monkeypatch, tmp_path) -> None:
    """Scenario (a): a legacy tools/call external engine maps to -32602, no egress/secret."""
    import docline.readers.mistral as mistral_mod

    called = {"n": 0}

    def _sentinel(*_a, **_k):
        called["n"] += 1
        return ""

    monkeypatch.setattr(mistral_mod, "read_pdf_mistral", _sentinel)
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "process",
                "arguments": {"staging_dir": "staging", "pdf_engine": "mistral_ocr"},
            },
        }
    )
    assert resp["error"]["code"] == -32602
    assert called["n"] == 0
    blob = json.dumps(resp)
    assert str(tmp_path) not in blob
    for secret in ("AZURE_AI_FOUNDRY_KEY", "AZURE_AI_FOUNDRY_ENDPOINT", "MISTRAL_API_KEY"):
        assert secret not in blob


def test_h8_transport_modern_reject_minus_32602(monkeypatch, tmp_path) -> None:
    """Scenario (b): a modern tools/call with an external engine maps to -32602 identically."""
    import docline.readers.mistral as mistral_mod

    monkeypatch.setattr(mistral_mod, "read_pdf_mistral", lambda *_a, **_k: "")
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    resp = _dispatch(
        _modern_tools_call("process", {"staging_dir": "staging", "pdf_engine": "mistral_ocr"})
    )
    assert resp["error"]["code"] == -32602


def test_h8_transport_optin_accept_anchor(monkeypatch, tmp_path) -> None:
    """Scenario (c) anchor: an opt-in server is NOT -32602-rejected over the transport."""
    import docline.readers.mistral as mistral_mod

    monkeypatch.setattr(mistral_mod, "read_pdf_mistral", lambda *_a, **_k: "")
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath("staging").mkdir()
    optin = DoclineMcpServer(external_pdf_engines_enabled=True)
    resp = _dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "process",
                "arguments": {
                    "staging_dir": "staging",
                    "output_dir": "output",
                    "pdf_engine": "mistral_ocr",
                },
            },
        },
        server=optin,
    )
    assert not (resp.get("error") and resp["error"]["code"] == -32602)


# ---------------------------------------------------------------------------
# 064.008-T — docline-mcp subprocess interactive smoke harness
# ---------------------------------------------------------------------------


def _read_frame_bounded(pipe, timeout: float = 15.0) -> bytes:
    """Read one line/frame from ``pipe`` bounded by ``timeout`` (deadlock -> fail)."""
    holder: dict[str, bytes] = {}

    def _reader() -> None:
        holder["line"] = pipe.readline()

    worker = threading.Thread(target=_reader, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise AssertionError("timed out waiting for a response frame (stdio deadlock)")
    return holder.get("line", b"")


def test_docline_mcp_subprocess_interactive_smoke() -> None:
    """python -m docline.mcp answers each frame before EOF (no greedy-read/buffer deadlock)."""
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "docline.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        # Frame 1: legacy initialize latches the era; require its response first.
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        proc.stdin.flush()
        line1 = _read_frame_bounded(proc.stdout)
        assert line1.strip(), "no response to initialize while stdin is still open"
        assert json.loads(line1)["id"] == 1
        # Frame 2: tools/list, required BEFORE closing stdin.
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        proc.stdin.flush()
        line2 = _read_frame_bounded(proc.stdout)
        assert line2.strip(), "no response to tools/list while stdin is still open"
        names = [t["name"] for t in json.loads(line2)["result"]["tools"]]
        assert names == ["fetch", "process", "export_schema"]
        assert "ingest_local_dir" not in names
        proc.stdin.close()
        assert proc.wait(timeout=15.0) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)


# ---------------------------------------------------------------------------
# 064.035-T — §H8 server-side opt-in startup config harness
# ---------------------------------------------------------------------------

_ENV_OPTIN = "DOCLINE_MCP_ALLOW_EXTERNAL_PDF_ENGINES"


def _run_main_capture(monkeypatch, env: str | None = None, argv: list[str] | None = None):
    """Run docline.mcp.__main__.main() with a patched serve() that captures the server."""
    import docline.mcp.__main__ as mainmod

    captured: dict[str, Any] = {}

    def _fake_serve(_stdin, _stdout, server):
        captured["server"] = server
        return 0

    monkeypatch.setattr(mainmod, "serve", _fake_serve)
    monkeypatch.delenv(_ENV_OPTIN, raising=False)
    if env is not None:
        monkeypatch.setenv(_ENV_OPTIN, env)
    monkeypatch.setattr(sys, "argv", ["docline-mcp", *(argv or [])])
    rc = mainmod.main()
    return captured["server"], rc


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("0", False),
        ("false", False),
        ("true", False),
        ("yes", False),
        ("", False),
        ("   ", False),
        (" 1", False),
        ("1 ", False),
        (" 1 ", False),
        ("1\n", False),
    ],
)
def test_h8_startup_env_resolution(monkeypatch, value: str, expected: bool) -> None:
    """Scenario (a): only the raw exact token '1' enables; padded/other values fail closed."""
    server, rc = _run_main_capture(monkeypatch, env=value)
    assert server.external_pdf_engines_enabled is expected
    assert rc == 0


def test_h8_startup_env_unset_disabled(monkeypatch) -> None:
    """Scenario (a) anchor: with no env var the server is disabled."""
    server, _ = _run_main_capture(monkeypatch, env=None)
    assert server.external_pdf_engines_enabled is False


def test_h8_startup_cli_flag_enables(monkeypatch) -> None:
    """Scenario (b): the --allow-external-pdf-engine flag constructs an enabled server."""
    server, _ = _run_main_capture(monkeypatch, argv=["--allow-external-pdf-engine"])
    assert server.external_pdf_engines_enabled is True


def test_h8_startup_no_flag_no_env_disabled(monkeypatch) -> None:
    """Scenario (b) anchor: absence of both the env token and the flag disables."""
    server, _ = _run_main_capture(monkeypatch)
    assert server.external_pdf_engines_enabled is False


def test_h8_startup_fresh_instance_not_module_server(monkeypatch, capsys) -> None:
    """Scenario (c): main() builds a fresh instance, never mutating the module SERVER; no secret."""
    server, _ = _run_main_capture(monkeypatch, argv=["--allow-external-pdf-engine"])
    assert server is not SERVER
    assert SERVER.external_pdf_engines_enabled is False
    captured = capsys.readouterr()
    for secret in ("AZURE_AI_FOUNDRY_KEY", "AZURE_AI_FOUNDRY_ENDPOINT", "MISTRAL_API_KEY"):
        assert secret not in captured.out
        assert secret not in captured.err
