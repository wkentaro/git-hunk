import json
import tempfile
from typing import Any
from typing import cast

from eval.grader import Result
from eval.grader import grade
from eval.repo import GitRepo
from eval.repo import init_repo
from eval.scenario import Solver
from eval.task import Task


def run_and_grade(task: Task, solver: Solver) -> Result:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = init_repo(path=temp_dir)
        task.build(repo)
        base = repo.git("rev-parse", "HEAD").strip()
        try:
            solver(repo)
        except RuntimeError as error:
            return Result(
                passed=False,
                reason="solver-error",
                detail=str(error),
            )
        return grade(repo=repo, task=task, base=base)


def run_git_hunk(repo: GitRepo, *args: str) -> str:
    result = repo.run("git-hunk", *args)
    if result.returncode != 0:
        raise RuntimeError(f"git-hunk {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def list_hunks(repo: GitRepo, *file_paths: str) -> list[dict[str, Any]]:
    envelope = json.loads(run_git_hunk(repo, "list", "--json", *file_paths))
    return cast("list[dict[str, Any]]", envelope["hunks"])
