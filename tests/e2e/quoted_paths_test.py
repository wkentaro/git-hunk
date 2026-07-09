import sys

import pytest

from .conftest import GitHunkCLI


def _hunk_id_for(cli: GitHunkCLI, path: str) -> str:
    hunks = cli.run_list_json("list", "--unstaged", "--json")
    return next(h["id"] for h in hunks if h["file"]["text"] == path)


def test_non_ascii_modified_file_round_trips(cli: GitHunkCLI) -> None:
    cli.repo.write_file("файл.txt", "a\nb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("файл.txt", "a\nB\n")

    cli.run_ok("stage", _hunk_id_for(cli, "файл.txt"))
    assert cli.repo.git("show", ":файл.txt") == "a\nB\n"

    staged = cli.run_list_json("list", "--staged", "--json")
    cli.run_ok("unstage", staged[0]["id"])
    assert cli.repo.git("diff", "--cached").strip() == ""

    cli.run_ok("discard", _hunk_id_for(cli, "файл.txt"))
    assert cli.repo.git("diff").strip() == ""


def test_non_ascii_untracked_shows_real_path(cli: GitHunkCLI) -> None:
    cli.repo.write_file("keep.txt", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("untrack𝟙.txt", "new\n")

    hunks = cli.run_list_json("list", "--json")
    untracked = [h for h in hunks if h["status"] == "untracked"]
    assert [h["file"]["text"] for h in untracked] == ["untrack𝟙.txt"]


def test_filename_with_b_slash_substring_stages(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a b/c.txt", "x\ny\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("a b/c.txt", "x\nY\n")

    hunks = cli.run_list_json("list", "--unstaged", "--json")
    assert [h["file"]["text"] for h in hunks] == ["a b/c.txt"]

    cli.run_ok("stage", _hunk_id_for(cli, "a b/c.txt"))
    assert cli.repo.git("show", ":a b/c.txt") == "x\nY\n"

    staged = cli.run_list_json("list", "--staged", "--json")
    cli.run_ok("unstage", staged[0]["id"])
    assert cli.repo.git("diff", "--cached").strip() == ""

    cli.run_ok("discard", _hunk_id_for(cli, "a b/c.txt"))
    assert cli.repo.git("diff").strip() == ""


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "tab, newline, backslash, double-quote, and control characters "
        "are illegal in Windows filenames"
    ),
)
@pytest.mark.parametrize(
    "path",
    ["od\ttab.txt", "od\nnl.txt", "od\\back.txt", 'od"q.txt', "od\x1besc.txt"],
    ids=["tab", "newline", "backslash", "quote", "escape"],
)
def test_quoted_path_modified_file_round_trips(cli: GitHunkCLI, path: str) -> None:
    cli.repo.write_file(path, "a\nb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file(path, "a\nB\n")

    hunks = cli.run_list_json("list", "--unstaged", "--json")
    assert [h["file"]["text"] for h in hunks] == [path]

    cli.run_ok("stage", _hunk_id_for(cli, path))
    assert cli.repo.git("show", f":{path}") == "a\nB\n"

    staged = cli.run_list_json("list", "--staged", "--json")
    cli.run_ok("unstage", staged[0]["id"])
    assert cli.repo.git("diff", "--cached").strip() == ""

    cli.run_ok("discard", _hunk_id_for(cli, path))
    assert cli.repo.git("diff").strip() == ""
