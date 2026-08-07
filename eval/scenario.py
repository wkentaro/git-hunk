import dataclasses
from collections.abc import Callable

from eval.grader import FailureReason
from eval.repo import GitRepo
from eval.task import Task

Solver = Callable[[GitRepo], None]


@dataclasses.dataclass(frozen=True)
class Scenario:
    task: Task
    golden: Solver
    adversarial: tuple[tuple[FailureReason, Solver], ...]
