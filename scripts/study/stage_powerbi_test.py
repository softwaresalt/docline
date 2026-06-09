# ruff: noqa: E501
"""Spike: stage a stratified sample of Power BI source MD files into the
docline staging format and run ``docline process`` against them.

Tests whether docline's existing local-file processing path handles
production Microsoft Learn source MD cleanly, characterizing what
works today vs what 023-F (source-MD ingestion pathway) would add.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

# Resolve docline repo root from this script's location so the script is
# portable across machines / clones. Falls back to cwd if the relative
# resolution fails (e.g., script copied out of tree).
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _SCRIPT_DIR.parent.parent
DOCLINE_ROOT = (
    _REPO_ROOT_CANDIDATE if (_REPO_ROOT_CANDIDATE / "pyproject.toml").exists() else Path.cwd()
)

# Default corpus path matches the operator's local Power BI docs checkout.
# Override via POWERBI_DOCS_ROOT environment variable for portability.
_DEFAULT_POWERBI_ROOT = r"E:\Source\powerbi-docs\powerbi-docs"
POWERBI_ROOT = Path(os.environ.get("POWERBI_DOCS_ROOT", _DEFAULT_POWERBI_ROOT))
STAGING_ROOT = DOCLINE_ROOT / ".elt" / "staging-powerbi-test"
OUTPUT_ROOT = DOCLINE_ROOT / ".elt" / "output" / "powerbi-test"

# Stratified sample: pick 1 representative file per major subdir.
SAMPLE_PATHS = [
    "fundamentals/desktop-diagnostics.md",
    "guidance/report-design-tips.md",  # large guidance doc
    "create-reports/desktop-getting-started.md",
    "connect-data/desktop-connect-to-data.md",
    "transform-model/desktop-relationship-view.md",
    "visuals/power-bi-visualization-types-for-reports-and-q-and-a.md",
    "collaborate-share/service-share-reports.md",
    "developer/visuals/develop-power-bi-visuals.md",
    "paginated-reports/paginated-reports-quickstart-aw.md",
    "explore-reports/end-user-reading-view.md",
]


def pick_existing_samples() -> list[Path]:
    """Return up to 10 existing file paths from SAMPLE_PATHS, with fallbacks."""
    picked: list[Path] = []
    for rel in SAMPLE_PATHS:
        p = POWERBI_ROOT / rel
        if p.exists():
            picked.append(p)
    # If anything missing, top up with first 10 files from each subdir
    if len(picked) < 10:
        seen = {p.resolve() for p in picked}
        for subdir in [
            "fundamentals",
            "guidance",
            "create-reports",
            "connect-data",
            "transform-model",
            "visuals",
            "collaborate-share",
            "developer",
            "paginated-reports",
            "explore-reports",
        ]:
            sub = POWERBI_ROOT / subdir
            if not sub.exists():
                continue
            for f in sub.rglob("*.md"):
                if len(picked) >= 10:
                    return picked
                if f.resolve() in seen or f.name == "TOC.yml":
                    continue
                if 5000 < f.stat().st_size < 30000:  # mid-sized
                    picked.append(f)
                    seen.add(f.resolve())
    return picked


def stage(files: list[Path]) -> Path:
    """Create the docline staging structure for the picked files."""
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    STAGING_ROOT.mkdir(parents=True)

    source_id = "powerbi-test-corpus"
    job_id = hashlib.sha256(source_id.encode()).hexdigest()[:16]
    job_dir = STAGING_ROOT / job_id[:2] / job_id
    files_dir = job_dir / "files"
    files_dir.mkdir(parents=True)

    crawl_entries: list[dict] = []
    for order, src in enumerate(files):
        rel = src.relative_to(POWERBI_ROOT)
        dst = files_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
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
            "source": f"local:powerbi-docs:test:{source_id}",
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
        "entries": crawl_entries,
    }
    (job_dir / "crawl-manifest.json").write_text(
        json.dumps(crawl_manifest, indent=2), encoding="utf-8"
    )

    return job_dir


def main() -> int:
    files = pick_existing_samples()
    if not files:
        print("ERROR: no sample files found")
        return 1

    print(f"Picked {len(files)} sample files:")
    for f in files:
        rel = f.relative_to(POWERBI_ROOT)
        print(f"  - {rel} ({f.stat().st_size:,} bytes)")

    job_dir = stage(files)
    print(f"\nStaged at: {job_dir}")
    print("\nNext step: run docline process pointing at the staging dir.")
    print(
        f"  .\\.venv\\Scripts\\python.exe -m docline process "
        f"--staging-dir {STAGING_ROOT.relative_to(DOCLINE_ROOT).as_posix()} "
        f"--output-dir {OUTPUT_ROOT.relative_to(DOCLINE_ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
