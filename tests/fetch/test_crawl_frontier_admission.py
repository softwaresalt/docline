"""Unit harness for 068.001-T (A.T1) and 068.002-T (A.T2).

Exercises the ``_Frontier`` admission dataclass directly — **no crawl, no
network, no event loop**. A.T1 pins the 058-S admission invariants (admit up to
the ceiling, refuse beyond it, never leak a refused link into ``visited``, a
single ceiling report). A.T2 pins the ``truncated`` predicate semantics from
plan decision D3: ``truncated`` reflects a *refusal of an eligible candidate*
(``refused_any``), never merely that the ceiling was reported or that the
admission count reached the cap.

The crawl-loop wiring of the three refusal sites (main-branch refusal,
print-page-branch refusal, and the depth-zero conservative TOC-script signal)
is asserted end-to-end against ``CrawlOutcome`` in
``tests/fetch/test_crawl_truncation_signal.py`` (A.T5); here each site is
represented by the ``_Frontier`` operation it performs so the predicate stays
green from A.T3 onward, before ``crawl()`` returns the outcome.

Harness pattern: red on ``_Frontier`` not existing; green once A.T3 introduces
it.
"""

import dataclasses
import logging

from docline.fetch.crawl import _Frontier

CRAWL_KEY = "https://example.com/docs/page-{index}"


def _make_frontier(max_frontier: int) -> _Frontier:
    """Return a ``_Frontier`` with a sanitized origin label."""
    return _Frontier(max_frontier=max_frontier, start_label="https://example.com")


def _admit_n(frontier: _Frontier, count: int, visited: set[str]) -> list[bool]:
    """Attempt ``count`` distinct admissions and return the per-call results."""
    outcomes: list[bool] = []
    for index in range(count):
        link = CRAWL_KEY.format(index=index)
        outcomes.append(frontier.admit(link, link, index + 1, visited))
    return outcomes


# ---------------------------------------------------------------------------
# A.T1 — admission unit semantics
# ---------------------------------------------------------------------------


def test_frontier_is_not_frozen() -> None:
    """``_Frontier`` mutates its counters, so it must not be frozen."""
    frontier = _make_frontier(3)
    frontier.admitted = 2
    assert frontier.admitted == 2


def test_frontier_container_fields_are_per_instance() -> None:
    """Two instances must not share a mutable ``queue`` default."""
    first = _make_frontier(3)
    second = _make_frontier(3)
    first.queue.append(("https://example.com/docs/a", 1))
    assert list(second.queue) == []


def test_admits_up_to_max_frontier() -> None:
    """Distinct links are admitted until the ceiling is full."""
    frontier = _make_frontier(3)
    visited: set[str] = set()

    outcomes = _admit_n(frontier, 3, visited)

    assert outcomes == [True, True, True]
    assert frontier.admitted == 3
    assert len(frontier.queue) == 3
    assert visited == {CRAWL_KEY.format(index=i) for i in range(3)}


def test_refuses_beyond_max_frontier() -> None:
    """Admissions past the ceiling are refused and return ``False``."""
    frontier = _make_frontier(3)
    visited: set[str] = set()
    _admit_n(frontier, 3, visited)

    refused_link = CRAWL_KEY.format(index=99)
    assert frontier.admit(refused_link, refused_link, 1, visited) is False
    assert frontier.admitted == 3
    assert len(frontier.queue) == 3


def test_refused_link_is_not_added_to_visited() -> None:
    """The 058-S invariant: a refused link never enters ``visited``."""
    frontier = _make_frontier(1)
    visited: set[str] = set()
    admitted_link = CRAWL_KEY.format(index=0)
    frontier.admit(admitted_link, admitted_link, 1, visited)

    refused_link = CRAWL_KEY.format(index=1)
    frontier.admit(refused_link, refused_link, 1, visited)

    assert admitted_link in visited
    assert refused_link not in visited


def test_zero_max_frontier_refuses_everything() -> None:
    """A ceiling of ``0`` refuses the very first discovered link."""
    frontier = _make_frontier(0)
    visited: set[str] = set()
    link = CRAWL_KEY.format(index=0)

    assert frontier.admit(link, link, 1, visited) is False
    assert frontier.admitted == 0
    assert visited == set()


def test_report_ceiling_emits_once(caplog) -> None:
    """``report_ceiling`` logs at most one record per crawl, idempotently."""
    frontier = _make_frontier(2)
    with caplog.at_level(logging.DEBUG):
        frontier.report_ceiling()
        frontier.report_ceiling()

    ceiling_records = [r for r in caplog.records if "ceiling" in r.getMessage().lower()]
    assert len(ceiling_records) == 1
    assert frontier.ceiling_reported is True


def test_frontier_declares_expected_fields() -> None:
    """The admission dataclass exposes exactly the D2 field surface."""
    field_names = {field.name for field in dataclasses.fields(_Frontier)}
    assert field_names == {
        "max_frontier",
        "start_label",
        "queue",
        "admitted",
        "ceiling_reported",
        "refused_any",
    }


# ---------------------------------------------------------------------------
# A.T2 — ``truncated`` predicate across all report sites (D3)
# ---------------------------------------------------------------------------


def test_truncated_false_under_cap() -> None:
    """Case 1: staying under the cap never reports truncation."""
    frontier = _make_frontier(5)
    visited: set[str] = set()
    _admit_n(frontier, 3, visited)

    assert frontier.exhausted is False
    assert frontier.truncated is False


def test_truncated_false_exactly_at_cap_no_further_candidates() -> None:
    """Case 2: exactly filling the cap with no later candidate is not truncation."""
    frontier = _make_frontier(4)
    visited: set[str] = set()
    _admit_n(frontier, 4, visited)

    assert frontier.exhausted is True
    assert frontier.truncated is False


def test_truncated_false_when_ceiling_reported_without_refusal() -> None:
    """Case 3: a link-free / TOC-free short-circuit reports the ceiling only.

    The main-branch short-circuit calls ``report_ceiling`` because the cap is
    full, but records no refusal when the page yields no eligible candidate.
    ``truncated`` must stay ``False`` — ``ceiling_reported`` is not truncation.
    """
    frontier = _make_frontier(4)
    visited: set[str] = set()
    _admit_n(frontier, 4, visited)

    frontier.report_ceiling()

    assert frontier.ceiling_reported is True
    assert frontier.truncated is False


def test_truncated_true_on_refused_eligible_candidate() -> None:
    """Case 4 / 6 / 7: refusing an eligible candidate is truncation.

    The same ``admit`` refusal backs the exactly-at-cap-with-eligible-link case,
    the print-page-branch refusal, and the main-branch refusal — every site
    funnels an eligible candidate through ``admit`` and observes a ``False``.
    """
    frontier = _make_frontier(2)
    visited: set[str] = set()
    _admit_n(frontier, 2, visited)

    refused_link = CRAWL_KEY.format(index=50)
    assert frontier.admit(refused_link, refused_link, 1, visited) is False
    assert frontier.truncated is True


def test_truncated_true_for_conservative_toc_short_circuit() -> None:
    """Case 5: a depth-zero eligible TOC-script reference sets truncation.

    The depth-zero short-circuit cannot admit through ``admit`` (it deliberately
    skips the TOC network fetch), so it records the conservative signal by
    setting ``refused_any`` directly after reporting the ceiling. ``truncated``
    must follow ``refused_any``, independently of the admission count.
    """
    frontier = _make_frontier(3)
    visited: set[str] = set()
    _admit_n(frontier, 3, visited)

    frontier.report_ceiling()
    assert frontier.truncated is False

    frontier.refused_any = True
    assert frontier.truncated is True
