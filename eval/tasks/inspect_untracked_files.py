from typing import Final

from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task
from eval.task import make_file

_BASE: Final = make_file(path="README.md", content="Invoice totals\n")
_RELATED: Final = {
    "batch_a.py": (
        "def total(invoices):\n"
        "    return sum(row['amount'] for row in invoices if not row['cancelled'])\n"
    ),
    "test_batch.py": (
        "from batch_a import total\n\n\n"
        "def test_cancelled_invoices_do_not_count():\n"
        "    assert total([{'amount': 20, 'cancelled': True},\n"
        "                  {'amount': 5, 'cancelled': False}]) == 5\n"
    ),
}
_DRAFT: Final = make_file(
    path="batch_b.py",
    content=(
        "def retry_delay(attempt):\n    return attempt * 5  # Still experimenting.\n"
    ),
)


def _build(repo: GitRepo, /) -> None:
    repo.write_file(name=_BASE.path, content=_BASE.content)
    repo.git("add", _BASE.path)
    repo.git("commit", "-m", "Initial state")
    for path, content in _RELATED.items():
        repo.write_file(name=path, content=content)
    repo.write_file(name=_DRAFT.path, content=_DRAFT.content)


def _golden(repo: GitRepo, /) -> None:
    run_git_hunk(
        repo, "commit", *_RELATED, "-m", "Exclude cancelled invoices from totals"
    )


def _commit_everything(repo: GitRepo, /) -> None:
    run_git_hunk(repo, "commit", *_RELATED, _DRAFT.path, "-m", "Update invoices")


def _commit_the_wrong_module(repo: GitRepo, /) -> None:
    run_git_hunk(repo, "commit", _DRAFT.path, "test_batch.py", "-m", "Update invoices")


def _omit_the_test(repo: GitRepo, /) -> None:
    run_git_hunk(repo, "commit", "batch_a.py", "-m", "Update invoices")


def _stage_the_draft(repo: GitRepo, /) -> None:
    _golden(repo)
    run_git_hunk(repo, "stage", _DRAFT.path)


def _delete_the_draft(repo: GitRepo, /) -> None:
    _golden(repo)
    (repo.path / _DRAFT.path).unlink()


_FINAL_FILES: Final = frozenset(
    {
        _BASE,
        *(make_file(path=path, content=content) for path, content in _RELATED.items()),
    }
)

SCENARIO: Final = Scenario(
    task=Task(
        name="inspect_untracked_files",
        build=_build,
        commits=(
            CommitSpec(
                label="cancelled-invoices",
                changes=frozenset(
                    ChangedLine(path=path, op="+", content=line)
                    for path, content in _RELATED.items()
                    for line in content.splitlines()
                ),
            ),
        ),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
            untracked=frozenset({_DRAFT}),
        ),
        prompt=(
            "Commit the completed change that excludes cancelled invoices from "
            "totals, together with its test, as one focused commit. Leave the "
            "unrelated retry experiment unchanged and untracked."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("partition", _commit_everything),
        ("partition", _commit_the_wrong_module),
        ("partition", _omit_the_test),
        ("leftover-index", _stage_the_draft),
        ("leftover-untracked", _delete_the_draft),
    ),
)
