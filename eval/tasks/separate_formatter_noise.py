from typing import Final

from eval.harness import find_hunk
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
    "GREETING = {greeting}\n"
    "FAREWELL = {farewell}\n"
    "\n"
    "\n"
    "def make_session():\n"
    "    session = pool.session()\n"
    "    session.headers = default_headers()\n"
    "    return session\n"
    "\n"
    "\n"
    "def fetch(url):\n"
    "    session = make_session()\n"
    "{fetch}\n"
    "\n"
    "\n"
    "def greet(name):\n"
    "{greet_line}\n"
    "\n"
    "\n"
    "def farewell(name):\n"
    "{farewell_line}\n"
)
_FINAL: Final = _TEMPLATE.format(
    greeting='"hello"',
    farewell='"goodbye"',
    fetch="    return session.get(url, timeout=30)",
    greet_line='    return GREETING + ", " + name',
    farewell_line='    return FAREWELL + ", " + name',
)


def _build(repo: GitRepo) -> None:
    BASE: Final = _TEMPLATE.format(
        greeting="'hello'",
        farewell="'goodbye'",
        fetch="    return session.get(url)",
        greet_line="    return GREETING + ', ' + name",
        farewell_line="    return FAREWELL + ', ' + name",
    )
    repo.write_file(name="client.py", content=BASE)
    repo.git("add", "client.py")
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name="client.py", content=_FINAL)


def _golden(repo: GitRepo) -> None:
    fix_hunk = find_hunk(repo, "client.py", "session.get")
    if 'GREETING + ", "' not in run_git_hunk(repo, "show", fix_hunk):
        raise RuntimeError("the fix no longer shares its hunk with the churn")
    run_git_hunk(
        repo,
        "commit",
        fix_hunk,
        "--include-matching",
        "session.get",
        "-m",
        "Add a request timeout",
    )
    run_git_hunk(repo, "commit", "client.py", "-m", "Normalize string quotes")


def _squash_into_one_commit(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", "client.py")
    repo.git("commit", "-m", "Add timeout and reformat")


def _commit_by_hunk_not_intent(repo: GitRepo) -> None:
    for index, hunk in enumerate(list_hunks(repo, "client.py")):
        run_git_hunk(repo, "commit", str(hunk["id"]), "-m", f"Update part {index}")


def _commit_one_sided_match(repo: GitRepo) -> None:
    # The guard rejects a lone half by default, so the adversarial solver has to
    # ask for it explicitly to still reproduce the broken partition.
    run_git_hunk(
        repo,
        "commit",
        find_hunk(repo, "client.py", "session.get"),
        "--include-matching",
        "session.get(url)",
        "--allow-one-sided",
        "-m",
        "Add a request timeout",
    )
    run_git_hunk(repo, "commit", "client.py", "-m", "Normalize string quotes")


_FIX: Final = CommitSpec(
    label="fix",
    changes=frozenset(
        {
            ChangedLine(
                path="client.py", op="-", content="    return session.get(url)"
            ),
            ChangedLine(
                path="client.py",
                op="+",
                content="    return session.get(url, timeout=30)",
            ),
        }
    ),
)
_CHURN: Final = CommitSpec(
    label="churn",
    changes=frozenset(
        {
            ChangedLine(path="client.py", op="-", content="GREETING = 'hello'"),
            ChangedLine(path="client.py", op="+", content='GREETING = "hello"'),
            ChangedLine(path="client.py", op="-", content="FAREWELL = 'goodbye'"),
            ChangedLine(path="client.py", op="+", content='FAREWELL = "goodbye"'),
            ChangedLine(
                path="client.py",
                op="-",
                content="    return GREETING + ', ' + name",
            ),
            ChangedLine(
                path="client.py",
                op="+",
                content='    return GREETING + ", " + name',
            ),
            ChangedLine(
                path="client.py",
                op="-",
                content="    return FAREWELL + ', ' + name",
            ),
            ChangedLine(
                path="client.py",
                op="+",
                content='    return FAREWELL + ", " + name',
            ),
        }
    ),
)
_FINAL_FILES: Final = frozenset({make_file(path="client.py", content=_FINAL)})

SCENARIO: Final = Scenario(
    task=Task(
        name="separate_formatter_noise",
        build=_build,
        commits=(_FIX, _CHURN),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
        prompt=(
            "An automatic formatter rewrote the string quoting while a bug fix "
            "was in progress. Keep the formatting churn out of the fix: commit "
            "the fix and the reformat separately."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("partition", _squash_into_one_commit),
        ("partition", _commit_by_hunk_not_intent),
        ("partition", _commit_one_sided_match),
    ),
)
