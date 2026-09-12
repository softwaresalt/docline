"""MDX -> Markdown normalization transforms for the HashiCorp
unified-docs preprocessor (071-F / 062-S).

Pipeline (see :func:`normalize_mdx_to_md`):

1. Split off frontmatter verbatim (:func:`split_frontmatter`) -- the
   YAML frontmatter block is copied byte-for-byte into the output,
   INCLUDING its original line-ending bytes exactly as authored (LF,
   CRLF, or a mixed convention), never touched by any transform. This
   guarantee holds precisely because the CALLER reads the source file
   with newline translation disabled (see
   ``hashicorp_mdx_normalize.py``'s MDX read/write branch) so the text
   handed to this function still carries its original, untranslated
   line-ending bytes; ``normalize_mdx_to_md`` then normalizes ONLY the
   BODY portion to plain ``\\n`` line endings for the transform pipeline
   below (review-fix cycle 4, finding p8Ph) -- the transform pipeline
   itself has always assumed, and is tested against, ``\\n``-only body
   content, so its behavior is unchanged by this fix. The net effect: a
   normalized ``.md`` file's frontmatter block is a byte-exact copy of
   the source ``.mdx`` file's frontmatter block; its body always uses
   ``\\n`` line endings regardless of the source body's original
   convention or the host platform.
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
5. Run a conservative generic fallback pass
   (:func:`apply_fallback_pass`) over whatever CapitalizedComponent-style
   tag the named pipeline above did not already understand: a genuinely
   paired tag (``<Foo ...>body</Foo>``) is unwrapped in place, and a
   genuinely self-closing tag (``<Foo .../>``) is rendered as a short
   readable Markdown annotation. This ensures ``--execute`` never
   silently emits raw, un-rendered custom JSX into ``.md`` output.
6. Classify whatever tag-shaped token still remains after the fallback
   pass (:func:`classify_remaining_constructs`) into either a known
   ambiguous/prose-notation token (see :data:`_KNOWN_AMBIGUOUS_TAGS`,
   preserved verbatim, never execute-blocking) or a genuinely unresolved
   construct (preserved verbatim, execute-blocking unless the operator
   passes the documented override) -- this MUST happen before
   fence/placeholder restoration so that look-alike tags inside fenced
   example code or inside placeholder tokens are never mis-tallied as
   live constructs.
7. Restore fenced code and placeholders verbatim, then prepend the
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

_FENCE_OPEN_CORE_RE = re.compile(r"^(?P<fencechar>`{3,}|~{3,})(?P<info>.*)$")
_FENCE_CLOSE_CORE_RE = re.compile(r"^(?P<fencechar>`+|~+)[ \t]*$")
_FENCE_TOKEN_FMT = "\x00FENCE{index}\x00"

#: CommonMark's own top-level threshold: a fence opener/closer indented 0-3
#: visual columns from the left margin is "top-level" (unindented, or
#: indented only enough to still count as flush-left prose); 4+ columns is
#: an indented code block in CommonMark terms, never a plain top-level
#: fence. Review-fix cycle 2, finding 4.
_TOP_LEVEL_MAX_INDENT = 3

#: List-item marker at the start of a line: ``-``/``*``/``+`` bullets or
#: ``1.``/``1)``-style ordered markers, followed by at least one space/tab
#: (the marker's own leading indentation is captured separately so the
#: content-start column can be computed precisely).
_LIST_MARKER_RE = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d{1,9}[.)])[ \t]+")
#: A blockquote marker (``>``) at the start of a line, optionally indented.
_BLOCKQUOTE_MARKER_RE = re.compile(r"^[ \t]*>")

#: Bound on how many lines :func:`_container_establishes_indent` scans
#: backward before conservatively giving up (returning "no container
#: context found"). This is a defensive cap against pathological input --
#: real list/blockquote continuations establishing a 4+-column fence are
#: always found within a handful of lines in practice.
_MAX_CONTAINER_BACKSCAN_LINES = 1000


def _container_establishes_indent(
    lines: list[str], opener_index: int, opener_indent_col: int
) -> bool:
    """True when a 4+-column indented fence opener at ``lines[opener_index]``
    is legitimately inside a list-item or blockquote continuation, rather
    than a bare CommonMark indented code block at the top level (bug,
    Copilot review cycle 4): scans backward from just before
    ``opener_index``, skipping blank lines, until it finds:

    * a list-item marker line (``- ``, ``* ``, ``+ ``, ``1. ``, ``1) ``)
      whose own content-start column is <= ``opener_indent_col`` -- the
      fence is indented far enough to be that item's continuation; or
    * a blockquote marker line (``>``) -- treated as establishing context
      unconditionally, since blockquote continuation indentation is
      relative to the marker, not the left margin; or, failing either,
    * a plain-text line indented AT LEAST as far as ``opener_indent_col``
      is skipped over (it may itself be part of the same list item's
      continuation paragraph) and the scan continues further back;
    * a plain-text line indented LESS than ``opener_indent_col`` ends the
      scan with no context found -- this is ordinary top-level prose, so
      the 4+-column line that follows is a genuine indented code block,
      not a fence.

    Without this check, ANY 4+-column indented backtick/tilde line was
    treated as a valid container fence opener purely from its own
    indentation, letting the scanner mask everything up to the next
    similarly-indented line as one opaque block -- hiding a real
    unresolved MDX/JSX construct in between from the execute preflight.
    """
    j = opener_index - 1
    scanned = 0
    while j >= 0 and scanned < _MAX_CONTAINER_BACKSCAN_LINES:
        raw = lines[j].rstrip("\r\n")
        if raw.strip() == "":
            j -= 1
            scanned += 1
            continue
        list_match = _LIST_MARKER_RE.match(raw)
        if list_match:
            marker_indent_col, _ = _leading_indent_columns(raw)
            content_col = (
                marker_indent_col + len(list_match.group(0)) - len(list_match.group("indent"))
            )
            return content_col <= opener_indent_col
        if _BLOCKQUOTE_MARKER_RE.match(raw):
            return True
        line_indent_col, _ = _leading_indent_columns(raw)
        if line_indent_col < opener_indent_col:
            return False
        j -= 1
        scanned += 1
    return False


def _leading_indent_columns(line: str) -> tuple[int, int]:
    """Return ``(visual_column_width, char_length)`` of the run of leading
    spaces/tabs at the start of ``line``.

    Tabs expand to the next multiple-of-4 column stop (CommonMark's tab
    -handling rule for block-structure purposes) rather than counting as a
    single column, so a tab-indented fence is measured the same way a
    real Markdown renderer would measure it.
    """
    col = 0
    length = 0
    for ch in line:
        if ch == " ":
            col += 1
            length += 1
        elif ch == "\t":
            col += 4 - (col % 4)
            length += 1
        else:
            break
    return col, length


def protect_fenced_code(body: str) -> tuple[str, dict[str, str]]:
    """Replace every fenced code block with an opaque token; return the token map.

    GROUNDING NOTE (review-fix cycle 1, P2 correctness finding): the
    original implementation used a single combined regex requiring the
    closing fence to reuse the opener's exact indentation
    (``(?P=indent)``) AND the opener's exact fence-character run
    (``(?P=fence)`` -- an equal-length backreference). Real, valid
    CommonMark permits a closing fence that (a) uses the same fence
    character (backtick or tilde) with length >= the opener's length
    (not necessarily equal), and (b) is indented independently of the
    opener (up to CommonMark's own list-continuation rules) -- a closing
    fence's indentation is never required to match the opener's. A
    same-length-only, same-indentation-only matcher therefore both (1)
    fails to close fences whose closing line is legitimately indented
    differently than the opener, and (2) fails to close fences whose
    closing run is deliberately longer than the opener's (a real,
    documented CommonMark feature used to let a *shorter* same-character
    run appear, unclosed, as literal content nested inside the block).

    GROUNDING NOTE (review-fix cycle 2, P2 correctness finding): the
    cycle-1 fix above removed indentation matching entirely, which
    over-corrected -- it let a closing-fence-shaped line at ANY
    indentation close ANY opener, including a top-level (unindented)
    opener being "closed" by an unrelated four-space-indented backtick
    line that CommonMark would treat as an indented code block, not a
    fence boundary at all. This implementation now applies a bounded,
    raw-line rule with two classes, both keyed off the OPENER's own
    visual indentation (:func:`_leading_indent_columns`, tab-aware):

    * **Top-level opener** (indented 0-3 columns): only a closing line
      ALSO indented 0-3 columns can close it (same marker character,
      length >= the opener's) -- a four-space-or-more-indented
      backtick/tilde line can never close a top-level fence.
    * **Container/list-indented opener** (indented 4+ columns -- the
      shape routinely seen in this real corpus under numbered-list
      continuations): a closing line is accepted when it is within
      **three visual columns** of the OPENER's own indentation (not
      necessarily equal), with the same marker character and length >=
      the opener's. This preserves every previously-recognized
      indented-list fence in the corpus (closing indentation was never
      required to match the opener's exactly) while still bounding how
      far the closer's indentation may drift from the opener before it
      is no longer considered "the same list continuation."

    A same-character run that is SHORTER than the opener never closes it
    (it is preserved as ordinary content inside the block, exactly as
    CommonMark requires) and a fence with no valid closing line at all
    runs through the end of the document. The entire matched span --
    opener line through closer line inclusive, or through end-of-document
    -- is preserved byte-for-byte in the token store, so restoration is
    always an exact round trip regardless of what construct-like text
    (including MDX-looking tags) the block's content contains.
    """
    store: dict[str, str] = {}
    counter = 0
    lines = body.splitlines(keepends=True)
    output: list[str] = []
    total = len(lines)
    i = 0
    while i < total:
        line = lines[i]
        stripped_line = line.rstrip("\r\n")
        indent_col, indent_len = _leading_indent_columns(stripped_line)
        open_match = _FENCE_OPEN_CORE_RE.match(stripped_line[indent_len:])
        if open_match is None:
            output.append(line)
            i += 1
            continue

        fence_run = open_match.group("fencechar")
        fence_char = fence_run[0]
        fence_len = len(fence_run)
        opener_is_top_level = indent_col <= _TOP_LEVEL_MAX_INDENT

        if not opener_is_top_level and not _container_establishes_indent(lines, i, indent_col):
            # A 4+-column indented backtick/tilde line with no genuine
            # preceding list-item/blockquote context is a CommonMark
            # INDENTED CODE BLOCK, not a fence boundary -- treat it as
            # ordinary text so nothing is masked and any real construct
            # later in the document remains visible to classification.
            output.append(line)
            i += 1
            continue

        close_index: int | None = None
        for j in range(i + 1, total):
            close_stripped = lines[j].rstrip("\r\n")
            close_col, close_len = _leading_indent_columns(close_stripped)
            close_match = _FENCE_CLOSE_CORE_RE.match(close_stripped[close_len:])
            if close_match is None:
                continue
            if close_match.group("fencechar")[0] != fence_char:
                continue
            if len(close_match.group("fencechar")) < fence_len:
                continue
            if opener_is_top_level:
                if close_col > _TOP_LEVEL_MAX_INDENT:
                    continue
            elif abs(close_col - indent_col) > _TOP_LEVEL_MAX_INDENT:
                continue
            close_index = j
            break

        end_index = close_index if close_index is not None else total - 1
        block_text = "".join(lines[i : end_index + 1])
        token = _FENCE_TOKEN_FMT.format(index=counter)
        store[token] = block_text
        counter += 1
        output.append(token)
        i = end_index + 1

    return "".join(output), store


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
    """Mask bare literal placeholder tokens; return the token map.

    GROUNDING NOTE (review-fix cycle 1, P2 finding 5): live-corpus
    grounding surfaced one file (``terraform/.../tfcomponent/removed.mdx``)
    authoring a real, paired callout component in all-caps --
    ``<TIP>...body...</TIP>`` -- structurally identical to the normal
    mixed-case ``Tip`` callout ``transform_callouts`` already handles,
    but spelled the same way a placeholder is spelled. Because this mask
    runs BEFORE the generic fallback pass, masking ``<TIP>`` away here
    would silently orphan the later ``</TIP>`` (which never matches this
    ALL-CAPS-only pattern, since it starts with ``/``), leaving it to be
    mis-tallied as a genuinely unresolved construct.

    A single ALL-CAPS bracket token is therefore only masked as a
    placeholder when NO matching closing tag (``</NAME>``) exists later
    in the document. When a matching close does exist, this is
    structurally a real paired MDX/JSX component (never a literal
    placeholder -- a placeholder is never "closed"), so it is left
    unmasked here and falls through to :func:`apply_fallback_pass`,
    which resolves it the same conservative way as any other unknown
    paired tag. This is a purely structural test (does the matching
    close exist), not a name-based special case, so it generalizes to
    any other all-caps-authored component variant without enumeration.
    """
    store: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        name = match.group(1)
        if f"</{name}>" in body[match.end() :]:
            return match.group(0)
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
# Inline code span protection (review finding p8PV, Copilot review cycle 4)
# ---------------------------------------------------------------------------

#: Matches a single-line inline code span delimited by a run of N
#: backticks (N >= 1, "variable-length" per CommonMark: a longer
#: delimiter run lets the span's content safely contain a SHORTER run of
#: literal backticks, e.g. ```` ``code with a ` backtick`` ````). The
#: backreference ``(?P=fence)`` requires the CLOSING run to reuse the
#: exact captured opening text, and the trailing ``(?!`)`` negative
#: lookahead rejects a "close" that is actually the first part of a
#: LONGER run of backticks -- forcing the non-greedy ``body`` to keep
#: expanding past it and try the next candidate closing run instead. Not
#: using ``re.DOTALL`` deliberately keeps a span from crossing a line
#: break: CommonMark code spans may technically span lines, but they
#: never cross a blank line (paragraph boundary), and restricting to a
#: single line sidesteps that edge case entirely for this disposable
#: tool -- a legitimate single-line inline code span (the shape used by
#: every known real-corpus example, including this finding's own
#: ``` `<PluginBadge type="official" />` ``` case) is still matched
#: correctly either way.
#:
#: Both the OPENING and CLOSING backtick runs are additionally required
#: to be MAXIMAL (Copilot review cycle 4, follow-up round 6: a malformed
#: sequence with UNEQUAL delimiter-run lengths -- e.g. an opening run of
#: 3 backticks with no matching 3-backtick close anywhere, but a shorter
#: 2-backtick run later -- could otherwise still be "matched" because
#: the greedy ``(?P<fence>`+)`` backtracks to a SHORTER count, silently
#: absorbing the leftover backtick(s) from the true opening run into
#: ``body`` instead of correctly failing to match at all. Per
#: CommonMark, a backtick string is a valid code-span delimiter only
#: when it is neither preceded nor followed by another backtick (i.e.
#: it is the FULL, maximal run at that position). The ``(?<!`)`` /
#: ``(?!`)`` guards immediately around the opening ``fence`` group
#: enforce that for the opening delimiter (a shortened backtracked
#: capture would always be immediately followed by the leftover
#: backtick it gave up, failing the trailing ``(?!`)``); the ``(?<!`)``
#: immediately before the closing ``(?P=fence)`` enforces the same
#: maximality for the closing delimiter (rejecting a "close" that
#: actually starts partway through a longer backtick run). Together
#: these force a genuinely unequal/malformed delimiter sequence to be
#: left as literal, unmasked text -- exactly CommonMark's behavior for
#: an unterminated code span -- rather than silently hiding real
#: JSX/HTML-looking content from the unresolved-construct execute gate.
_INLINE_CODE_RE = re.compile(r"(?<!`)(?P<fence>`+)(?!`)(?P<body>.+?)(?<!`)(?P=fence)(?!`)")
_INLINE_CODE_TOKEN_FMT = "\x00INLINECODE{index}\x00"


def protect_inline_code(body: str) -> tuple[str, dict[str, str]]:
    """Mask inline code spans with an opaque token; return the token map.

    Runs AFTER :func:`protect_fenced_code` (so real fenced-code blocks,
    and any backticks inside them, are already opaque tokens by this
    point) and BEFORE the named :data:`TRANSFORM_PIPELINE` and
    :func:`apply_fallback_pass` (review finding p8PV): without this
    protection, JSX-looking text written INSIDE an inline code span --
    e.g. `` `<PluginBadge type="official" />` `` -- is literal Markdown
    source, but the named/fallback transforms cannot tell that apart
    from a real, live MDX/JSX component and would silently rewrite or
    unwrap it, corrupting the example. Masking the whole span (backticks
    included) before those transforms run makes its contents completely
    inert, exactly mirroring :func:`protect_fenced_code`'s
    protect/restore architecture. A span with no valid same-length
    closing run anywhere in the remaining text is left as literal,
    unmasked backticks (CommonMark's own behavior for unterminated code
    spans), never masked or otherwise force-consumed.
    """
    store: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = _INLINE_CODE_TOKEN_FMT.format(index=counter)
        store[token] = match.group(0)
        counter += 1
        return token

    protected = _INLINE_CODE_RE.sub(_replace, body)
    return protected, store


def restore_inline_code(body: str, store: dict[str, str]) -> str:
    """Reverse :func:`protect_inline_code`, restoring every inline code span verbatim."""
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
# Generic MDX-component fallback pass (review-fix cycle 1, P2 finding)
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

_GENERIC_SELF_CLOSING_RE = re.compile(r"<(?P<tag>[A-Z][A-Za-z0-9]*)(?P<attrs>[^>\n]*)/>")
_GENERIC_PAIRED_RE = re.compile(
    r"<(?P<tag>[A-Z][A-Za-z0-9]*)(?P<attrs>[^>\n]*?)(?<!/)>(?P<body>.*?)</(?P=tag)>",
    re.DOTALL,
)
#: Matches one attribute token, tried in priority order per position:
#: a double-quoted string value (``name="value"``, a "useful scalar"),
#: a JSX expression value (``name={...}`` -- deliberately matched but
#: NEVER rendered/evaluated, so it can be skipped rather than
#: mis-captured by the bare-attribute alternative), or a bare
#: boolean-style attribute name alone.
_ATTR_TOKEN_RE = re.compile(
    r'(?P<quoted_name>[A-Za-z_][\w-]*)="(?P<quoted_value>[^"]*)"'
    r"|(?P<expr_name>[A-Za-z_][\w-]*)=\{[^{}]*\}"
    r"|(?P<bare_name>[A-Za-z_][\w-]*)"
)
_MAX_PAIRED_UNWRAP_PASSES = 5


def _extract_scalar_attrs(attrs_text: str) -> list[tuple[str, str | None]]:
    """Extract "useful scalar" attributes for a fallback annotation.

    A double-quoted string attribute is rendered with its value; a bare
    (no ``=``) attribute is rendered as a boolean flag. A JSX expression
    attribute (``name={...}``) is matched only so it is correctly SKIPPED
    (never rendered, never evaluated) rather than accidentally treated as
    a bare attribute by a looser pattern.
    """
    scalars: list[tuple[str, str | None]] = []
    for match in _ATTR_TOKEN_RE.finditer(attrs_text):
        if match.group("quoted_name"):
            scalars.append((match.group("quoted_name"), match.group("quoted_value")))
        elif match.group("expr_name"):
            continue
        elif match.group("bare_name"):
            scalars.append((match.group("bare_name"), None))
    return scalars


def _render_fallback_annotation(tag: str, attrs_text: str) -> str:
    """Render a self-closing unknown component as a readable Markdown annotation."""
    scalars = _extract_scalar_attrs(attrs_text)
    if not scalars:
        return f"*({tag})*"
    rendered = ", ".join(
        f'{name}="{value}"' if value is not None else name for name, value in scalars
    )
    return f"*({tag}: {rendered})*"


def apply_fallback_pass(body: str) -> tuple[str, Counter[str]]:
    """Conservative final pass: resolve any CapitalizedComponent-style tag not
    already handled by the named :data:`TRANSFORM_PIPELINE`, so ``--execute``
    never silently emits raw, unrendered custom JSX into ``.md`` output.

    Two structurally unambiguous shapes are resolved generically, by
    construction, regardless of the specific tag name:

    * A genuinely PAIRED tag (``<Foo ...>body</Foo>`` -- a real matching
      close tag exists) is unwrapped: the tags are dropped and the body
      is preserved (stripped only of leading/trailing blank lines, never
      interior whitespace/indentation), e.g. HashiCorp's real
      ``<ImageConfig width={624}>`` wrapping a bare Markdown image
      reference becomes just that image reference.
    * A genuinely SELF-CLOSING tag (``<Foo .../>``) is rendered as a
      short, readable Markdown annotation naming the component plus any
      "useful scalar" attributes (double-quoted string values, or bare
      boolean-style attributes). JSX EXPRESSION attributes
      (``name={...}``) are never evaluated or rendered, per the
      containment/conservatism contract -- e.g. HashiCorp's real
      ``<Placement global={true} />`` becomes ``*(Placement)*`` (its
      only attribute is a JSX expression, so it has no scalar to show),
      while ``<PluginBadge type="official" />`` becomes
      ``*(PluginBadge: type="official")*``.

    Paired tags are resolved in a small, bounded fixed-point loop (at
    most :data:`_MAX_PAIRED_UNWRAP_PASSES` re-scans) so that different-
    tag-name nesting (e.g. a real ``<BadgesHeader>`` wrapping self-closed
    ``<PluginBadge />`` children -- resolved directly by the
    self-closing pass afterwards -- or, in principle, nested distinct
    PAIRED tags) converges without an unbounded loop. Same-tag-name
    self-nesting is a known, accepted limitation of a regex-based (not a
    real parser) approach; live-corpus grounding found no such case.

    Anything left over after this pass is, by construction, neither a
    valid self-closing tag nor a valid paired tag -- i.e. not
    well-formed MDX/JSX at all. See :func:`classify_remaining_constructs`
    for how that residue is further split into "known ambiguous prose
    notation" vs. "genuinely unresolved".
    """
    fallback: Counter[str] = Counter()

    def _replace_paired(match: re.Match[str]) -> str:
        tag = match.group("tag")
        if tag in _KNOWN_HANDLED_TAGS:
            return match.group(0)
        fallback[tag] += 1
        return match.group("body").strip("\n")

    for _ in range(_MAX_PAIRED_UNWRAP_PASSES):
        new_body = _GENERIC_PAIRED_RE.sub(_replace_paired, body)
        if new_body == body:
            break
        body = new_body

    def _replace_self_closing(match: re.Match[str]) -> str:
        tag = match.group("tag")
        if tag in _KNOWN_HANDLED_TAGS:
            return match.group(0)
        fallback[tag] += 1
        return _render_fallback_annotation(tag, match.group("attrs") or "")

    body = _GENERIC_SELF_CLOSING_RE.sub(_replace_self_closing, body)

    return body, fallback


#: Tag-shaped tokens grounded against the real HashiCorp unified-docs
#: corpus (see the requirements-evidence doc's live-corpus evidence
#: section) as ALWAYS being prose / generic-type notation rather than a
#: real MDX/JSX component -- none of these ever appears with a matching
#: close tag or a self-closing ``/>`` anywhere in the corpus. They are
#: preserved verbatim (never stripped, never fabricated as an
#: annotation) and reported separately from genuinely unresolved
#: constructs, per the finding's explicit instruction to "explicitly
#: handle ambiguous known uppercase components such as TFE rather than
#: treating them as placeholders" (the existing placeholder mask is
#: deliberately narrow -- a single ALL-CAPS word with no spaces -- and
#: is NOT broadened here, since several of these are multi-word bracket
#: content, e.g. ``<TFE hostname (DNS) e.g. terraform.example.com>``).
#:
#: Grouped by the grounded shape each name was confirmed against:
#:   * multi-word / spaced bracket placeholders (original TFE-style seed
#:     plus a full pass over the live-corpus ``unresolved_constructs``
#:     bucket for review-fix cycle 1, finding 5's "aim for zero" bar);
#:   * Consul/Nomad API-reference "``(array<Name>)``" / "`` `<Name>` ``"
#:     backtick-wrapped generic-type notation -- these read as HTML/JSX
#:     tags but are always literal type references inside inline code
#:     spans, never rendered components;
#:   * generic prose/code type-parameter notation (e.g. ``Map<String,
#:     String>``, ``Test<Provider>Config``) sharing the same shape.
_KNOWN_AMBIGUOUS_TAGS = frozenset(
    {
        # Original seed (multi-word bracket placeholders).
        "TFE",
        "ACLLink",
        "Optional",
        "Expression",
        "Provider",
        "YOUR",
        "GITHUB",
        "SOURCE",
        "ORG",
        "PLUGIN",
        "UNIQUE",
        "BITBUCKET",
        "GITLAB",
        # Review-fix cycle 1, finding 5: full live-corpus pass over the
        # `unresolved_constructs` bucket -- multi-word / prose bracket
        # placeholders (same shape as TFE/YOUR above).
        "ADFS",
        "ATTR",
        "Allowed",
        "AuthMethod",
        "CI",
        "CONTEXT",
        "DATA",
        "DIRECTORY",
        "DOCKER0",
        "FALSE",
        "FILTER",
        "HCP",
        "HOSTNAME",
        "Hostname",
        "IP",
        "JWT",
        "LOCAL",
        "MODULE",
        "Namespace",
        "OUTPUT",
        "PASSWORD",
        "PATH",
        "PLAN",
        "PROJECT",
        "PROVIDER",
        "Path",
        "REPO",
        "RESOURCE",
        "STATE",
        "Subfolder",
        "TIME",
        "TRUE",
        "URL",
        "WORKSPACE",
        "Your",
        # Consul/Nomad API-reference backtick-wrapped generic-type
        # notation, e.g. `` `(array<PolicyLink>)` ``.
        "ACLRolePolicyLink",
        "ACLTemplatedPolicyVariables",
        "Check",
        "DiscoveryRoute",
        "DiscoverySplit",
        "ExtraVolume",
        "IntentionPermission",
        "Job",
        "LinkedService",
        "NamespaceRule",
        "Node",
        "NodeIdentity",
        "PolicyLink",
        "Port",
        "RoleLink",
        "ServiceCheck",
        "ServiceIdentity",
        "StatPrefix",
        "Target",
        "Toleration",
        "TopologySpreadConstraint",
        "VaultAccessor",
        "VolumeItem",
        # Generic prose/code type-parameter notation, e.g.
        # ``Map<String, String>`` or ``Test<Provider>Config``.
        "Object",
        "String",
        "Test",
        "Type",
    }
)

_REMAINING_TAG_SCAN_RE = re.compile(r"</?([A-Z][A-Za-z0-9]*)\b[^>\n]*/?>")


def classify_remaining_constructs(body: str) -> tuple[Counter[str], Counter[str]]:
    """Classify every tag-shaped token remaining after :func:`apply_fallback_pass`.

    Returns ``(ambiguous_tokens, unresolved_constructs)``. A token whose
    leading tag name is in :data:`_KNOWN_AMBIGUOUS_TAGS` is grounded,
    documented prose notation -- it is tallied as ``ambiguous`` and NEVER
    blocks ``--execute``. Everything else remaining is tallied as
    ``unresolved`` -- a genuinely unhandled MDX/JSX-shaped construct,
    which DOES block ``--execute`` (see
    ``hashicorp_mdx_normalize.py``'s execute-mode gate) unless the
    operator passes the documented override flag.

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
    reporting-precision property -- :func:`classify_remaining_constructs`
    never mutates ``body``, so it cannot affect the actual transformed
    output, only the accuracy of the coverage report.

    A tag name in :data:`_KNOWN_HANDLED_TAGS` is deliberately NOT given a
    blanket pass here (bug, Copilot review cycle 4): in the successful
    case, every well-formed occurrence of a known tag is already fully
    consumed by the named :data:`TRANSFORM_PIPELINE` before this function
    ever runs, so it structurally cannot appear in ``body`` at all --
    excluding it from classification was a no-op for that case. But when
    a malformed shape defeats the named transform's regex (e.g. nested
    same-tag ``<Note>`` elements defeating a non-greedy same-tag close
    match) and a raw, un-rendered tag genuinely SURVIVES to this point,
    that is precisely an unresolved construct -- a blanket skip let it
    escape the execute-mode gate entirely instead. Any tag-shaped residue
    reaching this function is, by construction (see
    :func:`apply_fallback_pass`'s docstring), not well-formed MDX/JSX;
    it is classified exactly like any other residue, by name, below.
    """
    ambiguous: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    for match in _REMAINING_TAG_SCAN_RE.finditer(body):
        name = match.group(1)
        if name in _KNOWN_AMBIGUOUS_TAGS:
            ambiguous[name] += 1
        else:
            unresolved[name] += 1
    return ambiguous, unresolved


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizeResult:
    """Result of :func:`normalize_mdx_to_md`.

    * ``fallback`` -- tags resolved generically by :func:`apply_fallback_pass`
      (structurally paired-unwrapped or self-closing-annotated). These
      ARE present, transformed, in ``text``.
    * ``ambiguous`` -- known prose/type-notation tokens (see
      :data:`_KNOWN_AMBIGUOUS_TAGS`) preserved verbatim in ``text``.
      Never blocks ``--execute``.
    * ``unresolved`` -- genuinely unhandled MDX/JSX-shaped constructs
      preserved verbatim in ``text``. Blocks ``--execute`` unless the
      operator passes the documented override flag.
    """

    text: str
    fallback: Counter[str]
    ambiguous: Counter[str]
    unresolved: Counter[str]


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
    # Normalize the BODY (only) to plain \n line endings for the transform
    # pipeline below, which has always assumed -- and is tested against
    # -- \n-only content (review-fix cycle 4, finding p8Ph). The
    # frontmatter block above is left completely untouched, preserving
    # whatever line-ending bytes it was authored with (LF, CRLF, or a
    # mixed convention) exactly, since callers now read the source file
    # with newline translation disabled precisely so this text still
    # carries those original bytes.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body, fence_store = protect_fenced_code(body)
    body, inline_code_store = protect_inline_code(body)
    body, placeholder_store = protect_placeholders(body)

    for transform in TRANSFORM_PIPELINE:
        body = transform(body)

    # Generic fallback pass runs after the named pipeline so every named
    # transform gets first refusal at a construct it understands
    # specifically; only what remains falls through to the generic,
    # structural (shape-only) resolution.
    body, fallback = apply_fallback_pass(body)

    # Remaining-construct classification MUST run before restoration:
    # fenced example code, inline code spans, and placeholder tokens are
    # still masked/opaque here, so look-alike tags inside them are never
    # mis-tallied as live constructs.
    ambiguous, unresolved = classify_remaining_constructs(body)

    body = restore_fenced_code(body, fence_store)
    body = restore_inline_code(body, inline_code_store)
    body = restore_placeholders(body, placeholder_store)

    return NormalizeResult(
        text=frontmatter + body, fallback=fallback, ambiguous=ambiguous, unresolved=unresolved
    )
