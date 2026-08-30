"""Stateless crawl request-policy helpers.

Holds the two stateless policy helpers used by the crawl loop's fetch layer:
``robots.txt`` allow-evaluation and exponential retry-backoff timing. They are
split out of :mod:`docline.fetch.crawl` to keep the loop module under the
module-size convention. This module imports only the standard library and
nothing from the crawl package, so it is a leaf.

Note:
    The fetch-performing helpers (``_fetch_with_retries``, ``_robots_allow``,
    ``_discover_toc_links``) remain in :mod:`docline.fetch.crawl` rather than
    moving here, because the crawl test suite monkeypatches
    ``docline.fetch.crawl.fetch_page`` — relocating those callers would break
    that seam. Only the two stateless, fetch-free helpers move.
"""

from urllib.robotparser import RobotFileParser


def compute_backoff_seconds(attempt: int, base: float = 1.0) -> float:
    """Compute an exponential backoff interval for a retry attempt.

    Args:
        attempt: Zero-based attempt index (0 = first retry).
        base: Base interval in seconds.

    Returns:
        The backoff duration in seconds (capped at 60 seconds).
    """
    return float(min(base * (2**attempt), 60.0))


def check_robots_allowed(robots_txt: str, user_agent: str, url: str) -> bool:
    """Parse *robots_txt* and return whether *url* is allowed for *user_agent*.

    Args:
        robots_txt: Full text content of a ``robots.txt`` file.
        user_agent: User-agent identifier to check rules against.
        url: The URL path (or full URL) to test against the parsed rules.

    Returns:
        ``True`` when the URL is allowed, ``False`` when disallowed.
    """
    if not robots_txt:
        return True
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


__all__ = [
    "check_robots_allowed",
    "compute_backoff_seconds",
]
