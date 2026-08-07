from typing import Final

from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file

_FINAL_HELPER: Final = 'def greet(who):\n    return "hi " + who\n'
_FINAL_APP: Final = (
    "from helper import greet\n\n\ndef main():\n"
    '    print(greet("world"))\n    print(greet("there"))\n'
)


def _build(repo: GitRepo) -> None:
    BASE_HELPER: Final = 'def greet(name):\n    return "hi " + name\n'
    BASE_APP: Final = (
        'from helper import greet\n\n\ndef main():\n    print(greet("world"))\n'
    )
    repo.write_file(name="helper.py", content=BASE_HELPER)
    repo.write_file(name="app.py", content=BASE_APP)
    repo.git("add", "helper.py", "app.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="helper.py", content=_FINAL_HELPER)
    repo.write_file(name="app.py", content=_FINAL_APP)


def _golden(repo: GitRepo) -> None:
    run_git_hunk(repo, "commit", "helper.py", "-m", "Rename the greet parameter")
    run_git_hunk(repo, "commit", "app.py", "-m", "Add a second greeting")


def _commit_feature_before_refactor(repo: GitRepo) -> None:
    run_git_hunk(repo, "commit", "app.py", "-m", "Add a second greeting")
    run_git_hunk(repo, "commit", "helper.py", "-m", "Rename the greet parameter")


def _squash_into_one_commit(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "helper.py", "app.py")
    repo.git("commit", "-m", "Update greeting behavior")


def _duplicate_feature_line(repo: GitRepo) -> None:
    run_git_hunk(repo, "commit", "helper.py", "-m", "Rename the greet parameter")
    repo.write_file(
        name="app.py",
        content=_FINAL_APP + '    print(greet("there"))\n',
    )
    run_git_hunk(repo, "commit", "app.py", "-m", "Add a second greeting")


_REFACTOR: Final = CommitSpec(
    label="refactor",
    changes=frozenset(
        {
            ChangedLine(path="helper.py", op="-", content="def greet(name):"),
            ChangedLine(path="helper.py", op="+", content="def greet(who):"),
            ChangedLine(path="helper.py", op="-", content='    return "hi " + name'),
            ChangedLine(path="helper.py", op="+", content='    return "hi " + who'),
        }
    ),
)
_FEATURE: Final = CommitSpec(
    label="feature",
    changes=frozenset(
        {ChangedLine(path="app.py", op="+", content='    print(greet("there"))')}
    ),
)
_FINAL_FILES: Final = frozenset(
    {
        make_file(path="helper.py", content=_FINAL_HELPER),
        make_file(path="app.py", content=_FINAL_APP),
    }
)

SCENARIO: Final = Scenario(
    task=Task(
        name="split_refactor_vs_feature",
        build=_build,
        commits=(_REFACTOR, _FEATURE),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
        order_constraints=(("refactor", "feature"),),
    ),
    golden=_golden,
    adversarial=(
        ("order", _commit_feature_before_refactor),
        ("partition", _squash_into_one_commit),
        ("final-tree", _duplicate_feature_line),
    ),
)
