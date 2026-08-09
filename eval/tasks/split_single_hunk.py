from typing import Final

from eval.harness import list_hunks
from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file

_TEMPLATE: Final = (
    "def total(items):\n"
    "    result = 0\n"
    "    for item in items:\n"
    "{accumulate}\n"
    "    tax = result * 0.1\n"
    "{return_line}\n"
)
_FINAL: Final = _TEMPLATE.format(
    accumulate="        result += item.price * item.qty",
    return_line="    return round(result + tax, 2)",
)


def _build(repo: GitRepo) -> None:
    BASE: Final = _TEMPLATE.format(
        accumulate="        result += item.price",
        return_line="    return result + tax",
    )
    repo.write_file(name="total.py", content=BASE)
    repo.git("add", "total.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="total.py", content=_FINAL)


def _commit_fix(repo: GitRepo, *, match: str) -> None:
    (hunk,) = list_hunks(repo, "total.py")
    run_git_hunk(
        repo,
        "commit",
        str(hunk["id"]),
        "--include-matching",
        match,
        "-m",
        "Multiply price by quantity",
    )


def _golden(repo: GitRepo) -> None:
    _commit_fix(repo, match="item.price")
    run_git_hunk(repo, "commit", "total.py", "-m", "Round the returned total")


def _squash_into_one_commit(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "total.py")
    repo.git("commit", "-m", "Fix totals")


def _commit_one_sided_match(repo: GitRepo) -> None:
    _commit_fix(repo, match="item.price * item.qty")
    run_git_hunk(repo, "commit", "total.py", "-m", "Round the returned total")


_FIX: Final = CommitSpec(
    label="fix",
    changes=frozenset(
        {
            ChangedLine(
                path="total.py", op="-", content="        result += item.price"
            ),
            ChangedLine(
                path="total.py",
                op="+",
                content="        result += item.price * item.qty",
            ),
        }
    ),
)
_ROUNDING: Final = CommitSpec(
    label="rounding",
    changes=frozenset(
        {
            ChangedLine(path="total.py", op="-", content="    return result + tax"),
            ChangedLine(
                path="total.py",
                op="+",
                content="    return round(result + tax, 2)",
            ),
        }
    ),
)
_FINAL_FILES: Final = frozenset({make_file(path="total.py", content=_FINAL)})

SCENARIO: Final = Scenario(
    task=Task(
        name="split_single_hunk",
        build=_build,
        commits=(_FIX, _ROUNDING),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
        prompt=(
            "The changes mix a price calculation fix with new rounding "
            "behavior. Commit each change separately."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("partition", _squash_into_one_commit),
        ("partition", _commit_one_sided_match),
    ),
)
