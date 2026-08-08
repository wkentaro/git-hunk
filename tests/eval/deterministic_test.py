import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Final

import pytest

import eval.harness as eval_harness
from eval.harness import prepare_task
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


def test_prepared_task_reuses_exact_initial_repository() -> None:
    scenario = SCENARIOS[0]
    initial_repositories: list[tuple[Path, str, str]] = []

    def record_and_solve(repo: GitRepo) -> None:
        initial_repositories.append(
            (
                repo.path,
                repo.git("rev-parse", "HEAD").strip(),
                repo.git("status", "--porcelain=v1", "--untracked-files=all"),
            )
        )
        scenario.golden(repo)

    with prepare_task(scenario.task) as prepared:
        first = prepared.run_and_grade(record_and_solve)
        second = prepared.run_and_grade(record_and_solve)

    assert first.passed, first.detail
    assert second.passed, second.detail
    assert initial_repositories[0] == initial_repositories[1]


def test_prepared_task_replaces_windows_readonly_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_shutil = eval_harness.shutil

    def windows_rmtree(
        path: str | Path,
        ignore_errors: bool = False,
        onerror: Callable[..., object] | None = None,
    ) -> None:
        checkout_path = Path(path)
        if checkout_path.name != "checkout":
            real_shutil.rmtree(path, ignore_errors=ignore_errors, onerror=onerror)
            return
        object_path = next(
            path
            for path in (checkout_path / ".git" / "objects").rglob("*")
            if path.is_file()
        )
        object_path.chmod(stat.S_IREAD)
        if onerror is None:
            raise PermissionError(object_path)

        def unlink_readonly(path: str) -> None:
            if not os.stat(path).st_mode & stat.S_IWRITE:
                raise PermissionError(path)
            os.unlink(path)

        try:
            raise PermissionError(object_path)
        except PermissionError:
            onerror(unlink_readonly, str(object_path), sys.exc_info())
        real_shutil.rmtree(path, ignore_errors=ignore_errors, onerror=onerror)

    monkeypatch.setattr(
        eval_harness,
        "shutil",
        SimpleNamespace(rmtree=windows_rmtree, copytree=real_shutil.copytree),
    )
    scenario = SCENARIOS[0]

    with prepare_task(scenario.task) as prepared:
        first = prepared.run_and_grade(scenario.golden)
        second = prepared.run_and_grade(scenario.golden)

    assert first.passed, first.detail
    assert second.passed, second.detail


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
