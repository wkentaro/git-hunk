"""A multi-target selection is resolved fully before anything is applied.

Every id and path is validated up front, so one bad target aborts the whole
command and the valid targets alongside it are left untouched. Without this,
reordering validation after the first apply would silently half-apply a
selection.
"""

import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def two_changed_files(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f1.py", "a\n")
    cli.repo.write_file("f2.py", "b\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f1.py", "A\n")
    cli.repo.write_file("f2.py", "B\n")
    return cli


def test_stage_with_one_unknown_id_stages_nothing(
    two_changed_files: GitHunkCLI,
) -> None:
    cli = two_changed_files
    valid_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]

    r = cli.run("stage", valid_id, "deadbee")

    assert r.returncode != 0
    assert "deadbee" in r.stderr  # the unknown target is named, not the valid one
    assert "not found" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_unstage_with_one_unknown_id_keeps_index(two_changed_files: GitHunkCLI) -> None:
    cli = two_changed_files
    cli.repo.git("add", ".")
    staged_before = cli.repo.git("diff", "--cached")
    valid_id = cli.run_list_json("list", "--staged", "--json")[0]["id"]

    r = cli.run("unstage", valid_id, "deadbee")

    assert r.returncode != 0
    assert "deadbee" in r.stderr
    assert "not found" in r.stderr
    assert cli.repo.git("diff", "--cached") == staged_before


def test_discard_with_one_unknown_id_keeps_working_tree(
    two_changed_files: GitHunkCLI,
) -> None:
    cli = two_changed_files
    unstaged_before = cli.repo.git("diff")
    valid_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]

    r = cli.run("discard", valid_id, "deadbee")

    assert r.returncode != 0
    assert "deadbee" in r.stderr
    assert "not found" in r.stderr
    assert cli.repo.git("diff") == unstaged_before


def test_stage_with_one_unknown_path_stages_nothing(
    two_changed_files: GitHunkCLI,
) -> None:
    cli = two_changed_files

    r = cli.run("stage", "f1.py", "nosuch.py")

    assert r.returncode != 0
    assert "no changed file matches 'nosuch.py'" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""
