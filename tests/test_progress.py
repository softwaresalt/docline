"""Unit tests for the CLI progress reporter (src/docline/progress.py).

Covers percentage math and clamping, count-only rendering when the total is
unknown, throttling of NORMAL updates, TTY vs non-TTY formatting, per-mode
rendering (SILENT/NORMAL/VERBOSE), and ``finish()`` completion semantics.
"""

from __future__ import annotations

import io

import pytest

from docline.progress import ProgressEvent, ProgressReporter, Verbosity


class FakeStream(io.StringIO):
    """StringIO with a controllable ``isatty()`` for TTY-branch tests."""

    def __init__(self, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:  # noqa: D102
        return self._tty


class FakeClock:
    """Monotonic clock stub whose value the test advances explicitly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_progress_event_holds_optional_total() -> None:
    event = ProgressEvent(done=3, total=None, detail="x")
    assert event.done == 3
    assert event.total is None
    assert event.detail == "x"


def test_known_total_renders_ratio_and_percent() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(20, 50, "page")
    out = stream.getvalue()
    assert "40%" in out
    assert "20/50" in out


def test_percent_clamped_and_rounded() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    # done > total must clamp to 100, not exceed it.
    reporter(60, 50, "page")
    assert "100%" in stream.getvalue()


def test_none_total_is_count_only() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(7, None, "page")
    out = stream.getvalue()
    assert "7" in out
    assert "%" not in out


def test_normal_throttles_rapid_calls_but_first_emits() -> None:
    stream = FakeStream(tty=False)
    clock = FakeClock()
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, min_interval=1.0, clock=clock)
    reporter(1, 10, "a")  # first always emits
    reporter(2, 10, "b")  # within interval -> throttled
    reporter(3, 10, "c")  # within interval -> throttled
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    clock.now = 5.0
    reporter(4, 10, "d")  # interval elapsed -> emits
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2


def test_non_tty_uses_newlines_and_no_carriage_return() -> None:
    stream = FakeStream(tty=False)
    clock = FakeClock()
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=clock)
    reporter(1, 10, "a")
    clock.now = 5.0
    reporter(2, 10, "b")
    out = stream.getvalue()
    assert "\r" not in out
    assert out.count("\n") == 2


def test_tty_uses_carriage_return_in_place() -> None:
    stream = FakeStream(tty=True)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(1, 10, "a")
    assert "\r" in stream.getvalue()


def test_silent_emits_nothing() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.SILENT, stream=stream, clock=FakeClock())
    reporter(1, 10, "a")
    reporter(2, None, "b")
    reporter.finish("done")
    assert stream.getvalue() == ""


def test_verbose_emits_one_detailed_line_per_item_unthrottled() -> None:
    stream = FakeStream(tty=False)
    clock = FakeClock()
    reporter = ProgressReporter(Verbosity.VERBOSE, stream=stream, clock=clock)
    reporter(1, 3, "https://a")
    reporter(2, 3, "https://b")  # not throttled even within the interval
    reporter(3, 3, "https://c")
    out = stream.getvalue()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert "https://a" in out
    assert "https://b" in out
    assert "https://c" in out


def test_normal_omits_per_item_detail() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(1, 3, "https://secret-detail")
    assert "https://secret-detail" not in stream.getvalue()


def test_finish_known_total_shows_true_ratio_not_forced_100() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(20, 50, "page")
    reporter.finish()
    out = stream.getvalue()
    assert "40%" in out
    assert "100%" not in out


def test_finish_known_total_complete_shows_100() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(50, 50, "page")
    reporter.finish()
    assert "100%" in stream.getvalue()


def test_finish_none_total_is_bare_count() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(12, None, "staged")
    reporter.finish()
    out = stream.getvalue()
    assert "12" in out
    assert "%" not in out


def test_finish_terminates_active_tty_line_with_newline() -> None:
    stream = FakeStream(tty=True)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(1, 10, "a")
    reporter.finish()
    assert stream.getvalue().endswith("\n")


@pytest.mark.parametrize("verbosity", [Verbosity.NORMAL, Verbosity.VERBOSE])
def test_finish_without_events_is_safe(verbosity: Verbosity) -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(verbosity, stream=stream, clock=FakeClock())
    reporter.finish()  # must not raise
    assert "\r" not in stream.getvalue()


def test_percent_caps_at_99_when_incomplete_rounds_up() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(999, 1000, "x")  # round(99.9) == 100, but done < total
    out = stream.getvalue()
    assert "99%" in out
    assert "100%" not in out


def test_percent_reaches_100_only_when_complete() -> None:
    stream = FakeStream(tty=False)
    reporter = ProgressReporter(Verbosity.NORMAL, stream=stream, clock=FakeClock())
    reporter(1000, 1000, "x")
    assert "100%" in stream.getvalue()
