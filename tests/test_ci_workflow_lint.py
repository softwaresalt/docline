"""Workflow lint tests for .github/workflows/ci.yml.

These tests assert structural invariants of the CI workflow so that
accidental regressions (matrix removal, fail-fast inversion, runs-on
drift) are caught in the local test suite.

The CI workflow OS coverage was reduced to ``ubuntu-latest`` only on
2026-06-10 as a cost-conservation measure after the 3,000-minute
private-repo allotment was exhausted (see ``.github/workflows/ci.yml``
header comment for the rationale). The matrix is preserved as a
structural feature so cost-reduction items #1 (macos) and #2 (windows)
can be reverted by re-adding entries without touching the workflow's
shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_OS_TARGETS = {"ubuntu-latest"}
UBUNTU_ONLY_JOBS = {"lint", "format", "typecheck", "build"}
TOPOLOGY_JOB = "topology-check"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert CI_WORKFLOW.exists(), f"missing {CI_WORKFLOW}"
    with CI_WORKFLOW.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_ci_workflow_has_test_job(workflow: dict) -> None:
    """ci.yml declares a `test` job."""
    assert "jobs" in workflow, "ci.yml must declare jobs"
    assert "test" in workflow["jobs"], "ci.yml must declare a test job"


def test_test_job_runs_on_matrix(workflow: dict) -> None:
    """The test job declares a strategy matrix over `os`."""
    test_job = workflow["jobs"]["test"]
    assert "strategy" in test_job, "test job must declare a strategy"
    matrix = test_job["strategy"].get("matrix")
    assert isinstance(matrix, dict), "test job strategy must include a matrix"
    assert "os" in matrix, "test job matrix must enumerate os"


def test_test_job_matrix_matches_expected_oses(workflow: dict) -> None:
    """The matrix covers the configured OS targets.

    Currently ``{ubuntu-latest}`` only after the 2026-06-10 cost-conservation
    change. Re-adding ``windows-latest`` and/or ``macos-latest`` requires
    updating ``EXPECTED_OS_TARGETS`` above and the cost-reduction tracker
    comment block at the top of ``.github/workflows/ci.yml``.
    """
    matrix_os = workflow["jobs"]["test"]["strategy"]["matrix"]["os"]
    assert set(matrix_os) == EXPECTED_OS_TARGETS, (
        f"expected matrix os {EXPECTED_OS_TARGETS}, got {set(matrix_os)}"
    )


def test_test_job_fail_fast_disabled(workflow: dict) -> None:
    """The test job sets fail-fast: false so per-OS failures don't cancel siblings.

    Preserved even though the matrix is currently single-OS, so re-adding
    OS entries doesn't require revisiting the fail-fast policy.
    """
    strategy = workflow["jobs"]["test"]["strategy"]
    assert strategy.get("fail-fast") is False, (
        "test job strategy must set fail-fast: false so a single-platform failure "
        "does not cancel the others (preserved for matrix re-expansion)"
    )


def test_test_job_runs_on_matrix_os(workflow: dict) -> None:
    """The test job's runs-on interpolates the matrix.os value."""
    runs_on = workflow["jobs"]["test"]["runs-on"]
    assert runs_on == "${{ matrix.os }}", (
        f"test job runs-on must interpolate matrix.os, got {runs_on!r}"
    )


@pytest.mark.parametrize("job_name", sorted(UBUNTU_ONLY_JOBS))
def test_non_test_jobs_remain_ubuntu_only(workflow: dict, job_name: str) -> None:
    """Non-test jobs stay on ubuntu-latest and do not declare an OS matrix."""
    job = workflow["jobs"].get(job_name)
    assert job is not None, f"ci.yml must declare {job_name} job"
    assert job["runs-on"] == "ubuntu-latest", f"{job_name} job must remain on ubuntu-latest"
    assert "strategy" not in job or "matrix" not in job.get("strategy", {}), (
        f"{job_name} job must not declare an OS matrix"
    )


def test_topology_check_job_exists(workflow: dict) -> None:
    """ci.yml declares the pipeline-topology backstop job."""
    assert TOPOLOGY_JOB in workflow["jobs"], (
        f"ci.yml must declare a {TOPOLOGY_JOB} job (autoharness pipeline-topology backstop)"
    )


def test_topology_check_is_ungated_by_changes(workflow: dict) -> None:
    """The topology backstop runs on every commit, not just code changes.

    The backstop guards harness/pipeline topology, which lives in Markdown and
    config that the `changes` path filter deliberately classifies as docs-only.
    Gating it behind `changes` would let a topology regression land unchecked.
    """
    job = workflow["jobs"][TOPOLOGY_JOB]
    needs = job.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "changes" not in needs, (
        f"{TOPOLOGY_JOB} must not depend on the changes job; it must run unconditionally"
    )
    assert "if" not in job, (
        f"{TOPOLOGY_JOB} must not declare an `if` condition; it must run unconditionally"
    )


def test_topology_check_required_by_ci_gate(workflow: dict) -> None:
    """`ci gate` depends on the topology backstop and aggregates its result."""
    gate = workflow["jobs"]["ci-gate"]
    assert TOPOLOGY_JOB in gate["needs"], (
        f"ci-gate.needs must include {TOPOLOGY_JOB} so the backstop cannot be silently dropped"
    )
    steps = gate["steps"]
    aggregated = "\n".join(step.get("run", "") for step in steps)
    assert f"needs['{TOPOLOGY_JOB}'].result" in aggregated, (
        f"ci-gate must aggregate needs['{TOPOLOGY_JOB}'].result; a needs entry alone "
        "does not fail the gate when the backstop fails"
    )


def test_topology_check_pins_autoharness_version(workflow: dict) -> None:
    """The backstop installs a pinned autoharness release, not floating latest."""
    steps = workflow["jobs"][TOPOLOGY_JOB]["steps"]
    installs = [s.get("run", "") for s in steps if "pip install autoharness" in s.get("run", "")]
    assert installs, f"{TOPOLOGY_JOB} must install autoharness"
    for command in installs:
        assert "autoharness==" in command, (
            "autoharness must be version-pinned so an upstream release cannot change "
            f"the topology verdict for an unchanged commit, got {command.strip()!r}"
        )
