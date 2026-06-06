"""One-shot corpus analysis for 017-S spike (H1 header synthesis).

Reads every `.md` part under `.elt/output/` and reports, per source job,
the four headerless-part metrics defined in 018.001-T:

* (a) parts with `section_title: null`
* (b) parts whose body first heading is H2/H3 (no H1)
* (c) parts where `title` frontmatter could plausibly serve as H1
* (d) parts where the first non-empty paragraph is a sensible candidate

Outputs a structured JSON summary to stdout and a Markdown table to
stderr (so the JSON pipeline can stay clean).

Usage:
    python scripts/spike_h1_corpus_analysis.py [corpus_root]

Default corpus root is `.elt/output/`.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CORPUS_ROOT = Path(".elt/output")

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MD_IMAGE_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$")
URL_RE = re.compile(r"^https?://\S+$")
PLACEHOLDER_TITLE_RE = re.compile(r"\s+Part\s+\d+\s*$", re.IGNORECASE)


def iter_part_files(root: Path) -> Iterator[Path]:
    """Yield every `.md` file under `root`, excluding the top-level manifest."""
    for path in root.rglob("*.md"):
        if path.is_file():
            yield path


def split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split a markdown file into (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    fm_raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError:
        return None, body
    if not isinstance(fm, dict):
        return None, body
    return fm, body


def first_body_heading_level(body: str) -> int | None:
    """Return the heading level of the first ATX heading in `body`, or None."""
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            return len(match.group(1))
    return None


def first_non_empty_paragraph(body: str) -> str | None:
    """Return the first non-empty, non-anchor, non-heading line in `body`."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if HEADING_RE.match(stripped):
            continue
        if stripped.startswith("<a id="):
            continue
        return stripped
    return None


def is_placeholder_title(title: str | None) -> bool:
    """Detect auto-generated placeholder titles like 'X Part N' or 'Untitled'."""
    if title is None:
        return True
    title = title.strip()
    if not title:
        return True
    if title.lower() in {"untitled", "untitled document", "document"}:
        return True
    if PLACEHOLDER_TITLE_RE.search(title):
        return True
    return False


def title_usable_as_h1(title: str | None) -> bool:
    """A title is a viable H1 candidate when it's non-placeholder and ≤ 100 chars."""
    if is_placeholder_title(title):
        return False
    assert title is not None
    return len(title.strip()) <= 100


def paragraph_usable_as_h1(paragraph: str | None) -> bool:
    """First-paragraph fallback is viable when length 10–120 and not image/URL."""
    if paragraph is None:
        return False
    stripped = paragraph.strip()
    length = len(stripped)
    if length < 10 or length > 120:
        return False
    if MD_IMAGE_RE.match(stripped):
        return False
    if URL_RE.match(stripped):
        return False
    return True


def get_section_title(fm: dict[str, Any]) -> str | None:
    """Pull `docline.section_title` from frontmatter."""
    docline = fm.get("docline")
    if not isinstance(docline, dict):
        return None
    value = docline.get("section_title")
    if isinstance(value, str):
        return value
    return None


def analyze_part(path: Path) -> dict[str, Any] | None:
    """Analyze a single `.md` part. Returns metrics dict or None on parse failure."""
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    fm, body = split_frontmatter(text)
    if fm is None:
        return None
    section_title = get_section_title(fm)
    body_heading = first_body_heading_level(body)
    first_para = first_non_empty_paragraph(body)
    title = fm.get("title")
    return {
        "section_title_null": section_title is None,
        "body_first_h2_or_h3_no_h1": body_heading is not None and body_heading >= 2,
        "title_usable": title_usable_as_h1(title),
        "first_para_usable": paragraph_usable_as_h1(first_para),
    }


def job_id_for(path: Path, root: Path) -> str:
    """The first path component under `root` is the job_id."""
    rel = path.relative_to(root)
    return rel.parts[0]


def aggregate(root: Path) -> dict[str, Any]:
    """Walk the corpus and aggregate per-job metrics including tier rescue rates."""
    per_job: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total_parts": 0,
            "section_title_null": 0,
            "body_first_h2_or_h3_no_h1": 0,
            "title_usable": 0,
            "first_para_usable": 0,
            "parse_failures": 0,
            # Rescue intersections: of the parts where section_title is null,
            # how many would each deterministic tier successfully rescue?
            "tier_a_rescues": 0,  # title promotion
            "tier_b_rescues": 0,  # first H2 → H1 promotion
            "tier_c_rescues": 0,  # first paragraph fallback
            "hybrid_rescues": 0,  # A → B → C escalation
            "unrescued": 0,  # sect_null AND no tier helps
        }
    )
    for part in iter_part_files(root):
        if part.name == "manifest.json":
            continue
        try:
            job = job_id_for(part, root)
        except ValueError:
            continue
        bucket = per_job[job]
        result = analyze_part(part)
        bucket["total_parts"] += 1
        if result is None:
            bucket["parse_failures"] += 1
            continue
        for key in (
            "section_title_null",
            "body_first_h2_or_h3_no_h1",
            "title_usable",
            "first_para_usable",
        ):
            if result[key]:
                bucket[key] += 1
        if result["section_title_null"]:
            rescued = False
            if result["title_usable"]:
                bucket["tier_a_rescues"] += 1
                rescued = True
            if result["body_first_h2_or_h3_no_h1"]:
                bucket["tier_b_rescues"] += 1
                rescued = True
            if result["first_para_usable"]:
                bucket["tier_c_rescues"] += 1
                rescued = True
            if rescued:
                bucket["hybrid_rescues"] += 1
            else:
                bucket["unrescued"] += 1
    totals: dict[str, int] = {
        "total_parts": 0,
        "section_title_null": 0,
        "body_first_h2_or_h3_no_h1": 0,
        "title_usable": 0,
        "first_para_usable": 0,
        "parse_failures": 0,
        "tier_a_rescues": 0,
        "tier_b_rescues": 0,
        "tier_c_rescues": 0,
        "hybrid_rescues": 0,
        "unrescued": 0,
    }
    for bucket in per_job.values():
        for key in totals:
            totals[key] += bucket[key]
    return {"jobs": dict(per_job), "totals": totals}


def render_markdown_table(summary: dict[str, Any]) -> str:
    """Render two Markdown tables: corpus shape and tier rescue rates."""
    shape_header = (
        "| Job | Parts | sect=null | H2/H3-first | title usable | first-para usable | parse fail |"
    )
    shape_sep = "|---|---:|---:|---:|---:|---:|---:|"
    shape_rows = [shape_header, shape_sep]
    for job, bucket in sorted(summary["jobs"].items()):
        shape_rows.append(
            f"| {job} | {bucket['total_parts']} | {bucket['section_title_null']} | "
            f"{bucket['body_first_h2_or_h3_no_h1']} | {bucket['title_usable']} | "
            f"{bucket['first_para_usable']} | {bucket['parse_failures']} |"
        )
    totals = summary["totals"]
    shape_rows.append(
        f"| **TOTAL** | **{totals['total_parts']}** | **{totals['section_title_null']}** | "
        f"**{totals['body_first_h2_or_h3_no_h1']}** | **{totals['title_usable']}** | "
        f"**{totals['first_para_usable']}** | **{totals['parse_failures']}** |"
    )

    rescue_header = (
        "| Job | sect=null | Tier A (title) | Tier B (H2->H1) | "
        "Tier C (1st para) | Hybrid | Unrescued |"
    )
    rescue_sep = "|---|---:|---:|---:|---:|---:|---:|"
    rescue_rows = [rescue_header, rescue_sep]
    for job, bucket in sorted(summary["jobs"].items()):
        rescue_rows.append(
            f"| {job} | {bucket['section_title_null']} | {bucket['tier_a_rescues']} | "
            f"{bucket['tier_b_rescues']} | {bucket['tier_c_rescues']} | "
            f"{bucket['hybrid_rescues']} | {bucket['unrescued']} |"
        )
    rescue_rows.append(
        f"| **TOTAL** | **{totals['section_title_null']}** | **{totals['tier_a_rescues']}** | "
        f"**{totals['tier_b_rescues']}** | **{totals['tier_c_rescues']}** | "
        f"**{totals['hybrid_rescues']}** | **{totals['unrescued']}** |"
    )
    return (
        "## Corpus shape\n\n"
        + "\n".join(shape_rows)
        + "\n\n## Tier rescue rates\n\n"
        + "\n".join(rescue_rows)
    )


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else DEFAULT_CORPUS_ROOT
    if not root.exists():
        print(f"corpus root does not exist: {root}", file=sys.stderr)
        return 1
    summary = aggregate(root)
    print(json.dumps(summary, indent=2))
    print(render_markdown_table(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
