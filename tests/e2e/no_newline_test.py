from pathlib import Path

from .conftest import GitHunkCLI


def _commit(cli: GitHunkCLI, content: str) -> None:
    cli.repo.write_file("f.txt", content)
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")


def _only_hunk_id(cli: GitHunkCLI) -> str:
    hunks = cli.run_list_json("list", "--unstaged", "--json")
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
    staged = cli.run_list_json("list", "--staged", "--json")
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
    remaining = cli.run_list_json("list", "--unstaged", "--json")
    body = cli.run_list_json("show", remaining[0]["id"], "--unstaged", "--json")[0]
    assert any(line.get("no_newline") for line in body["lines"])


def test_list_counts_ignore_no_newline_marker(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    hunks = cli.run_list_json("list", "--unstaged", "--json")
    assert hunks[0]["additions"] == 1
    assert hunks[0]["deletions"] == 1


def test_stage_addition_of_no_newline_to_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    # Regression for #54: staging only the addition of a no-newline -> newline
    # edit must not merge the old last line with the addition.
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    # Body lines: 1= a 2=-b 3=+B. Stage only the addition.
    cli.run_ok("stage", _only_hunk_id(cli), "-l", "3")

    assert cli.repo.git("show", ":f.txt") == "a\nb\nB\n"


def test_stage_addition_then_remainder_reaches_working_tree(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok("stage", _only_hunk_id(cli), "-l", "3")
    assert cli.repo.git("show", ":f.txt") == "a\nb\nB\n"

    remaining = cli.run_list_json("list", "--unstaged", "--json")
    cli.run_ok("stage", remaining[0]["id"])

    assert cli.repo.git("show", ":f.txt") == "a\nB\n"


def test_stage_addition_both_sides_no_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB")

    # Body lines: 1= a 2=-b 3=+B, both last lines lack a trailing newline.
    cli.run_ok("stage", _only_hunk_id(cli), "-l", "3")

    assert cli.repo.git("show", ":f.txt") == "a\nb\nB"


def test_discard_addition_of_no_newline_to_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok("discard", _only_hunk_id(cli), "-l", "3")

    # Discarding only the +B addition reverts it; the -b deletion stays.
    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\n"


def test_unstage_addition_of_no_newline_to_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok("stage", _only_hunk_id(cli))
    staged = cli.run_list_json("list", "--staged", "--json")

    # Body lines: 1= a 2=-b 3=+B. Unstage only the addition from the index.
    cli.run_ok("unstage", staged[0]["id"], "-l", "3")

    assert cli.repo.git("show", ":f.txt") == "a\n"
    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\nB\n"
