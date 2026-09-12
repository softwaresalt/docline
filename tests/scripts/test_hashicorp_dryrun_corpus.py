"""Integration tests for ``scripts/hashicorp_mdx_normalize.py`` (071.006-T /
071.007-T / 071.010-T -- C.T1, C.T2, D.T3).

All tests invoke the script as a real subprocess (the same way an
operator would), against either:

* a small synthetic fixture corpus checked into
  ``tests/scripts/fixtures/hashicorp/synthetic_corpus`` (deterministic,
  always runs), or
* the REAL external corpus at
  ``C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content`` (read-only;
  skipped cleanly when absent on the current machine).

HARD CONTAINMENT for this test file itself: every ``--dest`` used here is
a ``tmp_path``-derived directory, and ``tmp_path`` is always rooted under
the repo-local pytest ``--basetemp`` the operator/agent passes on the
command line (e.g. ``--basetemp=build/.pytest-tmp``) -- never the OS
temp directory. The real-corpus dry-run test never passes ``--execute``
and asserts the dest directory is never created at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "hashicorp_mdx_normalize.py"
_SYNTHETIC_CORPUS = Path(__file__).resolve().parent / "fixtures" / "hashicorp" / "synthetic_corpus"
_REAL_CORPUS = Path(r"C:\Source\Docs\hashicorp-tf-unified-dev-docs\content")

_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import hashicorp_mdx_normalize  # noqa: E402


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )


# ---------------------------------------------------------------------------
# C.T2 -- CLI surface / dry-run default / containment guard / help text
# ---------------------------------------------------------------------------


def test_help_documents_exact_operator_command() -> None:
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "--execute" in result.stdout
    assert "--source" in result.stdout
    assert "--dest" in result.stdout
    assert "--report" in result.stdout
    # The exact operator command for the real external run must be documented.
    assert "hashicorp-tf-unified-dev-docs" in result.stdout
    assert "tf-unified-dev-docs-normalized" in result.stdout


def test_dry_run_default_performs_zero_writes(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    assert not dest.exists(), "dry-run (default) must never create the --dest directory"


def test_dry_run_emits_json_plan_with_expected_shape(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    report_path = tmp_path / "report.json"
    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert not dest.exists()
    # P1 regression (review-fix cycle 1): dry-run must NEVER write the
    # report file, even when --report is supplied. The plan is only ever
    # available on stdout in dry-run mode.
    assert not report_path.exists()
    assert "ignored in dry-run mode" in result.stderr
    report = json.loads(result.stdout)

    assert report["execute"] is False
    assert report["schema_version"] == 1

    products = report["products"]
    assert products["vault"]["versioned"] is True
    assert products["vault"]["selected_version"] == "v2.x"
    assert products["terraform"]["selected_version"] == "v1.16.x"
    assert products["hcp-docs"]["versioned"] is False
    assert products["hcp-docs"]["selected_version"] is None

    vault_counts = products["vault"]["file_counts"]
    assert vault_counts["mdx_normalized"] == 2  # index.mdx + sub/page.mdx
    assert vault_counts["skipped_partials"] == 1  # content/partials/alert.mdx

    terraform_counts = products["terraform"]["file_counts"]
    assert terraform_counts["mdx_normalized"] == 1
    assert terraform_counts["assets_copied"] == 1
    assert terraform_counts["md_copied"] == 1
    # P2 regression (review-fix cycle 1): config.json is no longer silently
    # dropped -- it is copied byte-for-byte and reported as such.
    assert terraform_counts["generic_copied"] == 1

    assert "mystery-product" in report["excluded_top_level_dirs"]
    assert "global" in report["excluded_top_level_dirs"]
    assert any("mystery-product" in warning for warning in report["warnings"])

    assert report["totals"]["mdx_normalized"] == (
        vault_counts["mdx_normalized"] + terraform_counts["mdx_normalized"] + 1  # hcp-docs index
    )
    assert report["containment_violations"] == []


def test_dry_run_plan_includes_planned_dest_paths(tmp_path: Path) -> None:
    """C.T2 acceptance-criterion regression (post-push Copilot review): the
    dry-run JSON plan must include the planned destination paths per
    product so an operator can audit exactly what --execute would write
    before running it. Covers every write-eligible kind (.mdx normalized
    to .md, .md copied unchanged, an image asset, and a generic
    byte-for-byte copy) -- skipped partials must never appear."""
    dest = tmp_path / "dest"
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    vault = report["products"]["vault"]
    assert sorted(vault["planned_paths"]) == [
        "vault/v2.x/index.md",
        "vault/v2.x/sub/page.md",
    ]
    assert vault["planned_paths_truncated"] is False

    terraform = report["products"]["terraform"]
    assert sorted(terraform["planned_paths"]) == [
        "terraform/v1.16.x/config.json",
        "terraform/v1.16.x/diagram.png",
        "terraform/v1.16.x/index.md",
        "terraform/v1.16.x/notes.md",
    ]
    assert terraform["planned_paths_truncated"] is False

    hcp_docs = report["products"]["hcp-docs"]
    assert sorted(hcp_docs["planned_paths"]) == [
        "hcp-docs/assets/logo.svg",
        "hcp-docs/index.md",
    ]
    assert hcp_docs["planned_paths_truncated"] is False


def test_dry_run_plan_truncates_planned_paths_per_product(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Planned-path reporting is bounded per product (review suggestion:
    "preferably with a bounded/paginated representation if report size is
    a concern") so a real corpus with thousands of files per product
    cannot balloon the JSON report unboundedly."""
    monkeypatch.setattr(hashicorp_mdx_normalize, "MAX_PLANNED_PATHS_PER_PRODUCT", 1)
    dest = tmp_path / "dest"
    report = hashicorp_mdx_normalize.process_corpus(
        source=_SYNTHETIC_CORPUS, dest=dest, execute=False
    )
    vault = report["products"]["vault"]
    assert len(vault["planned_paths"]) == 1
    assert vault["planned_paths_truncated"] is True
    # Truncation never affects the authoritative file-count totals.
    assert vault["file_counts"]["mdx_normalized"] == 2


def test_dry_run_stdout_also_contains_json_plan() -> None:
    result = _run_cli(
        ["--source", str(_SYNTHETIC_CORPUS), "--dest", str(_SYNTHETIC_CORPUS / "nope")]
    )
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["execute"] is False


def test_execute_writes_expected_tree_and_never_materializes_mdx(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode == 0, result.stderr

    # Non-latest / non-version / non-product directories must never appear.
    assert not (dest / "vault" / "v1.20.x").exists()
    assert not (dest / "terraform" / "v1.15.x").exists()
    assert not (dest / "terraform" / "templates").exists()
    assert not (dest / "global").exists()
    assert not (dest / "mystery-product").exists()

    # Partials must never be emitted as standalone docs.
    assert not (dest / "vault" / "v2.x" / "content" / "partials" / "alert.md").exists()
    assert not (dest / "vault" / "v2.x" / "content" / "partials" / "alert.mdx").exists()

    # Latest versioned content, normalized in-flight.
    vault_index = dest / "vault" / "v2.x" / "index.md"
    assert vault_index.exists()
    vault_text = vault_index.read_text(encoding="utf-8")
    assert "> **Heads up**" in vault_text
    assert "<Note" not in vault_text
    assert "<PATH>" in vault_text  # literal placeholder preserved
    assert "<TYPE>" in vault_text
    assert "<NAMESPACE>" in vault_text  # placeholder inside fenced code preserved

    sub_page = dest / "vault" / "v2.x" / "sub" / "page.md"
    assert sub_page.exists()
    assert "**(Enterprise-only)**" in sub_page.read_text(encoding="utf-8")

    terraform_index = dest / "terraform" / "v1.16.x" / "index.md"
    assert terraform_index.exists()
    terraform_text = terraform_index.read_text(encoding="utf-8")
    assert "#### CLI" in terraform_text
    assert "#### API" in terraform_text

    # Asset + ordinary markdown copy rule.
    assert (dest / "terraform" / "v1.16.x" / "diagram.png").exists()
    assert (
        (dest / "terraform" / "v1.16.x" / "notes.md")
        .read_text(encoding="utf-8")
        .startswith("# Ordinary Markdown Notes")
    )
    # P2 regression (review-fix cycle 1): generic non-md/image files (JSON
    # data, PDFs, videos, etc.) are copied byte-for-byte, not dropped.
    dest_config = dest / "terraform" / "v1.16.x" / "config.json"
    assert dest_config.exists()
    source_config = _SYNTHETIC_CORPUS / "terraform" / "v1.16.x" / "config.json"
    assert dest_config.read_bytes() == source_config.read_bytes()

    # Unversioned product: whole tree copied, not just a "latest" subdirectory.
    assert (dest / "hcp-docs" / "index.md").exists()
    assert (dest / "hcp-docs" / "assets" / "logo.svg").exists()

    # No intermediate .mdx ever materialized anywhere at dest.
    assert list(dest.rglob("*.mdx")) == []


def test_execute_required_flag_is_not_default() -> None:
    """Sanity check: omitting --execute must never write, even if --dest pre-exists."""
    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(_SYNTHETIC_CORPUS)])
    # --dest reused the read-only source corpus path on purpose here: if the
    # tool ever attempted a real write in dry-run mode, this would corrupt the
    # checked-in fixture. A zero-write dry-run leaves it untouched.
    assert result.returncode == 0, result.stderr
    assert not (_SYNTHETIC_CORPUS / "vault" / "v2.x" / "index.md").exists()


# ---------------------------------------------------------------------------
# P1/P2 regressions (review-fix cycle 1): report containment + non-empty
# --dest rejection under --execute
# ---------------------------------------------------------------------------


def test_execute_rejects_non_empty_existing_dest(tmp_path: Path) -> None:
    """P1 regression: execute must fail closed against a pre-existing,
    non-empty --dest rather than overlaying it (which would leave stale
    versions/files behind). No deletion/replacement logic is implemented --
    the run simply refuses to proceed."""
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "stale-leftover.txt").write_text("stale", encoding="utf-8")

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode != 0
    assert "already exists" in result.stderr
    # Nothing new was written; the stale file is untouched and no product
    # trees were created.
    assert list(dest.iterdir()) == [dest / "stale-leftover.txt"]
    assert not (dest / "vault").exists()


def test_execute_succeeds_against_existing_empty_dest(tmp_path: Path) -> None:
    """P2 regression / usability fix (review-fix cycle 3): an EXISTING but
    EMPTY --dest is a valid execute target again. Cycle 2's atomic-claim
    redesign (finding 3) had incidentally narrowed the contract to require
    --dest to be ABSENT, which rejected the documented exact operator
    command whenever the operator's real destination happened to already
    exist (created ahead of time, or left empty by a prior aborted run)
    while still being completely empty -- a same-contract-surface
    usability defect, since the whole point of finding 3 was mutual
    exclusion, not "must not exist yet". The claim is now performed by
    :func:`claim_destination` (an exclusive sentinel-file create under
    --dest) rather than by --dest's own creation, so an existing empty
    directory can be claimed exactly as safely as a freshly created one."""
    dest = tmp_path / "dest"
    dest.mkdir()

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode == 0, result.stderr
    assert (dest / "vault" / "v2.x" / "index.md").exists()
    # The claim sentinel is removed once the run finishes successfully --
    # only real corpus/report output remains under --dest.
    assert not (dest / ".docline-hashicorp-mdx-normalize.claim").exists()


def test_execute_succeeds_against_absent_dest(tmp_path: Path) -> None:
    """An absent --dest is claimed atomically and populated normally."""
    dest = tmp_path / "dest"
    assert not dest.exists()

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert result.returncode == 0, result.stderr
    assert (dest / "vault" / "v2.x" / "index.md").exists()


def test_dry_run_leaves_existing_empty_dest_unchanged(tmp_path: Path) -> None:
    """Dry-run never claims --dest, even when it exists and is empty
    (review-fix cycle 3): claiming (the exclusive sentinel create) only
    ever happens on the --execute path. An existing, empty --dest must
    come out of a dry-run run exactly as it went in -- still present,
    still empty, no sentinel, no report file."""
    dest = tmp_path / "dest"
    dest.mkdir()

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    assert dest.is_dir()
    assert list(dest.iterdir()) == []


def test_execute_removes_claim_sentinel_after_success(tmp_path: Path) -> None:
    """Sentinel lifecycle (review-fix cycle 3): the exclusive claim
    sentinel this invocation creates under --dest is removed once the run
    finishes successfully, leaving only real corpus/report output behind
    -- proven here directly against the module's own sentinel-name
    constant rather than a hardcoded literal, so this test tracks the
    production constant if it is ever renamed."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_sentinel_success", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_sentinel_success"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    exit_code = module.main(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])

    assert exit_code == module.EXIT_OK
    assert (dest / "vault" / "v2.x" / "index.md").exists()
    assert not (dest / module.CLAIM_SENTINEL_NAME).exists()
    # Only real product output remains -- no leftover claim artifact.
    assert module.CLAIM_SENTINEL_NAME not in {p.name for p in dest.iterdir()}


def test_claim_destination_two_claims_cannot_coexist(tmp_path: Path) -> None:
    """Mutual exclusion (review-fix cycle 3): two claims against the same
    --dest can never both succeed. This calls :func:`claim_destination`
    directly (unit level, fully deterministic, no real threading or
    subprocess timing needed) to prove the invariant: the first claim
    succeeds and creates the sentinel; a second claim attempted WHILE the
    first invocation's sentinel is still present (i.e. before that first
    invocation has finished and released its own claim) must fail closed
    with :class:`DestAlreadyClaimedError`, leaving the first claim's
    sentinel completely untouched. Exercised against both an initially
    absent --dest and an initially existing, empty --dest, since cycle 3
    accepts both as claim targets."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_claim_mutex", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_claim_mutex"] = module
    spec.loader.exec_module(module)

    for label, prepare in (
        ("absent", lambda d: None),
        ("existing-empty", lambda d: d.mkdir()),
    ):
        dest = tmp_path / f"dest-{label}"
        prepare(dest)

        first_sentinel = module.claim_destination(dest)
        assert first_sentinel.exists()

        with pytest.raises(module.DestAlreadyClaimedError):
            module.claim_destination(dest)

        # The rejected second claim must not have disturbed the first
        # invocation's still-held sentinel in any way.
        assert first_sentinel.exists()
        assert [p.name for p in dest.iterdir()] == [module.CLAIM_SENTINEL_NAME]

        # Simulate the first invocation finishing and releasing its claim.
        module.release_destination_claim(first_sentinel)
        assert not first_sentinel.exists()


def test_execute_rejects_rerun_against_dest_with_existing_output(
    tmp_path: Path,
) -> None:
    """P2 regression (review-fix cycle 2, finding 3), retitled and
    re-verified in review-fix cycle 3 (this test was previously named
    ...already_claimed_dest_fails_closed, but it does NOT exercise a
    genuine claim collision -- see the note below): once a --dest already
    holds REAL, complete corpus output from a prior successful --execute
    run, a second --execute attempt against that same --dest must fail
    closed with the ordinary non-empty-directory rejection
    (EXIT_DEST_NOT_EMPTY), leaving the prior run's output completely
    untouched.

    By the time the second invocation starts here, the first invocation
    has already finished AND released its own claim sentinel (main()'s
    finally block ran), so --dest contains real product files, not just
    the sentinel -- this is the "--dest already has content from a
    finished prior run" case, distinct from "--dest is actively claimed by
    a still-running invocation" (covered by
    test_execute_rejects_dest_actively_claimed_by_another_invocation
    below, added in review-fix cycle 3 to close a real gap: this test's
    original loose ``"already exists" in stderr`` assertion happened to
    pass for either exit code and could not have caught that gap)."""
    dest = tmp_path / "dest"

    first = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert first.returncode == 0, first.stderr
    vault_index = dest / "vault" / "v2.x" / "index.md"
    assert vault_index.exists()
    first_mtime_ns = vault_index.stat().st_mtime_ns
    first_bytes = vault_index.read_bytes()

    second = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    assert second.returncode == 10  # EXIT_DEST_NOT_EMPTY -- ordinary non-empty rejection
    assert "already exists and is not empty" in second.stderr
    # The already-populated destination is left completely untouched by the
    # rejected second attempt.
    assert vault_index.stat().st_mtime_ns == first_mtime_ns
    assert vault_index.read_bytes() == first_bytes


def test_execute_rejects_dest_actively_claimed_by_another_invocation(
    tmp_path: Path,
) -> None:
    """P0 regression (review-fix cycle 3, finding 1, independent review
    gate): a --dest whose ONLY entry is the reserved claim sentinel --
    i.e. another invocation is genuinely still claiming it -- must be
    rejected at the real CLI entry point with the SPECIFIC
    EXIT_DEST_ALREADY_EXISTS code and an "already claimed by another
    in-progress invocation" message, never the generic EXIT_DEST_NOT_EMPTY
    rejection used for ordinary pre-existing content.

    Before this fix, main()'s early _dest_precheck() gate intercepted this
    exact scenario first and unconditionally reported EXIT_DEST_NOT_EMPTY,
    because it was not sentinel-aware the way claim_destination()'s own
    internal pre-check already was -- so the documented claim-collision
    exit code was unreachable through the real CLI entry point for the
    realistic staggered-rerun case (a second invocation starting sometime
    after a first has already claimed --dest but is still writing), and
    was only ever proven at the direct-function-call level by
    test_claim_destination_two_claims_cannot_coexist, which bypasses
    main()/_dest_precheck()/the CLI entirely. This test pre-seeds --dest
    with ONLY the sentinel (simulating a still-active claim held by
    another invocation) rather than running a prior invocation to full
    completion, so it exercises exactly the CLI-level path the fix
    corrects."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_claimed_dest_cli", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_claimed_dest_cli"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    dest.mkdir()
    live_sentinel = dest / module.CLAIM_SENTINEL_NAME
    live_sentinel.write_bytes(b"")

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])

    assert result.returncode == module.EXIT_DEST_ALREADY_EXISTS
    assert "already claimed by another in-progress invocation" in result.stderr
    # The rejected attempt must not have disturbed the still-live sentinel
    # or written any corpus output alongside it.
    assert [p.name for p in dest.iterdir()] == [module.CLAIM_SENTINEL_NAME]
    assert live_sentinel.read_bytes() == b""


def test_execute_rejects_report_path_equal_to_reserved_sentinel(tmp_path: Path) -> None:
    """Regression (review-fix cycle 3, finding: independent-review /
    Copilot shadow-review comment on commit 201fc58): a --report path that
    resolves to EXACTLY the reserved claim-sentinel filename under --dest
    must be rejected with a dedicated EXIT_REPORT_PATH_RESERVED code
    before --dest is created or claimed, in BOTH the absent-dest and
    existing-empty-dest cases.

    Before this fix, --report was only checked for containment (does it
    resolve inside --dest), never for collision with the reserved
    sentinel name. Because the reserved name is trivially "inside --dest"
    too, the containment guard let it through: the report write would
    overwrite the live sentinel, and main()'s finally-block cleanup would
    then delete it as "the sentinel this process created" -- silently
    losing the report while the run still returned exit 0. This test
    pre-empts --dest being created at all in the absent case, proving the
    rejection happens at the early pre-claim guard, not merely after some
    partial side effect."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_reserved_report_cli", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_reserved_report_cli"] = module
    spec.loader.exec_module(module)

    # Case 1: --dest does not exist yet. The rejection must fire before
    # --dest is ever created.
    dest_absent = tmp_path / "dest-absent"
    reserved_report_path = dest_absent / module.CLAIM_SENTINEL_NAME

    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest_absent),
            "--report",
            str(reserved_report_path),
            "--execute",
        ]
    )

    assert result.returncode == module.EXIT_REPORT_PATH_RESERVED
    assert "reserved claim sentinel path" in result.stderr
    assert not dest_absent.exists()

    # Case 2: --dest already exists and is empty (the exact scenario this
    # review-fix cycle's headline fix made legal again) -- the reserved
    # --report path must still be rejected before claim, and --dest must
    # be left empty (no sentinel, no partial output).
    dest_existing_empty = tmp_path / "dest-existing-empty"
    dest_existing_empty.mkdir()
    reserved_report_path_existing = dest_existing_empty / module.CLAIM_SENTINEL_NAME

    result_existing = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest_existing_empty),
            "--report",
            str(reserved_report_path_existing),
            "--execute",
        ]
    )

    assert result_existing.returncode == module.EXIT_REPORT_PATH_RESERVED
    assert "reserved claim sentinel path" in result_existing.stderr
    assert list(dest_existing_empty.iterdir()) == []


def test_execute_leaves_partial_dest_in_place_when_write_pass_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2 regression (review-fix cycle 2, finding 3): if --dest is
    successfully atomically claimed but the subsequent write pass then
    fails partway through, the partial destination is left in place
    (NEVER auto-deleted) and the failure is reported clearly as a
    partial-output failure, not silently swallowed or cleaned up."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_partial_failure", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_partial_failure"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    real_process_corpus = module.process_corpus
    call_count = {"n": 0}

    def flaky_process_corpus(*, source, dest, execute, planned_dest_paths=None):
        call_count["n"] += 1
        if execute:
            raise OSError("simulated disk failure partway through writing")
        return real_process_corpus(
            source=source, dest=dest, execute=execute, planned_dest_paths=planned_dest_paths
        )

    monkeypatch.setattr(module, "process_corpus", flaky_process_corpus)

    exit_code = module.main(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    captured = capsys.readouterr()

    assert exit_code == module.EXIT_EXECUTION_FAILED
    assert dest.exists(), "the atomically-claimed --dest must be left in place, not deleted"
    assert "partial" in captured.err.lower()
    assert call_count["n"] == 2  # preflight (execute=False) + the failing write pass
    # Sentinel removal (review-fix cycle 3): the claim sentinel THIS
    # invocation created must be removed on failure too, via main()'s
    # finally block -- only the sentinel, never the partial output above.
    assert not (dest / module.CLAIM_SENTINEL_NAME).exists()


def test_execute_dest_claim_failure_other_than_file_exists_reports_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2 regression (independent re-review of review-fix cycle 2, finding 3;
    logic relocated into :func:`claim_destination` in review-fix cycle 3):
    the atomic --dest claim (``mkdir(..., exist_ok=False)``) explicitly
    caught only ``FileExistsError``; any OTHER ``OSError`` (permission
    denial, a blocked ancestor path component, disk exhaustion, ...)
    escaped as a raw, uncontrolled traceback instead of a clear,
    stable-exit-code CLI failure. Simulated here via a monkeypatched
    ``Path.mkdir`` that raises ``PermissionError`` only for the exact
    --dest path under test (with ``exist_ok=False``, i.e. only the real
    claim call), delegating every other ``mkdir`` call -- including the
    preflight pass's read-only work and pytest's own fixture
    machinery -- to the real implementation."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_dest_claim_oserror", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_dest_claim_oserror"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    real_mkdir = pathlib.Path.mkdir

    def flaky_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == dest and kwargs.get("exist_ok") is False:
            raise PermissionError("simulated permission denial claiming --dest")
        real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "mkdir", flaky_mkdir)

    exit_code = module.main(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest), "--execute"])
    captured = capsys.readouterr()

    assert exit_code == module.EXIT_DEST_CLAIM_FAILED
    assert not dest.exists(), "a failed claim must never leave a partially-created --dest"
    assert "failed to claim --dest" in captured.err
    assert "permission denial" in captured.err.lower()


def test_execute_report_write_failure_after_successful_corpus_write_reports_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2 regression (independent re-review of review-fix cycle 2, finding 2):
    if the corpus write pass succeeds but the subsequent --report write
    itself then fails (permission denial, disk exhaustion, ...), that
    failure must be reported distinctly and clearly -- noting the corpus
    output already succeeded and was left in place -- rather than
    escaping as a raw, uncontrolled traceback after --dest has already
    been fully and successfully populated. Simulated via a monkeypatched
    ``Path.write_text`` that raises only for the exact resolved --report
    path, delegating every other write (every corpus file) to the real
    implementation."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_report_write_oserror", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_report_write_oserror"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    report_path = dest / "report.json"
    real_write_text = pathlib.Path.write_text

    def flaky_write_text(self: Path, *args: object, **kwargs: object) -> int:
        if self == report_path.resolve():
            raise OSError("simulated disk failure writing --report")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", flaky_write_text)

    exit_code = module.main(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(report_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == module.EXIT_REPORT_WRITE_FAILED
    assert not report_path.exists()
    # The corpus output that succeeded BEFORE the report write failure
    # must be left in place, not rolled back.
    assert (dest / "vault" / "v2.x" / "index.md").exists()
    assert "failed to write --report" in captured.err
    assert "already written successfully" in captured.err
    # Sentinel removal (review-fix cycle 3): removed on this failure path
    # too, leaving only the successful corpus output behind.
    assert not (dest / module.CLAIM_SENTINEL_NAME).exists()


def test_dry_run_may_point_dest_at_a_non_empty_directory_without_creating_it(
    tmp_path: Path,
) -> None:
    """Dry-run is exempt from the non-empty --dest check entirely: it may
    point anywhere, including a pre-existing non-empty directory, without
    ever creating or touching it."""
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "pre-existing.txt").write_text("pre-existing", encoding="utf-8")

    result = _run_cli(["--source", str(_SYNTHETIC_CORPUS), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    assert list(dest.iterdir()) == [dest / "pre-existing.txt"]


def test_execute_report_guarded_under_dest_succeeds(tmp_path: Path) -> None:
    """P1: in --execute mode, a --report path resolving INSIDE --dest is
    written normally, guarded by the same containment check as every other
    write."""
    dest = tmp_path / "dest"
    report_path = dest / "_normalize-report.json"

    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["execute"] is True


def test_execute_report_outside_dest_fails_closed_before_any_corpus_write(
    tmp_path: Path,
) -> None:
    """P1 regression: a --report path resolving OUTSIDE --dest in --execute
    mode must fail closed with a containment violation BEFORE any corpus
    write begins -- --dest must never even be created."""
    dest = tmp_path / "dest"
    outside_report = tmp_path / "sibling" / "report.json"

    result = _run_cli(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(outside_report),
        ]
    )
    assert result.returncode != 0
    assert "containment violation" in result.stderr
    assert not outside_report.exists()
    assert not dest.exists(), "no corpus write may occur when the report path is rejected"


def test_execute_report_written_using_resolved_guard_path_not_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1 regression (review-fix cycle 2, finding 2): the report file MUST
    be written using the RESOLVED path returned by ``guard_write_path`` at
    actual write time, not the original ``--report`` argument that was
    merely checked earlier in the run. Verified by monkeypatching
    ``guard_write_path`` so that -- only for the report candidate -- it
    returns a deliberately DIFFERENT (but still --dest-contained) path,
    and asserting the report lands there, never at the literal, unresolved
    ``--report`` path. A real symlink/junction substitution was considered
    but is not reliably creatable cross-platform without elevated
    privileges on Windows, so this test proves the same contract (the
    code always writes through guard_write_path's RETURN VALUE) at the
    call-site level instead."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docline_hashicorp_mdx_normalize_report_redirect", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize_report_redirect"] = module
    spec.loader.exec_module(module)

    dest = tmp_path / "dest"
    requested_report_path = dest / "requested-report.json"
    redirected_report_path = dest / "actually-written-report.json"

    real_guard_write_path = module.guard_write_path
    report_guard_calls = {"n": 0}

    def fake_guard_write_path(dest_root: Path, candidate: Path) -> Path:
        if Path(candidate) == requested_report_path:
            report_guard_calls["n"] += 1
            # Still exercise the real containment logic (so a genuine
            # violation would still raise), but return a different,
            # still-valid resolved path -- exactly what a symlink
            # retargeting the last path component would produce.
            real_guard_write_path(dest_root, candidate)
            return redirected_report_path.resolve()
        return real_guard_write_path(dest_root, candidate)

    monkeypatch.setattr(module, "guard_write_path", fake_guard_write_path)

    exit_code = module.main(
        [
            "--source",
            str(_SYNTHETIC_CORPUS),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(requested_report_path),
        ]
    )

    assert exit_code == module.EXIT_OK
    # Called once for the pre-write containment probe and once again
    # immediately before the actual write (finding 2's explicit
    # "call guard_write_path again" requirement).
    assert report_guard_calls["n"] == 2
    assert redirected_report_path.exists()
    assert not requested_report_path.exists()
    report = json.loads(redirected_report_path.read_text(encoding="utf-8"))
    assert report["execute"] is True


# ---------------------------------------------------------------------------
# P2 regression (review-fix cycle 1, finding 5): execute fails closed on
# genuine unresolved MDX components unless explicitly overridden
# ---------------------------------------------------------------------------


def _write_unresolved_construct_source(root: Path) -> Path:
    """Build a tiny unversioned-product source tree with one genuinely
    unresolved (bare, non-self-closing, non-paired, non-registry) MDX-shaped
    tag, using a recognized unversioned product name (``hcp-docs``)."""
    product_dir = root / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text(
        "---\npage_title: Unresolved Example\n---\n"
        "This mentions <BrandNewWidget> which nothing understands.\n",
        encoding="utf-8",
    )
    return root


def test_execute_fails_closed_when_unresolved_mdx_constructs_remain(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(["--source", str(source), "--dest", str(dest), "--execute"])
    assert result.returncode != 0
    assert "unresolved" in result.stderr.lower()
    assert "BrandNewWidget" in result.stderr


def test_execute_unresolved_input_leaves_dest_absent_and_report_absent(tmp_path: Path) -> None:
    """P1 regression (review-fix cycle 2, finding 1): the unresolved-MDX
    gate is now a READ-ONLY PREFLIGHT that runs BEFORE --dest is created or
    anything is written -- not a check applied after execute has already
    written the corpus (and the report). Proves both halves of the
    contract: --dest must never even be created, AND a --report path (also
    guarded, inside --dest) must never be written either, when the
    preflight finds unresolved constructs and --allow-unresolved-mdx was
    not passed."""
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"
    report_path = dest / "_normalize-report.json"

    result = _run_cli(
        [
            "--source",
            str(source),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode != 0
    assert "unresolved" in result.stderr.lower()
    assert not dest.exists(), (
        "--dest must never be created when the preflight finds unresolved constructs"
    )
    assert not report_path.exists(), "the report must never be written when execution never ran"


def test_execute_succeeds_with_explicit_allow_unresolved_mdx_override(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(
        ["--source", str(source), "--dest", str(dest), "--execute", "--allow-unresolved-mdx"]
    )
    assert result.returncode == 0, result.stderr
    assert (dest / "hcp-docs" / "index.md").exists()
    assert "<BrandNewWidget>" in (dest / "hcp-docs" / "index.md").read_text(encoding="utf-8")


def test_dry_run_never_fails_on_unresolved_mdx_constructs(tmp_path: Path) -> None:
    source = _write_unresolved_construct_source(tmp_path / "source")
    dest = tmp_path / "dest"

    result = _run_cli(["--source", str(source), "--dest", str(dest)])
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["unresolved_constructs"]["BrandNewWidget"] == 1


def test_guard_read_path_rejects_paths_outside_source(tmp_path: Path) -> None:
    """Unit-level read-side containment guard check (Copilot review cycle
    4 -- read-side counterpart of ``test_guard_write_path_rejects_paths_outside_dest``).
    """
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "sibling" / "escaped.mdx"
    with pytest.raises(hashicorp_mdx_normalize.ContainmentViolation):
        hashicorp_mdx_normalize.guard_read_path(source_root, outside)

    inside = source_root / "nested" / "ok.mdx"
    resolved = hashicorp_mdx_normalize.guard_read_path(source_root, inside)
    assert resolved == inside.resolve()


def test_process_corpus_rejects_symlinked_file_escaping_source(tmp_path: Path) -> None:
    """P2 regression (Copilot review cycle 4): ``Path.is_file()`` /
    ``Path.rglob()`` follow symlinks transparently, so a symlinked file
    inside an otherwise-legitimate product tree could point at content
    OUTSIDE the operator-authorized ``--source`` corpus without any
    indication in the report. ``process_corpus`` must refuse to read such
    an escape (fail closed with :class:`ContainmentViolation`) rather than
    silently normalizing/copying whatever the symlink resolves to, and
    must do so BEFORE anything is written to ``--dest``.
    """
    source = tmp_path / "source"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.mdx"
    secret.write_text("# secret content\n", encoding="utf-8")

    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text("# ok\n", encoding="utf-8")
    escape_link = product_dir / "escape.mdx"
    try:
        os.symlink(secret, escape_link)
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported in this environment: {exc}")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.ContainmentViolation):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists(), "a rejected read must never create --dest, even in dry-run"


def test_process_corpus_reads_mdx_through_resolved_path_not_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1 regression (Copilot review cycle 4 follow-up round, finding
    htcWC): ``guard_read_path()`` resolves ``source_path`` and verifies
    the RESOLVED target stays inside ``--source``, but the resolved
    return value was previously discarded -- the actual read
    (``_read_text_preserving_newlines``) re-used the ORIGINAL,
    possibly-symlink-bearing path variable instead. That means the read
    performs its OWN, independent symlink resolution at read-time,
    entirely separate from the one the guard already validated. A
    symlink retargeted in the (however small) window between the guard
    check and the read would therefore escape ``--source`` undetected,
    because nothing then re-validates -- or even reuses -- the
    already-resolved, already-proven-safe path.

    This test does not attempt to simulate an actual filesystem race
    (Python has no portable way to do that deterministically); instead
    it directly enforces the code-level contract that closes the gap:
    the read must be issued against the concrete, fully-resolved path
    captured by the guard at check time, not against the original
    (potentially symlink-bearing) path reference the corpus walk
    produced. That is what makes a later, out-of-band symlink retarget
    unable to affect this already-completed resolution.

    Uses a symlinked FILE (leaf-level), not a symlinked directory:
    Python 3.13+'s ``pathlib`` ``rglob()`` does not descend into
    symlinked directories by default (``recurse_symlinks=False``), but
    it still matches an individual symlinked FILE within a directory it
    does traverse -- that is the actual shape of the TOCTOU gap this
    finding describes.
    """
    source = tmp_path / "source"
    real_subdir = source / "_real_subdir_outside_product"
    real_subdir.mkdir(parents=True)
    real_file = real_subdir / "target.mdx"
    real_file.write_text("# real content\n", encoding="utf-8")

    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    linked_file = product_dir / "foo.mdx"
    try:
        os.symlink(real_file, linked_file)
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported in this environment: {exc}")

    dest = tmp_path / "dest"
    calls: list[Path] = []
    original_read = hashicorp_mdx_normalize._read_text_preserving_newlines

    def _spy_read(path: Path) -> str:
        calls.append(path)
        return original_read(path)

    monkeypatch.setattr(hashicorp_mdx_normalize, "_read_text_preserving_newlines", _spy_read)

    hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)

    assert len(calls) == 1, f"expected exactly one MDX read, got {calls!r}"
    read_path = calls[0]
    expected_resolved = linked_file.resolve()
    assert read_path == expected_resolved, (
        "the MDX read must go through the already-guarded, fully-resolved "
        f"path ({expected_resolved!r}), not the original symlink-bearing "
        f"candidate path; got {read_path!r}"
    )


def test_process_corpus_rejects_symlinked_top_level_product_dir_escaping_source(
    tmp_path: Path,
) -> None:
    """P2 regression (Copilot review cycle 4): a top-level product
    directory that is ITSELF a symlink pointing outside ``--source`` must
    also be rejected -- not just an individual symlinked leaf file. Both
    cases are caught by the same resolved-path containment check since
    ``Path.resolve()`` follows the entire symlink chain.
    """
    source = tmp_path / "source"
    source.mkdir()
    outside_product = tmp_path / "outside-hcp-docs"
    outside_product.mkdir()
    (outside_product / "index.mdx").write_text("# secret\n", encoding="utf-8")

    product_link = source / "hcp-docs"
    try:
        os.symlink(outside_product, product_link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported in this environment: {exc}")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.ContainmentViolation):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists()


def test_process_corpus_rejects_symlinked_top_level_product_dir_to_empty_dir(
    tmp_path: Path,
) -> None:
    """P1 regression (Copilot review cycle 4 follow-up round, finding
    htL40): the sibling test above only covers a symlinked top-level
    product directory whose external target CONTAINS files -- those
    files get caught via ``_iter_files_sorted``'s per-file
    ``guard_read_path`` check. But if the external target is empty (or
    contains only subdirectories with no regular files at all),
    ``root.rglob("*")`` filtered to ``is_file()`` yields zero candidates,
    so ``guard_read_path`` is never invoked on anything and the escape
    succeeds completely undetected. The product/version ROOT itself must
    be guarded before any enumeration begins, not just the files
    discovered inside it.
    """
    source = tmp_path / "source"
    source.mkdir()
    outside_product = tmp_path / "outside-hcp-docs-empty"
    outside_product.mkdir()
    # Deliberately directory-only: a nested subdirectory but zero files
    # anywhere under it, so rglob("*") filtered to is_file() yields nothing.
    (outside_product / "nested").mkdir()

    product_link = source / "hcp-docs"
    try:
        os.symlink(outside_product, product_link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported in this environment: {exc}")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.ContainmentViolation):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists()


def test_process_corpus_rejects_symlinked_version_dir_pointing_to_empty_dir_escaping_source(
    tmp_path: Path,
) -> None:
    """P1 regression (Copilot review cycle 4 follow-up round, finding
    htL40): same gap as the sibling unversioned-product test above, but
    at the version-directory level for a VERSIONED product.
    ``process_corpus`` lists version directory NAMES via
    ``product_source_root.iterdir()`` before
    ``_process_one_product_tree``/``_iter_files_sorted`` ever runs, and
    the selected version directory itself may be a symlink pointing
    outside ``--source`` to an empty external target -- which, absent a
    guard on the root itself, would never reach any per-file check.
    """
    source = tmp_path / "source"
    product_dir = source / "terraform"
    product_dir.mkdir(parents=True)

    outside_version = tmp_path / "outside-terraform-v1.16.x-empty"
    outside_version.mkdir()
    (outside_version / "nested").mkdir()

    version_link = product_dir / "v1.16.x"
    try:
        os.symlink(outside_version, version_link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported in this environment: {exc}")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.ContainmentViolation):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists()


def test_process_corpus_rejects_mdx_md_destination_collision(tmp_path: Path) -> None:
    """P2 regression (finding p8PN, Copilot review cycle 4): normalizing
    ``foo.mdx`` to ``foo.md`` can collide with an existing ``foo.md`` in
    the same selected tree. ``process_corpus`` must detect this during
    the read-only preflight (dry-run or --execute alike) and refuse to
    proceed with :class:`DestinationCollisionError`, rather than silently
    letting one file's output overwrite the other's.
    """
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "foo.mdx").write_text("# mdx version\n", encoding="utf-8")
    (product_dir / "foo.md").write_text("# md version\n", encoding="utf-8")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.DestinationCollisionError):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists(), "a rejected collision must never create --dest, even in dry-run"


def test_process_corpus_rejects_case_insensitive_destination_collision(tmp_path: Path) -> None:
    """P1 regression (Copilot review cycle 4 follow-up round, finding
    htTX0): the documented operator target is Windows, whose filesystems
    are normally case-INSENSITIVE, but the original collision-detection
    key was a raw posix-relative string comparison (case-SENSITIVE).
    ``Foo.mdx`` normalizes to ``Foo.md``, which is a DIFFERENT Python
    string than an existing ``foo.md`` in the same tree, so the original
    check let both through -- even though on the real destination
    filesystem they are the exact same path, and one write would silently
    clobber the other. The fix compares ``os.path.normcase()``-normalized
    keys while still reporting the original, human-readable casing in the
    raised error message.
    """
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "Foo.mdx").write_text("# mdx version\n", encoding="utf-8")
    (product_dir / "foo.md").write_text("# md version\n", encoding="utf-8")

    dest = tmp_path / "dest"
    with pytest.raises(hashicorp_mdx_normalize.DestinationCollisionError):
        hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=False)
    assert not dest.exists(), "a rejected collision must never create --dest, even in dry-run"


def test_process_corpus_collects_full_planned_dest_paths_when_requested(tmp_path: Path) -> None:
    """The uncapped ``planned_dest_paths`` out-parameter (used by
    ``main()``'s --report collision check, finding qAsu) is populated
    in-place with every planned destination path, independent of the
    per-product JSON-report cap."""
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text("# ok\n", encoding="utf-8")

    dest = tmp_path / "dest"
    planned: set[str] = set()
    hashicorp_mdx_normalize.process_corpus(
        source=source, dest=dest, execute=False, planned_dest_paths=planned
    )
    assert "hcp-docs/index.md" in planned


def test_execute_rejects_report_path_colliding_with_planned_output(tmp_path: Path) -> None:
    """P2 regression (finding qAsu, Copilot review cycle 4): a contained
    ``--report`` path may equal a planned corpus OUTPUT path (not just the
    reserved claim-sentinel name), e.g. ``--report <dest>/hcp-docs/index.md``.
    ``write_text`` would then silently replace the successfully normalized
    document with the JSON report. This must be rejected before ``--dest``
    is ever claimed.
    """
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text("# ok\n", encoding="utf-8")

    dest = tmp_path / "dest"
    colliding_report = dest / "hcp-docs" / "index.md"

    result = _run_cli(
        [
            "--source",
            str(source),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(colliding_report),
        ]
    )
    assert result.returncode == hashicorp_mdx_normalize.EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT
    assert not dest.exists(), "--dest must never be claimed/created when --report collides"
    assert "collides" in result.stderr.lower() or "planned corpus output" in result.stderr.lower()


def test_execute_rejects_report_path_colliding_with_planned_output_case_insensitive(
    tmp_path: Path,
) -> None:
    """P1 regression (Copilot review cycle 4 follow-up round, finding
    htTX0): the --report collision check (finding qAsu) must apply the
    same case-insensitive-filesystem normalization as the destination
    collision check, since the documented operator target is Windows.
    ``--report <dest>/hcp-docs/INDEX.MD`` must be rejected exactly like
    the same-case ``index.md`` collision above, even though the two
    strings differ.
    """
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)
    (product_dir / "index.mdx").write_text("# ok\n", encoding="utf-8")

    dest = tmp_path / "dest"
    colliding_report = dest / "hcp-docs" / "INDEX.MD"

    result = _run_cli(
        [
            "--source",
            str(source),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(colliding_report),
        ]
    )
    assert result.returncode == hashicorp_mdx_normalize.EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT
    assert not dest.exists(), "--dest must never be claimed/created when --report collides"
    assert "collides" in result.stderr.lower() or "planned corpus output" in result.stderr.lower()


def test_guard_write_path_rejects_paths_outside_dest(tmp_path: Path) -> None:
    """Unit-level containment guard check -- no actual I/O is attempted on rejection."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("docline_hashicorp_mdx_normalize", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["docline_hashicorp_mdx_normalize"] = module
    spec.loader.exec_module(module)

    dest_root = tmp_path / "dest"
    outside = tmp_path / "sibling" / "escaped.md"
    with pytest.raises(module.ContainmentViolation):
        module.guard_write_path(dest_root, outside)
    assert not outside.exists()
    assert not outside.parent.exists()

    inside = dest_root / "nested" / "ok.md"
    resolved = module.guard_write_path(dest_root, inside)
    assert resolved == inside.resolve()


def test_execute_preserves_frontmatter_byte_exact_on_crlf_source(tmp_path: Path) -> None:
    """P2 regression (finding p8Ph, Copilot review cycle 4): on Windows,
    ``Path.read_text()``/``Path.write_text()`` perform universal-newline
    translation by default, silently rewriting a source file's CRLF
    frontmatter delimiters to LF before a single transform runs, and then
    re-translating the (now-LF) body back to CRLF on write -- corrupting
    the "frontmatter preserved verbatim" contract the very first time a
    real CRLF source file is processed. ``--execute`` must instead
    preserve the frontmatter block byte-for-byte, exactly as the source
    wrote it, regardless of the host platform's newline convention.
    """
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)

    frontmatter = b"---\r\npage_title: CRLF Frontmatter\r\ndescription: exact bytes\r\n---\r\n"
    body = b"# Heading\n\nSome body text.\n"
    (product_dir / "index.mdx").write_bytes(frontmatter + body)

    dest = tmp_path / "dest"
    hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=True)

    output_bytes = (dest / "hcp-docs" / "index.md").read_bytes()
    assert output_bytes.startswith(frontmatter), (
        "frontmatter block (including its CRLF line endings) must survive "
        "the full read/transform/write round trip byte-for-byte"
    )
    # The body is intentionally re-normalized to bare \n regardless of the
    # source's original convention (documented narrowing) -- it must not
    # retain any \r, and it must not be silently dropped either.
    body_bytes = output_bytes[len(frontmatter) :]
    assert b"\r" not in body_bytes
    assert b"Heading" in body_bytes


def test_execute_preserves_frontmatter_byte_exact_on_lf_source(tmp_path: Path) -> None:
    """Companion case for p8Ph: a plain LF-only source file's frontmatter
    must ALSO survive byte-for-byte (i.e. the fix must not introduce a
    regression -- or accidentally inject CRLF -- for the common non-Windows
    source-file case)."""
    source = tmp_path / "source"
    product_dir = source / "hcp-docs"
    product_dir.mkdir(parents=True)

    frontmatter = b"---\npage_title: LF Frontmatter\n---\n"
    body = b"# Heading\n"
    (product_dir / "index.mdx").write_bytes(frontmatter + body)

    dest = tmp_path / "dest"
    hashicorp_mdx_normalize.process_corpus(source=source, dest=dest, execute=True)

    output_bytes = (dest / "hcp-docs" / "index.md").read_bytes()
    assert output_bytes.startswith(frontmatter)
    assert b"\r" not in output_bytes


# ---------------------------------------------------------------------------
# D.T3 -- full-corpus read-only dry-run integration test against the REAL
# external corpus. Skips cleanly when the corpus is absent on this machine.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_real_corpus_dry_run_zero_writes_and_coverage_report(tmp_path: Path) -> None:
    if not _REAL_CORPUS.is_dir():
        pytest.skip(f"real external corpus not present at {_REAL_CORPUS}")

    dest = tmp_path / "dest-would-be-external"
    report_path = tmp_path / "real-corpus-report.json"
    result = _run_cli(
        [
            "--source",
            str(_REAL_CORPUS),
            "--dest",
            str(dest),
            "--report",
            str(report_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert not dest.exists(), "dry-run must perform zero writes, including against the real corpus"
    # P1 regression (review-fix cycle 1): dry-run never writes the --report
    # file either -- the JSON plan is only ever available on stdout.
    assert not report_path.exists()

    report = json.loads(result.stdout)
    assert report["execute"] is False

    products = report["products"]
    # Live-verified findings (see requirements-evidence doc for the full narrative):
    assert products["vault"]["selected_version"] == "v2.x"
    assert products["terraform"]["selected_version"] == "v1.16.x"
    assert products["terraform-policy"]["selected_version"] == "v0.2.x (beta)"
    # Correction vs. the plan's assumed v202507-1: the real corpus's semver-style
    # directories (1.0.x/1.1.x/1.2.x/2.0.x) postdate every date-based release.
    assert products["terraform-enterprise"]["selected_version"] == "2.0.x"

    assert len(products) == 23
    versioned_count = sum(1 for p in products.values() if p["versioned"])
    unversioned_count = sum(1 for p in products.values() if not p["versioned"])
    assert versioned_count == 19
    assert unversioned_count == 4

    assert "global" in report["excluded_top_level_dirs"]
    assert isinstance(report["fallback_constructs"], dict)
    assert isinstance(report["ambiguous_tokens"], dict)
    # P3 regression (review-fix cycle 2, finding 5): the live corpus must
    # have ZERO genuine unresolved MDX constructs, not merely "some dict" --
    # this was the "aim for zero" bar the review-fix cycle 1 grounded
    # registry expansion was meant to satisfy (requirements-evidence doc §9.5).
    #
    # Updated in review-fix cycle 4 (Copilot finding qAsc, PR 192): removing
    # classify_remaining_constructs()'s unsafe `if name in
    # _KNOWN_HANDLED_TAGS: continue` skip made the classifier accurate --
    # and, as a direct consequence, revealed that this "== {}" bar was ONLY
    # ever passing because that skip was silently hiding real residue for
    # any tag name the transform pipeline sometimes fails to fully consume.
    # The four counts below are the classifier's now-honest baseline against
    # the live corpus: a list-item-indented <Note>, a mid-sentence-embedded
    # <EnterpriseAlert inline />, a bare self-closing <Warning/>, and an
    # attribute-shape-mismatched <VideoEmbed url="..."> (8 occurrences, one
    # file). None of these four share qAsc's root cause (nested same-tag
    # elements defeating a non-greedy regex, covered by its own synthetic
    # regression test) and closing them is deliberately deferred as
    # out-of-scope for this cycle per P-021 C1/C2 -- see stash entry
    # 7F80C39E for the full analysis. This assertion is intentionally
    # precise (not just type-checked) so it still catches any further
    # regression -- or any accidental improvement -- against this documented
    # baseline.
    assert report["unresolved_constructs"] == {
        "EnterpriseAlert": 12,
        "Note": 1,
        "VideoEmbed": 8,
        "Warning": 2,
    }
    assert report["containment_violations"] == []

    # Persist the real coverage report to a repo-local, git-ignored path so it
    # can be cited as requirements evidence without polluting the repo tree.
    evidence_dir = _REPO_ROOT / "build" / "hashicorp-dryrun-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "real-corpus-dry-run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
