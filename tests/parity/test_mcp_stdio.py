"""Stdio MCP server protocol, dispatch, security, and dual-era conformance harness.

Authored test-first across the 064-F task chain. Each task appends its scenarios
here; shared framing/driver helpers live at the top of the module.
"""

from __future__ import annotations

import json
import threading
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
    payload: bytes, server: DoclineMcpServer | None = None
) -> tuple[list[dict], list[int]]:
    """Drive serve() over a raw byte payload using the recording stdin."""
    from docline.mcp.stdio import CHUNK_SIZE, serve

    stdin = _RecordingReadStdin(payload, CHUNK_SIZE)
    stdout = _RecordingStdout()
    worker = threading.Thread(target=serve, args=(stdin, stdout, server or SERVER))
    worker.start()
    worker.join(15.0)
    assert not worker.is_alive(), "serve() did not terminate within timeout"
    return stdout.responses(), stdin.read_sizes


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
# ===END-006===
