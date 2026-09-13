"""Deterministic and sanitized source-key builders for ELT staging jobs."""

from __future__ import annotations

import re
from urllib.parse import unquote

from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import GitHubRepoSource, LocalFileSource, SourceConfig, WebCrawlSource
from docline.fetch.staging import _is_credential_param, sanitize_source

_MAX_CREDENTIAL_DECODE_LAYERS = 5
_SOURCE_ID_REDACTED = "<source-id-redacted>"
_SOURCE_URL_REDACTED = "<source-url-redacted>"
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_QUERY_COMPONENT_SEPARATOR_RE = re.compile(r"([&?])")


def build_source_key(config: SourceConfig) -> str:
    """Derive a deterministic staging key for a typed source config.

    Args:
        config: Typed source configuration.

    Returns:
        Deterministic source text for job ID generation and metadata.
    """
    if isinstance(config, LocalFileSource):
        return f"local_file:{','.join(sorted(config.paths))}"
    if isinstance(config, WebCrawlSource):
        return _build_crawl_source_key(
            "web_crawl",
            config.url,
            max_depth=config.depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, GitHubRepoSource):
        return f"github_repo:{config.repo_url}@{config.branch}:{config.path_glob}"
    if isinstance(config, ManifestLocalSource):
        includes = ",".join(sorted(config.include))
        return f"manifest_local:{config.id}:{config.path}:{includes}"
    if isinstance(config, ManifestUrlSource):
        return _build_crawl_source_key(
            f"manifest_url:{config.id}",
            config.url,
            max_depth=config.max_depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, ManifestGitSource):
        return f"manifest_git:{config.id}:{config.url}@{config.branch}"
    raise TypeError(f"Unsupported source config type: {type(config)!r}")


def sanitize_source_key(config: SourceConfig) -> str:
    """Derive a credential-scrubbed staging key for persisted metadata.

    Args:
        config: Typed source configuration.

    Returns:
        A sanitized source key safe to persist in metadata and logs.
    """
    if isinstance(config, LocalFileSource):
        return build_source_key(config)
    if isinstance(config, WebCrawlSource):
        return _build_crawl_source_key(
            "web_crawl",
            _sanitize_url_field(config.url),
            max_depth=config.depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, GitHubRepoSource):
        return (
            f"github_repo:{_sanitize_url_field(config.repo_url)}@"
            f"{sanitize_source_id(config.branch)}:{sanitize_source_id(config.path_glob)}"
        )
    if isinstance(config, ManifestLocalSource):
        includes = ",".join(sorted(config.include))
        return f"manifest_local:{sanitize_source_id(config.id)}:{config.path}:{includes}"
    if isinstance(config, ManifestUrlSource):
        return _build_crawl_source_key(
            f"manifest_url:{sanitize_source_id(config.id)}",
            _sanitize_url_field(config.url),
            max_depth=config.max_depth,
            max_pages=config.max_pages,
            domain_lock=config.domain_lock,
            rate_limit_ms=config.rate_limit_ms,
        )
    if isinstance(config, ManifestGitSource):
        return (
            f"manifest_git:{sanitize_source_id(config.id)}:{_sanitize_url_field(config.url)}@"
            f"{sanitize_source_id(config.branch)}"
        )
    raise TypeError(f"Unsupported source config type: {type(config)!r}")


def sanitize_source_id(raw_id: str) -> str:
    """Redact credential markers from a manifest/source identifier.

    Detection is marker-gated and non-throwing. Credential-free identifiers are
    returned byte-for-byte, even when they resemble malformed URLs.

    Args:
        raw_id: Raw identifier to sanitize.

    Returns:
        The credential-scrubbed identifier, the original identifier when no
        marker is present, or a fail-closed sentinel when redaction cannot be
        completed safely.
    """
    if not _contains_credential_marker(raw_id):
        return raw_id
    try:
        sanitized = _strip_userinfo(raw_id)
        return _redact_query_and_fragment_values(sanitized)
    except ValueError:
        return _SOURCE_ID_REDACTED


def _build_crawl_source_key(
    prefix: str,
    url: str,
    *,
    max_depth: int,
    max_pages: int | None,
    domain_lock: bool,
    rate_limit_ms: int,
) -> str:
    """Build a canonical crawl-source key."""
    parts = [prefix, url, *_crawl_option_parts(max_depth, max_pages, domain_lock, rate_limit_ms)]
    return ":".join(parts)


def _crawl_option_parts(
    max_depth: int,
    max_pages: int | None,
    domain_lock: bool,
    rate_limit_ms: int,
) -> list[str]:
    """Return canonical crawl-option suffixes for non-default values."""
    parts: list[str] = []
    if max_depth != 0:
        parts.append(f"depth={max_depth}")
    if max_pages is not None:
        parts.append(f"max_pages={max_pages}")
    if not domain_lock:
        parts.append(f"domain_lock={str(domain_lock).lower()}")
    if rate_limit_ms != 0:
        parts.append(f"rate_limit_ms={rate_limit_ms}")
    return parts


def _sanitize_url_field(raw_url: str) -> str:
    """Return a fail-closed sanitized URL field."""
    stripped_url = _strip_reversed_query_credentials(raw_url)
    try:
        sanitized = sanitize_source(stripped_url)
    except ValueError:
        return _SOURCE_URL_REDACTED
    if sanitized.lower().startswith(("http://", "https://")):
        return _remove_credential_query_params(sanitized)
    return sanitize_source_id(sanitized)


def _strip_reversed_query_credentials(raw_value: str) -> str:
    """Drop ``?``/``&``-joined credential-bearing query/fragment tokens up front.

    ``staging.sanitize_source`` (and any other URL-shape-specific processing
    downstream) only treats ``&`` as a query-token boundary, via
    ``urllib.parse.parse_qsl``. When a value contains a *reversed* or duplicated
    ``?`` boundary (e.g. ``?detail=x?token=SECRET``), the entire
    ``x?token=SECRET`` text becomes the single value of ``detail``, hiding
    ``token=SECRET`` from that credential-param filter. Worse, the later
    ``urlencode`` step then percent-encodes the embedded ``?``/``=`` characters
    while leaving the literal secret text completely unredacted.

    This pre-pass uses the same ``?``/``&``-aware token splitter as
    :func:`_remove_credential_query_params` to drop (not redact-in-place)
    credential-named tokens from the raw query/fragment *before* any
    URL-shape-specific processing runs, closing that gap regardless of how many
    ``?`` characters appear in the query/fragment text.

    Args:
        raw_value: Raw URL or URL-shaped text to pre-scrub.

    Returns:
        *raw_value* with credential-bearing query/fragment tokens dropped.
    """
    prefix, fragment_sep, fragment = raw_value.partition("#")
    base, query_sep, query = prefix.partition("?")

    def _strip_component(component: str) -> str:
        survivors = [
            token
            for token in _split_query_component_preserving_separators(component)[::2]
            if not _token_has_credential_name(token)
        ]
        return "&".join(token for token in survivors if token != "")

    result = base
    if query_sep:
        stripped_query = _strip_component(query)
        if stripped_query:
            result = f"{result}?{stripped_query}"
    if fragment_sep:
        stripped_fragment = _strip_component(fragment)
        if stripped_fragment:
            result = f"{result}#{stripped_fragment}"
    return result


def _remove_credential_query_params(raw_url: str) -> str:
    """Remove credential-bearing query tokens from a URL while preserving others."""
    fragment_index = raw_url.find("#")
    prefix = raw_url if fragment_index == -1 else raw_url[:fragment_index]
    query_index = prefix.find("?")
    if query_index == -1:
        return prefix

    base = prefix[:query_index]
    query = prefix[query_index + 1 :]
    kept_tokens = [token for token in query.split("&") if not _token_has_credential_name(token)]
    if not kept_tokens or all(token == "" for token in kept_tokens):
        return base
    return f"{base}?{'&'.join(kept_tokens)}"


def _token_has_credential_name(token: str) -> bool:
    """Return True when a query token's key is credential-like."""
    if "=" not in token:
        return False
    name, _ = token.split("=", 1)
    return _is_credential_name(name)


def _contains_credential_marker(raw_value: str) -> bool:
    """Return True when *raw_value* contains credential-like markers."""
    return _contains_userinfo_marker(raw_value) or any(
        _query_component_has_credential_marker(component)
        for component in _iter_query_like_components(raw_value)
    )


def _contains_userinfo_marker(raw_value: str) -> bool:
    """Return True when the authority portion contains userinfo credentials."""
    if not _is_url_shaped(raw_value):
        return False
    raw_authority = _authority_segment(raw_value)
    if "@" not in raw_authority:
        return False
    if raw_authority.count("@") != 1:
        # Ambiguous authority (more than one "@"): treat it as a marker so
        # sanitize_source_id's try/except reaches _strip_userinfo's existing
        # fail-closed ValueError path instead of returning the raw,
        # credential-bearing identifier unchanged.
        return True
    raw_userinfo, _ = raw_authority.split("@", 1)
    return _userinfo_has_marker(raw_userinfo)


def _userinfo_has_marker(raw_userinfo: str) -> bool:
    """Return True when *raw_userinfo* is a present, unambiguous userinfo segment."""
    return raw_userinfo != ""


def _iter_query_like_components(raw_value: str) -> tuple[str, ...]:
    """Return query-like components from *raw_value* for marker scanning."""
    prefix, fragment_separator, fragment = raw_value.partition("#")
    _, query_separator, query = prefix.partition("?")
    components: list[str] = []
    if query_separator:
        components.append(query)
    if fragment_separator:
        components.append(fragment)
    return tuple(components)


def _query_component_has_credential_marker(component: str) -> bool:
    """Return True when a query-like component contains a credential key."""
    return any(
        _token_has_credential_name(token)
        for token in _split_query_component_preserving_separators(component)[::2]
    )


def _split_query_component_preserving_separators(component: str) -> list[str]:
    """Return alternating token/separator parts without normalizing delimiters."""
    return _QUERY_COMPONENT_SEPARATOR_RE.split(component)


def _is_credential_name(raw_name: str) -> bool:
    """Return True when *raw_name* matches credential markers on any decode layer."""
    current = raw_name
    if _is_credential_param(current):
        return True
    for _ in range(_MAX_CREDENTIAL_DECODE_LAYERS):
        decoded = unquote(current, encoding="utf-8", errors="replace")
        if decoded == current:
            return False
        current = decoded
        if _is_credential_param(current):
            return True
    return True


def _strip_userinfo(raw_value: str) -> str:
    """Strip credential-bearing userinfo from *raw_value* when present."""
    if not _is_url_shaped(raw_value):
        return raw_value
    authority_start, authority_end = _authority_span(raw_value)
    raw_authority = raw_value[authority_start:authority_end]
    if "@" not in raw_authority:
        return raw_value
    if raw_authority.count("@") != 1:
        raise ValueError("ambiguous authority userinfo")
    raw_userinfo, raw_host = raw_authority.split("@", 1)
    if not _userinfo_has_marker(raw_userinfo):
        return raw_value
    return f"{raw_value[:authority_start]}{raw_host}{raw_value[authority_end:]}"


def _redact_query_and_fragment_values(raw_value: str) -> str:
    """Redact credential values in the query and fragment portions of *raw_value*."""
    prefix, fragment_separator, fragment = raw_value.partition("#")
    base, query_separator, query = prefix.partition("?")

    parts = [base]
    if query_separator:
        parts.append(query_separator)
        parts.append(_redact_query_component(query))
    if fragment_separator:
        parts.append(fragment_separator)
        parts.append(_redact_query_component(fragment))
    return "".join(parts)


def _redact_query_component(component: str) -> str:
    """Redact credential values from a query-like component without changing separators."""
    parts = _split_query_component_preserving_separators(component)
    for index in range(0, len(parts), 2):
        token = parts[index]
        if "=" not in token:
            continue
        name, _ = token.split("=", 1)
        if _is_credential_name(name):
            parts[index] = f"{name}=<redacted>"
    return "".join(parts)


def _authority_segment(raw_value: str) -> str:
    """Return the authority-like segment used for userinfo detection."""
    authority_start, authority_end = _authority_span(raw_value)
    return raw_value[authority_start:authority_end]


def _authority_span(raw_value: str) -> tuple[int, int]:
    """Return the start/end indexes of the authority-like portion."""
    authority_start = 0
    scheme_match = _URL_SCHEME_RE.match(raw_value)
    if scheme_match is not None:
        authority_start = scheme_match.end()
    elif raw_value.startswith("//"):
        authority_start = 2

    authority_end = len(raw_value)
    for separator in ("/", "?", "#"):
        index = raw_value.find(separator, authority_start)
        if index != -1:
            authority_end = min(authority_end, index)
    return authority_start, authority_end


def _is_url_shaped(raw_value: str) -> bool:
    """Return True when *raw_value* looks like a URL with an authority section."""
    return raw_value.startswith("//") or _URL_SCHEME_RE.match(raw_value) is not None


__all__ = ["build_source_key", "sanitize_source_id", "sanitize_source_key"]
