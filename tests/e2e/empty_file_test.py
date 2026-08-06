import os

import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def committed_keep_file(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("keep.txt", "keep\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    return cli


@pytest.fixture
def committed_empty_file(committed_keep_file: GitHunkCLI) -> GitHunkCLI:
    cli = committed_keep_file
    cli.repo.write_file("empty.txt", "")
    cli.repo.git("add", "empty.txt")
    cli.repo.git("commit", "-m", "add empty file")
    return cli


@pytest.fixture
def staged_empty_addition(committed_keep_file: GitHunkCLI) -> GitHunkCLI:
    cli = committed_keep_file
    cli.repo.write_file("empty.txt", "")
    cli.repo.git("add", "empty.txt")
    return cli


@pytest.fixture
def staged_empty_deletion(committed_empty_file: GitHunkCLI) -> GitHunkCLI:
    cli = committed_empty_file
    cli.repo.git("rm", "empty.txt")
    return cli


@pytest.fixture
def unstaged_empty_deletion(committed_empty_file: GitHunkCLI) -> GitHunkCLI:
    cli = committed_empty_file
    os.unlink(os.path.join(cli.repo.path, "empty.txt"))
    return cli


def test_empty_addition_inventory_has_whole_file_shape(
    staged_empty_addition: GitHunkCLI,
) -> None:
    cli = staged_empty_addition
    [hunk] = cli.run_list_json("show", "--staged", "--json")

    assert hunk == {
        "id": hunk["id"],
        "file": {"text": "empty.txt"},
        "status": "staged",
        "change_kind": "A",
        "a_mode": None,
        "b_mode": "100644",
        "binary": False,
        "header": None,
        "context_before": None,
        "additions": 0,
        "deletions": 0,
        "lines": [],
    }
    assert "Empty file (added)" in cli.run_ok("list", "--staged")


def test_empty_deletion_inventory_has_whole_file_shape(
    staged_empty_deletion: GitHunkCLI,
) -> None:
    cli = staged_empty_deletion
    [hunk] = cli.run_list_json("show", "--staged", "--json")

    assert hunk == {
        "id": hunk["id"],
        "file": {"text": "empty.txt"},
        "status": "staged",
        "change_kind": "D",
        "a_mode": "100644",
        "b_mode": None,
        "binary": False,
        "header": None,
        "context_before": None,
        "additions": 0,
        "deletions": 0,
        "lines": [],
    }
    assert "Empty file (deleted)" in cli.run_ok("list", "--staged")


@pytest.mark.parametrize("selection", ["id", "path"])
@pytest.mark.parametrize(
    "fixture_name", ["staged_empty_addition", "staged_empty_deletion"]
)
def test_unstage_empty_file(
    request: pytest.FixtureRequest, fixture_name: str, selection: str
) -> None:
    cli: GitHunkCLI = request.getfixturevalue(fixture_name)
    target = cli.get_only_hunk_id("--staged") if selection == "id" else "empty.txt"

    cli.run_ok("unstage", target)

    assert cli.repo.git("diff", "--cached") == ""


@pytest.mark.parametrize("selection", ["id", "path"])
def test_stage_empty_deletion(
    unstaged_empty_deletion: GitHunkCLI, selection: str
) -> None:
    cli = unstaged_empty_deletion
    hunk_id = cli.get_only_hunk_id("--unstaged")

    cli.run_ok("stage", hunk_id if selection == "id" else "empty.txt")

    assert cli.repo.git("diff", "--cached", "--name-status") == "D\tempty.txt\n"


def test_discard_empty_deletion_restores_file(
    unstaged_empty_deletion: GitHunkCLI,
) -> None:
    cli = unstaged_empty_deletion

    cli.run_ok("discard", "empty.txt")

    assert os.path.isfile(os.path.join(cli.repo.path, "empty.txt"))
    assert cli.repo.git("status", "--short") == ""


def test_commit_empty_deletion(unstaged_empty_deletion: GitHunkCLI) -> None:
    cli = unstaged_empty_deletion

    cli.run_ok("commit", "empty.txt", "-m", "delete empty file")

    assert (
        cli.repo.git("show", "--format=", "--name-status", "HEAD") == "D\tempty.txt\n"
    )


def test_unstaged_empty_addition_is_untracked_after_unstage(
    staged_empty_addition: GitHunkCLI,
) -> None:
    cli = staged_empty_addition

    cli.run_ok("unstage", "empty.txt")

    [untracked] = cli.run_list_json("list", "empty.txt", "--json")
    assert untracked["status"] == "untracked"
    assert untracked["id"] == ""
    result = cli.run("stage", "empty.txt")
    assert result.returncode != 0
    assert "no changed file matches" in result.stderr


def test_unstage_empty_addition_in_unborn_repository(cli: GitHunkCLI) -> None:
    cli.repo.write_file("empty.txt", "")
    cli.repo.git("add", "empty.txt")

    cli.run_ok("unstage", "empty.txt")

    assert cli.repo.git("diff", "--cached") == ""
    assert cli.repo.git("status", "--short") == "?? empty.txt\n"


@pytest.mark.parametrize(
    "option",
    [
        ("-l", "1"),
        ("--include-matching", "x"),
        ("--exclude-matching", "x"),
    ],
)
def test_line_selection_rejects_empty_file_before_mutation(
    staged_empty_addition: GitHunkCLI, option: tuple[str, str]
) -> None:
    cli = staged_empty_addition
    before = cli.repo.git("diff", "--cached", "--raw")

    result = cli.run("unstage", "empty.txt", *option)

    assert result.returncode != 0
    assert "line selection is not supported" in result.stderr
    assert cli.repo.git("diff", "--cached", "--raw") == before


@pytest.mark.parametrize("command", ["stage", "discard"])
def test_empty_deletion_dry_run_changes_nothing(
    unstaged_empty_deletion: GitHunkCLI, command: str
) -> None:
    cli = unstaged_empty_deletion
    before = cli.repo.git("status", "--porcelain=v1", "-z")

    cli.run_ok(command, "empty.txt", "--dry-run")

    assert cli.repo.git("status", "--porcelain=v1", "-z") == before


@pytest.mark.parametrize(
    "fixture_name", ["staged_empty_addition", "staged_empty_deletion"]
)
def test_empty_file_unstage_dry_run_changes_nothing(
    request: pytest.FixtureRequest, fixture_name: str
) -> None:
    cli: GitHunkCLI = request.getfixturevalue(fixture_name)
    before = cli.repo.git("status", "--porcelain=v1", "-z")

    cli.run_ok("unstage", "empty.txt", "--dry-run")

    assert cli.repo.git("status", "--porcelain=v1", "-z") == before
