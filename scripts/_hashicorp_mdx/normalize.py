"""MDX -> Markdown normalization transforms for the HashiCorp
unified-docs preprocessor (071-F / 062-S).

Pipeline (see :func:`normalize_mdx_to_md`):

1. Split off frontmatter verbatim (:func:`split_frontmatter`) -- the
   YAML frontmatter block is copied byte-for-byte into the output, never
   touched by any transform.
2. Mask fenced code blocks (:func:`protect_fenced_code`) so their
   contents -- including any text that superficially resembles an MDX/
   JSX tag, and any literal placeholder tokens -- are completely inert
   to every subsequent regex-based transform.
3. Mask bare literal placeholder tokens outside fenced code
   (:func:`protect_placeholders`), e.g. ``<TYPE>``, ``<PATH>``,
   ``<VALUE>``, ``<NAMESPACE>`` -- ALL-CAPS angle-bracket tokens used as
   documentation placeholders. These never collide with real construct
   tag names because every known construct tag is CamelCase (mixed
   case), and the placeholder pattern requires every character after the
   first to be uppercase/digit/underscore.
4. Run the ordered transform pipeline (:data:`TRANSFORM_PIPELINE`) over
   the now-inert body: callouts, EnterpriseAlert, HCPCallout, Tabs,
   CodeTabs, CodeBlockConfig, VideoEmbed.
5. Scan the transformed body for any remaining unhandled
   CapitalizedComponent-style tag (:func:`scan_unhandled_constructs`) --
   this MUST happen before fence/placeholder restoration so that
   look-alike tags inside fenced example code or inside placeholder
   tokens are never mis-tallied as live unhandled constructs.
6. Restore fenced code and placeholders verbatim, then prepend the
   preserved frontmatter.

Known, deliberately simplified renderings (documented as such, since
this is a disposable requirements-evidence tool, not a permanent docline
feature):

* ``Note``/``Warning``/``Tip``/``Highlight`` -> blockquote admonition
  with a bold label line (the tag's ``title`` attribute, or the tag name
  itself when no ``title`` is present).
* ``EnterpriseAlert`` -- self-closing (the common shape, an inline
  marker embedded mid-sentence) -> ``**(Enterprise-only)**`` inline;
  block form with a body (rare outside ``partials/alerts/*.mdx``
  fragment files, which are themselves excluded as partials) -> a
  blockquote admonition titled "Enterprise Only".
* ``HCPCallout`` -> a short blockquote note referencing the product (no
  real body text exists on this self-closing tag to draw from).
* ``Tabs``/``Tab`` -> flattened to a fixed H4 heading per tab, in
  document order; nested ``Tabs`` flatten to the same flat sequence
  (a documented simplification -- true nesting-aware heading-level
  inference is out of scope for this disposable tool).
* ``CodeTabs`` -> an optional bold caption line for its ``heading``
  attribute, wrapping a sequence of ``CodeBlockConfig`` children.
* ``CodeBlockConfig`` -> unwrapped; an optional bold caption line for
  ``heading`` (preferred) or ``filename`` (fallback); the inner fenced
  code block is preserved exactly (it is masked/opaque at this stage).
* ``VideoEmbed`` -> a plain Markdown link, ``[Video](url)``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^(---\r?\n.*?\r?\n---\r?\n)", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split ``text`` into ``(frontmatter_incl_delimiters, body)``.

    Returns ``("", text)`` verbatim when no leading frontmatter block is
    present. The frontmatter block, when present, is returned exactly as
    written (including both ``---`` delimiter lines) so it can be
    reattached to the transformed body unchanged.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    frontmatter = match.group(1)
    body = text[match.end() :]
    return frontmatter, body


# ---------------------------------------------------------------------------
# Fenced-code protection
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[^\n]*\n"
    r"(?P<body>.*?)\n"
    r"(?P=indent)(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_FENCE_TOKEN_FMT = "\x00FENCE{index}\x00"


def protect_fenced_code(body: str) -> tuple[str, dict[str, str]]:
    """Replace every fenced code block with an opaque token; return the token map.

    GROUNDING NOTE (live-corpus correction): fences are matched with
    their own leading indentation captured and required to match again
    on the closing line (``^(?P<indent>[ \\t]*)(?P<fence>...)`` ...
    ``(?P=indent)(?P=fence)``). This was NOT the first working
    implementation -- the real corpus routinely nests fenced code under
    numbered-list continuations (e.g. ``  ```shell-session`` / ``  ``` ``
    indented by the list item's continuation width, seen throughout
    ``vault/v2.x/content/docs/auth/jwt/oidc-providers/adfs.mdx`` and
    many similar files). An indentation-blind fence matcher fails to
    close the fence at its true boundary, letting placeholder-bearing
    code content (e.g. ``<YOUR_OIDC_MOUNT_PATH>``) leak past masking
    into subsequent transform regexes and the unhandled-construct scan.

    Known, documented simplification: a closing fence must reuse the
    exact same fence-character run as its opener (e.g. ` ``` ` closed by
    ` ``` `). CommonMark technically permits a longer closing fence of the
    same character; this simpler exact-match rule holds for every
    fenced block observed in the real corpus during grounding.
    """
    store: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = _FENCE_TOKEN_FMT.format(index=counter)
        store[token] = match.group(0)
        counter += 1
        return token

    protected = _FENCE_RE.sub(_replace, body)
    return protected, store


def restore_fenced_code(body: str, store: dict[str, str]) -> str:
    """Reverse :func:`protect_fenced_code`, restoring every fence verbatim."""
    for token, original in store.items():
        body = body.replace(token, original)
    return body


# ---------------------------------------------------------------------------
# Literal placeholder protection
# ---------------------------------------------------------------------------

#: Matches bare ALL-CAPS angle-bracket placeholder tokens such as
#: ``<TYPE>``, ``<PATH>``, ``<VALUE>``, ``<NAMESPACE>``,
#: ``<QUOTA_NAME>``, and hyphenated conventions like ``<YOUR-ORG>`` /
#: ``<GITHUB-TOKEN>`` (grounded from the real corpus's unhandled-
#: construct tally: many "unknown constructs" were actually hyphenated
#: placeholder tokens, not real MDX components). Every known construct
#: tag name is CamelCase (mixed case), so this pattern can never match a
#: real construct tag: the moment a lowercase letter appears after the
#: first character, the match fails.
_PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_-]*)>")
_PLACEHOLDER_TOKEN_FMT = "\x00PLACEHOLDER{index}\x00"


def protect_placeholders(body: str) -> tuple[str, dict[str, str]]:
    """Mask bare literal placeholder tokens; return the token map."""
    store: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = _PLACEHOLDER_TOKEN_FMT.format(index=counter)
        store[token] = match.group(0)
        counter += 1
        return token

    protected = _PLACEHOLDER_RE.sub(_replace, body)
    return protected, store


def restore_placeholders(body: str, store: dict[str, str]) -> str:
    """Reverse :func:`protect_placeholders`, restoring every placeholder verbatim."""
    for token, original in store.items():
        body = body.replace(token, original)
    return body


# ---------------------------------------------------------------------------
# B.T2 -- callouts / admonitions
# ---------------------------------------------------------------------------

_CALLOUT_RE = re.compile(
    r"<(?P<tag>Note|Warning|Tip|Highlight)(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
    re.DOTALL,
)
_TITLE_ATTR_RE = re.compile(r'title="([^"]*)"')


def _render_admonition(label: str, inner: str) -> str:
    inner = inner.strip("\n")
    lines = inner.split("\n") if inner else [""]
    quoted_lines = [f"> {line}".rstrip() if line.strip() else ">" for line in lines]
    return f"> **{label}**\n>\n" + "\n".join(quoted_lines)


def transform_callouts(body: str) -> str:
    """Render ``Note``/``Warning``/``Tip``/``Highlight`` as blockquote admonitions."""

    def _replace(match: re.Match[str]) -> str:
        tag = match.group("tag")
        attrs = match.group("attrs") or ""
        title_match = _TITLE_ATTR_RE.search(attrs)
        label = title_match.group(1) if title_match else tag
        return _render_admonition(label, match.group("body"))

    return _CALLOUT_RE.sub(_replace, body)


_ENTERPRISE_BLOCK_RE = re.compile(
    r"<EnterpriseAlert(?:\s[^>]*)?>(?P<body>.*?)</EnterpriseAlert>", re.DOTALL
)
_ENTERPRISE_SELF_RE = re.compile(r"<EnterpriseAlert\b[^>]*/>")


def transform_enterprise_alert(body: str) -> str:
    """Render ``EnterpriseAlert``: inline marker (self-closing) or blockquote (block form)."""
    body = _ENTERPRISE_BLOCK_RE.sub(
        lambda m: _render_admonition("Enterprise Only", m.group("body")), body
    )
    body = _ENTERPRISE_SELF_RE.sub("**(Enterprise-only)**", body)
    return body


_HCP_CALLOUT_RE = re.compile(r"<HCPCallout\b(?P<attrs>[^>]*)/>")
_PRODUCT_ATTR_RE = re.compile(r'product="([^"]*)"')


def transform_hcp_callout(body: str) -> str:
    """Render self-closing ``HCPCallout`` as a short blockquote note referencing the product."""

    def _replace(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        product_match = _PRODUCT_ATTR_RE.search(attrs)
        product = product_match.group(1) if product_match else "this product"
        return _render_admonition("HCP", f"This content applies to HCP `{product}`.")

    return _HCP_CALLOUT_RE.sub(_replace, body)


# ---------------------------------------------------------------------------
# B.T3 -- Tabs, CodeTabs, CodeBlockConfig, VideoEmbed
# ---------------------------------------------------------------------------

_TABS_WRAPPER_RE = re.compile(r"</?Tabs\b[^>]*>\n?")
_TAB_OPEN_RE = re.compile(r"<Tab\b(?P<attrs>[^>]*)>")
_TAB_CLOSE_RE = re.compile(r"</Tab>\n?")
_HEADING_ATTR_RE = re.compile(r'heading="([^"]*)"')


def transform_tabs(body: str) -> str:
    """Flatten ``Tabs``/``Tab`` to a fixed-level heading per tab, in document order.

    Nested ``Tabs`` (a ``Tabs`` block inside a ``Tab``'s content) flatten
    to the same flat heading sequence: every ``<Tab ...>`` occurrence,
    regardless of nesting depth, is replaced independently, so nesting
    depth never changes the deterministic output shape.
    """

    def _replace_open(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        heading_match = _HEADING_ATTR_RE.search(attrs)
        label = heading_match.group(1) if heading_match else "Tab"
        return f"#### {label}"

    body = _TAB_OPEN_RE.sub(_replace_open, body)
    body = _TAB_CLOSE_RE.sub("", body)
    body = _TABS_WRAPPER_RE.sub("", body)
    return body


_CODE_TABS_HEADING_RE = re.compile(r'<CodeTabs\b(?:[^>]*\sheading="([^"]*)")?[^>]*>\n?')
_CODE_TABS_CLOSE_RE = re.compile(r"</CodeTabs>\n?")


def transform_code_tabs(body: str) -> str:
    """Unwrap ``CodeTabs``, optionally emitting a bold caption for its ``heading`` attribute."""

    def _replace_open(match: re.Match[str]) -> str:
        heading = match.group(1)
        if heading:
            return f"**{heading}**\n\n"
        return ""

    body = _CODE_TABS_HEADING_RE.sub(_replace_open, body)
    body = _CODE_TABS_CLOSE_RE.sub("", body)
    return body


_CODE_BLOCK_CONFIG_OPEN_RE = re.compile(r"<CodeBlockConfig\b(?P<attrs>[^>]*)>\n?")
_CODE_BLOCK_CONFIG_CLOSE_RE = re.compile(r"</CodeBlockConfig>\n?")
_FILENAME_ATTR_RE = re.compile(r'filename="([^"]*)"')


def transform_code_block_config(body: str) -> str:
    """Unwrap ``CodeBlockConfig``, preserving its (masked) inner fenced code exactly.

    Attribute -> caption priority: ``heading`` first, then ``filename``.
    Neither attribute present -> no caption line is emitted, just the
    unwrapped fenced code.
    """

    def _replace_open(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        heading_match = _HEADING_ATTR_RE.search(attrs)
        filename_match = _FILENAME_ATTR_RE.search(attrs)
        label = heading_match.group(1) if heading_match else None
        if label is None and filename_match:
            label = filename_match.group(1)
        if label:
            return f"**{label}**\n\n"
        return ""

    body = _CODE_BLOCK_CONFIG_OPEN_RE.sub(_replace_open, body)
    body = _CODE_BLOCK_CONFIG_CLOSE_RE.sub("", body)
    return body


_VIDEO_EMBED_RE = re.compile(r"<VideoEmbed\b(?P<attrs>[^>]*)/>")
_URL_ATTR_RE = re.compile(r'url="([^"]*)"')


def transform_video_embed(body: str) -> str:
    """Render self-closing ``VideoEmbed`` as a plain Markdown link."""

    def _replace(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        url_match = _URL_ATTR_RE.search(attrs)
        url = url_match.group(1) if url_match else ""
        return f"[Video]({url})"

    return _VIDEO_EMBED_RE.sub(_replace, body)


# ---------------------------------------------------------------------------
# Unhandled-construct tally
# ---------------------------------------------------------------------------

_KNOWN_HANDLED_TAGS = {
    "Note",
    "Warning",
    "Tip",
    "Highlight",
    "EnterpriseAlert",
    "HCPCallout",
    "Tabs",
    "Tab",
    "CodeBlockConfig",
    "CodeTabs",
    "VideoEmbed",
}
_TAG_SCAN_RE = re.compile(r"</?([A-Z][A-Za-z0-9]*)\b[^>\n]*/?>")


def scan_unhandled_constructs(body: str) -> Counter[str]:
    """Tally any remaining CapitalizedComponent-style tag not in the known-handled set.

    Standard lowercase inline HTML (``<a>``, ``<b>``, ``<br />``, ...) is
    never tallied here: the scan pattern only matches tag names beginning
    with an uppercase letter, which structurally excludes lowercase HTML
    passthrough elements.

    The scan is deliberately bounded to a single line (``[^>\\n]*``
    instead of an unbounded ``[^>]*``): live-corpus grounding surfaced
    prose containing an unclosed ``<`` (e.g. shell heredoc markers like
    ``<<EOF``) with no matching ``>`` on the same line. An unbounded
    scan would greedily consume everything up to the next UNRELATED
    ``>`` character anywhere later in the document (e.g. an unrelated
    blockquote marker), mis-tallying names like ``EOF``/``YOUR``/
    ``GITHUB`` as fabricated "unhandled constructs". This is purely a
    reporting-precision fix -- :func:`scan_unhandled_constructs` never
    mutates ``body``, so it cannot affect the actual transformed output,
    only the accuracy of the unhandled-construct tally in the CLI's
    coverage report.
    """
    tally: Counter[str] = Counter()
    for match in _TAG_SCAN_RE.finditer(body):
        name = match.group(1)
        if name not in _KNOWN_HANDLED_TAGS:
            tally[name] += 1
    return tally


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizeResult:
    """Result of :func:`normalize_mdx_to_md`: final Markdown text + unhandled tally."""

    text: str
    unhandled: Counter[str]


#: Ordered transform-pipeline seam (B.T1): :func:`normalize_mdx_to_md` runs
#: these, in this order, over the fence/placeholder-protected body. B.T2/
#: B.T3 transforms plug in here; this list is the single place that
#: defines execution order, so a future additional construct transform is
#: added by appending to this list rather than editing the orchestration
#: function itself.
TRANSFORM_PIPELINE: list[Callable[[str], str]] = [
    transform_callouts,
    transform_enterprise_alert,
    transform_hcp_callout,
    transform_tabs,
    transform_code_tabs,
    transform_code_block_config,
    transform_video_embed,
]


def normalize_mdx_to_md(text: str) -> NormalizeResult:
    """Convert one MDX document's text to Markdown, per the module-level pipeline."""
    frontmatter, body = split_frontmatter(text)
    body, fence_store = protect_fenced_code(body)
    body, placeholder_store = protect_placeholders(body)

    for transform in TRANSFORM_PIPELINE:
        body = transform(body)

    # Unhandled-construct scan MUST run before restoration: fenced example
    # code and placeholder tokens are still masked/opaque here, so
    # look-alike tags inside them are never mis-tallied as live constructs.
    unhandled = scan_unhandled_constructs(body)

    body = restore_fenced_code(body, fence_store)
    body = restore_placeholders(body, placeholder_store)

    return NormalizeResult(text=frontmatter + body, unhandled=unhandled)
