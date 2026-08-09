from typing import Final

from eval.harness import find_hunk
from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file

_TEMPLATE: Final = (
    "import os\n\n\n"
    "def read_config():\n"
    "{read_config}\n\n\n"
    "def helper_one():\n    return 1\n\n\n"
    "def helper_two():\n    return 2\n\n\n"
    "def write_log(msg):\n"
    "{write_log}\n"
)
_FINAL: Final = _TEMPLATE.format(
    read_config='    return os.environ.get("CONFIG", "default")',
    write_log='    print("LOG: " + msg)',
)


def _build(repo: GitRepo) -> None:
    BASE: Final = _TEMPLATE.format(
        read_config='    return os.environ.get("CONFIG")',
        write_log="    print(msg)",
    )
    repo.write_file(name="a.py", content=BASE)
    repo.git("add", "a.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="a.py", content=_FINAL)


def _golden(repo: GitRepo) -> None:
    run_git_hunk(
        repo,
        "commit",
        find_hunk(repo, "a.py", "CONFIG"),
        "-m",
        "Default config",
    )
    run_git_hunk(
        repo,
        "commit",
        find_hunk(repo, "a.py", "LOG:"),
        "-m",
        "Prefix log output",
    )


def _squash_into_one_commit(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "a.py")
    repo.git("commit", "-m", "Update configuration and logging")


_CONFIG: Final = CommitSpec(
    label="config",
    changes=frozenset(
        {
            ChangedLine(
                path="a.py",
                op="-",
                content='    return os.environ.get("CONFIG")',
            ),
            ChangedLine(
                path="a.py",
                op="+",
                content='    return os.environ.get("CONFIG", "default")',
            ),
        }
    ),
)
_LOG: Final = CommitSpec(
    label="log",
    changes=frozenset(
        {
            ChangedLine(path="a.py", op="-", content="    print(msg)"),
            ChangedLine(path="a.py", op="+", content='    print("LOG: " + msg)'),
        }
    ),
)
_FINAL_FILES: Final = frozenset({make_file(path="a.py", content=_FINAL)})

SCENARIO: Final = Scenario(
    task=Task(
        name="separate_mixed_hunks",
        build=_build,
        commits=(_CONFIG, _LOG),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
    ),
    golden=_golden,
    adversarial=(("partition", _squash_into_one_commit),),
)
