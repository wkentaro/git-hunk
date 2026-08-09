import ast
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

_PATH: Final = "report.py"
_MESSAGE: Final = "Skip voided rows"
# The hunk body interleaves the change to keep with debug scaffolding:
#
#   4 +        if row.voided:
#   5 +            print("DEBUG", "voided", row)
#   6 +            continue
#   7 +        if total > 1000:
#   8 +            print("DEBUG", "large total", total)
#
# Only lines 4 and 6 belong in the commit. Dropping the two `print` lines by
# content or by number strands line 7, and any single range covering both of
# them also swallows line 6, so all three tempting selections stage a file that
# no longer parses.
_KEEP_LINES: Final = "4,6"
_DEBUG_PATTERN: Final = 'print("DEBUG"'
_STRANDING_RANGE: Final = "^5-8"

_BASE: Final = (
    "def summarize(rows):\n"
    "    total = 0\n"
    "    for row in rows:\n"
    "        total += row.amount\n"
    "    return total\n"
)
_DIRTY: Final = (
    "def summarize(rows):\n"
    "    total = 0\n"
    "    for row in rows:\n"
    "        if row.voided:\n"
    '            print("DEBUG", "voided", row)\n'
    "            continue\n"
    "        if total > 1000:\n"
    '            print("DEBUG", "large total", total)\n'
    "        total += row.amount\n"
    "    return total\n"
)
_FINAL: Final = (
    "def summarize(rows):\n"
    "    total = 0\n"
    "    for row in rows:\n"
    "        if row.voided:\n"
    "            continue\n"
    "        total += row.amount\n"
    "    return total\n"
)


def _build(repo: GitRepo) -> None:
    repo.write_file(name=_PATH, content=_BASE)
    repo.git("add", _PATH)
    repo.git("commit", "-m", "Initial state")
    repo.write_file(name=_PATH, content=_DIRTY)


def _single_hunk_id(repo: GitRepo) -> str:
    # The trap only exists while both intents share one hunk.
    (hunk,) = list_hunks(repo, _PATH)
    return str(hunk["id"])


def _commit_selection(repo: GitRepo, *selection: str) -> None:
    hunk_id = _single_hunk_id(repo)
    run_git_hunk(repo, "commit", hunk_id, *selection, "-m", _MESSAGE)


def _golden(repo: GitRepo) -> None:
    # Stage, read back what the index now holds, and only commit once it parses
    # — the check an agent has to perform by hand today, and the one #58 wants
    # to fold into `stage --verify`. Committing from the verified index means
    # nothing can change between the check and the commit.
    hunk_id = _single_hunk_id(repo)
    run_git_hunk(repo, "stage", hunk_id, "-l", _KEEP_LINES)
    try:
        ast.parse(repo.git("show", f":{_PATH}"))
    except SyntaxError as error:
        run_git_hunk(repo, "unstage", _PATH)
        raise RuntimeError(f"the selection staged unparsable Python: {error}")
    repo.git("commit", "-m", _MESSAGE)
    run_git_hunk(repo, "discard", _PATH)


def _commit_without_matching_debug_lines(repo: GitRepo) -> None:
    _commit_selection(repo, "--exclude-matching", _DEBUG_PATTERN)


def _commit_without_the_debug_range(repo: GitRepo) -> None:
    _commit_selection(repo, "-l", _STRANDING_RANGE)


def _commit_everything(repo: GitRepo) -> None:
    run_git_hunk(repo, "stage", _PATH)
    repo.git("commit", "-m", _MESSAGE)


def _forget_to_drop_the_scaffolding(repo: GitRepo) -> None:
    _commit_selection(repo, "-l", _KEEP_LINES)


_SKIP_VOIDED: Final = CommitSpec(
    label="skip-voided",
    changes=frozenset(
        {
            ChangedLine(path=_PATH, op="+", content="        if row.voided:"),
            ChangedLine(path=_PATH, op="+", content="            continue"),
        }
    ),
)
_FINAL_FILES: Final = frozenset({make_file(path=_PATH, content=_FINAL)})

SCENARIO: Final = Scenario(
    task=Task(
        name="commit_parseable_subset",
        build=_build,
        commits=(_SKIP_VOIDED,),
        expected_state=RepositoryState(
            head=_FINAL_FILES,
            worktree=_FINAL_FILES,
        ),
        prompt=(
            "Keep the skip for voided rows. The temporary debug tracing goes: "
            "the print statements and the threshold check that exists only to "
            "print. Every commit must leave the file valid Python."
        ),
    ),
    golden=_golden,
    adversarial=(
        ("broken-commit", _commit_without_matching_debug_lines),
        ("broken-commit", _commit_without_the_debug_range),
        ("partition", _commit_everything),
        ("leftover-worktree", _forget_to_drop_the_scaffolding),
    ),
)
