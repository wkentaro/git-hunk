from pathlib import Path

from git_hunk._hunk import NO_NEWLINE_MARKER

from .conftest import GitHunkCLI


def _commit(cli: GitHunkCLI, content: str) -> None:
    cli.repo.write_file("f.txt", content)
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")


def _only_hunk_id(cli: GitHunkCLI) -> str:
    hunks = cli.run_json("list", "--unstaged", "--json")
    assert len(hunks) == 1
    return hunks[0]["id"]


def test_stage_edit_last_line_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("stage", _only_hunk_id(cli))

    assert cli.repo.git("show", ":f.txt") == "a\nb\ncX"


def test_stage_newline_to_no_newline_removes_trailing_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc\n")
    cli.repo.write_file("f.txt", "a\nb\nc")

    cli.run_ok("stage", _only_hunk_id(cli))

    assert cli.repo.git("show", ":f.txt") == "a\nb\nc"


def test_stage_no_newline_to_newline_adds_trailing_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\nc\n")

    cli.run_ok("stage", _only_hunk_id(cli))

    assert cli.repo.git("show", ":f.txt") == "a\nb\nc\n"


def test_unstage_round_trips_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("stage", _only_hunk_id(cli))
    staged = cli.run_json("list", "--staged", "--json")
    cli.run_ok("unstage", staged[0]["id"])

    assert cli.repo.git("diff", "--cached").strip() == ""
    assert cli.repo.git("show", ":f.txt") == "a\nb\nc"


def test_discard_round_trips_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("discard", _only_hunk_id(cli))

    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\nb\nc"


def test_stage_line_selection_on_no_newline_hunk(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "aX\nb\ncX")

    # Body lines (markers unnumbered): 1=-a 2=+aX 3= b 4=-c 5=+cX.
    # Select the first change only; the no-newline tail must survive intact.
    cli.run_ok("stage", _only_hunk_id(cli), "-l", "1,2")

    assert cli.repo.git("show", ":f.txt") == "aX\nb\nc"

    # The dropped change still carries its no-newline marker in the remainder.
    remaining = cli.run_json("list", "--unstaged", "--json")
    assert NO_NEWLINE_MARKER in remaining[0]["diff"]


def test_list_counts_ignore_no_newline_marker(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    hunks = cli.run_json("list", "--unstaged", "--json")
    assert hunks[0]["additions"] == 1
    assert hunks[0]["deletions"] == 1
