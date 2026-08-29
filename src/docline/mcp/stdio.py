"""Core stdio JSON-RPC 2.0 transport loop for the docline MCP server (legacy era).

Provides a pure :func:`dispatch` (single JSON-RPC request -> response dict or
``None`` for a notification) and a :func:`serve` read/dispatch/write loop that
reserves the real stdout for JSON-RPC frames, reads non-greedily with a bounded
binary framing reader, and flushes after every response so an interactive client
never deadlocks. The transport is a pure translator: tool identity and server
identity live only in the adapter (:mod:`docline.mcp.server`).
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import sys
from typing import Protocol

from pydantic import ValidationError

from docline.app_models import FetchResult, ProcessResult
from docline.mcp.exceptions import UnknownToolError
from docline.mcp.server import (
    LEGACY_PROTOCOL_VERSION,
    SERVER,
    SUPPORTED_PROTOCOL_VERSIONS,
    DoclineMcpServer,
)

# Fixed-chunk non-greedy read size and the hard per-frame payload cap (§H2).
CHUNK_SIZE: int = 64 * 1024
MAX_FRAME_BYTES: int = 1 * 1024 * 1024

# Modern-era (`2026-07-28`) per-request `_meta` negotiation members and result shape.
_META_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
_META_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
_SERVERINFO_META_KEY = "io.modelcontextprotocol/serverInfo"
UNSUPPORTED_PROTOCOL_VERSION = -32022
MODERN_CACHE_TTL_MS = 60_000
MODERN_CACHE_SCOPE = "session"


class _ByteReader(Protocol):
    """A non-greedy binary input stream exposing ``read1``."""

    def read1(self, size: int = ..., /) -> bytes: ...


class _ByteWriter(Protocol):
    """A binary output stream exposing ``write`` and ``flush``."""

    def write(self, data: bytes, /) -> int: ...

    def flush(self) -> None: ...


# Absolute filesystem paths (Windows drive form or POSIX) stripped from any
# client-facing error text so no path is disclosed on the untrusted surface (§H3).
_ABS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']*|(?<![\w:/])/[^\s\"']+")


def _sanitize(text: str) -> str:
    """Genericize absolute filesystem paths in client-facing error text (§H3)."""
    return _ABS_PATH_RE.sub("<path>", text)


def _valid_id(value: object) -> bool:
    """Return ``True`` when ``value`` is a valid JSON-RPC RequestId (string or finite number)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _error(id_value: object, code: int, message: str, data: object = None) -> dict:
    """Build a JSON-RPC error envelope, including optional ``data`` when provided."""
    err: dict[str, object] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_value, "error": err}


def _result(id_value: object, result: object) -> dict:
    """Build a JSON-RPC result envelope."""
    return {"jsonrpc": "2.0", "id": id_value, "result": result}


def _to_call_tool_result(name: str, result: object) -> dict:
    """Shape a domain result into a standards-valid MCP CallToolResult body."""
    if isinstance(result, (FetchResult, ProcessResult)):
        is_error = not result.success
        text = _sanitize(result.error) if (is_error and result.error) else f"{name} completed."
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result.model_dump(),
            "isError": is_error,
        }
    if isinstance(result, str):
        return {"content": [{"type": "text", "text": result}], "isError": False}
    return {"content": [{"type": "text", "text": str(result)}], "isError": False}


def _dispatch_tools_call(message: dict, echo_id: object, server: DoclineMcpServer) -> dict:
    """Dispatch a ``tools/call`` and shape the CallToolResult (legacy-era body).

    Applies the §H1 ``workspace_root`` reject, §H4 fail-closed unknown-tool
    mapping, §H5 child-stdout redirect, and §H3 error-text sanitization.
    """
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(echo_id, -32602, "Invalid params")
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _error(echo_id, -32602, "Invalid params")
    # §H1: reject a client-supplied workspace_root (root is pinned to the server cwd).
    if name == "process" and "workspace_root" in arguments:
        return _error(echo_id, -32602, "Invalid params")
    try:
        # §H5: reserve the protocol stdout — redirect child-library writes to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            result = server.call_tool(name, arguments)
    except UnknownToolError:
        return _error(echo_id, -32602, "Invalid params")
    except ValidationError:
        return _error(echo_id, -32602, "Invalid params")
    except Exception:
        return _error(echo_id, -32603, "Internal error")
    return _result(echo_id, _to_call_tool_result(name, result))


def _request_meta(message: dict) -> object:
    """Return the per-request ``_meta`` block from ``params`` (or ``None``)."""
    params = message.get("params")
    if isinstance(params, dict):
        return params.get("_meta")
    return None


def _is_modern_request(message: dict, method: str) -> bool:
    """Classify a request as modern by key membership of a namespaced negotiation member.

    A ``server/discover`` (modern-only) is always modern; otherwise a request is
    modern when its ``_meta`` carries ``io.modelcontextprotocol/protocolVersion``
    or ``io.modelcontextprotocol/clientCapabilities`` — detected by KEY MEMBERSHIP,
    not truthiness, so a present-but-malformed member still routes to the modern
    validator rather than falling through to the legacy path. Ancillary ``_meta``
    (e.g. ``progressToken``) with no modern member is NOT modern.
    """
    if method == "server/discover":
        return True
    meta = _request_meta(message)
    if isinstance(meta, dict) and (_META_VERSION_KEY in meta or _META_CAPS_KEY in meta):
        return True
    return False


def _validate_modern_meta(meta: object) -> tuple[int, str, object] | None:
    """Validate a modern ``_meta`` block (version first, then clientCapabilities).

    Returns an ``(code, message, data)`` tuple on rejection, or ``None`` when both
    required members are present and well-typed. An unsupported protocol version
    takes precedence (``-32022``); a missing/malformed member is ``-32602``.
    """
    if not isinstance(meta, dict) or _META_VERSION_KEY not in meta:
        return (-32602, "Invalid params", None)
    version = meta[_META_VERSION_KEY]
    if not isinstance(version, str):
        return (-32602, "Invalid params", None)
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        return (
            UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version",
            {"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": version},
        )
    if _META_CAPS_KEY not in meta:
        return (-32602, "Invalid params", None)
    if not isinstance(meta[_META_CAPS_KEY], dict):
        return (-32602, "Invalid params", None)
    return None


def _dispatch_modern(
    message: dict, echo_id: object, method: str, server: DoclineMcpServer, meta: object
) -> dict:
    """Dispatch a modern-era request, wrapping results in the ``resultType`` envelope.

    Validates the per-request ``_meta`` first (``-32022``/``-32602``), then serves
    ``server/discover``/``tools/list``/``tools/call`` through the SAME hardened
    dispatch as the legacy path and applies the modern envelope only as a
    post-return wrapper (guards-by-construction).
    """
    err = _validate_modern_meta(meta)
    if err is not None:
        code, msg, data = err
        return _error(echo_id, code, msg, data)
    info = server.describe_server()
    serverinfo_meta = {_SERVERINFO_META_KEY: info["serverInfo"]}
    if method == "server/discover":
        return _result(
            echo_id,
            {
                "supportedVersions": info["supportedVersions"],
                "capabilities": info["capabilities"],
                "resultType": "complete",
                "ttlMs": MODERN_CACHE_TTL_MS,
                "cacheScope": MODERN_CACHE_SCOPE,
                "_meta": serverinfo_meta,
            },
        )
    if method == "tools/list":
        tools = server.list_callable_tools().model_dump(by_alias=True)["tools"]
        return _result(
            echo_id,
            {
                "tools": tools,
                "resultType": "complete",
                "ttlMs": MODERN_CACHE_TTL_MS,
                "cacheScope": MODERN_CACHE_SCOPE,
                "_meta": serverinfo_meta,
            },
        )
    if method == "tools/call":
        resp = _dispatch_tools_call(message, echo_id, server)
        if "result" in resp:
            body = dict(resp["result"])
            body["resultType"] = "complete"
            body["_meta"] = serverinfo_meta
            return _result(echo_id, body)
        return resp
    return _error(echo_id, -32601, "Method not found")


def dispatch(message: object, server: DoclineMcpServer) -> dict | None:
    """Map a single JSON-RPC request to a response dict, or ``None`` for a notification.

    Performs request-shape validation (``-32600``) BEFORE the id-absent
    notification-suppression branch, so a malformed no-id payload returns
    ``-32600`` (``id:null``) while an otherwise-valid no-id request is silent.
    """
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request")

    has_id = "id" in message
    raw_id = message.get("id")
    id_is_valid = _valid_id(raw_id) if has_id else False
    echo_id = raw_id if id_is_valid else None

    # Request-shape validation (root/jsonrpc/method/id-type) precedes suppression.
    if message.get("jsonrpc") != "2.0":
        return _error(echo_id, -32600, "Invalid Request")
    method = message.get("method")
    if not (isinstance(method, str) and method != ""):
        return _error(echo_id, -32600, "Invalid Request")
    if has_id and not id_is_valid:
        return _error(None, -32600, "Invalid Request")

    # Notification: an otherwise-valid request lacking an id is silent.
    if not has_id:
        return None

    # Era classification (modern member / server/discover) — modern is stateless
    # and its classification wins even after a legacy latch (064.023-T).
    if _is_modern_request(message, method):
        return _dispatch_modern(message, echo_id, method, server, _request_meta(message))

    if method == "initialize":
        info = server.describe_server()
        return _result(
            echo_id,
            {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": info["capabilities"],
                "serverInfo": info["serverInfo"],
            },
        )
    if method == "notifications/initialized":
        return _result(echo_id, {})
    if method == "ping":
        return _result(echo_id, {})
    if method == "tools/list":
        tools = server.list_callable_tools().model_dump(by_alias=True)["tools"]
        return _result(echo_id, {"tools": tools})
    if method == "tools/call":
        return _dispatch_tools_call(message, echo_id, server)
    return _error(echo_id, -32601, "Method not found")


def _reject_constant(_token: str) -> object:
    """Reject Python's permissive non-finite JSON tokens (NaN/Infinity/-Infinity)."""
    raise ValueError("Non-finite JSON constants are not permitted.")


def _emit(stdout: _ByteWriter, obj: dict) -> None:
    """Serialize and write one JSON-RPC frame, flushing after every response."""
    try:
        payload = json.dumps(obj, allow_nan=False)
    except ValueError:
        payload = json.dumps(_error(None, -32603, "Internal error"))
    stdout.write(payload.encode("utf-8") + b"\n")
    stdout.flush()


def _process_frame(frame: bytes, stdout: _ByteWriter, server: DoclineMcpServer) -> None:
    """Parse one frame and emit its response (unless it is a silent notification)."""
    try:
        message = json.loads(frame, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        _emit(stdout, _error(None, -32700, "Parse error"))
        return
    try:
        response = dispatch(message, server)
    except RecursionError:
        _emit(stdout, _error(None, -32603, "Internal error"))
        return
    if response is not None:
        _emit(stdout, response)


def _drain_to_newline(stdin: _ByteReader) -> bytearray:
    """Discard bytes up to and including the next newline; return the carry-over."""
    while True:
        chunk = stdin.read1(CHUNK_SIZE)
        if not chunk:
            return bytearray()
        idx = chunk.find(b"\n")
        if idx != -1:
            return bytearray(chunk[idx + 1 :])


def serve(stdin: _ByteReader, stdout: _ByteWriter, server: DoclineMcpServer = SERVER) -> int:
    """Run the stdio read/dispatch/write loop until EOF.

    Reads frames with a non-greedy ``read1`` primitive bounded by
    ``MAX_FRAME_BYTES``, preserving post-newline carry-over, draining oversized
    frames, and flushing stdout after every response.

    Args:
        stdin: Binary input stream exposing ``read1(size) -> bytes``.
        stdout: Binary output stream exposing ``write`` and ``flush``.
        server: The MCP adapter singleton to dispatch against.

    Returns:
        ``0`` on clean EOF exit.
    """
    buffer = bytearray()
    while True:
        newline = buffer.find(b"\n")
        if newline != -1:
            frame = bytes(buffer[:newline])
            del buffer[: newline + 1]
            _process_frame(frame, stdout, server)
            continue
        if len(buffer) > MAX_FRAME_BYTES:
            # Oversized frame with no terminator: discard, report, resynchronize.
            _emit(stdout, _error(None, -32700, "Parse error"))
            buffer = _drain_to_newline(stdin)
            continue
        cap = min(CHUNK_SIZE, MAX_FRAME_BYTES - len(buffer) + 1)
        if cap <= 0:
            cap = 1
        chunk = stdin.read1(cap)
        if not chunk:
            if buffer.strip():
                _process_frame(bytes(buffer), stdout, server)
            return 0
        buffer.extend(chunk)


__all__ = ["CHUNK_SIZE", "MAX_FRAME_BYTES", "dispatch", "serve"]
