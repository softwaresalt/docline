# ruff: noqa: E501
"""Compute structural + semantic + graphability metrics on extracted markdown.

For each range pair in the dataset, parses both ``markitdown.md`` and
``docling.md`` with markdown-it-py and computes ~12 metrics covering:

* AST parseability (parse success, total token count, depth)
* Structural density (heading count, list item count, code block count,
  table cell count, blockquote count, inline code count, link count)
* Semantic density (unique-token ratio, structured-vs-plain token ratio)
* Embedding-chunk friendliness (count of heading-anchored sections,
  median section length, paragraphs per section)
* Graphability (heading depth distribution, code-block density,
  table presence)

Writes ``study/results/per-range.tsv`` and ``study/results/per-engine-aggregate.json``.

The metrics are deliberately AST-aware (markdown-it tokens) rather than
naive regex / char counts, because the goal use cases (graph DB,
embeddings, LLM context) all benefit from semantic-structural quality
over raw text length.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_md = MarkdownIt("commonmark", {"html": True}).enable("table")


def _parse_tokens(text: str) -> list[Any]:
    try:
        return _md.parse(text)
    except Exception:
        return []


def _content_text(tokens: list[Any]) -> str:
    """Concatenate all leaf-level text (inline content)."""
    out: list[str] = []
    for t in tokens:
        if t.type == "inline" and t.children:
            for c in t.children:
                if c.type == "text":
                    out.append(c.content)
                elif c.type == "code_inline":
                    out.append(c.content)
        elif t.type in {"code_block", "fence"}:
            out.append(t.content or "")
    return " ".join(out)


def metrics_for(text: str) -> dict[str, Any]:
    """Compute all per-document metrics."""
    char_len = len(text)
    tokens = _parse_tokens(text)
    parse_ok = bool(tokens) or char_len == 0

    type_counter = Counter(t.type for t in tokens)

    headings_open = [t for t in tokens if t.type == "heading_open"]
    heading_count = len(headings_open)
    heading_levels = Counter(int(t.tag[1]) for t in headings_open if t.tag.startswith("h"))
    heading_depth_max = max(heading_levels) if heading_levels else 0

    list_item_count = type_counter.get("list_item_open", 0)
    bullet_lists = type_counter.get("bullet_list_open", 0)
    ordered_lists = type_counter.get("ordered_list_open", 0)
    code_block_count = type_counter.get("code_block", 0) + type_counter.get("fence", 0)
    blockquote_count = type_counter.get("blockquote_open", 0)
    paragraph_count = type_counter.get("paragraph_open", 0)
    hr_count = type_counter.get("hr", 0)

    # Tables (commonmark + gfm)
    table_open = type_counter.get("table_open", 0)
    table_row_open = type_counter.get("tr_open", 0)
    table_cell_count = type_counter.get("td_open", 0) + type_counter.get("th_open", 0)

    # Inline-level: walk inline tokens for code_inline, link_open, em_open, strong_open
    inline_counter: Counter[str] = Counter()
    for t in tokens:
        if t.type == "inline" and t.children:
            for c in t.children:
                inline_counter[c.type] += 1
    code_inline_count = inline_counter.get("code_inline", 0)
    link_count = inline_counter.get("link_open", 0)
    emph_count = inline_counter.get("em_open", 0) + inline_counter.get("strong_open", 0)

    # Token-based semantic metrics
    plain_text = _content_text(tokens)
    word_tokens = _TOKEN_RE.findall(plain_text.lower())
    word_count = len(word_tokens)
    unique_words = len(set(word_tokens))
    type_token_ratio = (unique_words / word_count) if word_count else 0.0

    # Structural-token-to-content ratio
    structural_total = (
        heading_count
        + list_item_count
        + code_block_count
        + blockquote_count
        + table_cell_count
        + link_count
    )
    structural_density = (structural_total / char_len * 1000) if char_len else 0.0
    # (per 1k chars — easier to read)

    # Embedding-chunk friendliness:
    # heading-anchored sections = number of sections starting with a heading.
    # If no headings, the whole document is 1 section.
    section_lengths_chars: list[int] = []
    if heading_count == 0:
        section_lengths_chars = [char_len]
    else:
        # Split text on heading lines (use markdown-it line info)
        lines = text.split("\n")
        sections: list[list[str]] = []
        cur_section: list[str] = []
        heading_line_re = re.compile(r"^#{1,6}\s")
        for line in lines:
            if heading_line_re.match(line):
                if cur_section:
                    sections.append(cur_section)
                cur_section = [line]
            else:
                cur_section.append(line)
        if cur_section:
            sections.append(cur_section)
        section_lengths_chars = [len("\n".join(s)) for s in sections]

    section_count = len(section_lengths_chars)
    median_section_chars = (
        int(statistics.median(section_lengths_chars)) if section_lengths_chars else 0
    )
    p90_section_chars = (
        int(statistics.quantiles(section_lengths_chars, n=10)[8])
        if len(section_lengths_chars) >= 10
        else max(section_lengths_chars, default=0)
    )

    return {
        "parse_ok": parse_ok,
        "char_len": char_len,
        "token_count": len(tokens),
        "heading_count": heading_count,
        "heading_depth_max": heading_depth_max,
        "list_item_count": list_item_count,
        "bullet_lists": bullet_lists,
        "ordered_lists": ordered_lists,
        "code_block_count": code_block_count,
        "code_inline_count": code_inline_count,
        "blockquote_count": blockquote_count,
        "paragraph_count": paragraph_count,
        "hr_count": hr_count,
        "table_count": table_open,
        "table_row_count": table_row_open,
        "table_cell_count": table_cell_count,
        "link_count": link_count,
        "emph_count": emph_count,
        "word_count": word_count,
        "unique_words": unique_words,
        "type_token_ratio": round(type_token_ratio, 4),
        "structural_density_per_1k": round(structural_density, 3),
        "section_count": section_count,
        "median_section_chars": median_section_chars,
        "p90_section_chars": p90_section_chars,
    }


def _flatten_for_tsv(prefix: str, m: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{k}": v for k, v in m.items()}


def main() -> int:
    dataset_root = Path(".elt/output/cosmos-triage-022/study/dataset")
    out_dir = Path(".elt/output/cosmos-triage-022/study/results")
    if not dataset_root.exists():
        print(f"ERROR: dataset not built: {dataset_root}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    range_dirs = sorted(p for p in dataset_root.iterdir() if p.is_dir())
    if not range_dirs:
        print(f"ERROR: no range dirs under {dataset_root}", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    for rd in range_dirs:
        meta_path = rd / "meta.json"
        md_path = rd / "markitdown.md"
        dl_path = rd / "docling.md"
        if not (meta_path.exists() and md_path.exists() and dl_path.exists()):
            print(f"  SKIP {rd.name} (missing files)")
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        md_text = md_path.read_text(encoding="utf-8")
        dl_text = dl_path.read_text(encoding="utf-8")

        md_metrics = metrics_for(md_text)
        dl_metrics = metrics_for(dl_text)

        row: dict[str, Any] = {
            "range_start": meta["range_start"],
            "range_end": meta["range_end"],
            "page_count": meta["page_count"],
            "bucket": (
                "small"
                if meta["page_count"] <= 5
                else "medium"
                if meta["page_count"] <= 30
                else "large"
            ),
        }
        row.update(_flatten_for_tsv("md", md_metrics))
        row.update(_flatten_for_tsv("dl", dl_metrics))
        rows.append(row)
        print(
            f"[{rd.name}] md_chars={md_metrics['char_len']:>6} dl_chars={dl_metrics['char_len']:>6} "
            f"md_headings={md_metrics['heading_count']:>3} dl_headings={dl_metrics['heading_count']:>3} "
            f"md_tables={md_metrics['table_count']} dl_tables={dl_metrics['table_count']}"
        )

    # TSV
    if not rows:
        print("No rows produced.")
        return 1
    headers = list(rows[0].keys())
    tsv_path = out_dir / "per-range-metrics.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(headers) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(h, "")) for h in headers) + "\n")
    print(f"\nWrote {tsv_path} ({len(rows)} rows)")

    # JSON aggregate
    (out_dir / "per-range-metrics.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
