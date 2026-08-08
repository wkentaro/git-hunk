from typing import Final

import pytest

from eval.grader import FailureReason
from eval.grader import Result
from eval.grader import grade
from eval.repo import GitRepo
from eval.scenario import Solver
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file
from eval.tasks import SCENARIOS

_FAILURE_CASES: Final = {
    reason: (scenario.task, solver)
    for scenario in SCENARIOS
    for reason, solver in scenario.adversarial
}
_FAILURE_PARAMS: Final = [
    pytest.param(task, solver, reason, id=reason)
    for reason, (task, solver) in _FAILURE_CASES.items()
]


@pytest.mark.parametrize(
    ("passed", "reason"),
    [(False, None), (True, "order")],
    ids=["failed-without-reason", "passed-with-reason"],
)
def test_result_requires_a_failure_reason_exactly_when_it_failed(
    passed: bool,
    reason: FailureReason | None,
) -> None:
    with pytest.raises(ValueError, match="if and only if it failed"):
        Result(passed=passed, reason=reason)


def test_grade_accepts_exact_repository_state(eval_repo: GitRepo) -> None:
    eval_repo.write_file(name="a.py", content="old\n")
    eval_repo.git("add", "a.py")
    eval_repo.git("commit", "-m", "Initial state")
    base = eval_repo.git("rev-parse", "HEAD").strip()
    eval_repo.write_file(name="a.py", content="new\n")
    eval_repo.git("add", "a.py")
    eval_repo.git("commit", "-m", "Update value")
    expected_file = make_file(path="a.py", content="new\n")
    task = Task(
        name="exact-state",
        build=lambda repo: None,
        commits=(
            CommitSpec(
                label="update",
                changes=frozenset(
                    {
                        ChangedLine(path="a.py", op="-", content="old"),
                        ChangedLine(path="a.py", op="+", content="new"),
                    }
                ),
            ),
        ),
        expected_state=RepositoryState(
            head=frozenset({expected_file}),
            worktree=frozenset({expected_file}),
        ),
    )

    assert grade(repo=eval_repo, task=task, base=base).passed


@pytest.mark.parametrize("task,solver,expected_reason", _FAILURE_PARAMS)
def test_grade_reports_each_repository_failure_reason(
    eval_repo: GitRepo,
    task: Task,
    solver: Solver,
    expected_reason: FailureReason,
) -> None:
    task.build(eval_repo)
    base = eval_repo.git("rev-parse", "HEAD").strip()
    solver(eval_repo)

    result = grade(repo=eval_repo, task=task, base=base)

    assert result.reason == expected_reason
    assert result.detail


def test_failure_cases_cover_every_repository_boundary() -> None:
    assert set(_FAILURE_CASES) == {
        "partition",
        "order",
        "final-tree",
        "leftover-index",
        "leftover-worktree",
        "leftover-untracked",
    }
