"""Schema-driven Markdown AST lint stubs."""

from markdown_it import MarkdownIt

_MAX_HEADING_DEPTH = 3
_REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {"adr": ("Decision",)}


def _heading_text(inline_token: object) -> str:
    """Return plain text from an inline token, stripping markup."""
    if hasattr(inline_token, "children") and inline_token.children:
        return "".join(
            child.content
            for child in inline_token.children
            if child.type in ("text", "softbreak", "hardbreak", "code_inline")
        )
    return getattr(inline_token, "content", "")


def _collect_headings(markdown_text: str) -> list[tuple[int, str]]:
    """Collect heading levels and text from Markdown content.

    Args:
        markdown_text: Markdown document text.

    Returns:
        Heading level and text pairs in encounter order.
    """
    headings: list[tuple[int, str]] = []
    tokens = MarkdownIt().parse(markdown_text)
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].type != "inline":
            continue
        headings.append((int(token.tag[1:]), _heading_text(tokens[index + 1])))
    return headings


def lint_markdown_ast(markdown_text: str, doc_type: str) -> list[str]:
    """Lint Markdown structure against schema-derived rules.

    Args:
        markdown_text: Assembled Markdown document text.
        doc_type: Document type identifier used for schema lookup.

    Returns:
        A list of structural lint errors.
    """
    headings = _collect_headings(markdown_text)
    errors: list[str] = []

    if any(level > _MAX_HEADING_DEPTH for level, _ in headings):
        errors.append("Heading depth exceeded schema limits")

    present_h2_sections = {text for level, text in headings if level == 2}
    for required_section in _REQUIRED_SECTIONS.get(doc_type, ()):
        if required_section not in present_h2_sections:
            errors.append(f"Missing required section: {required_section}")

    return errors


__all__ = ["lint_markdown_ast"]
