"""Console progress reporting for the docline CLI.

Pure, TTY-aware progress rendering used only at the CLI layer. The library
functions (``crawl``, ``execute_fetch``, ``execute_process`` and the ELT seam)
stay print-free and accept an optional ``progress`` callback; the CLI
constructs a :class:`ProgressReporter` and passes it in.

Rendering rules:

* ``SILENT`` emits nothing.
* ``NORMAL`` emits a single throttled, concise percentage/count line — in-place
  via carriage-return when the stream is a TTY, otherwise newline-terminated.
* ``VERBOSE`` emits one newline-terminated line per item, including the item
  detail (URL/path/job phase), and is not throttled.

A known ``total`` renders ``done/total`` (reaching 100% only when
``done == total``); ``total is None`` is the only count-only case. ``finish()``
emits a final line but never fabricates 100%.
"""

from __future__ import annotations

import enum
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO


class Verbosity(enum.Enum):
    """Console verbosity level for CLI progress output."""

    SILENT = "silent"
    NORMAL = "normal"
    VERBOSE = "verbose"


@dataclass(frozen=True)
class ProgressEvent:
    """A single progress observation.

    Attributes:
        done: Number of units completed so far.
        total: Total unit count, or ``None`` when the total is unknown
            (count-only rendering).
        detail: Human-readable detail such as a URL, path, or job phase.
    """

    done: int
    total: int | None
    detail: str = ""


def _clamp_percent(done: int, total: int) -> int:
    """Return ``done/total`` as an integer percent clamped to ``[0, 100]``.

    Rounding never fabricates 100% for an incomplete total: when ``done < total``
    a rounded value of 100 is capped at 99 so completion is reserved for
    ``done >= total``.
    """
    if total <= 0:
        return 100
    pct = max(0, min(100, int(round(done * 100 / total))))
    if done < total and pct >= 100:
        return 99
    return pct


def _sanitize(text: str) -> str:
    """Replace non-printable characters in untrusted progress detail.

    Progress ``detail`` is derived from crawled URLs and staged filenames, which
    can contain newlines, carriage returns, or ANSI escape sequences that would
    forge extra progress lines or corrupt the terminal in verbose mode. Every
    non-printable character is replaced with a space so each event renders as a
    single, safe line.
    """
    return "".join(ch if ch.isprintable() else " " for ch in text)


class ProgressReporter:
    """Render throttled, TTY-aware progress to a stream.

    The reporter is callable: ``reporter(done, total, detail)`` records and
    renders a progress event. Call :meth:`finish` once after the run completes
    to emit the final line and terminate any in-place TTY line.

    Args:
        verbosity: Controls what is emitted (SILENT/NORMAL/VERBOSE).
        stream: Destination stream; defaults to ``sys.stderr`` so the terminal
            JSON result on stdout stays clean.
        min_interval: Minimum seconds between throttled ``NORMAL`` updates.
        label: Optional phase label prefixed to each line (e.g. ``"fetch"``).
        clock: Monotonic time source; injectable for deterministic tests.
    """

    def __init__(
        self,
        verbosity: Verbosity,
        stream: TextIO | None = None,
        min_interval: float = 1.0,
        label: str = "",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._verbosity = verbosity
        self._stream: TextIO = stream if stream is not None else sys.stderr
        self._min_interval = min_interval
        self._label = label
        self._clock = clock
        self._isatty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._last_emit = 0.0
        self._emitted = False
        self._last_event: ProgressEvent | None = None
        self._active_line = False
        self._last_len = 0

    def __call__(self, done: int, total: int | None, detail: str = "") -> None:
        """Record and (subject to mode/throttle) render a progress event."""
        if self._verbosity is Verbosity.SILENT:
            return
        event = ProgressEvent(done=done, total=total, detail=detail)
        self._last_event = event
        if self._verbosity is Verbosity.VERBOSE:
            self._write_line(self._format(event, verbose=True))
            return
        now = self._clock()
        if self._emitted and (now - self._last_emit) < self._min_interval:
            return
        self._last_emit = now
        self._emitted = True
        self._render_inplace(self._format(event, verbose=False))

    def finish(self, detail: str = "") -> None:
        """Emit the final line, terminating any in-place TTY line.

        Renders the last observed event (never fabricating 100%): a known
        ``total`` shows its true ratio, ``total is None`` shows a bare count.
        Safe to call when no events were reported.
        """
        if self._verbosity is Verbosity.SILENT:
            return
        if self._last_event is None:
            if self._active_line:
                self._stream.write("\n")
                self._stream.flush()
                self._active_line = False
            return
        event = self._last_event
        if detail:
            event = ProgressEvent(event.done, event.total, detail)
        verbose = self._verbosity is Verbosity.VERBOSE
        line = self._format(event, verbose=verbose)
        if self._active_line and self._isatty:
            pad = " " * max(0, self._last_len - len(line))
            self._stream.write("\r" + line + pad + "\n")
        else:
            self._stream.write(line + "\n")
        self._stream.flush()
        self._active_line = False

    def _format(self, event: ProgressEvent, verbose: bool) -> str:
        """Format *event* into a single-line string (no trailing newline)."""
        prefix = f"{self._label}: " if self._label else ""
        if event.total is None:
            core = str(event.done)
        else:
            pct = _clamp_percent(event.done, event.total)
            core = f"{pct}% ({event.done}/{event.total})"
        if verbose and event.detail:
            return f"{prefix}{core} {_sanitize(event.detail)}"
        return f"{prefix}{core}"

    def _write_line(self, line: str) -> None:
        """Write a newline-terminated line (VERBOSE / non-TTY NORMAL)."""
        self._stream.write(line + "\n")
        self._stream.flush()

    def _render_inplace(self, line: str) -> None:
        """Render a throttled NORMAL line: carriage-return on a TTY."""
        if self._isatty:
            pad = " " * max(0, self._last_len - len(line))
            self._stream.write("\r" + line + pad)
            self._stream.flush()
            self._active_line = True
            self._last_len = len(line)
        else:
            self._write_line(line)
