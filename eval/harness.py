import contextlib
import dataclasses
import json
import shutil
import stat
import tempfile
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any
from typing import cast

from eval.grader import SOLVER_ERROR
from eval.grader import Result
from eval.grader import grade
from eval.repo import GitRepo
from eval.repo import init_repo
from eval.scenario import Solver
from eval.task import Task


def _remove_readonly(
    function: Callable[..., object],
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    error = exc_info[1]
    if not isinstance(error, PermissionError):
        raise error
    file_path = Path(path)
    file_path.chmod(file_path.stat().st_mode | stat.S_IWRITE)
    function(path)


@dataclasses.dataclass(frozen=True)
class PreparedTask:
    task: Task
    snapshot_path: Path
    checkout_path: Path
    base: str

    def run_and_grade(self, solver: Solver) -> Result:
        if self.checkout_path.exists():
            shutil.rmtree(self.checkout_path, onerror=_remove_readonly)
        shutil.copytree(self.snapshot_path, self.checkout_path, symlinks=True)
        repo = GitRepo(self.checkout_path)
        try:
            solver(repo)
        except RuntimeError as error:
            return Result(
                passed=False,
                reason=SOLVER_ERROR,
                detail=str(error),
            )
        return grade(repo=repo, task=self.task, base=self.base)


@contextlib.contextmanager
def prepare_task(task: Task) -> Iterator[PreparedTask]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        snapshot_path = root / "snapshot"
        snapshot_path.mkdir()
        repo = init_repo(path=snapshot_path)
        task.build(repo)
        yield PreparedTask(
            task=task,
            snapshot_path=snapshot_path,
            checkout_path=root / "checkout",
            base=repo.git("rev-parse", "HEAD").strip(),
        )


def run_and_grade(task: Task, solver: Solver) -> Result:
    with prepare_task(task) as prepared:
        return prepared.run_and_grade(solver)


def run_git_hunk(repo: GitRepo, *args: str) -> str:
    result = repo.run("git-hunk", *args)
    if result.returncode != 0:
        raise RuntimeError(f"git-hunk {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def list_hunks(repo: GitRepo, *file_paths: str) -> list[dict[str, Any]]:
    envelope = json.loads(run_git_hunk(repo, "list", "--json", *file_paths))
    return cast("list[dict[str, Any]]", envelope["hunks"])


def find_hunk(repo: GitRepo, path: str, needle: str) -> str:
    # The needle is matched against the full `show` rendering, context lines
    # included, so pick text unique to the target hunk's changed lines.
    matches = [
        hunk_id
        for hunk in list_hunks(repo, path)
        if needle in run_git_hunk(repo, "show", hunk_id := str(hunk["id"]))
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{len(matches)} hunks in {path} contain {needle!r}, expected one"
        )
    return matches[0]
