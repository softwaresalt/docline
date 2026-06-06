"""Load-test harness for the docline split-and-throttle pipeline.

Drives a corpus of PDFs through
:func:`docline.process.pdf_batch.process_pdf_in_chunks` with per-chunk
instrumentation, writing one TSV row per chunk for empirical baseline
measurement.

**Operator constraint** (per RCA
``docs/memory/2026-06-05/rca-2026-06-04-load-test-system-oom.md``):
this harness MUST be run from a plain PowerShell / shell session, NOT
inside an AI agent's tool calls. The Copilot CLI process co-hosted
with docling triggered the 2026-06-04 paging spiral / hard reboot.

Usage::

    python scripts/load_test.py \\
        --corpus-dir .elt/pbi \\
        --output-dir logs/load-test-output \\
        --tsv-path logs/load-test.tsv \\
        --tier all \\
        --pause-seconds 30

Tiers (file-size buckets):

* ``small`` — PDFs <= 10 MB
* ``medium`` — PDFs 10-30 MB
* ``large`` — PDFs > 30 MB (includes the 109 MB cosmos PDF)
* ``all`` — process every PDF in the corpus

TSV columns:

``timestamp file mb pages chunk_index engine exit_code elapsed_s peak_rss_mb
output_chars fallback_reason probe_available_gb probe_max_pages probe_serialize``

Each PDF gets one row per chunk, plus a synthetic ``summary`` row with
the aggregated stitched-output character count and total elapsed time.
"""

from __future__ import annotations

import argparse
import csv
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psutil

from docline.process.pdf_batch import BatchResult, process_pdf_in_chunks
from docline.runtime.resource_probe import probe

_log = logging.getLogger("docline.load_test")


_BYTES_PER_MB = 1_000_000

_TSV_FIELDS: tuple[str, ...] = (
    "timestamp",
    "file",
    "mb",
    "chunk_index",
    "engine",
    "exit_code",
    "elapsed_s",
    "peak_rss_mb",
    "output_chars",
    "fallback_reason",
    "probe_available_gb",
    "probe_max_pages",
    "probe_serialize",
)


@dataclass(frozen=True)
class TierThresholds:
    """File-size bucket boundaries for harness tiering."""

    small_max_mb: float = 10.0
    medium_max_mb: float = 30.0


def classify_tier(size_mb: float, thresholds: TierThresholds | None = None) -> str:
    """Classify a PDF by file size into ``small`` / ``medium`` / ``large``."""

    t = thresholds or TierThresholds()
    if size_mb <= t.small_max_mb:
        return "small"
    if size_mb <= t.medium_max_mb:
        return "medium"
    return "large"


def iter_corpus(
    corpus_dir: Path,
    tier_filter: str = "all",
    thresholds: TierThresholds | None = None,
) -> Iterator[tuple[Path, float]]:
    """Yield ``(pdf_path, size_mb)`` for each PDF in ``corpus_dir`` matching the tier.

    Args:
        corpus_dir: Directory containing PDFs (non-recursive).
        tier_filter: ``small`` / ``medium`` / ``large`` / ``all``.
        thresholds: Optional bucket boundary override.

    Raises:
        FileNotFoundError: If ``corpus_dir`` does not exist.
        ValueError: If ``tier_filter`` is not a recognized value.
    """

    if tier_filter not in ("small", "medium", "large", "all"):
        raise ValueError(f"Unknown tier filter: {tier_filter}")
    if not corpus_dir.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    for pdf_path in sorted(corpus_dir.glob("*.pdf")):
        size_mb = pdf_path.stat().st_size / _BYTES_PER_MB
        if tier_filter != "all" and classify_tier(size_mb, thresholds) != tier_filter:
            continue
        yield pdf_path, size_mb


def _sample_peak_rss_mb() -> float:
    """Sample the current process peak RSS in MB."""

    proc = psutil.Process()
    info = proc.memory_info()
    return info.rss / _BYTES_PER_MB


def run_one_pdf(
    pdf_path: Path,
    *,
    output_dir: Path,
) -> tuple[BatchResult, float, float]:
    """Run a single PDF through the batch processor; return result + elapsed + peak RSS."""

    start = time.monotonic()
    rss_start = _sample_peak_rss_mb()
    result = process_pdf_in_chunks(pdf_path, output_dir=output_dir / pdf_path.stem)
    elapsed = time.monotonic() - start
    rss_peak = max(_sample_peak_rss_mb(), rss_start)
    return result, elapsed, rss_peak


def write_tsv_rows(
    tsv_path: Path,
    rows: list[dict[str, object]],
    *,
    append: bool = False,
) -> None:
    """Write rows to ``tsv_path`` using the canonical field order.

    When ``append`` is True the header is omitted (assumed already
    present in the file).
    """

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and tsv_path.exists() else "w"
    write_header = not (append and tsv_path.exists())
    with tsv_path.open(mode, encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=list(_TSV_FIELDS), delimiter="\t", extrasaction="ignore"
        )
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_rows_for_result(
    pdf_path: Path,
    size_mb: float,
    result: BatchResult,
    elapsed_s: float,
    peak_rss_mb: float,
    budget_snapshot: dict[str, object],
) -> list[dict[str, object]]:
    """Produce one TSV row per chunk + one summary row for ``pdf_path``."""

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rows: list[dict[str, object]] = []
    for idx, chunk in enumerate(result.chunks, start=1):
        rows.append(
            {
                "timestamp": timestamp,
                "file": pdf_path.name,
                "mb": f"{size_mb:.2f}",
                "chunk_index": idx,
                "engine": chunk.engine,
                "exit_code": chunk.exit_code,
                "elapsed_s": "",  # per-chunk elapsed is not tracked at this layer
                "peak_rss_mb": "",
                "output_chars": len(chunk.markdown),
                "fallback_reason": chunk.reason,
                "probe_available_gb": budget_snapshot.get("available_ram_gb", ""),
                "probe_max_pages": budget_snapshot.get("recommended_docling_max_pages", ""),
                "probe_serialize": budget_snapshot.get("serialize_docling", ""),
            }
        )
    # Summary row with aggregated metrics for this PDF.
    rows.append(
        {
            "timestamp": timestamp,
            "file": pdf_path.name,
            "mb": f"{size_mb:.2f}",
            "chunk_index": "summary",
            "engine": "summary",
            "exit_code": result.fallback_chunk_count,
            "elapsed_s": f"{elapsed_s:.2f}",
            "peak_rss_mb": f"{peak_rss_mb:.2f}",
            "output_chars": len(result.stitched_markdown),
            "fallback_reason": f"{result.fallback_chunk_count}/{len(result.chunks)}",
            "probe_available_gb": budget_snapshot.get("available_ram_gb", ""),
            "probe_max_pages": budget_snapshot.get("recommended_docling_max_pages", ""),
            "probe_serialize": budget_snapshot.get("serialize_docling", ""),
        }
    )
    return rows


def _budget_snapshot() -> dict[str, object]:
    b = probe()
    return {
        "available_ram_gb": f"{b.available_ram_gb:.2f}",
        "recommended_docling_max_pages": b.recommended_docling_max_pages,
        "serialize_docling": b.serialize_docling,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python scripts/load_test.py``.

    Returns:
        Process exit code (0 on success, 1 on configuration failure).
    """

    parser = argparse.ArgumentParser(
        description=(
            "Drive a PDF corpus through the docline split-and-throttle "
            "pipeline and emit per-chunk TSV measurements."
        ),
    )
    parser.add_argument("--corpus-dir", type=Path, required=True, help="Directory of input PDFs")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where chunk outputs land")
    parser.add_argument("--tsv-path", type=Path, required=True, help="TSV output file path")
    parser.add_argument(
        "--tier",
        choices=("small", "medium", "large", "all"),
        default="all",
        help="File-size tier to process",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=30.0,
        help="Seconds to wait between PDFs so the OS can reclaim memory",
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    parsed = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, parsed.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        sources = list(iter_corpus(parsed.corpus_dir, tier_filter=parsed.tier))
    except (FileNotFoundError, ValueError) as err:
        _log.error("Corpus configuration error: %s", err)
        return 1

    if not sources:
        _log.warning("No PDFs matched tier %s in %s", parsed.tier, parsed.corpus_dir)
        return 0

    budget_snapshot = _budget_snapshot()
    _log.info("Probe snapshot: %s", budget_snapshot)
    _log.info("Processing %d PDFs in tier %s", len(sources), parsed.tier)

    # Truncate / create the TSV with header before the first PDF row.
    write_tsv_rows(parsed.tsv_path, rows=[], append=False)

    for idx, (pdf_path, size_mb) in enumerate(sources, start=1):
        _log.info(
            "[%d/%d] %s (%.2f MB, tier=%s)",
            idx,
            len(sources),
            pdf_path.name,
            size_mb,
            classify_tier(size_mb),
        )
        try:
            result, elapsed, peak_rss = run_one_pdf(pdf_path, output_dir=parsed.output_dir)
        except Exception as err:  # noqa: BLE001 — keep the corpus run alive
            _log.error("Failed to process %s: %s", pdf_path.name, err)
            continue

        rows = build_rows_for_result(pdf_path, size_mb, result, elapsed, peak_rss, budget_snapshot)
        write_tsv_rows(parsed.tsv_path, rows, append=True)

        if idx < len(sources) and parsed.pause_seconds > 0:
            _log.info("Sleeping %.0fs before next PDF...", parsed.pause_seconds)
            time.sleep(parsed.pause_seconds)

    _log.info("Done. TSV written to %s", parsed.tsv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
