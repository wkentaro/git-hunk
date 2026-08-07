import subprocess
from pathlib import Path
from typing import Final

import pytest

from eval.harness import run_and_grade
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.scenario import Solver
from eval.task import Task
from eval.tasks import SCENARIOS

_GOLDEN: Final = [
    pytest.param(scenario, id=scenario.task.name) for scenario in SCENARIOS
]
_ADVERSARIAL: Final = [
    pytest.param(
        scenario.task,
        solver,
        reason,
        id=f"{scenario.task.name}-{reason}",
    )
    for scenario in SCENARIOS
    for reason, solver in scenario.adversarial
]


@pytest.mark.parametrize("scenario", _GOLDEN)
def test_golden_solver_passes(scenario: Scenario) -> None:
    result = run_and_grade(task=scenario.task, solver=scenario.golden)

    assert result.passed, result.detail


@pytest.mark.parametrize("task,solver,expected_reason", _ADVERSARIAL)
def test_adversarial_solver_fails_at_expected_boundary(
    task: Task, solver: Solver, expected_reason: str
) -> None:
    result = run_and_grade(task=task, solver=solver)

    assert not result.passed
    assert result.reason == expected_reason
    assert result.detail


def test_solver_error_is_a_failed_result() -> None:
    def fail(repo: GitRepo) -> None:
        raise RuntimeError("solver stopped")

    result = run_and_grade(task=SCENARIOS[0].task, solver=fail)

    assert not result.passed
    assert result.reason == "solver-error"
    assert result.detail == "solver stopped"


def test_drop_debug_golden_ignores_global_autocrlf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_config = tmp_path / "gitconfig"
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(global_config),
            "core.autocrlf",
            "true",
        ],
        capture_output=True,
        check=True,
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    scenario = next(
        scenario for scenario in SCENARIOS if scenario.task.name == "drop_debug_lines"
    )

    result = run_and_grade(task=scenario.task, solver=scenario.golden)

    assert result.passed, result.detail
