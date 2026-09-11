#!/usr/bin/env python
"""Temporary, disposable HashiCorp unified-docs MDX -> MD normalization
preprocessor (shipment 062-S / feature 071-F).

Selectively copies ONLY the latest-version directory of every versioned
HashiCorp product, plus the entire tree of every unversioned product,
from a read-only external corpus (the HashiCorp unified-docs
``content/`` directory), converting ``.mdx`` to standard ``.md`` in
flight. This is disposable requirements-evidence tooling for a future
first-class docline MDX ingestion feature -- it is NOT integrated into
the docline application and is not intended to be maintained long-term.
See
``docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md``
for the full rationale, scope boundary, and live-verification findings.

HARD CONTAINMENT CONTRACT
=========================
* Dry-run is the default mode: the tool performs ZERO writes and prints a
  JSON plan (per-product selected version, file counts, unhandled
  MDX-construct tally, warnings) to stdout. ``--execute`` is REQUIRED to
  write anything to disk.
* Every write, in ``--execute`` mode, is guarded to resolve strictly
  inside ``--dest`` (:func:`guard_write_path` /
  :class:`ContainmentViolation`). A resolved write path outside
  ``--dest`` is refused and the process exits non-zero.
* This script never hardcodes or defaults to the operator's real external
  destination; ``--source`` and ``--dest`` are always explicit,
  operator-supplied arguments.

EXACT OPERATOR COMMAND (documented per C.T2's acceptance criterion; this
command is never executed by an agent -- only the operator runs it):

    python scripts/hashicorp_mdx_normalize.py `
        --source "C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content" `
        --dest "C:\\Source\\Docs\\tf-unified-dev-docs-normalized" `
        --execute `
        --report "C:\\Source\\Docs\\tf-unified-dev-docs-normalized\\_normalize-report.json"

Omit ``--execute`` (and, if desired, point ``--report`` at any local
path) to preview the exact same plan with zero writes -- this is the
default mode and is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _hashicorp_mdx import normalize, selection  # noqa: E402

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_SOURCE_NOT_FOUND = 4
EXIT_CONTAINMENT_VIOLATION = 3

#: Image-like binary assets copied byte-for-byte, unchanged.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})
#: Ordinary Markdown files copied byte-for-byte, unchanged (no normalization needed).
ORDINARY_MD_EXTENSIONS = frozenset({".md", ".markdown"})
#: MDX files are normalized in-flight (read -> transform -> write .md).
MDX_EXTENSIONS = frozenset({".mdx"})


class ContainmentViolation(RuntimeError):
    """Raised when a resolved write path falls outside the configured ``--dest`` root."""


def guard_write_path(dest_root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and verify it falls strictly inside ``dest_root``.

    Returns the resolved candidate path on success. Raises
    :class:`ContainmentViolation` -- WITHOUT touching the filesystem --
    when the resolved candidate is not contained by ``dest_root``.
    """
    dest_resolved = dest_root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(dest_resolved)
    except ValueError as exc:
        raise ContainmentViolation(
            f"refusing to write outside --dest: {candidate_resolved} is not under {dest_resolved}"
        ) from exc
    return candidate_resolved


def _is_partial_path(relative_path: Path) -> bool:
    """True if any path component is literally ``partials`` (case-insensitive).

    Partials/fragment files never carry frontmatter and must never be
    emitted as standalone documents, regardless of how deeply nested
    they are inside a selected product/version tree.
    """
    return any(part.lower() == "partials" for part in relative_path.parts)


@dataclass
class ProductCounts:
    mdx_normalized: int = 0
    md_copied: int = 0
    assets_copied: int = 0
    skipped_partials: int = 0
    skipped_other: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "mdx_normalized": self.mdx_normalized,
            "md_copied": self.md_copied,
            "assets_copied": self.assets_copied,
            "skipped_partials": self.skipped_partials,
            "skipped_other": self.skipped_other,
        }

    def add(self, other: ProductCounts) -> None:
        self.mdx_normalized += other.mdx_normalized
        self.md_copied += other.md_copied
        self.assets_copied += other.assets_copied
        self.skipped_partials += other.skipped_partials
        self.skipped_other += other.skipped_other


@dataclass
class ProductReport:
    versioned: bool
    selected_version: str | None
    counts: ProductCounts = field(default_factory=ProductCounts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "versioned": self.versioned,
            "selected_version": self.selected_version,
            "file_counts": self.counts.as_dict(),
        }


@dataclass
class ReportBuilder:
    source: Path
    dest: Path
    execute: bool
    products: dict[str, ProductReport] = field(default_factory=dict)
    unhandled_constructs: Counter[str] = field(default_factory=Counter)
    excluded_top_level_dirs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    containment_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        totals = ProductCounts()
        for product_report in self.products.values():
            totals.add(product_report.counts)
        return {
            "schema_version": SCHEMA_VERSION,
            "source": str(self.source),
            "dest": str(self.dest),
            "execute": self.execute,
            "generated_at": datetime.now(UTC).isoformat(),
            "products": {name: pr.as_dict() for name, pr in sorted(self.products.items())},
            "totals": totals.as_dict(),
            "unhandled_constructs": dict(sorted(self.unhandled_constructs.items())),
            "excluded_top_level_dirs": sorted(self.excluded_top_level_dirs),
            "warnings": self.warnings,
            "containment_violations": self.containment_violations,
        }


def _iter_files_sorted(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


def _process_one_product_tree(
    *,
    product_root: Path,
    dest_product_root: Path,
    dest_root: Path,
    execute: bool,
    counts: ProductCounts,
    unhandled_tally: Counter[str],
) -> None:
    """Streaming walk: for each file under ``product_root``, read -> (normalize) -> write.

    No bulk pre-copy or intermediate materialization occurs -- each file
    is handled individually, in one pass, whether or not ``execute`` is
    set. Only the final "write to disk" step is skipped when
    ``execute`` is ``False``.
    """
    for source_path in _iter_files_sorted(product_root):
        relative_path = source_path.relative_to(product_root)
        if _is_partial_path(relative_path):
            counts.skipped_partials += 1
            continue

        suffix = source_path.suffix.lower()
        if suffix in MDX_EXTENSIONS:
            text = source_path.read_text(encoding="utf-8")
            result = normalize.normalize_mdx_to_md(text)
            unhandled_tally.update(result.unhandled)
            counts.mdx_normalized += 1
            dest_relative = relative_path.with_suffix(".md")
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / dest_relative)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_text(result.text, encoding="utf-8")
        elif suffix in ORDINARY_MD_EXTENSIONS:
            counts.md_copied += 1
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / relative_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, dest_path)
        elif suffix in IMAGE_EXTENSIONS:
            counts.assets_copied += 1
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / relative_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, dest_path)
        else:
            counts.skipped_other += 1


def process_corpus(source: Path, dest: Path, execute: bool) -> dict[str, Any]:
    """Run the full selection + normalize-on-copy pipeline; return the JSON-able report dict.

    Shared by both dry-run and execute modes: the exact same selection
    and per-file read/normalize computation happens either way, so a
    dry-run's report is a faithful preview of what ``--execute`` would
    produce. Only the actual disk-write step is conditioned on
    ``execute``.
    """
    builder = ReportBuilder(source=source, dest=dest, execute=execute)

    top_level_dirs = sorted(p.name for p in source.iterdir() if p.is_dir())
    classification = selection.classify_products(top_level_dirs)

    for name in classification.excluded:
        builder.excluded_top_level_dirs.append(name)
        if name != "global":
            builder.warnings.append(
                f"Unrecognized top-level directory '{name}' -- not in the known "
                "product map; excluded from selection."
            )

    for product in classification.versioned:
        product_source_root = source / product
        version_dirnames = sorted(p.name for p in product_source_root.iterdir() if p.is_dir())
        selected = selection.select_latest_version(version_dirnames)
        product_report = ProductReport(versioned=True, selected_version=selected)
        builder.products[product] = product_report
        if selected is None:
            builder.warnings.append(
                f"Versioned product '{product}' has no valid version directories; skipped."
            )
            continue
        _process_one_product_tree(
            product_root=product_source_root / selected,
            dest_product_root=dest / product / selected,
            dest_root=dest,
            execute=execute,
            counts=product_report.counts,
            unhandled_tally=builder.unhandled_constructs,
        )

    for product in classification.unversioned:
        product_source_root = source / product
        product_report = ProductReport(versioned=False, selected_version=None)
        builder.products[product] = product_report
        _process_one_product_tree(
            product_root=product_source_root,
            dest_product_root=dest / product,
            dest_root=dest,
            execute=execute,
            counts=product_report.counts,
            unhandled_tally=builder.unhandled_constructs,
        )

    return builder.to_dict()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashicorp_mdx_normalize.py",
        description=(
            "Selectively copy the latest version of each versioned HashiCorp "
            "product (plus all unversioned products) from a read-only "
            "unified-docs corpus, converting .mdx to .md in-flight. Dry-run "
            "(zero writes) is the default; pass --execute to write."
        ),
        epilog=(
            "Exact operator command for the real external run (never executed "
            "by an agent):\n\n"
            "  python scripts/hashicorp_mdx_normalize.py "
            '--source "C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content" '
            '--dest "C:\\Source\\Docs\\tf-unified-dev-docs-normalized" '
            "--execute "
            '--report "C:\\Source\\Docs\\tf-unified-dev-docs-normalized'
            '\\_normalize-report.json"\n\n'
            "Omit --execute to preview the identical plan with zero writes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", required=True, type=Path, help="Read-only source corpus root")
    parser.add_argument(
        "--dest", required=True, type=Path, help="Destination root for normalized output"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually write output (default: dry-run, zero writes)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to also write the JSON report (always printed to stdout)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    source: Path = args.source
    dest: Path = args.dest

    if not source.is_dir():
        print(f"error: --source is not a directory: {source}", file=sys.stderr)
        return EXIT_SOURCE_NOT_FOUND

    try:
        report = process_corpus(source=source, dest=dest, execute=args.execute)
    except ContainmentViolation as exc:
        print(f"error: containment violation: {exc}", file=sys.stderr)
        return EXIT_CONTAINMENT_VIOLATION

    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
