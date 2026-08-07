from typing import Final

from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file

_FINAL_FEATURE: Final = "def add(a, b):\n    return int(a) + int(b)\n"
_BASE_NOTES: Final = "todo: nothing yet\n"
_FINAL_NOTES: Final = "todo: write the parser\n"


def _build(repo: GitRepo) -> None:
    BASE_FEATURE: Final = "def add(a, b):\n    return a + b\n"
    repo.write_file(name="feature.py", content=BASE_FEATURE)
    repo.write_file(name="notes.txt", content=_BASE_NOTES)
    repo.git("add", "feature.py", "notes.txt")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="feature.py", content=_FINAL_FEATURE)
    repo.write_file(name="notes.txt", content=_FINAL_NOTES)


def _golden(repo: GitRepo) -> None:
    run_git_hunk(repo, "commit", "feature.py", "-m", "Coerce add operands to int")


def _commit_unrelated_work(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "feature.py", "notes.txt")
    repo.git("commit", "-m", "Coerce add operands to int")


def _stage_unrelated_work(repo: GitRepo) -> None:
    _golden(repo)
    run_git_hunk(repo, "stage", "notes.txt")


def _leave_intent_to_add(repo: GitRepo) -> None:
    _golden(repo)
    repo.write_file(name="scratch.bin", content=b"\x00\xff")
    repo.git("add", "--intent-to-add", "scratch.bin")


def _discard_unrelated_work(repo: GitRepo) -> None:
    _golden(repo)
    run_git_hunk(repo, "discard", "notes.txt")


def _leave_ignored_untracked_file(repo: GitRepo) -> None:
    _golden(repo)
    repo.write_file(name="scratch.bin", content=b"\x00\xff")
    repo.write_file(name=".git/info/exclude", content="scratch.bin\n")


_FEATURE: Final = CommitSpec(
    label="feature",
    changes=frozenset(
        {
            ChangedLine(path="feature.py", op="-", content="    return a + b"),
            ChangedLine(
                path="feature.py",
                op="+",
                content="    return int(a) + int(b)",
            ),
        }
    ),
)
_EXPECTED_HEAD: Final = frozenset(
    {
        make_file(path="feature.py", content=_FINAL_FEATURE),
        make_file(path="notes.txt", content=_BASE_NOTES),
    }
)
_EXPECTED_WORKTREE: Final = frozenset(
    {
        make_file(path="feature.py", content=_FINAL_FEATURE),
        make_file(path="notes.txt", content=_FINAL_NOTES),
    }
)

SCENARIO: Final = Scenario(
    task=Task(
        name="protect_unrelated_work",
        build=_build,
        commits=(_FEATURE,),
        expected_state=RepositoryState(
            head=_EXPECTED_HEAD,
            worktree=_EXPECTED_WORKTREE,
        ),
        prompt=(
            "Some changes are unrelated in-progress work. Keep them in the working "
            "tree. Commit only the coherent, complete change."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("partition", _commit_unrelated_work),
        ("leftover-index", _stage_unrelated_work),
        ("leftover-index", _leave_intent_to_add),
        ("leftover-worktree", _discard_unrelated_work),
        ("leftover-untracked", _leave_ignored_untracked_file),
    ),
)
