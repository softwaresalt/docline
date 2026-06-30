"""Adaptive OCR-group downsizing retry tests (038.003-T / feature 038-F).

``dispatch_batched_groups_with_retry`` dispatches each group as a
``docling_worker --batch`` invocation. When a group that contains any OCR item
hard-crashes (non-zero exit, e.g. the 0xC0000005 OOM), it re-splits that group
at half the page cap and retries recursively (8->4->2->1) before conceding to
heuristic fallback. OCR-free groups never retry; a single OCR item that still
crashes (or cap==1) is left without an envelope so the caller's post-pass can
fall back to heuristic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _crash_when_ocr_pages_gt(
    manifests: list[list[dict[str, Any]]],
    page_of: dict[str, int],
    *,
    threshold: int,
) -> Any:
    """Runner that crashes a --batch group whose OCR page total exceeds ``threshold``.

    Successful groups write a one-page envelope per chunk; crashed groups write
    nothing (mimicking a worker subprocess that died before flushing output).
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        manifest_path = Path(args[args.index("--batch") + 1])
        chunks = json.loads(manifest_path.read_text(encoding="utf-8"))["chunks"]
        manifests.append(chunks)
        ocr_pages = sum(page_of[c["input"]] for c in chunks if c["do_ocr"])
        if ocr_pages > threshold:
            return subprocess.CompletedProcess(
                args=args, returncode=3221225477, stdout="", stderr="bad_alloc"
            )
        for chunk in chunks:
            out = Path(chunk["output"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps({"schema_version": 1, "pages": ["# x"], "page_count": 1, "text": "# x"}),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return runner


def _items(tmp_path: Path, page_counts: list[int]) -> tuple[list[str], list[str], dict[str, int]]:
    inputs = [f"item-{i}.pdf" for i in range(len(page_counts))]
    outputs = [str(tmp_path / f"out-{i}.json") for i in range(len(page_counts))]
    page_of = {inp: pc for inp, pc in zip(inputs, page_counts)}
    return inputs, outputs, page_of


def test_ocr_free_group_dispatched_once_without_retry(tmp_path: Path) -> None:
    from docline.process.batch_dispatch import dispatch_batched_groups_with_retry

    page_counts = [20, 20]
    inputs, outputs, page_of = _items(tmp_path, page_counts)
    manifests: list[list[dict[str, Any]]] = []

    rcs = dispatch_batched_groups_with_retry(
        [[0, 1]],
        inputs=inputs,
        outputs=outputs,
        do_ocr=[False, False],
        page_counts=page_counts,
        runner=_crash_when_ocr_pages_gt(manifests, page_of, threshold=0),
        manifest_dir=tmp_path,
    )

    assert rcs == [0, 0]
    assert len(manifests) == 1
    assert all(Path(o).exists() for o in outputs)


def test_small_ocr_group_succeeds_first_try(tmp_path: Path) -> None:
    from docline.process.batch_dispatch import dispatch_batched_groups_with_retry

    page_counts = [1, 1]
    inputs, outputs, page_of = _items(tmp_path, page_counts)
    manifests: list[list[dict[str, Any]]] = []

    rcs = dispatch_batched_groups_with_retry(
        [[0, 1]],
        inputs=inputs,
        outputs=outputs,
        do_ocr=[True, True],
        page_counts=page_counts,
        runner=_crash_when_ocr_pages_gt(manifests, page_of, threshold=5),
        manifest_dir=tmp_path,
    )

    assert rcs == [0, 0]
    assert len(manifests) == 1


def test_oversized_ocr_group_recovers_via_downsizing(tmp_path: Path) -> None:
    """An OCR group too big for memory shrinks (8->4->2) until every item succeeds."""
    from docline.process.batch_dispatch import dispatch_batched_groups_with_retry

    # Four 2-page OCR ranges -> one group of 8 pages (the OCR cap). The runner
    # crashes any OCR group totaling >2 pages, so recovery requires shrinking
    # to 2-page subgroups.
    page_counts = [2, 2, 2, 2]
    inputs, outputs, page_of = _items(tmp_path, page_counts)
    manifests: list[list[dict[str, Any]]] = []

    rcs = dispatch_batched_groups_with_retry(
        [[0, 1, 2, 3]],
        inputs=inputs,
        outputs=outputs,
        do_ocr=[True, True, True, True],
        page_counts=page_counts,
        runner=_crash_when_ocr_pages_gt(manifests, page_of, threshold=2),
        manifest_dir=tmp_path,
        ocr_max_pages=8,
    )

    # Every item recovered (docling envelope written, rc 0) after retries.
    assert rcs == [0, 0, 0, 0]
    assert all(Path(o).exists() for o in outputs)
    # Downsizing actually happened (more than the single initial dispatch).
    assert len(manifests) > 1


def test_single_ocr_item_that_always_crashes_gives_up(tmp_path: Path) -> None:
    """A lone OCR item that keeps crashing is left for heuristic with bounded attempts."""
    from docline.process.batch_dispatch import dispatch_batched_groups_with_retry

    page_counts = [5]
    inputs, outputs, page_of = _items(tmp_path, page_counts)
    manifests: list[list[dict[str, Any]]] = []

    rcs = dispatch_batched_groups_with_retry(
        [[0]],
        inputs=inputs,
        outputs=outputs,
        do_ocr=[True],
        page_counts=page_counts,
        runner=_crash_when_ocr_pages_gt(manifests, page_of, threshold=0),
        manifest_dir=tmp_path,
        ocr_max_pages=8,
    )

    assert rcs[0] != 0  # signals heuristic fallback to the caller
    assert not Path(outputs[0]).exists()
    assert len(manifests) == 1  # len==1 group does not retry


def test_multi_item_never_fits_terminates(tmp_path: Path) -> None:
    """If even single-page OCR crashes, the retry terminates (no infinite loop)."""
    from docline.process.batch_dispatch import dispatch_batched_groups_with_retry

    page_counts = [1, 1, 1]
    inputs, outputs, page_of = _items(tmp_path, page_counts)
    manifests: list[list[dict[str, Any]]] = []

    rcs = dispatch_batched_groups_with_retry(
        [[0, 1, 2]],
        inputs=inputs,
        outputs=outputs,
        do_ocr=[True, True, True],
        page_counts=page_counts,
        runner=_crash_when_ocr_pages_gt(manifests, page_of, threshold=0),
        manifest_dir=tmp_path,
        ocr_max_pages=8,
    )

    assert all(rc != 0 for rc in rcs)
    assert all(not Path(o).exists() for o in outputs)
    # Bounded: cap halves 8->4->2->1 then single items give up.
    assert len(manifests) < 40
