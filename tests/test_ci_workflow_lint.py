"""Workflow lint tests for .github/workflows/ci.yml.

These tests assert structural invariants of the CI workflow so that accidental
regressions (matrix removal, OS coverage shrink, fail-fast inversion) are caught
in the local test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_OS_TARGETS = {"ubuntu-latest", "windows-latest", "macos-latest"}
UBUNTU_ONLY_JOBS = {"lint", "format", "typecheck", "build"}


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert CI_WORKFLOW.exists(), f"missing {CI_WORKFLOW}"
    with CI_WORKFLOW.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_ci_workflow_has_test_job(workflow: dict) -> None:
    assert "jobs" in workflow, "ci.yml must declare jobs"
    assert "test" in workflow["jobs"], "ci.yml must declare a test job"


def test_test_job_runs_on_matrix(workflow: dict) -> None:
    test_job = workflow["jobs"]["test"]
    assert "strategy" in test_job, "test job must declare a strategy"
    matrix = test_job["strategy"].get("matrix")
    assert isinstance(matrix, dict), "test job strategy must include a matrix"
    assert "os" in matrix, "test job matrix must enumerate os"


def test_test_job_matrix_includes_three_oses(workflow: dict) -> None:
    matrix_os = workflow["jobs"]["test"]["strategy"]["matrix"]["os"]
    assert set(matrix_os) == EXPECTED_OS_TARGETS, (
        f"expected matrix os {EXPECTED_OS_TARGETS}, got {set(matrix_os)}"
    )


def test_test_job_fail_fast_disabled(workflow: dict) -> None:
    strategy = workflow["jobs"]["test"]["strategy"]
    assert strategy.get("fail-fast") is False, (
        "test job strategy must set fail-fast: false so a single-platform failure "
        "does not cancel the others"
    )


def test_test_job_runs_on_matrix_os(workflow: dict) -> None:
    runs_on = workflow["jobs"]["test"]["runs-on"]
    assert runs_on == "${{ matrix.os }}", (
        f"test job runs-on must interpolate matrix.os, got {runs_on!r}"
    )


@pytest.mark.parametrize("job_name", sorted(UBUNTU_ONLY_JOBS))
def test_non_test_jobs_remain_ubuntu_only(workflow: dict, job_name: str) -> None:
    job = workflow["jobs"].get(job_name)
    assert job is not None, f"ci.yml must declare {job_name} job"
    assert job["runs-on"] == "ubuntu-latest", f"{job_name} job must remain on ubuntu-latest"
    assert "strategy" not in job or "matrix" not in job.get("strategy", {}), (
        f"{job_name} job must not declare an OS matrix"
    )
