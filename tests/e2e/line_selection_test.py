from pathlib import Path

import pytest

from .conftest import GitHunkCLI

# HEAD "a b c d" -> working "a B c D": one hunk, two change groups.
# Body line numbers: 1=" a" 2="-b" 3="+B" 4=" c" 5="-d" 6="+D".
# Group A = lines 2,3 (b->B); group B = lines 5,6 (d->D).


@pytest.fixture
def two_group(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.txt", "a\nb\nc\nd\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nB\nc\nD\n")
    return cli


def _only_id(cli: GitHunkCLI, *flags: str) -> str:
    hunks = cli.run_json("list", *flags, "--json")
    assert len(hunks) == 1
    return hunks[0]["id"]


def _working(cli: GitHunkCLI) -> str:
    return (Path(cli.repo.path) / "f.txt").read_text()


def test_stage_include_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("stage", _only_id(two_group, "--unstaged"), "-l", "2,3")
    assert two_group.repo.git("show", ":f.txt") == "a\nB\nc\nd\n"


def test_stage_exclude_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("stage", _only_id(two_group, "--unstaged"), "-l", "^2,^3")
    assert two_group.repo.git("show", ":f.txt") == "a\nb\nc\nD\n"


def test_unstage_include_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("stage", _only_id(two_group, "--unstaged"))
    two_group.run_ok("unstage", _only_id(two_group, "--staged"), "-l", "2,3")
    assert two_group.repo.git("show", ":f.txt") == "a\nb\nc\nD\n"


def test_unstage_exclude_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("stage", _only_id(two_group, "--unstaged"))
    two_group.run_ok("unstage", _only_id(two_group, "--staged"), "-l", "^2,^3")
    assert two_group.repo.git("show", ":f.txt") == "a\nB\nc\nd\n"


def test_discard_include_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("discard", _only_id(two_group, "--unstaged"), "-l", "2,3")
    assert _working(two_group) == "a\nb\nc\nD\n"


def test_discard_exclude_first_group(two_group: GitHunkCLI) -> None:
    two_group.run_ok("discard", _only_id(two_group, "--unstaged"), "-l", "^2,^3")
    assert _working(two_group) == "a\nB\nc\nd\n"


def test_full_round_trip(two_group: GitHunkCLI) -> None:
    two_group.run_ok("stage", _only_id(two_group, "--unstaged"), "-l", "2,3")
    assert two_group.repo.git("show", ":f.txt") == "a\nB\nc\nd\n"

    two_group.run_ok("stage", _only_id(two_group, "--unstaged"))
    assert two_group.repo.git("show", ":f.txt") == "a\nB\nc\nD\n"

    two_group.run_ok("unstage", _only_id(two_group, "--staged"), "-l", "2,3")
    assert two_group.repo.git("show", ":f.txt") == "a\nb\nc\nD\n"

    two_group.run_ok("discard", _only_id(two_group, "--unstaged"), "-l", "2,3")
    assert _working(two_group) == "a\nb\nc\nD\n"
