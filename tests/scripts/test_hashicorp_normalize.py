"""Unit + golden tests for ``scripts/_hashicorp_mdx/normalize.py``
(071.003-T / 071.004-T / 071.005-T).

Covers:

* B.T1 -- frontmatter preservation, fenced-code protection, literal
  placeholder protection (``<TYPE>``, ``<PATH>``, ``<VALUE>``, ...), and
  the transform-pipeline seam.
* B.T2 -- callout/admonition transforms: ``Note``/``Warning``/``Tip``/
  ``Highlight``, ``EnterpriseAlert`` (inline self-closing + block form),
  ``HCPCallout``.
* B.T3 -- ``Tabs``/``Tab`` flattening, ``CodeTabs``/``CodeBlockConfig``
  unwrapping, ``VideoEmbed`` link rendering, and the unhandled-construct
  tally.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _hashicorp_mdx import normalize  # noqa: E402

# ---------------------------------------------------------------------------
# B.T1 -- frontmatter, fence protection, placeholder protection
# ---------------------------------------------------------------------------


def test_split_frontmatter_preserves_verbatim() -> None:
    text = (
        "---\n"
        "page_title: Terraform Enterprise\n"
        "description: >-\n"
        "  Some description.\n"
        "# START AUTO GENERATED METADATA, DO NOT EDIT\n"
        "created_at: 2026-02-02T17:54:50Z\n"
        "last_modified: 2026-02-02T17:54:50Z\n"
        "# END AUTO GENERATED METADATA\n"
        "---\n"
        "\n"
        "# Body heading\n"
    )
    frontmatter, body = normalize.split_frontmatter(text)
    assert frontmatter == (
        "---\n"
        "page_title: Terraform Enterprise\n"
        "description: >-\n"
        "  Some description.\n"
        "# START AUTO GENERATED METADATA, DO NOT EDIT\n"
        "created_at: 2026-02-02T17:54:50Z\n"
        "last_modified: 2026-02-02T17:54:50Z\n"
        "# END AUTO GENERATED METADATA\n"
        "---\n"
    )
    assert body == "\n# Body heading\n"


def test_split_frontmatter_absent_returns_empty_prefix() -> None:
    text = "# No frontmatter here\n"
    frontmatter, body = normalize.split_frontmatter(text)
    assert frontmatter == ""
    assert body == text


def test_protect_and_restore_fenced_code_round_trips_exactly() -> None:
    body = (
        "Some prose.\n\n"
        "```shell-session\n"
        '$ vault kv get -namespace="<NAMESPACE>" secret/data\n'
        "```\n\n"
        "More prose.\n"
    )
    protected, store = normalize.protect_fenced_code(body)
    assert "```" not in protected
    assert "<NAMESPACE>" not in protected  # inside the fence, masked away wholesale
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


def test_protect_and_restore_indented_fenced_code_round_trips_exactly() -> None:
    """Regression: real corpus fences are often indented under a numbered-list
    continuation (e.g. '  ```shell-session' / '  ```'). An opening/closing
    fence-boundary detector that ignores indentation fails to close the
    fence at the correct line, letting placeholder-bearing code content leak
    into the unhandled-construct scan (and risking transform interference).
    """
    body = (
        "1. Enable the plugin:\n\n"
        "  ```shell-session\n"
        "  $ vault auth enable -path=<YOUR_OIDC_MOUNT_PATH> oidc\n"
        "  ```\n\n"
        "  For example:\n\n"
        "  ```shell-session\n"
        '  $ export VAULT_NAMESPACE="oidc-ns"\n'
        "  ```\n"
    )
    protected, store = normalize.protect_fenced_code(body)
    assert "```" not in protected
    assert "<YOUR_OIDC_MOUNT_PATH>" not in protected
    assert "oidc-ns" not in protected
    assert len(store) == 2  # both indented fences detected as separate blocks
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


# ---------------------------------------------------------------------------
# Regression (review-fix cycle 1, P2): Markdown-correct fence-closing rules
# ---------------------------------------------------------------------------


def test_protect_fenced_code_closing_fence_may_be_longer_than_opening() -> None:
    """CommonMark: a closing fence needs the SAME character with length >=
    the opener's -- a longer closing run (4 backticks closing a 3-backtick
    opener) is a valid, correct close, not a mismatch."""
    body = "Intro.\n\n```text\ncontent line with <MysteryWidget /> inside\n````\n\nAfter.\n"
    protected, store = normalize.protect_fenced_code(body)
    assert "````" not in protected
    assert "<MysteryWidget" not in protected
    assert len(store) == 1
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


def test_protect_fenced_code_shorter_run_inside_does_not_terminate_block() -> None:
    """A same-character run SHORTER than the opener's length must never
    terminate the fence -- it is literal content nested inside the block
    (e.g. real corpus docs illustrating nested fenced examples)."""
    body = (
        "Intro.\n\n````text\nNested example:\n```\ninner <AlsoMysterious />\n```\n````\n\nAfter.\n"
    )
    protected, store = normalize.protect_fenced_code(body)
    assert "````" not in protected
    assert "<AlsoMysterious" not in protected
    assert len(store) == 1  # the whole span is ONE block, not split at the inner ``` lines
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


def test_protect_fenced_code_closing_indentation_independent_of_opener() -> None:
    """The closing fence's own indentation is never required to match the
    opener's indentation."""
    body = "1. Step one:\n\n  ```shell-session\n  $ command <TYPE>\n```\n\nMore text.\n"
    protected, store = normalize.protect_fenced_code(body)
    assert "```" not in protected
    assert "<TYPE>" not in protected
    assert len(store) == 1
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


def test_protect_fenced_code_unclosed_fence_runs_to_end_of_document() -> None:
    """An opener with no valid closing line anywhere preserves everything
    through end-of-document as one opaque block (CommonMark's own rule for
    an unterminated fence), rather than leaking un-masked content."""
    body = "Intro.\n\n```text\nunterminated <Mystery /> content\nmore lines\n"
    protected, store = normalize.protect_fenced_code(body)
    assert "<Mystery" not in protected
    assert len(store) == 1
    restored = normalize.restore_fenced_code(protected, store)
    assert restored == body


def test_normalize_mdx_to_md_fence_variants_never_leak_mdx_looking_text() -> None:
    """End-to-end: construct-like text inside any of the above fence
    variants must never be tallied as unhandled nor transformed, and the
    fenced block must survive byte-for-byte."""
    text = (
        "---\n"
        "page_title: Example\n"
        "---\n"
        "Real unknown construct: <MysteryWidget>\n\n"
        "````text\n"
        "```\n"
        "<AlsoUnknown> nested example </AlsoUnknown>\n"
        "```\n"
        "````\n"
    )
    result = normalize.normalize_mdx_to_md(text)
    assert result.unresolved["MysteryWidget"] == 1
    assert "AlsoUnknown" not in result.unresolved
    assert "AlsoUnknown" not in result.fallback
    assert "```\n<AlsoUnknown> nested example </AlsoUnknown>\n```" in result.text


def test_protect_and_restore_placeholders_round_trips_exactly() -> None:
    body = "Set the mount to <PATH> and the type to <TYPE> with value <VALUE>."
    protected, store = normalize.protect_placeholders(body)
    assert "<PATH>" not in protected
    assert "<TYPE>" not in protected
    assert "<VALUE>" not in protected
    restored = normalize.restore_placeholders(protected, store)
    assert restored == body


def test_protect_and_restore_hyphenated_placeholder_round_trips_exactly() -> None:
    """Grounded from the real corpus: hyphenated ALL-CAPS conventions like
    <YOUR-ORG> are common placeholders, not real MDX components."""
    body = "Clone https://github.com/<YOUR-ORG>/<YOUR-REPO>.git"
    protected, store = normalize.protect_placeholders(body)
    assert "<YOUR-ORG>" not in protected
    assert "<YOUR-REPO>" not in protected
    restored = normalize.restore_placeholders(protected, store)
    assert restored == body


def test_known_construct_tag_not_mistaken_for_placeholder() -> None:
    """CamelCase construct tags (mixed case) must never match the ALL-CAPS placeholder pattern."""
    body = '<Tab heading="Example">content</Tab>'
    protected, store = normalize.protect_placeholders(body)
    assert protected == body
    assert store == {}


def test_protect_placeholders_skips_masking_when_a_matching_close_tag_exists_later() -> None:
    """Regression (review-fix cycle 1, P2 finding 5): a single ALL-CAPS
    bracket token that has a genuine matching closing tag elsewhere in the
    document (grounded in the real corpus's all-caps
    ``<TIP>...</TIP>`` callout) is a real paired MDX component, not a
    literal placeholder -- it must not be masked away before the generic
    fallback pass gets a chance to structurally resolve it. An ordinary
    placeholder with no matching close (e.g. ``<PATH>``) is unaffected."""
    body = "Before.\n\n<TIP>\n\nDo not do the thing.\n\n</TIP>\n\nAfter <PATH> unaffected."
    protected, store = normalize.protect_placeholders(body)
    assert "<TIP>" in protected  # left unmasked -- a real paired component
    assert "</TIP>" in protected
    assert "<PATH>" not in protected  # ordinary placeholder still masked
    assert len(store) == 1
    restored = normalize.restore_placeholders(protected, store)
    assert restored == body


def test_normalize_mdx_to_md_all_caps_paired_callout_resolved_not_orphaned() -> None:
    """End-to-end: the all-caps <TIP>...</TIP> callout must be resolved by
    the generic fallback pass (unwrapped, body preserved) rather than
    leaving an orphaned, genuinely-unresolved </TIP> closing tag."""
    text = "---\npage_title: Example\n---\n<TIP>\n\nDo not remove providers.\n\n</TIP>\n"
    result = normalize.normalize_mdx_to_md(text)
    assert result.fallback["TIP"] == 1
    assert result.unresolved == {}
    assert result.ambiguous == {}
    assert "Do not remove providers." in result.text
    assert "<TIP>" not in result.text
    assert "</TIP>" not in result.text


def test_normalize_preserves_placeholders_end_to_end() -> None:
    text = (
        "---\n"
        "page_title: Example\n"
        "---\n"
        "Run with type <TYPE> and path <PATH>.\n\n"
        "```shell-session\n"
        "$ command <VALUE>\n"
        "```\n"
    )
    result = normalize.normalize_mdx_to_md(text)
    assert "<TYPE>" in result.text
    assert "<PATH>" in result.text
    assert "<VALUE>" in result.text
    assert "page_title: Example" in result.text


# ---------------------------------------------------------------------------
# B.T2 -- callouts / admonitions
# ---------------------------------------------------------------------------


def test_transform_callouts_note_with_title() -> None:
    body = '<Note title="Heads up">This is important.</Note>'
    out = normalize.transform_callouts(body)
    assert out == "> **Heads up**\n>\n> This is important."


def test_transform_callouts_warning_without_title_uses_tag_name() -> None:
    body = "<Warning>Danger ahead.</Warning>"
    out = normalize.transform_callouts(body)
    assert out == "> **Warning**\n>\n> Danger ahead."


def test_transform_callouts_multiline_body_all_lines_quoted() -> None:
    body = '<Tip title="Fast path">\nLine one.\nLine two.\n</Tip>'
    out = normalize.transform_callouts(body)
    assert out.startswith("> **Fast path**\n>\n")
    assert "> Line one." in out
    assert "> Line two." in out


def test_transform_callouts_highlight() -> None:
    body = '<Highlight title="New">Feature launched.</Highlight>'
    out = normalize.transform_callouts(body)
    assert out == "> **New**\n>\n> Feature launched."


def test_transform_enterprise_alert_self_closing_inline() -> None:
    body = 'Vault Enterprise supports this. <EnterpriseAlert inline="true" /> Read more.'
    out = normalize.transform_enterprise_alert(body)
    assert out == "Vault Enterprise supports this. **(Enterprise-only)** Read more."


def test_transform_enterprise_alert_self_closing_with_product_attr() -> None:
    body = '<EnterpriseAlert product="vault" inline="true" />'
    out = normalize.transform_enterprise_alert(body)
    assert out == "**(Enterprise-only)**"


def test_transform_enterprise_alert_block_form_with_body() -> None:
    body = "<EnterpriseAlert>This feature requires a paid tier.</EnterpriseAlert>"
    out = normalize.transform_enterprise_alert(body)
    assert out == "> **Enterprise Only**\n>\n> This feature requires a paid tier."


def test_transform_hcp_callout_renders_product_reference() -> None:
    body = '<HCPCallout product="vault" />'
    out = normalize.transform_hcp_callout(body)
    assert out == "> **HCP**\n>\n> This content applies to HCP `vault`."


# ---------------------------------------------------------------------------
# B.T3 -- Tabs, CodeTabs, CodeBlockConfig, VideoEmbed
# ---------------------------------------------------------------------------


def test_transform_tabs_flattens_to_headed_sections() -> None:
    body = (
        "<Tabs>\n"
        '<Tab heading="CLI" group="method">\nUse the CLI.\n</Tab>\n'
        '<Tab heading="API" group="method">\nUse the API.\n</Tab>\n'
        "</Tabs>\n"
    )
    out = normalize.transform_tabs(body)
    assert "<Tabs>" not in out
    assert "</Tab>" not in out
    assert "#### CLI" in out
    assert "#### API" in out
    assert out.index("#### CLI") < out.index("#### API")


def test_transform_tabs_nested_flattens_deterministically() -> None:
    """Nested Tabs-within-Tab flattens to a flat sequence of headings."""
    body = (
        "<Tabs>\n"
        '<Tab heading="Outer" group="g">\n'
        "<Tabs>\n"
        '<Tab heading="Inner" group="h">\nnested content\n</Tab>\n'
        "</Tabs>\n"
        "</Tab>\n"
        "</Tabs>\n"
    )
    out = normalize.transform_tabs(body)
    assert "<Tabs>" not in out
    assert "<Tab " not in out
    assert "#### Outer" in out
    assert "#### Inner" in out
    assert out.index("#### Outer") < out.index("#### Inner")


def test_transform_code_tabs_and_code_block_config_sequential_labeled_blocks() -> None:
    body = (
        '<CodeTabs heading="Shell examples">\n'
        '<CodeBlockConfig filename="main.tf">\n\n'
        '```hcl\nresource "x" "y" {}\n```\n\n'
        "</CodeBlockConfig>\n"
        '<CodeBlockConfig heading="Output">\n\n'
        "```text\nok\n```\n\n"
        "</CodeBlockConfig>\n"
        "</CodeTabs>\n"
    )
    protected, fence_store = normalize.protect_fenced_code(body)
    out = normalize.transform_code_tabs(protected)
    out = normalize.transform_code_block_config(out)
    restored = normalize.restore_fenced_code(out, fence_store)
    assert "<CodeTabs" not in restored
    assert "<CodeBlockConfig" not in restored
    assert "**Shell examples**" in restored
    assert "**main.tf**" in restored
    assert "**Output**" in restored
    assert 'resource "x" "y" {}' in restored
    assert "```text\nok\n```" in restored


def test_transform_video_embed_renders_markdown_link() -> None:
    body = '<VideoEmbed url="https://example.com/video.mp4"/>'
    out = normalize.transform_video_embed(body)
    assert out == "[Video](https://example.com/video.mp4)"


# ---------------------------------------------------------------------------
# Generic fallback pass (review-fix cycle 1, P2 finding): paired unwrap,
# self-closing annotation, and ambiguous/unresolved classification
# ---------------------------------------------------------------------------


def test_apply_fallback_pass_unwraps_generic_paired_tag_preserving_body() -> None:
    """Real corpus shape: <ImageConfig width={624}>...markdown image...</ImageConfig>."""
    body = (
        "Before.\n\n<ImageConfig width={624}>\n\n![Diagram](/img/diagram.png)"
        "\n\n</ImageConfig>\n\nAfter.\n"
    )
    transformed, fallback = normalize.apply_fallback_pass(body)
    assert fallback["ImageConfig"] == 1
    assert "<ImageConfig" not in transformed
    assert "</ImageConfig>" not in transformed
    assert "![Diagram](/img/diagram.png)" in transformed


def test_apply_fallback_pass_self_closing_with_only_expr_attr_renders_bare_annotation() -> None:
    """Real corpus shape: <Placement global={true} /> -- its only attribute is
    a JSX expression, which must never be evaluated or rendered."""
    body = "Some text <Placement global={true} /> more text."
    transformed, fallback = normalize.apply_fallback_pass(body)
    assert fallback["Placement"] == 1
    assert "*(Placement)*" in transformed
    assert "global" not in transformed
    assert "{true}" not in transformed


def test_apply_fallback_pass_self_closing_with_quoted_attr_renders_scalar_annotation() -> None:
    """Real corpus shape: <PluginBadge type="official" />."""
    body = 'Badges: <PluginBadge type="official" />'
    transformed, fallback = normalize.apply_fallback_pass(body)
    assert fallback["PluginBadge"] == 1
    assert '*(PluginBadge: type="official")*' in transformed


def test_apply_fallback_pass_nested_paired_and_self_closing_resolves_both() -> None:
    """Real corpus shape: <BadgesHeader><PluginBadge type="official" /></BadgesHeader>."""
    body = '<BadgesHeader>\n<PluginBadge type="official" />\n</BadgesHeader>\n'
    transformed, fallback = normalize.apply_fallback_pass(body)
    assert fallback["BadgesHeader"] == 1
    assert fallback["PluginBadge"] == 1
    assert "<BadgesHeader>" not in transformed
    assert '*(PluginBadge: type="official")*' in transformed


def test_apply_fallback_pass_leaves_known_handled_tags_untouched() -> None:
    body = '<Note title="Heads up">Still here.</Note>'
    transformed, fallback = normalize.apply_fallback_pass(body)
    assert fallback == {}
    assert transformed == body


def test_classify_remaining_constructs_flags_unknown_capitalized_tags_as_unresolved() -> None:
    body = "Some text <MysteryWidget> and more <Note>known</Note>."
    body = normalize.transform_callouts(body)
    ambiguous, unresolved = normalize.classify_remaining_constructs(body)
    assert unresolved["MysteryWidget"] == 1
    assert "Note" not in unresolved
    assert ambiguous == {}


def test_classify_remaining_constructs_treats_known_ambiguous_tags_as_non_blocking() -> None:
    """Real corpus shape: <TFE HOSTNAME> / <TFE hostname (DNS) e.g. ...> --
    grounded, documented prose notation, never a real component."""
    body = "Set the URL to <TFE HOSTNAME> in your configuration."
    ambiguous, unresolved = normalize.classify_remaining_constructs(body)
    assert ambiguous["TFE"] == 1
    assert "TFE" not in unresolved


def test_classify_remaining_constructs_treats_review_fix_cycle1_grounded_tags() -> None:
    """Review-fix cycle 1, finding 5 "aim for zero" bar: every name in the
    full live-corpus `unresolved_constructs` pass (Consul/Nomad API-doc
    backtick generic-type notation, plus additional prose placeholders)
    was individually grounded as never a real component and added to the
    registry so it is reported as non-blocking `ambiguous`, never
    `unresolved`."""
    body = (
        "Policies `(array<PolicyLink>)` and node identity "
        "`(array<NodeIdentity>)` are optional. Set the URL to "
        "`https://<ADFS hostname>/<HOSTNAME>` accordingly. "
        "Generic notation: Map<String, String>."
    )
    ambiguous, unresolved = normalize.classify_remaining_constructs(body)
    assert ambiguous["PolicyLink"] == 1
    assert ambiguous["NodeIdentity"] == 1
    assert ambiguous["ADFS"] == 1
    assert ambiguous["HOSTNAME"] == 1
    assert ambiguous["String"] == 1
    assert unresolved == {}


def test_classify_remaining_constructs_ignores_lowercase_html_passthrough() -> None:
    body = 'Click <a href="https://example.com">here</a> or press <b>enter</b>.'
    ambiguous, unresolved = normalize.classify_remaining_constructs(body)
    assert ambiguous == {}
    assert unresolved == {}


def test_classify_remaining_constructs_does_not_span_lines_to_a_distant_unrelated_bracket() -> None:
    """Regression: a heredoc-like '<<EOF' on one line must not spuriously match
    an unrelated '>' character many lines later (e.g. a blockquote marker),
    which would otherwise mis-tally a large intervening span as attributes of
    a fake 'EOF' construct tag.
    """
    body = (
        "Use a heredoc like this in your shell:\n\n"
        "some prose <<EOF marker text here\n"
        "more unrelated prose on its own line\n"
        "> this is an unrelated blockquote far below\n"
    )
    ambiguous, unresolved = normalize.classify_remaining_constructs(body)
    assert "EOF" not in unresolved
    assert "EOF" not in ambiguous


def test_normalize_mdx_to_md_excludes_fenced_example_code_from_construct_tallies() -> None:
    """A construct-like tag INSIDE a fenced code sample must not be tallied at all."""
    text = (
        "---\n"
        "page_title: Example\n"
        "---\n"
        "Real unknown construct: <MysteryWidget>\n\n"
        "```mdx\n"
        "<AlsoUnknown />\n"
        "```\n"
    )
    result = normalize.normalize_mdx_to_md(text)
    assert result.unresolved["MysteryWidget"] == 1
    assert "AlsoUnknown" not in result.unresolved
    assert "AlsoUnknown" not in result.fallback
    assert "AlsoUnknown" not in result.ambiguous
    assert "<AlsoUnknown />" in result.text  # fenced example preserved verbatim


def test_normalize_mdx_to_md_full_pipeline_end_to_end() -> None:
    text = (
        "---\n"
        "page_title: Vault Example\n"
        "---\n"
        '<Note title="Heads up">Read this first.</Note>\n\n'
        'Vault Enterprise only. <EnterpriseAlert inline="true" />\n\n'
        '<HCPCallout product="vault" />\n\n'
        "<Tabs>\n"
        '<Tab heading="CLI">\nUse the CLI.\n</Tab>\n'
        "</Tabs>\n\n"
        '<VideoEmbed url="https://example.com/demo.mp4"/>\n\n'
        "```shell-session\n"
        "$ vault kv get -namespace=<NAMESPACE> secret/data\n"
        "```\n"
    )
    result = normalize.normalize_mdx_to_md(text)
    assert "page_title: Vault Example" in result.text
    assert "> **Heads up**" in result.text
    assert "**(Enterprise-only)**" in result.text
    assert "> **HCP**" in result.text
    assert "#### CLI" in result.text
    assert "[Video](https://example.com/demo.mp4)" in result.text
    assert "<NAMESPACE>" in result.text
    assert result.fallback == {}
    assert result.ambiguous == {}
    assert result.unresolved == {}


def test_normalize_mdx_to_md_golden_fallback_and_ambiguous_end_to_end() -> None:
    """Golden end-to-end case combining a real paired component
    (ImageConfig), a real self-closing component (PluginBadge), a known
    ambiguous prose token (TFE), and a genuinely unresolved bare tag."""
    text = (
        "---\n"
        "page_title: Golden Example\n"
        "---\n"
        "<ImageConfig width={624}>\n\n![Diagram](/img/diagram.png)\n\n</ImageConfig>\n\n"
        'Badge: <PluginBadge type="official" />\n\n'
        "Point the agent at <TFE HOSTNAME> to continue.\n\n"
        "This is <BrandNewWidget> still unresolved.\n"
    )
    result = normalize.normalize_mdx_to_md(text)
    assert "![Diagram](/img/diagram.png)" in result.text
    assert '*(PluginBadge: type="official")*' in result.text
    assert "<TFE HOSTNAME>" in result.text
    assert "<BrandNewWidget>" in result.text
    assert result.fallback["ImageConfig"] == 1
    assert result.fallback["PluginBadge"] == 1
    assert result.ambiguous["TFE"] == 1
    assert result.unresolved["BrandNewWidget"] == 1
