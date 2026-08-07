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


def _build(repo: GitRepo) -> None:
    BASE: Final = (
        "def process(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item\n"
        "    return total\n"
    )
    DIRTY: Final = (
        "def process(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        '        print("DEBUG", item)\n'
        "        total += item\n"
        "    return total * 2\n"
    )
    repo.write_file(name="a.py", content=BASE)
    repo.git("add", "a.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="a.py", content=DIRTY)


def _commit_without_debug(repo: GitRepo) -> None:
    DEBUG: Final = 'print("DEBUG"'
    (hunk,) = list_hunks(repo, "a.py")
    run_git_hunk(
        repo,
        "stage",
        str(hunk["id"]),
        "--exclude-matching",
        DEBUG,
    )
    repo.git("commit", "-m", "Double item totals")


def _golden(repo: GitRepo) -> None:
    _commit_without_debug(repo)
    run_git_hunk(repo, "discard", "a.py")


def _commit_including_debug(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "a.py")
    repo.git("commit", "-m", "Double item totals")


def _forget_to_drop_debug(repo: GitRepo) -> None:
    _commit_without_debug(repo)


_FEATURE: Final = CommitSpec(
    label="feature",
    changes=frozenset(
        {
            ChangedLine(path="a.py", op="-", content="    return total"),
            ChangedLine(path="a.py", op="+", content="    return total * 2"),
        }
    ),
)
_FINAL_FILES: Final = frozenset(
    {
        make_file(
            path="a.py",
            content=(
                "def process(items):\n"
                "    total = 0\n"
                "    for item in items:\n"
                "        total += item\n"
                "    return total * 2\n"
            ),
        )
    }
)

SCENARIO: Final = Scenario(
    task=Task(
        name="drop_debug_lines",
        build=_build,
        commits=(_FEATURE,),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
        prompt=(
            "Some changes are temporary debug statements. Drop those statements "
            "instead of committing them."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("partition", _commit_including_debug),
        ("leftover-worktree", _forget_to_drop_debug),
    ),
)
