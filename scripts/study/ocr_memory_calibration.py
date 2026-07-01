"""Calibrate docling OCR peak memory into a portable, host-independent cost model.

The OCR OOM risk (038-F) depends on how much memory rasterizing + OCR-ing a page
bitmap needs versus how much memory the *host* has. Peak memory for a given
bitmap is largely hardware-independent (same computation, same working set), so
this harness measures that per-bitmap cost once and fits a portable model::

    peak_mb ~= base_mb + k_mb_per_mpx * (page_megapixels * scale^2 * pages_per_group)

``docline`` then computes, at runtime on ANY host, the OCR pages-per-group cap and
the render scale that keep peak memory within a safe fraction of *that host's*
available memory (the follow-up runtime algorithm, stash 699FB5DC). A 128 GB box
caps higher than an 8 GB box from the same coefficients.

Two modes:

* ``--run`` (operator, needs docling + psutil): sweep render scale x pages-per-group
  over representative input PDFs, spawn the docling worker, sample peak child RSS,
  and write a measurements TSV.
* ``--analyze`` (anywhere, no docling): fit the cost model from a measurements TSV
  and print the fitted coefficients + a per-host recommendation.

The ``--analyze`` path and all the fit/recommendation logic are pure and unit
tested; the ``--run`` measurement path is guarded behind availability checks.

Usage::

    # Operator, on a docling host:
    python scripts/study/ocr_memory_calibration.py --run \\
        --input normal.pdf scan.pdf poster.pdf \\
        --scales 2.0 1.0 0.5 0.25 --group-sizes 1 2 4 8 16 \\
        --out-tsv .elt/output/ocr-mem/measurements.tsv

    # Anywhere, to fit + recommend for a host with 16 GB free:
    python scripts/study/ocr_memory_calibration.py --analyze \\
        .elt/output/ocr-mem/measurements.tsv \\
        --available-mb 16000 --page-megapixels 8.0

Exit codes: ``0`` success; ``2`` bad arguments / unreadable input; ``3`` the
``--run`` measurement path is unavailable (docling/psutil not installed).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_TSV_HEADER = "page_class\tpage_megapixels\tscale\tpages_per_group\tpeak_rss_mb\toutcome"

# Default render scales / group sizes for the operator sweep. These are SWEEP
# INPUTS (what to measure), not calibrated limits — the limits come out of the fit.
_DEFAULT_SCALES: tuple[float, ...] = (2.0, 1.0, 0.5, 0.25)
_DEFAULT_GROUP_SIZES: tuple[int, ...] = (1, 2, 4, 8, 16)
# Base DPI mapping scale 1.0 -> pixels; only a normalization constant folded into
# the fitted k coefficient, so its exact value does not affect the recommendation.
_BASE_DPI = 72.0


@dataclass(frozen=True)
class Measurement:
    """One measured (or attempted) docling OCR run."""

    page_class: str
    page_megapixels: float
    scale: float
    pages_per_group: int
    peak_rss_mb: float
    outcome: str  # "ok" | "oom"


@dataclass(frozen=True)
class CostModel:
    """Portable, host-independent OCR peak-memory model.

    ``peak_mb ~= base_mb + k_mb_per_mpx * (page_megapixels * scale^2 * pages_per_group)``.
    """

    base_mb: float
    k_mb_per_mpx: float

    def predict(self, *, page_megapixels: float, scale: float, pages_per_group: int) -> float:
        """Predicted peak RSS (MB) for the given bitmap workload."""
        return self.base_mb + self.k_mb_per_mpx * page_megapixels * scale * scale * pages_per_group


def _load_factor(m: Measurement) -> float:
    """The single explanatory variable ``mpx * scale^2 * pages`` for the fit."""
    return m.page_megapixels * m.scale * m.scale * m.pages_per_group


def fit_cost_model(rows: Sequence[Measurement]) -> CostModel:
    """Least-squares fit of ``peak_mb = base + k * load_factor`` over OK rows.

    Args:
        rows: Measurements; only ``outcome == "ok"`` rows carry a valid peak and
            are used for the fit.

    Returns:
        The fitted :class:`CostModel`.

    Raises:
        ValueError: If fewer than two OK rows exist, or all rows share one load
            factor (degenerate — slope undefined).
    """
    ok = [m for m in rows if m.outcome == "ok"]
    if len(ok) < 2:
        raise ValueError(f"need >= 2 OK measurements to fit, got {len(ok)}")

    n = float(len(ok))
    xs = [_load_factor(m) for m in ok]
    ys = [m.peak_rss_mb for m in ok]
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        raise ValueError("degenerate fit: all measurements share one load factor")
    k = (n * sxy - sx * sy) / denom
    base = (sy - k * sx) / n
    return CostModel(base_mb=base, k_mb_per_mpx=k)


def recommend_max_pages(
    model: CostModel,
    *,
    available_mb: float,
    safe_fraction: float,
    page_megapixels: float,
    scale: float,
) -> int:
    """Max OCR pages-per-group that fit within ``safe_fraction`` of available memory.

    Uses the fixed ``base_mb`` overhead plus the marginal per-page cost at the
    given page size and scale. Never returns below 1 (a single page is always
    attempted, then downscaled via the scale schedule if it still does not fit).
    """
    budget = available_mb * safe_fraction
    marginal = model.k_mb_per_mpx * page_megapixels * scale * scale
    if marginal <= 0:
        return 1
    usable = budget - model.base_mb
    if usable <= 0:
        return 1
    return max(1, int(usable // marginal))


def recommend_scale_schedule(
    model: CostModel,
    *,
    available_mb: float,
    safe_fraction: float,
    page_megapixels: float,
    candidate_scales: Sequence[float],
) -> tuple[float, ...]:
    """Candidate render scales (descending) at which a SINGLE page fits the budget.

    The first entry is the highest-resolution scale that still fits; the
    downscale-retry path walks this schedule before conceding to heuristic.
    """
    budget = available_mb * safe_fraction
    fitting = [
        s
        for s in sorted(candidate_scales, reverse=True)
        if model.predict(page_megapixels=page_megapixels, scale=s, pages_per_group=1) <= budget
    ]
    return tuple(fitting)


def write_measurements_tsv(rows: Sequence[Measurement], path: Path) -> None:
    """Write measurements to a tab-separated file with a header row."""
    lines = [_TSV_HEADER]
    for m in rows:
        lines.append(
            f"{m.page_class}\t{m.page_megapixels!r}\t{m.scale!r}\t"
            f"{m.pages_per_group}\t{m.peak_rss_mb!r}\t{m.outcome}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_measurements_tsv(text: str) -> list[Measurement]:
    """Parse a measurements TSV (produced by :func:`write_measurements_tsv`)."""
    rows: list[Measurement] = []
    for line in text.splitlines():
        line = line.rstrip("\n")
        if not line or line.startswith("page_class\t"):
            continue
        parts = line.split("\t")
        if len(parts) != 6:
            raise ValueError(f"malformed measurements row: {line!r}")
        rows.append(
            Measurement(
                page_class=parts[0],
                page_megapixels=float(parts[1]),
                scale=float(parts[2]),
                pages_per_group=int(parts[3]),
                peak_rss_mb=float(parts[4]),
                outcome=parts[5],
            )
        )
    return rows


def _measurement_available() -> tuple[bool, str]:
    """Whether the ``--run`` measurement path can execute on this host."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        return False, "psutil not installed"
    try:
        from docline.dependencies import pdf_available
    except ImportError:
        return False, "docline.dependencies not importable"
    if not pdf_available():
        return False, "docling extras not installed (docline[pdf])"
    return True, ""


def _analyze(args: argparse.Namespace) -> int:
    tsv_path: Path = args.analyze
    try:
        text = tsv_path.read_text(encoding="utf-8")
    except OSError as err:
        print(f"ERROR: could not read {tsv_path}: {err}")
        return 2
    try:
        rows = parse_measurements_tsv(text)
        model = fit_cost_model(rows)
    except ValueError as err:
        print(f"ERROR: {err}")
        return 2

    cap = recommend_max_pages(
        model,
        available_mb=args.available_mb,
        safe_fraction=args.safe_fraction,
        page_megapixels=args.page_megapixels,
        scale=args.reference_scale,
    )
    schedule = recommend_scale_schedule(
        model,
        available_mb=args.available_mb,
        safe_fraction=args.safe_fraction,
        page_megapixels=args.page_megapixels,
        candidate_scales=args.scales,
    )
    print("OCR memory cost model (portable, host-independent):")
    print(f"  base_mb        = {model.base_mb:.2f}")
    print(f"  k_mb_per_mpx   = {model.k_mb_per_mpx:.4f}  (per megapixel * scale^2 * page)")
    print()
    print(
        f"Recommendation for available_mb={args.available_mb:.0f} "
        f"(safe_fraction={args.safe_fraction}, page_megapixels={args.page_megapixels}):"
    )
    print(f"  budget_mb            = {args.available_mb * args.safe_fraction:.0f}")
    print(f"  max_pages_per_group  = {cap}")
    print(f"  scale_schedule       = {schedule if schedule else '(none fit; heuristic fallback)'}")
    return 0


def _run(args: argparse.Namespace) -> int:
    available, reason = _measurement_available()
    if not available:
        print(f"ERROR: --run measurement path unavailable: {reason}")
        return 3

    import subprocess
    import time

    import psutil
    import pypdf

    def page_megapixels(pdf: Path) -> float:
        reader = pypdf.PdfReader(str(pdf), strict=False)
        box = reader.pages[0].mediabox
        w_in = float(box.width) / 72.0
        h_in = float(box.height) / 72.0
        return (w_in * _BASE_DPI) * (h_in * _BASE_DPI) / 1_000_000.0

    def build_group_pdf(src: Path, pages: int, dest: Path) -> None:
        reader = pypdf.PdfReader(str(src), strict=False)
        writer = pypdf.PdfWriter()
        for i in range(pages):
            writer.add_page(reader.pages[i % len(reader.pages)])
        with dest.open("wb") as fh:
            writer.write(fh)

    def measure(cmd: list[str]) -> tuple[int, float]:
        # NOTE: peak RSS is sampled (every 50 ms), so for OK runs it is a lower
        # bound on true peak, and a crash between samples may under-report the
        # peak that triggered it. The fit uses only OK rows, so this biases the
        # cost model conservatively (slightly under-predicts) rather than unsafely.
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        peak = 0.0
        ps = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                peak = max(peak, ps.memory_info().rss / 1_000_000.0)
            except psutil.Error:
                break
            time.sleep(0.05)
        return proc.returncode or 0, peak

    out_tsv: Path = args.out_tsv
    work = out_tsv.parent / "_ocr_calib_work"
    work.mkdir(parents=True, exist_ok=True)
    rows: list[Measurement] = []
    for src in args.input:
        page_class = src.stem
        mpx = page_megapixels(src)
        for pages in args.group_sizes:
            group_pdf = work / f"{page_class}-g{pages}.pdf"
            build_group_pdf(src, pages, group_pdf)
            for scale in args.scales:
                out_md = work / f"{page_class}-g{pages}-s{scale}.json"
                cmd = [
                    sys.executable,
                    "-m",
                    "docline._tools.docling_worker",
                    str(group_pdf),
                    str(out_md),
                    f"--ocr-scale={scale}",
                ]
                rc, peak = measure(cmd)
                # "oom" here means "did not produce a valid envelope" — it
                # conflates a true OOM with any other worker failure (e.g. a
                # docling runtime error). The operator should sanity-check the
                # worker stderr for a run before treating a failure as the
                # memory ceiling at that (scale, pages) point.
                outcome = "ok" if rc == 0 and out_md.exists() else "oom"
                rows.append(Measurement(page_class, mpx, scale, pages, peak, outcome))
                print(
                    f"{page_class}\tmpx={mpx:.2f}\tscale={scale}\tpages={pages}\t"
                    f"peak={peak:.0f}MB\t{outcome}"
                )

    write_measurements_tsv(rows, out_tsv)
    print(f"\nWrote {len(rows)} measurements to {out_tsv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python scripts/study/ocr_memory_calibration.py``."""
    parser = argparse.ArgumentParser(description="Calibrate docling OCR peak memory.")
    parser.add_argument("--analyze", type=Path, help="Fit + recommend from a measurements TSV.")
    parser.add_argument("--run", action="store_true", help="Run the measurement sweep (operator).")
    parser.add_argument("--input", type=Path, nargs="+", help="[--run] representative input PDFs.")
    parser.add_argument("--out-tsv", type=Path, help="[--run] measurements TSV output path.")
    parser.add_argument(
        "--scales",
        type=float,
        nargs="+",
        default=list(_DEFAULT_SCALES),
        help="Render scales to sweep / consider for the scale schedule.",
    )
    parser.add_argument(
        "--group-sizes",
        type=int,
        nargs="+",
        default=list(_DEFAULT_GROUP_SIZES),
        help="[--run] pages-per-group values to sweep.",
    )
    parser.add_argument(
        "--available-mb",
        type=float,
        default=0.0,
        help="[--analyze] host available memory (MB) for the recommendation.",
    )
    parser.add_argument(
        "--safe-fraction",
        type=float,
        default=0.6,
        help="[--analyze] fraction of available memory to stay within.",
    )
    parser.add_argument(
        "--page-megapixels",
        type=float,
        default=8.0,
        help="[--analyze] reference page size for the recommendation.",
    )
    parser.add_argument(
        "--reference-scale",
        type=float,
        default=1.0,
        help="[--analyze] render scale for the pages-per-group recommendation.",
    )
    args = parser.parse_args(argv)

    if args.analyze is not None:
        return _analyze(args)
    if args.run:
        if not args.input or not args.out_tsv:
            print("ERROR: --run requires --input and --out-tsv")
            return 2
        return _run(args)
    print("ERROR: specify --analyze TSV or --run --input ... --out-tsv ...")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
