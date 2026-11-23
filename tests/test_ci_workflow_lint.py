"""Workflow lint tests for .github/workflows/ci.yml.

These tests assert structural invariants of the GSD-managed four-job CI
workflow (``changes``, ``expensive``, ``topology-check``, ``ci-gate``) so
accidental regressions (path-filter fail-open drift, missing quality gates,
runner drift, unpinned GSD runtime, or dropped gate aggregation) are caught
in the local test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_JOBS = {"changes", "expensive", "topology-check", "ci-gate"}
METADATA_ONLY_JOBS = {"changes", "ci-gate"}
WINDOWS_JOBS = {"expensive", "topology-check"}
TOPOLOGY_JOB = "topology-check"
REQUIRED_QUALITY_GATES = (
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run pyright src/",
    "uv run pytest",
    "uv run python -m build",
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert CI_WORKFLOW.exists(), f"missing {CI_WORKFLOW}"
    with CI_WORKFLOW.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_ci_workflow_declares_four_job_shape(workflow: dict) -> None:
    """ci.yml declares the GSD four-job pipeline shape."""
    assert "jobs" in workflow, "ci.yml must declare jobs"
    assert set(workflow["jobs"]) == EXPECTED_JOBS, (
        f"expected jobs {EXPECTED_JOBS}, got {set(workflow['jobs'])}"
    )


def test_changes_job_uses_fail_closed_paths_filter(workflow: dict) -> None:
    """The changes job uses dorny/paths-filter with predicate-quantifier every."""
    changes_job = workflow["jobs"]["changes"]
    filter_steps = [
        s for s in changes_job["steps"] if str(s.get("uses", "")).startswith("dorny/paths-filter@")
    ]
    assert filter_steps, "changes job must use dorny/paths-filter"
    step_with = filter_steps[0].get("with", {})
    assert step_with.get("predicate-quantifier") == "every", (
        "paths-filter must set predicate-quantifier: 'every' so negations fail closed"
    )
    filters = step_with.get("filters", "")
    for excluded in ("!docs/**", "!.backlogit/**", "!.gsd/**"):
        assert excluded in filters, f"changes filter must exclude {excluded}"


def test_expensive_job_gated_on_changes_and_runs_all_gates(workflow: dict) -> None:
    """The expensive job is gated on changes.outputs.code and runs all quality gates."""
    expensive = workflow["jobs"]["expensive"]
    needs = expensive.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "changes" in needs, "expensive job must depend on changes"
    assert expensive.get("if") == "needs.changes.outputs.code == 'true'", (
        "expensive job must run only when changes.outputs.code == 'true'"
    )
    run_commands = "\n".join(s.get("run", "") for s in expensive["steps"])
    for gate_cmd in REQUIRED_QUALITY_GATES:
        assert gate_cmd in run_commands, f"expensive job must run `{gate_cmd}`"


@pytest.mark.parametrize("job_name", sorted(METADATA_ONLY_JOBS))
def test_metadata_jobs_run_on_ubuntu_without_matrix(workflow: dict, job_name: str) -> None:
    """Metadata-only jobs run on ubuntu-latest without an OS matrix."""
    job = workflow["jobs"].get(job_name)
    assert job is not None, f"ci.yml must declare {job_name} job"
    assert job["runs-on"] == "ubuntu-latest", f"{job_name} job must run on ubuntu-latest"
    assert "strategy" not in job or "matrix" not in job.get("strategy", {}), (
        f"{job_name} job must not declare an OS matrix"
    )


@pytest.mark.parametrize("job_name", sorted(WINDOWS_JOBS))
def test_product_and_topology_jobs_run_on_windows(workflow: dict, job_name: str) -> None:
    """Product validation and GSD topology jobs run on windows-latest."""
    job = workflow["jobs"].get(job_name)
    assert job is not None, f"ci.yml must declare {job_name} job"
    assert job["runs-on"] == "windows-latest", f"{job_name} job must run on windows-latest"


def test_topology_check_job_exists(workflow: dict) -> None:
    """ci.yml declares the pipeline-topology backstop job."""
    assert TOPOLOGY_JOB in workflow["jobs"], (
        f"ci.yml must declare a {TOPOLOGY_JOB} job (GSD pipeline-topology backstop)"
    )


def test_topology_check_is_ungated_by_changes(workflow: dict) -> None:
    """The topology backstop runs on every commit, not just code changes."""
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
    """`ci gate` depends on all upstream jobs and aggregates their results."""
    gate = workflow["jobs"]["ci-gate"]
    assert gate.get("name") == "ci gate", "ci-gate job must report check name `ci gate`"
    assert gate.get("if") == "always()", "ci-gate must set if: always()"
    for dep in ("changes", "expensive", TOPOLOGY_JOB):
        assert dep in gate["needs"], f"ci-gate.needs must include {dep}"
    steps = gate["steps"]
    aggregated = "\n".join(step.get("run", "") for step in steps)
    assert "needs.changes.result" in aggregated
    assert "needs.expensive.result" in aggregated
    assert f"needs['{TOPOLOGY_JOB}'].result" in aggregated, (
        f"ci-gate must aggregate needs['{TOPOLOGY_JOB}'].result; a needs entry alone "
        "does not fail the gate when the backstop fails"
    )


def test_topology_check_pins_gsd_version_and_hashes(workflow: dict) -> None:
    """The topology backstop installs a version- and SHA-256-pinned GSD release."""
    steps = workflow["jobs"][TOPOLOGY_JOB]["steps"]
    install_runs = [s.get("run", "") for s in steps if "gsd.exe" in s.get("run", "")]
    assert install_runs, f"{TOPOLOGY_JOB} must install gsd.exe"
    script = "\n".join(install_runs)
    assert "$version = '" in script, "GSD install step must pin an explicit version"
    assert "$exeHash = '" in script, "GSD install step must pin gsd.exe SHA-256"
    assert "$bundleHash = '" in script, "GSD install step must pin gsd-assets.zip SHA-256"
    assert "Get-FileHash" in script, "GSD install step must verify downloaded hashes"
    assert any("ci-topology-check.sh" in s.get("run", "") for s in steps), (
        f"{TOPOLOGY_JOB} must run scripts/ci-topology-check.sh"
    )
