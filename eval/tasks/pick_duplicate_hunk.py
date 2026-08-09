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

_VALIDATE_LINE: Final = "        validate(message)"
_HANDLER_TEMPLATE: Final = (
    "def {name}(batch):\n"
    "    for message in batch:\n"
    "        log(message)\n"
    "        decode(message)\n"
    "{validate}"
    "        process(message)\n"
    "        ack(message)\n"
    "        done(message)\n"
)


def _handlers(*, orders_validated: bool, refunds_validated: bool) -> str:
    def handler(name: str, validated: bool) -> str:
        validate = f"{_VALIDATE_LINE}\n" if validated else ""
        return _HANDLER_TEMPLATE.format(name=name, validate=validate)

    return (
        handler("handle_orders", orders_validated)
        + "\n\n"
        + handler("handle_refunds", refunds_validated)
    )


_ALL_VALIDATED: Final = _handlers(orders_validated=True, refunds_validated=True)


def _build(repo: GitRepo) -> None:
    repo.write_file(
        name="handlers.py",
        content=_handlers(orders_validated=False, refunds_validated=False),
    )
    repo.git("add", "handlers.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="handlers.py", content=_ALL_VALIDATED)


def _find_hunk_under(repo: GitRepo, function_line: str) -> str:
    # Disambiguating the twins relies on git's default funcname heading
    # heuristic filling context_before with the unindented def line above
    # each hunk; the fixture's layout is load-bearing for that.
    for hunk in list_hunks(repo, "handlers.py"):
        context = hunk["context_before"]
        if context is not None and context.get("text") == function_line:
            if hunk["id_stability"] != "conditional":
                raise RuntimeError("handlers.py no longer holds a Duplicate Hunk group")
            return str(hunk["id"])
    raise RuntimeError(f"no hunk in handlers.py sits under {function_line!r}")


def _golden(repo: GitRepo) -> None:
    run_git_hunk(
        repo,
        "commit",
        _find_hunk_under(repo, "def handle_orders(batch):"),
        "-m",
        "Validate order messages",
    )


def _commit_wrong_duplicate(repo: GitRepo) -> None:
    run_git_hunk(
        repo,
        "commit",
        _find_hunk_under(repo, "def handle_refunds(batch):"),
        "-m",
        "Validate order messages",
    )


def _commit_both_duplicates(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "handlers.py")
    repo.git("commit", "-m", "Validate order messages")


def _discard_refunds_duplicate(repo: GitRepo) -> None:
    _golden(repo)
    run_git_hunk(repo, "discard", "handlers.py")


_VALIDATION: Final = CommitSpec(
    label="validation",
    changes=frozenset(
        {ChangedLine(path="handlers.py", op="+", content=_VALIDATE_LINE)}
    ),
)
_EXPECTED_HEAD: Final = frozenset(
    {
        make_file(
            path="handlers.py",
            content=_handlers(orders_validated=True, refunds_validated=False),
        )
    }
)
_EXPECTED_WORKTREE: Final = frozenset(
    {make_file(path="handlers.py", content=_ALL_VALIDATED)}
)

SCENARIO: Final = Scenario(
    task=Task(
        name="pick_duplicate_hunk",
        build=_build,
        commits=(_VALIDATION,),
        expected_state=RepositoryState(
            head=_EXPECTED_HEAD,
            worktree=_EXPECTED_WORKTREE,
        ),
        prompt=(
            "The validation added to handle_orders is ready to ship. The "
            "identical change in handle_refunds belongs to unfinished work: "
            "keep it in the working tree. Commit only the handle_orders change."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("final-tree", _commit_wrong_duplicate),
        ("final-tree", _commit_both_duplicates),
        ("leftover-worktree", _discard_refunds_duplicate),
    ),
)
