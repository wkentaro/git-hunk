from pathlib import Path

import pytest

from .conftest import GitHunkCLI

# _apply_line_filter's "exactly one hunk" guard is shared by stage, unstage,
# discard and commit; only the stage direction is pinned (error_test.py).
# Body line numbers of the first hunk: 1=" line1" 2="-line2" 3="+CHANGED2",
# so -l 2,3 would apply to that hunk alone if the guard ever stopped firing.


@pytest.fixture
def two_hunks(cli: GitHunkCLI) -> GitHunkCLI:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    return cli


def _both_ids(cli: GitHunkCLI, *flags: str) -> list[str]:
    hunks = cli.run_list_json("list", *flags, "--json")
    assert len(hunks) == 2
    return [h["id"] for h in hunks]


def test_discard_rejects_line_selection_across_two_hunks(
    two_hunks: GitHunkCLI,
) -> None:
    worktree_file = Path(two_hunks.repo.path) / "f.py"
    before = worktree_file.read_text()
    r = two_hunks.run("discard", *_both_ids(two_hunks, "--unstaged"), "-l", "2,3")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr
    assert worktree_file.read_text() == before


def test_unstage_rejects_line_selection_across_two_hunks(
    two_hunks: GitHunkCLI,
) -> None:
    two_hunks.run_ok("stage", *_both_ids(two_hunks, "--unstaged"))
    staged = two_hunks.repo.git("show", ":f.py")
    r = two_hunks.run("unstage", *_both_ids(two_hunks, "--staged"), "-l", "2,3")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr
    assert two_hunks.repo.git("show", ":f.py") == staged


def test_commit_rejects_line_selection_across_two_hunks(
    two_hunks: GitHunkCLI,
) -> None:
    head = two_hunks.repo.git("rev-parse", "HEAD")
    r = two_hunks.run(
        "commit", *_both_ids(two_hunks, "--unstaged"), "-l", "2,3", "-m", "partial"
    )
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr
    assert two_hunks.repo.git("rev-parse", "HEAD") == head
