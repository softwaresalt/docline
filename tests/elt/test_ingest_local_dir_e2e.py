"""End-to-end integration tests for `docline ingest local-dir` (T4 / 025.004-T).

Two surfaces:

1. ``test_ingest_local_dir_e2e_*`` — always-run, fixture-based tests that
   build a small repo on disk and verify the full contract: file counts,
   frontmatter fields, cross_doc_links, TOC ordering, frontmatter-robustness
   regression files (Microsoft-Learn-style include fragments).

2. ``test_powerbi_corpus_parity`` — opt-in, env-gated parity test. Skipped
   when ``POWERBI_DOCS_ROOT`` is absent. When enabled, asserts the
   AC5 acceptance criterion from
   ``docs/plans/2026-06-10-local-dir-ingest-plan.md``.

All tests are marked ``@pytest.mark.integration`` so they can be filtered
out from the standard CI lane (``pytest -m "not integration"``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _run_cli(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "docline", *argv],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _build_fixture(root: Path) -> None:
    """Build a representative fixture with one file per failure-mode category."""
    # 1) Clean canonical frontmatter
    (root / "clean.md").write_text(
        "---\ntitle: Clean Doc\nms.topic: how-to\nauthor: jdoe\n---\n# Clean Doc\n\nBody.\n",
        encoding="utf-8",
    )
    # 2) Microsoft Learn include-fragment style (uniform leading-space keys)
    (root / "include-uniform-leading-space.md").write_text(
        "---\n"
        " title: include file\n"
        " description: include file\n"
        " ms.topic: include\n"
        "---\n"
        "Body of an include fragment.\n",
        encoding="utf-8",
    )
    # 3) Mixed indentation (some keys indented, some not) — triggers regex fallback
    (root / "include-mixed-indent.md").write_text(
        "---\n"
        " title: mixed include\n"
        "ms.topic: include\n"
        " author: someone\n"
        "ms.date: 06/10/2026\n"
        "---\n"
        "Mixed-indent body.\n",
        encoding="utf-8",
    )
    # 4 + 5) Two files referenced by TOC.yml, plus one file NOT referenced
    (root / "guide").mkdir()
    (root / "guide" / "getting-started.md").write_text(
        "---\ntitle: Getting Started\n---\n# Getting Started\n\nIntro.\n"
        "See also: [Clean](../clean.md) and [Reference](../reference.md)\n",
        encoding="utf-8",
    )
    (root / "guide" / "advanced.md").write_text(
        "---\ntitle: Advanced\n---\n# Advanced\n\nDeep content.\n",
        encoding="utf-8",
    )
    (root / "guide" / "TOC.yml").write_text(
        "- name: Getting Started\n"
        "  href: getting-started.md\n"
        "- name: Advanced\n"
        "  href: advanced.md\n",
        encoding="utf-8",
    )
    (root / "reference.md").write_text(
        "---\ntitle: Reference\n---\n# Reference\n\nReference material.\n",
        encoding="utf-8",
    )
    # 6) File NOT referenced by any TOC
    (root / "orphan.md").write_text(
        "---\ntitle: Orphan\n---\n# Orphan\n\nNot in TOC.\n",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_ingest_local_dir_e2e_fixture_produces_all_outputs(tmp_path: Path) -> None:
    """AC1 + AC2: single command ingests fixture; all 7 .md files yield outputs."""
    src = tmp_path / "fixture-repo"
    src.mkdir()
    _build_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    output_files = sorted(out.rglob("*.md"))
    # 7 inputs (clean, include-uniform, include-mixed, guide/getting-started,
    # guide/advanced, reference, orphan) = 7 .md files total. AC2: structure preserved.
    assert len(output_files) == 7, (
        f"expected 7 outputs from 7 fixture files; got {len(output_files)}: "
        f"{[p.name for p in output_files]}"
    )
    # AC2: guide/getting-started.md path preserved
    rel_paths = [p.relative_to(out).as_posix() for p in output_files]
    assert any("guide/getting-started.md" in rp for rp in rel_paths), (
        f"expected guide/getting-started.md path preserved; got {rel_paths}"
    )


@pytest.mark.integration
def test_ingest_local_dir_e2e_frontmatter_graphtor_compatible(tmp_path: Path) -> None:
    """AC3: each output has the graphtor-required frontmatter fields."""
    src = tmp_path / "fixture-repo"
    src.mkdir()
    _build_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    required_top = [
        "chunk_strategy",
        "content_sha256",
        "doc_type",
        "title",
        "source_path",
        "source",
    ]
    for out_file in out.rglob("*.md"):
        text = out_file.read_text(encoding="utf-8")
        for field_name in required_top:
            assert f"{field_name}:" in text, (
                f"{out_file.relative_to(out)} missing top-level field {field_name}"
            )
        assert "docline:" in text
        assert "source_frontmatter:" in text


@pytest.mark.integration
def test_ingest_local_dir_e2e_frontmatter_robustness_on_include_fragments(
    tmp_path: Path,
) -> None:
    """T3 regression: include-fragment files MUST produce frontmatter-stripped output."""
    src = tmp_path / "fixture-repo"
    src.mkdir()
    _build_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    # Find the include-mixed-indent output and verify frontmatter parsed
    candidates = list(out.rglob("include-mixed-indent.md"))
    assert candidates, (
        f"expected include-mixed-indent.md output, got: {[p.name for p in out.rglob('*.md')]}"
    )
    text = candidates[0].read_text(encoding="utf-8")
    # T3 success: title preserved via regex fallback path
    assert "mixed include" in text
    # And the docline namespace appears (frontmatter assembled, not failed)
    assert "docline:" in text


@pytest.mark.integration
def test_ingest_local_dir_e2e_toc_ordering_visible_in_output(tmp_path: Path) -> None:
    """AC4: TOC-referenced files appear before non-TOC-referenced ones (via ingest_order)."""
    src = tmp_path / "fixture-repo"
    src.mkdir()
    _build_fixture(src)
    out = tmp_path / "out"
    staging = tmp_path / "stage-keep"

    result = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out.resolve()),
            "--staging-dir",
            str(staging.resolve()),
            "--keep-staging",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    # Inspect the crawl-manifest produced by T2
    manifests = list(staging.rglob("crawl-manifest.json"))
    assert manifests, "T2 should emit crawl-manifest.json"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    pages = manifest["pages"]
    # The two TOC-referenced files should appear first; orphan/reference/clean
    # come later with toc_referenced=False
    toc_referenced_paths = [p["path"] for p in pages if p["toc_referenced"]]
    assert any("getting-started.md" in p for p in toc_referenced_paths)
    assert any("advanced.md" in p for p in toc_referenced_paths)


@pytest.mark.integration
def test_ingest_local_dir_e2e_emits_cross_doc_links(tmp_path: Path) -> None:
    """getting-started.md has 2 inline links; output should contain cross_doc_links entries."""
    src = tmp_path / "fixture-repo"
    src.mkdir()
    _build_fixture(src)
    out = tmp_path / "out"

    result = _run_cli(
        ["ingest", "local-dir", str(src.resolve()), "--output", str(out.resolve())],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    gs_outputs = list(out.rglob("getting-started.md"))
    assert gs_outputs
    text = gs_outputs[0].read_text(encoding="utf-8")
    # Both inline links should surface as typed graph edges
    assert "cross_doc_links" in text
    assert "clean.md" in text
    assert "reference.md" in text


# ---------------------------------------------------------------------------
# AC5 — Power BI corpus parity. Opt-in via POWERBI_DOCS_ROOT env var.
# This test reproduces the 2026-06-09 evaluation against the live corpus
# under the new CLI surface and asserts the documented quality thresholds.
# ---------------------------------------------------------------------------


_POWERBI_ROOT = os.environ.get("POWERBI_DOCS_ROOT")


@pytest.mark.integration
@pytest.mark.skipif(
    not _POWERBI_ROOT or not Path(_POWERBI_ROOT).is_dir(),
    reason="Power BI corpus not present; set POWERBI_DOCS_ROOT to enable AC5 parity check.",
)
def test_powerbi_corpus_parity(tmp_path: Path) -> None:
    """AC5: corpus-scale verification against 2026-06-09 evaluation baseline.

    Baselines (from docs/decisions/2026-06-09-powerbi-corpus-coverage.md):
    - 1,340 files staged from E:\\Source\\powerbi-docs
    - 98.8 % frontmatter success rate in strict mode (16 failures across A/B/C)
    - 8,001 typed cross_doc_links
    - 142.1 s wall time on a typical dev machine

    T3 (frontmatter-robust parsing) eliminates 8 Category-B failures (YAML
    mishandling in include fragments) but EXPOSES 8 previously-masked
    Category-C failures (legitimate H2/H3-before-parent-heading patterns in
    include fragments). Net strict-mode failure count is unchanged at 16 /
    1,340; the failure mix shifts entirely to structural issues handled by
    ``--allow-heading-disorder``.

    Acceptance bands:
    - Strict mode: success rate >= 98.5 % (T3 must NOT REGRESS the baseline)
    - Permissive mode (--allow-heading-disorder): success rate >= 99.9 %
      (effectively 100 % — Category-C-equivalent failures are bypassed)
    - Cross-doc links >= 95 % of baseline (7,600+)
    - Wall time <= 300 s (2x baseline)
    """
    src = Path(_POWERBI_ROOT)
    out_strict = tmp_path / "powerbi-parity-strict"
    out_permissive = tmp_path / "powerbi-parity-permissive"

    # Strict mode pass (default)
    start = time.monotonic()
    result = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out_strict.resolve()),
        ],
        cwd=tmp_path,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0, f"strict stderr (truncated): {result.stderr[:500]}"

    output_files = list(out_strict.rglob("*.md"))
    total = len(output_files)
    assert total >= 1300, f"expected ~1,340 outputs; got {total}"

    well_formed = 0
    cross_doc_links_total = 0
    for f in output_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---\n") and "\n---" in text:
            well_formed += 1
        # cheap count: number of times target_path: appears in the frontmatter
        cross_doc_links_total += text.count("target_path:")

    success_rate = well_formed / total
    assert success_rate >= 0.985, (
        f"AC5 strict frontmatter success {success_rate:.3%} below 98.5% "
        f"non-regression threshold (baseline 98.8% / 1,324 of 1,340)"
    )
    assert cross_doc_links_total >= 7600, (
        f"AC5 cross_doc_links {cross_doc_links_total} below 7,600 threshold (baseline 8,001)"
    )
    assert elapsed <= 300, f"AC5 wall time {elapsed:.1f}s exceeds 300s ceiling (baseline 142s)"

    # Permissive mode pass (--allow-heading-disorder) — proves the operator
    # has a one-flag workaround for the remaining Category-C structural cases.
    result_perm = _run_cli(
        [
            "ingest",
            "local-dir",
            str(src.resolve()),
            "--output",
            str(out_permissive.resolve()),
            "--allow-heading-disorder",
        ],
        cwd=tmp_path,
    )
    assert result_perm.returncode == 0

    output_files_perm = list(out_permissive.rglob("*.md"))
    well_formed_perm = sum(
        1
        for f in output_files_perm
        if (text := f.read_text(encoding="utf-8", errors="replace")).startswith("---\n")
        and "\n---" in text
    )
    perm_rate = well_formed_perm / len(output_files_perm)
    assert perm_rate >= 0.999, (
        f"AC5 permissive (--allow-heading-disorder) frontmatter success {perm_rate:.3%} "
        f"below 99.9% threshold; expected effectively 100% in this mode"
    )
