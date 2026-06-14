"""PDF batch processor — split, run docling in subprocesses, stitch outputs.

This module is the production entry point for any PDF that exceeds the
:func:`docline.runtime.resource_probe.probe` size budget. It implements
RCA remediations 3 and 6 from the 2026-06-04 load-test post-mortem:

* **Split first**: invoke :func:`docline.readers.pdf_splitter.split_pdf`
  to chunk the input below the probe's per-call page budget. Avoids
  ever handing docling a workload it cannot safely complete.
* **Subprocess per chunk**: invoke
  ``python -m docline._tools.docling_worker`` for each chunk so a
  c10::Error / SIGABRT inside docling is contained to that one chunk —
  the OS reaps the child and the parent records exit code without
  inheriting torch's broken allocator state.
* **Adaptive throttling**: when ``probe.serialize_docling`` is True,
  insert a small reclaim pause between sequential chunks so the OS
  can release torch tensor pages. When False, chunks still process
  sequentially in this shipment (true parallel chunk execution via
  ProcessPoolExecutor is deferred to a follow-on shipment after the
  load-test harness produces baseline measurements).
* **Per-chunk fallback**: a chunk whose subprocess exits non-zero falls
  back to the in-process heuristic engine for that chunk only. The
  rest of the batch keeps running. This is the inverse of the
  2026-06-04 failure where one bad PDF aborted the entire run.
* **Stitching**: per-chunk markdown is concatenated in chunk order
  with overlap-aware H1 deduplication. When two adjacent chunks
  produce the same H1 (because of ``page_overlap`` in the splitter),
  the later occurrence is dropped so the first chunk's frontmatter
  semantics win.

The single public entry point is :func:`process_pdf_in_chunks`.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from docline.readers.pdf import read_pdf_pages
from docline.readers.pdf_splitter import split_pdf
from docline.runtime.resource_probe import ResourceBudget
from docline.runtime.resource_probe import probe as default_probe

_log = logging.getLogger(__name__)


_RECLAIM_PAUSE_SECONDS = 10.0  # Time to wait between serial docling chunks.
_H1_PATTERN = re.compile(r"^# (?P<title>.+)$", re.MULTILINE)

# Type alias for the subprocess runner. Tests substitute a deterministic
# callable; production uses ``_default_runner`` which delegates to
# :func:`subprocess.run`.
ChunkRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class ChunkResult:
    """Outcome for a single chunk in :class:`BatchResult`."""

    chunk_path: Path
    engine: str  # "docling" or "heuristic"
    exit_code: int  # subprocess exit code (0 = success); 0 for heuristic path
    markdown: str
    reason: str  # "ok", "subprocess_failed", "heuristic_fallback"
    chunk_pages: tuple[str, ...] = ()
    """Per-page markdown from the docling worker envelope (030-F T2).

    Populated only when the chunk was processed by docling AND the
    worker output parsed as a valid envelope. Empty for heuristic
    fallback chunks. A single-element tuple containing the raw body
    is used when the worker output failed to parse as envelope JSON
    (defensive fallback for partial T1 rollouts).
    """


@dataclass(frozen=True)
class BatchResult:
    """Aggregated outcome of :func:`process_pdf_in_chunks`."""

    source: Path
    chunks: tuple[ChunkResult, ...]
    stitched_markdown: str
    fallback_chunk_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


def process_pdf_in_chunks(
    path: Path,
    *,
    output_dir: Path,
    budget: ResourceBudget | None = None,
    runner: ChunkRunner | None = None,
    reclaim_pause_seconds: float = _RECLAIM_PAUSE_SECONDS,
    use_batched_worker: bool = True,
) -> BatchResult:
    """Process a (possibly oversized) PDF via split + subprocess + stitch.

    Args:
        path: Source PDF.
        output_dir: Where per-chunk markdown outputs and the final
            stitched output go.
        budget: Resource budget snapshot. Defaults to a fresh
            :func:`docline.runtime.resource_probe.probe` call.
        runner: Callable with the signature
            ``runner(args: list[str]) -> CompletedProcess``. Defaults to
            :func:`subprocess.run` with capture_output and text=True.
            Allows tests to substitute a deterministic stand-in for
            the real docling subprocess.
        reclaim_pause_seconds: When ``budget.serialize_docling`` is
            True, sleep this many seconds between docling subprocess
            invocations so the OS can release torch tensor pages.
            Ignored when batched worker mode is active.
        use_batched_worker: When True (default) AND N>=2 chunks AND
            ``budget.serialize_docling`` is False, invoke the docling
            worker once in ``--batch`` mode with a manifest of all
            chunks. This amortizes the ~5-10s docling model-load cost
            across N chunks (030-F T3). Set to False to force the
            legacy per-chunk subprocess loop.

    Returns:
        :class:`BatchResult` with one :class:`ChunkResult` per chunk
        plus the stitched markdown body.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if budget is None:
        budget = default_probe()
    if runner is None:
        runner = _default_runner

    # If the budget says docling is not safe on this host at all, the
    # entire PDF goes through the heuristic engine in-process.
    if budget.recommended_docling_max_pages <= 0:
        markdown = "\n\n".join(read_pdf_pages(path, layout_engine="heuristic"))
        chunk_result = ChunkResult(
            chunk_path=path,
            engine="heuristic",
            exit_code=0,
            markdown=markdown,
            reason="heuristic_fallback",
        )
        return BatchResult(
            source=path,
            chunks=(chunk_result,),
            stitched_markdown=markdown,
            fallback_chunk_count=1,
            metadata={"split_chunks": 0},
        )

    chunks = split_pdf(
        path,
        max_pages=budget.recommended_docling_max_pages,
        cache_dir=output_dir / "chunks",
    )
    if not chunks:
        return BatchResult(
            source=path,
            chunks=(),
            stitched_markdown="",
            fallback_chunk_count=0,
            metadata={"split_chunks": 0},
        )

    chunk_outputs: list[Path] = [
        output_dir / f"chunk-{index + 1:04d}.md" for index in range(len(chunks))
    ]

    use_batched = use_batched_worker and len(chunks) >= 2 and not budget.serialize_docling

    if use_batched:
        chunk_results = _run_chunks_batched(chunks, chunk_outputs, runner, output_dir)
    else:
        chunk_results = []
        for index, (chunk_path, chunk_out) in enumerate(zip(chunks, chunk_outputs)):
            result = _process_one_chunk(chunk_path, chunk_out, runner)
            chunk_results.append(result)
            if budget.serialize_docling and index < len(chunks) - 1 and reclaim_pause_seconds > 0:
                time.sleep(reclaim_pause_seconds)

    stitched = _stitch_chunk_markdown([cr.markdown for cr in chunk_results])
    fallback_count = sum(1 for cr in chunk_results if cr.reason != "ok")

    return BatchResult(
        source=path,
        chunks=tuple(chunk_results),
        stitched_markdown=stitched,
        fallback_chunk_count=fallback_count,
        metadata={"split_chunks": len(chunks), "batched_worker": use_batched},
    )


def _run_chunks_batched(
    chunks: list[Path],
    chunk_outputs: list[Path],
    runner: ChunkRunner,
    output_dir: Path,
) -> list[ChunkResult]:
    """Run all chunks in a single batched-mode worker subprocess.

    Builds a manifest file under ``output_dir / "_batch_manifest.json"``,
    invokes ``docling._tools.docling_worker --batch MANIFEST``, then
    inspects each chunk's output to build a :class:`ChunkResult`.

    Per-chunk error envelopes (worker wrote ``{"error": "..."}``) are
    handled the same way subprocess-level failures are in single-chunk
    mode: that chunk falls back to the in-process heuristic engine.

    If the batched subprocess itself fails (non-zero exit), every chunk
    falls back to heuristic. The reason field reflects the actual cause.
    """

    manifest_path = output_dir / "_batch_manifest.json"
    manifest_payload = {
        "chunks": [
            {"input": str(inp), "output": str(out)} for inp, out in zip(chunks, chunk_outputs)
        ]
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "docline._tools.docling_worker",
        "--batch",
        str(manifest_path),
    ]
    completed = runner(cmd)

    batch_subprocess_failed = completed.returncode != 0
    if batch_subprocess_failed:
        _log.warning(
            "Batched docling worker failed (exit=%s); falling back to heuristic for all %d chunks",
            completed.returncode,
            len(chunks),
        )

    chunk_results: list[ChunkResult] = []
    for chunk_path, chunk_out in zip(chunks, chunk_outputs):
        if (not batch_subprocess_failed) and chunk_out.exists():
            raw = chunk_out.read_text(encoding="utf-8")
            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                envelope = None
            chunk_failed = envelope is None or not isinstance(envelope, dict) or "error" in envelope
        else:
            chunk_failed = True

        if not chunk_failed and chunk_out.exists():
            raw = chunk_out.read_text(encoding="utf-8")
            markdown, chunk_pages = _parse_worker_envelope(raw)
            chunk_results.append(
                ChunkResult(
                    chunk_path=chunk_path,
                    engine="docling",
                    exit_code=0,
                    markdown=markdown,
                    reason="ok",
                    chunk_pages=chunk_pages,
                )
            )
            continue

        # Per-chunk fallback to heuristic.
        try:
            heuristic_pages = read_pdf_pages(chunk_path, layout_engine="heuristic")
            heuristic_md = "\n\n".join(heuristic_pages)
        except Exception as err:  # noqa: BLE001 — keep the batch alive
            _log.warning("Heuristic fallback also failed for %s: %s", chunk_path, err)
            heuristic_md = ""
        chunk_results.append(
            ChunkResult(
                chunk_path=chunk_path,
                engine="heuristic",
                exit_code=completed.returncode if batch_subprocess_failed else 0,
                markdown=heuristic_md,
                reason="subprocess_failed",
            )
        )

    return chunk_results


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner — captures stderr so diagnostics survive."""

    return subprocess.run(args, capture_output=True, text=True, check=False)


def _parse_worker_envelope(raw: str) -> tuple[str, tuple[str, ...]]:
    """Parse the docling_worker output envelope.

    Args:
        raw: Raw file body from the worker output path.

    Returns:
        ``(text, chunk_pages)`` where ``text`` is the joined markdown for
        stitching consumers and ``chunk_pages`` is the per-page tuple.

    Falls back to ``(raw, (raw,))`` if the body is not a valid envelope
    (defensive fallback for partial T1 rollouts or downgrade scenarios).
    """

    try:
        envelope = json.loads(raw)
        if (
            isinstance(envelope, dict)
            and "pages" in envelope
            and "text" in envelope
            and isinstance(envelope["pages"], list)
        ):
            pages = envelope["pages"]
            text = envelope["text"]
            if isinstance(text, str) and all(isinstance(p, str) for p in pages):
                return text, tuple(pages)
    except (json.JSONDecodeError, ValueError):
        pass
    # Defensive fallback: legacy flat body becomes a single-page payload.
    return raw, (raw,)


def _process_one_chunk(
    chunk_path: Path,
    output_path: Path,
    runner: ChunkRunner,
) -> ChunkResult:
    """Run docling on a single chunk via the worker subprocess.

    Falls back to the in-process heuristic engine on any non-zero exit.
    """

    cmd = [sys.executable, "-m", "docline._tools.docling_worker", str(chunk_path), str(output_path)]
    completed = runner(cmd)
    if completed.returncode == 0 and output_path.exists():
        raw = output_path.read_text(encoding="utf-8")
        markdown, chunk_pages = _parse_worker_envelope(raw)
        return ChunkResult(
            chunk_path=chunk_path,
            engine="docling",
            exit_code=0,
            markdown=markdown,
            reason="ok",
            chunk_pages=chunk_pages,
        )

    # Subprocess failed — fall back to the heuristic engine for this chunk only.
    _log.warning(
        "Docling worker failed for chunk %s (exit=%s); falling back to heuristic",
        chunk_path,
        completed.returncode,
    )
    try:
        pages = read_pdf_pages(chunk_path, layout_engine="heuristic")
        markdown = "\n\n".join(pages)
    except Exception as err:  # noqa: BLE001 — keep the batch alive
        _log.warning("Heuristic fallback also failed for %s: %s", chunk_path, err)
        markdown = ""
    return ChunkResult(
        chunk_path=chunk_path,
        engine="heuristic",
        exit_code=completed.returncode,
        markdown=markdown,
        reason="subprocess_failed",
    )


def _stitch_chunk_markdown(chunk_bodies: list[str]) -> str:
    """Concatenate chunk markdowns; drop H1s duplicated at adjacent-chunk boundaries.

    The page_overlap option on :func:`split_pdf` makes the first ``N``
    pages of chunk K identical to the last ``N`` pages of chunk K-1.
    Headers that fall inside that overlap window will appear in both
    chunks. This stitcher drops the duplicate by checking only the
    **adjacent-chunk boundary** condition: if chunk K's first H1
    matches chunk K-1's last H1, drop chunk K's leading H1.

    Non-adjacent duplicates (e.g. "Introduction" appearing in both
    Chapter 1 and Appendix A, which span separate non-overlapping
    chunks) are preserved — only the boundary collision pattern
    introduced by page_overlap is removed.
    """

    if not chunk_bodies:
        return ""

    kept: list[str] = []
    prior_trailing_h1: str | None = None
    for body in chunk_bodies:
        cleaned = _drop_leading_h1_if_matches(body, prior_trailing_h1)
        if cleaned.strip():
            kept.append(cleaned)
            prior_trailing_h1 = _last_h1_title(cleaned) or prior_trailing_h1

    return "\n\n".join(kept)


def _drop_leading_h1_if_matches(body: str, target_title: str | None) -> str:
    """Drop the chunk's first non-blank H1 line if its title matches ``target_title``.

    Inspects only the leading H1; any subsequent H1s in the body are
    preserved verbatim. This is the boundary-collision case caused by
    ``page_overlap`` in the splitter.
    """

    if target_title is None:
        return body
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        match = _H1_PATTERN.fullmatch(line)
        if match and match.group("title").strip() == target_title:
            # Drop this leading H1; preserve every other line including
            # blank lines so paragraph spacing stays intact.
            return "\n".join(lines[:i] + lines[i + 1 :])
        return body  # First non-blank line isn't a matching H1 — keep body as-is.
    return body  # All blank lines; nothing to dedupe.


def _last_h1_title(body: str) -> str | None:
    """Return the title text of the last H1 line in ``body``, or None if none."""

    last_title: str | None = None
    for line in body.splitlines():
        match = _H1_PATTERN.fullmatch(line)
        if match:
            last_title = match.group("title").strip()
    return last_title
