# ruff: noqa: E501
"""Stage the full Power BI source-MD corpus (or a stratified sample) into the
docline staging layout for end-to-end ``docline process`` evaluation.

Companion to ``stage_powerbi_test.py``. The test variant uses 10 hand-picked
files for fast smoke testing. This variant scales to the full corpus
(~1,300+ .md files) or a configurable sample size so we can characterize
docline's source-MD pathway end-to-end against a production-grade corpus.

Usage::

    python scripts/study/stage_powerbi_full.py --all
    python scripts/study/stage_powerbi_full.py --sample 200
    POWERBI_DOCS_ROOT="E:\\Source\\powerbi-docs\\powerbi-docs" python scripts/study/stage_powerbi_full.py --all

Output layout matches what ``docline process`` consumes::

    .elt/staging-powerbi-full/<hash[:2]>/<hash>/metadata.json
    .elt/staging-powerbi-full/<hash[:2]>/<hash>/crawl-manifest.json
    .elt/staging-powerbi-full/<hash[:2]>/<hash>/files/<relative-path>.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _SCRIPT_DIR.parent.parent
DOCLINE_ROOT = (
    _REPO_ROOT_CANDIDATE if (_REPO_ROOT_CANDIDATE / "pyproject.toml").exists() else Path.cwd()
)

_DEFAULT_POWERBI_ROOT = r"E:\Source\powerbi-docs\powerbi-docs"
POWERBI_ROOT = Path(os.environ.get("POWERBI_DOCS_ROOT", _DEFAULT_POWERBI_ROOT))
STAGING_ROOT = DOCLINE_ROOT / ".elt" / "staging-powerbi-full"
OUTPUT_ROOT = DOCLINE_ROOT / ".elt" / "output" / "powerbi-full"

# Skip patterns: docline.process does not yet handle YAML TOCs (.yml files
# aren't matched by rglob("*.md") anyway, but listing them here documents the
# intent so future maintainers extending discover_md_files to also walk *.yml
# know to keep skipping them); README/LICENSE/CHANGELOG (repo metadata, not
# product docs).
_SKIP_NAMES = {"README.md", "LICENSE.md", "CHANGELOG.md"}


def discover_md_files(root: Path) -> list[Path]:
    """Walk ``root`` for all .md files we want to stage."""
    out: list[Path] = []
    for p in root.rglob("*.md"):
        if p.name in _SKIP_NAMES:
            continue
        out.append(p)
    return sorted(out)


def stratified_sample(files: list[Path], root: Path, target_total: int) -> list[Path]:
    """Pick approximately ``target_total`` files distributed across top-level subdirs.

    Each top-level subdir of ``root`` gets a proportional share of the sample.
    Stable across runs via fixed seed so re-runs hit the same set.
    """
    rng = random.Random(20260609)
    by_area: dict[str, list[Path]] = {}
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        area = rel.parts[0] if len(rel.parts) > 1 else "_top"
        by_area.setdefault(area, []).append(f)

    total_available = sum(len(v) for v in by_area.values())
    picked: list[Path] = []
    for area, area_files in by_area.items():
        # Proportional share, round up so small areas still get at least 1.
        share = max(1, round(target_total * len(area_files) / total_available))
        share = min(share, len(area_files))
        picked.extend(rng.sample(area_files, share))
    rng.shuffle(picked)
    return picked[:target_total]


def stage(files: list[Path], source_id: str) -> Path:
    """Create the docline staging structure for ``files``."""
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    STAGING_ROOT.mkdir(parents=True)

    job_id = hashlib.sha256(source_id.encode()).hexdigest()[:16]
    job_dir = STAGING_ROOT / job_id[:2] / job_id
    files_dir = job_dir / "files"
    files_dir.mkdir(parents=True)

    crawl_entries: list[dict] = []
    for order, src in enumerate(files):
        try:
            rel = src.relative_to(POWERBI_ROOT)
        except ValueError:
            continue
        dst = files_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as err:
            print(f"WARN: skip {rel}: {err}", file=sys.stderr)
            continue
        crawl_entries.append(
            {
                "url": f"file://{src.as_posix()}",
                "path": rel.as_posix(),
                "order": order,
                "depth": 0,
                "http_status": 200,
                "content_type": "text/markdown",
            }
        )

    metadata = {
        "job_id": job_id,
        "metadata": {
            "source": f"local:powerbi-docs:full:{source_id}",
            "fetch_timestamp": datetime.now(UTC).isoformat(),
            "http_status": None,
            "content_type": "text/markdown",
        },
        "cache_path": str(job_dir.relative_to(DOCLINE_ROOT).as_posix()),
        "complete": True,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    crawl_manifest = {
        "job_id": job_id,
        # docline app._load_crawl_manifest expects the key ``pages``; ``entries`` is
        # silently ignored (the loader logs a warning and falls back to directory walk).
        "pages": crawl_entries,
    }
    (job_dir / "crawl-manifest.json").write_text(
        json.dumps(crawl_manifest, indent=2), encoding="utf-8"
    )
    return job_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Stage every .md file in the corpus")
    group.add_argument("--sample", type=int, metavar="N", help="Stratified sample of N files")
    args = parser.parse_args()

    if not POWERBI_ROOT.exists():
        print(f"ERROR: POWERBI_ROOT does not exist: {POWERBI_ROOT}", file=sys.stderr)
        return 1

    print(f"Scanning {POWERBI_ROOT} ...")
    all_files = discover_md_files(POWERBI_ROOT)
    print(f"Discovered {len(all_files):,} .md files")

    if args.all:
        picked = all_files
        source_id = f"all-{len(all_files)}"
    else:
        picked = stratified_sample(all_files, POWERBI_ROOT, args.sample)
        source_id = f"sample-{len(picked)}"

    print(f"Staging {len(picked):,} files ({source_id})")
    job_dir = stage(picked, source_id)
    print(f"\nStaged at: {job_dir}")
    print("\nRun docline process with:")
    print(
        f"  .\\.venv\\Scripts\\python.exe -m docline process "
        f"--staging-dir {STAGING_ROOT.relative_to(DOCLINE_ROOT).as_posix()} "
        f"--output-dir {OUTPUT_ROOT.relative_to(DOCLINE_ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
