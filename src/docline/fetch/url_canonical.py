"""URL canonicalization for fetch-time dedup (010-S F6.T4).

Implements the rules pinned by ``tests/fetch/test_url_canonical.py``:

* lowercase scheme and host (RFC 3986 case-insensitive components)
* drop the fragment (client-side, never reaches the server)
* strip default ports (``:80`` for http, ``:443`` for https)
* sort query parameters by key for stable dedup comparison
* drop ad/analytics tracking params (``utm_*``, ``fbclid``, ``gclid``)
* normalize empty path to ``/``
* collapse duplicate path slashes and resolve ``.``/``..`` segments
* idempotent: ``canonicalize_url(canonicalize_url(x)) == canonicalize_url(x)``
* reject empty input, non-http(s) schemes, and missing host
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from docline.schema.models import DoclineError

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}
_TRACKING_PARAMS_EXACT: frozenset[str] = frozenset({"fbclid", "gclid"})
_TRACKING_PARAM_PREFIXES: tuple[str, ...] = ("utm_",)


class UrlCanonicalizationError(DoclineError):
    """Raised when a URL cannot be canonicalized."""


def _is_tracking_param(key: str) -> bool:
    key_lower = key.lower()
    if key_lower in _TRACKING_PARAMS_EXACT:
        return True
    return any(key_lower.startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES)


def _normalize_path(path: str) -> str:
    """Normalize path: collapse duplicate slashes and resolve dot segments."""
    if not path:
        return "/"
    has_trailing_slash = path.endswith("/") and path != "/"
    segments = path.split("/")
    resolved: list[str] = []
    for segment in segments:
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            if resolved:
                resolved.pop()
            continue
        resolved.append(segment)
    normalized = "/" + "/".join(resolved)
    if has_trailing_slash and not normalized.endswith("/"):
        normalized += "/"
    return normalized


def canonicalize_url(url: str) -> str:
    """Canonicalize ``url`` for fetch-time dedup.

    Args:
        url: Absolute http(s) URL to canonicalize.

    Returns:
        Canonicalized URL string.

    Raises:
        UrlCanonicalizationError: If ``url`` is empty, has a non-http(s)
            scheme, or is missing a host.
    """
    if not url:
        raise UrlCanonicalizationError("url must be a non-empty string")

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlCanonicalizationError(f"url could not be parsed: {url!r}") from exc

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlCanonicalizationError(f"scheme {parts.scheme!r} is not http or https")

    host = (parts.hostname or "").lower()
    if not host:
        raise UrlCanonicalizationError(f"url is missing a host: {url!r}")

    port = parts.port
    if port is not None and port == _DEFAULT_PORTS.get(scheme):
        port = None

    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo = f"{userinfo}:{parts.password}"
        userinfo = f"{userinfo}@"

    netloc = userinfo + host
    if port is not None:
        netloc = f"{netloc}:{port}"

    path = _normalize_path(parts.path)

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query_pairs.sort(key=lambda kv: kv[0])
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def dedup_key_for_url(url: str) -> str:
    """Return a stable dedup key for ``url``.

    Currently identical to :func:`canonicalize_url`. Kept as a separate
    public name so callers expressing dedup intent are decoupled from the
    canonicalization implementation.
    """
    return canonicalize_url(url)


__all__ = ["UrlCanonicalizationError", "canonicalize_url", "dedup_key_for_url"]
