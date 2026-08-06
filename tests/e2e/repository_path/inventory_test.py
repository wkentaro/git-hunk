import os
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import GitRepo
from tests.e2e.conftest import GitHunkCLI

from .conftest import TRACKED_LITERAL_PATH
from .conftest import UNTRACKED_LITERAL_PATH


def _get_paths(hunks: list[dict[str, Any]]) -> list[str]:
    return [hunk["file"]["text"] for hunk in hunks]


def test_inventory_is_stable_from_root_and_subdirectory(
    inventory_cli: GitHunkCLI,
) -> None:
    cli = inventory_cli
    root_hunks = cli.run_list_json("list", "--json")
    sub_hunks = cli.run_list_json("list", "--json", subdir="sub")

    assert sub_hunks == root_hunks
    paths = _get_paths(sub_hunks)
    assert paths == [
        TRACKED_LITERAL_PATH,
        "same.txt",
        "sibling/change.bin",
        "sibling/change.txt",
        "sub/same.txt",
        UNTRACKED_LITERAL_PATH,
        "new.txt",
        "sub/new.txt",
    ]

    root_plain_list = cli.run_ok("list")
    sub_plain_list = cli.run_ok("list", subdir="sub")
    root_plain_show = cli.run_ok("show")
    sub_plain_show = cli.run_ok("show", subdir="sub")
    root_json_show = cli.run_list_json("show", "--json")
    sub_json_show = cli.run_list_json("show", "--json", subdir="sub")
    assert sub_plain_list == root_plain_list
    assert sub_plain_show == root_plain_show
    assert sub_json_show == root_json_show
    assert _get_paths(sub_json_show) == paths[:5]
    for path in paths[:5]:
        assert path in sub_plain_list
        assert path in sub_plain_show
    for path in paths[5:]:
        assert path in sub_plain_list
        assert path not in sub_plain_show
    assert "../sibling/change.txt" not in sub_plain_list


@pytest.mark.parametrize(
    ("operand", "expected"),
    [
        ("same.txt", "same.txt"),
        ("sub/same.txt", "sub/same.txt"),
        ("./sub/same.txt", "sub/same.txt"),
        ("sub/../same.txt", "same.txt"),
        (TRACKED_LITERAL_PATH, TRACKED_LITERAL_PATH),
        ("new.txt", "new.txt"),
        ("sub/new.txt", "sub/new.txt"),
        ("./sub/new.txt", "sub/new.txt"),
        ("sub/../new.txt", "new.txt"),
        (UNTRACKED_LITERAL_PATH, UNTRACKED_LITERAL_PATH),
    ],
)
def test_list_selects_one_exact_repository_path(
    inventory_cli: GitHunkCLI, operand: str, expected: str
) -> None:
    hunks = inventory_cli.run_list_json("list", "--json", operand, subdir="sub")
    assert _get_paths(hunks) == [expected]


def _assert_rejected(cli: GitHunkCLI, operand: str) -> None:
    result = cli.run("list", "--json", operand, subdir="sub")
    assert result.returncode != 0
    assert "schema_version" not in result.stdout
    assert '"hunks"' not in result.stdout


def test_list_rejects_an_escaping_path(inventory_cli: GitHunkCLI) -> None:
    _assert_rejected(inventory_cli, "../same.txt")


def test_list_rejects_an_absolute_path_even_inside_the_worktree(
    inventory_cli: GitHunkCLI,
) -> None:
    _assert_rejected(inventory_cli, str(Path(inventory_cli.repo.path) / "same.txt"))


@pytest.mark.parametrize("operand", ["sub", "*.txt", ":(glob)*.txt"])
def test_list_does_not_expand_non_file_operands(
    inventory_cli: GitHunkCLI, operand: str
) -> None:
    hunks = inventory_cli.run_list_json("list", "--json", operand, subdir="sub")
    assert hunks == []


def test_show_id_has_same_meaning_from_root_and_subdirectory(
    inventory_cli: GitHunkCLI,
) -> None:
    cli = inventory_cli
    hunk = next(
        hunk
        for hunk in cli.run_list_json("list", "--json", subdir="sub")
        if hunk["file"]["text"] == "sibling/change.txt"
    )
    root = cli.run_list_json("show", hunk["id"], "--json")
    sub = cli.run_list_json("show", hunk["id"], "--json", subdir="sub")

    assert sub == root
    assert _get_paths(sub) == ["sibling/change.txt"]
    assert "sibling/change.txt" in cli.run_ok("show", hunk["id"], subdir="sub")


@pytest.mark.skipif(os.name == "nt", reason="Windows strips trailing path spaces")
def test_repository_root_preserves_trailing_space(tmp_path: Path) -> None:
    root = tmp_path / "repo "
    root.mkdir()
    repo = GitRepo(str(root))
    repo.git("init")
    repo.git("config", "user.email", "test@test.com")
    repo.git("config", "user.name", "Test")
    repo.write_file("changed.txt", "old\n")
    repo.git("add", ".")
    repo.git("commit", "-m", "init")
    repo.write_file("changed.txt", "new\n")

    cli = GitHunkCLI(repo)
    hunks = cli.run_list_json("list", "--json")

    assert _get_paths(hunks) == ["changed.txt"]
