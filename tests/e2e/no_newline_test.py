from pathlib import Path
from typing import NamedTuple

import pytest

from .conftest import GitHunkCLI


def _commit(cli: GitHunkCLI, content: str) -> None:
    cli.repo.write_file("f.txt", content)
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")


class _NewlineChange(NamedTuple):
    cli: GitHunkCLI
    old_text: str
    new_text: str


@pytest.fixture(params=[("b", "B\n"), ("b\n", "B"), ("b", "B")])
def newline_change(cli: GitHunkCLI, request: pytest.FixtureRequest) -> _NewlineChange:
    old, new = request.param
    _commit(cli, "a\n" + old)
    cli.repo.write_file("f.txt", "a\n" + new)
    return _NewlineChange(cli=cli, old_text=old, new_text=new)


@pytest.fixture
def staged_newline_change(newline_change: _NewlineChange) -> _NewlineChange:
    cli = newline_change.cli
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    return newline_change


def test_stage_edit_last_line_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))

    assert cli.repo.git("show", ":f.txt") == "a\nb\ncX"


def test_stage_newline_to_no_newline_removes_trailing_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc\n")
    cli.repo.write_file("f.txt", "a\nb\nc")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))

    assert cli.repo.git("show", ":f.txt") == "a\nb\nc"


def test_stage_no_newline_to_newline_adds_trailing_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\nc\n")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))

    assert cli.repo.git("show", ":f.txt") == "a\nb\nc\n"


def test_unstage_round_trips_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    staged = cli.run_list_json("list", "--staged", "--json")
    cli.run_ok("unstage", staged[0]["id"])

    assert cli.repo.git("diff", "--cached").strip() == ""
    assert cli.repo.git("show", ":f.txt") == "a\nb\nc"


def test_discard_round_trips_no_newline(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    cli.run_ok("discard", cli.get_only_hunk_id("--unstaged"))

    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\nb\nc"


def test_stage_line_selection_on_no_newline_hunk(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb\nc")
    cli.repo.write_file("f.txt", "aX\nb\ncX")

    # Body lines (markers unnumbered): 1=-a 2=+aX 3= b 4=-c 5=+cX.
    # Select the first change only; the no-newline tail must survive intact.
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "1,2")

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
    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    assert cli.repo.git("show", ":f.txt") == "a\nb\nB\n"


def test_stage_addition_then_remainder_reaches_working_tree(cli: GitHunkCLI) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )
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
    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    assert cli.repo.git("show", ":f.txt") == "a\nb\nB"


def test_discard_addition_of_no_newline_to_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok(
        "discard", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    # Discarding only the +B addition reverts it; the -b deletion stays.
    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\n"


def test_unstage_addition_of_no_newline_to_newline_keeps_lines_separate(
    cli: GitHunkCLI,
) -> None:
    _commit(cli, "a\nb")
    cli.repo.write_file("f.txt", "a\nB\n")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    staged = cli.run_list_json("list", "--staged", "--json")

    # Body lines: 1= a 2=-b 3=+B. Unstage only the addition from the index.
    cli.run_ok("unstage", staged[0]["id"], "-l", "3", "--allow-one-sided")

    assert cli.repo.git("show", ":f.txt") == "a\n"
    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\nB\n"


def test_stage_deletion_preserves_each_side_newline_state(
    newline_change: _NewlineChange,
) -> None:
    cli = newline_change.cli

    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "2", "--allow-one-sided"
    )

    assert cli.repo.git("show", ":f.txt").encode() == b"a\n"


def test_stage_addition_preserves_each_side_newline_state(
    newline_change: _NewlineChange,
) -> None:
    cli = newline_change.cli

    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    new = newline_change.new_text
    assert cli.repo.git("show", ":f.txt").encode() == b"a\nb\n" + new.encode()


def test_stage_replacement_preserves_each_side_newline_state(
    newline_change: _NewlineChange,
) -> None:
    cli = newline_change.cli

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "2,3")

    new = newline_change.new_text
    assert cli.repo.git("show", ":f.txt").encode() == b"a\n" + new.encode()


def test_unstage_deletion_preserves_each_side_newline_state(
    staged_newline_change: _NewlineChange,
) -> None:
    cli = staged_newline_change.cli
    staged_id = cli.run_list_json("list", "--staged", "--json")[0]["id"]

    cli.run_ok("unstage", staged_id, "-l", "2", "--allow-one-sided")

    new = staged_newline_change.new_text
    assert cli.repo.git("show", ":f.txt").encode() == b"a\nb\n" + new.encode()


def test_discard_deletion_preserves_each_side_newline_state(
    newline_change: _NewlineChange,
) -> None:
    cli = newline_change.cli

    cli.run_ok(
        "discard", cli.get_only_hunk_id("--unstaged"), "-l", "2", "--allow-one-sided"
    )

    # read_text, not read_bytes: the working tree holds CRLF on Windows, and
    # universal newlines normalize it while still telling the two trailing
    # newline states apart, which is what this asserts.
    expected = "a\nb\n" + newline_change.new_text
    assert (Path(cli.repo.path) / "f.txt").read_text() == expected


def test_commit_addition_preserves_each_side_newline_state(
    newline_change: _NewlineChange,
) -> None:
    cli = newline_change.cli

    cli.run_ok(
        "commit",
        cli.get_only_hunk_id("--unstaged"),
        "-l",
        "3",
        "--allow-one-sided",
        "-m",
        "partial",
    )

    new = newline_change.new_text
    assert cli.repo.git("show", "HEAD:f.txt").encode() == b"a\nb\n" + new.encode()
    assert (Path(cli.repo.path) / "f.txt").read_text() == "a\n" + new


def test_unstage_addition_preserves_each_side_newline_state(
    staged_newline_change: _NewlineChange,
) -> None:
    cli = staged_newline_change.cli
    staged_id = cli.run_list_json("list", "--staged", "--json")[0]["id"]

    cli.run_ok("unstage", staged_id, "-l", "3", "--allow-one-sided")

    assert cli.repo.git("show", ":f.txt").encode() == b"a\n"


def test_unstage_replacement_preserves_each_side_newline_state(
    staged_newline_change: _NewlineChange,
) -> None:
    cli = staged_newline_change.cli
    staged_id = cli.run_list_json("list", "--staged", "--json")[0]["id"]

    cli.run_ok("unstage", staged_id, "-l", "2,3")

    old = staged_newline_change.old_text
    assert cli.repo.git("show", ":f.txt").encode() == b"a\n" + old.encode()
