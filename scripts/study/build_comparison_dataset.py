# ruff: noqa: E501
"""Build the comparative study dataset.

Pairs markitdown vs docling output across a stratified sample of the
84 flagged ranges from the cosmos PA3+PA4 run, reusing the per-page
``baseline-NNNN.pdf`` files and the existing ``splice-AAAA-BBBB.md``
docling outputs. Markitdown is regenerated locally (fast: ~1-2 s/page).

Strategy
--------

Reads ``.elt/output/cosmos-triage-022/pa3-summary.json``, partitions
the 84 ranges with docling output by ``page_count`` into 3 buckets
(small ≤ 5, medium 6-30, large > 30), and samples up to ``N_PER_BUCKET``
ranges per bucket (deterministic via random_seed). Writes paired
markdown files for each sampled range under
``.elt/output/cosmos-triage-022/study/dataset/range-NNNN-MMMM/``.

Output
------

For each sampled range:

    range-NNNN-MMMM/
      ├── markitdown.md          (regenerated per-page concat)
      ├── docling.md             (the existing splice md, copied)
      └── meta.json              ({range, page_count, source files})

Plus dataset-level:

    dataset/index.json           (full list of sampled ranges + metadata)

Not committed to repo; output lives under ``.elt/`` which is gitignored.
"""

from __future__ import annotations

import json
import logging
import random
import sys
from pathlib import Path


def _silence_pdfminer() -> None:
    for name in ("pdfminer.pdffont", "pdfminer.pdfinterp"):
        logging.getLogger(name).setLevel(logging.ERROR)


def _markitdown_one(pdf_path: Path) -> str:
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(pdf_path))
    return result.text_content


_MD_SINGLETON = {"value": None}


def _markitdown_singleton(pdf_path: Path) -> str:
    if _MD_SINGLETON["value"] is None:
        from markitdown import MarkItDown

        _MD_SINGLETON["value"] = MarkItDown(enable_plugins=False)
    return _MD_SINGLETON["value"].convert(str(pdf_path)).text_content


def stratified_sample(
    ranges: list[tuple[int, int]],
    docling_present: set[tuple[int, int]],
    n_per_bucket: int,
    seed: int,
) -> list[tuple[int, int]]:
    """Stratify by page count into 3 buckets; sample up to n_per_bucket each."""
    rng = random.Random(seed)

    eligible = [r for r in ranges if tuple(r) in docling_present]
    small = [r for r in eligible if (r[1] - r[0] + 1) <= 5]
    medium = [r for r in eligible if 6 <= (r[1] - r[0] + 1) <= 30]
    large = [r for r in eligible if (r[1] - r[0] + 1) > 30]

    def pick(bucket: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if len(bucket) <= n_per_bucket:
            return list(bucket)
        return rng.sample(bucket, n_per_bucket)

    return pick(small) + pick(medium) + pick(large)


def build_pair(
    splice_dir: Path,
    out_root: Path,
    range_start: int,
    range_end: int,
) -> dict:
    out_dir = out_root / f"range-{range_start:04d}-{range_end:04d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # docling: copy splice md as-is
    splice_md = splice_dir / f"splice-{range_start:04d}-{range_end:04d}.md"
    docling_text = splice_md.read_text(encoding="utf-8")
    (out_dir / "docling.md").write_text(docling_text, encoding="utf-8")

    # markitdown: per-page concat with page-boundary markers
    parts: list[str] = []
    per_page_lengths: list[int] = []
    for page_idx in range(range_start, range_end + 1):
        baseline = splice_dir / f"baseline-{page_idx:04d}.pdf"
        if not baseline.exists():
            text = f"<!-- page {page_idx}: baseline PDF missing -->"
        else:
            try:
                text = _markitdown_singleton(baseline)
            except Exception as exc:
                text = f"<!-- markitdown failed on page {page_idx}: {exc} -->"
        parts.append(f"\n\n<!-- ===== page {page_idx} ===== -->\n\n{text}")
        per_page_lengths.append(len(text))

    markitdown_text = "".join(parts).lstrip()
    (out_dir / "markitdown.md").write_text(markitdown_text, encoding="utf-8")

    meta = {
        "range_start": range_start,
        "range_end": range_end,
        "page_count": range_end - range_start + 1,
        "splice_md": splice_md.name,
        "markitdown_total_chars": len(markitdown_text),
        "docling_total_chars": len(docling_text),
        "markitdown_per_page_chars": per_page_lengths,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    splice_dir = Path(".elt/output/cosmos-triage-022/splices")
    summary_path = Path(".elt/output/cosmos-triage-022/pa3-summary.json")
    out_root = Path(".elt/output/cosmos-triage-022/study/dataset")

    if not splice_dir.exists() or not summary_path.exists():
        print(
            f"ERROR: missing inputs (splice_dir={splice_dir}, summary={summary_path})",
            file=sys.stderr,
        )
        return 1

    _silence_pdfminer()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    flagged = [tuple(r) for r in summary["flagged_ranges"]]

    # Determine which ranges have docling output
    docling_present: set[tuple[int, int]] = set()
    for s, e in flagged:
        if (splice_dir / f"splice-{s:04d}-{e:04d}.md").exists():
            docling_present.add((s, e))
    print(f"Total flagged ranges: {len(flagged)}; with docling md: {len(docling_present)}")

    sampled = stratified_sample(flagged, docling_present, n_per_bucket=5, seed=2026)
    print(f"Sampled {len(sampled)} ranges across small/medium/large buckets")
    for s, e in sampled:
        size = e - s + 1
        bucket = "small" if size <= 5 else "medium" if size <= 30 else "large"
        print(f"  range ({s:>4}, {e:>4}) — {size} pages [{bucket}]")

    out_root.mkdir(parents=True, exist_ok=True)
    metas = []
    for i, (s, e) in enumerate(sampled, 1):
        print(f"[{i}/{len(sampled)}] building range {s}-{e}...")
        meta = build_pair(splice_dir, out_root, s, e)
        metas.append(meta)

    index = {
        "n_ranges": len(sampled),
        "n_pages_total": sum(m["page_count"] for m in metas),
        "ranges": metas,
    }
    (out_root / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"\nDataset built: {out_root}")
    print(f"Index: {out_root / 'index.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
