import subprocess
from pathlib import Path

import pytest

from .conftest import GitHunkCLI

# 0xe9 is "é" in Latin-1 and an invalid standalone UTF-8 byte.
_BEFORE = b"pass\xe9\nline2\n"
_AFTER = b"pass\xe9\nLINE2\n"


@pytest.fixture
def latin1_repo(cli: GitHunkCLI) -> GitHunkCLI:
    path = Path(cli.repo.path) / "latin1.txt"
    path.write_bytes(_BEFORE)
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.write_bytes(_AFTER)
    return cli


def test_list_does_not_crash_on_non_utf8_content(latin1_repo: GitHunkCLI) -> None:
    hunks = latin1_repo.run_list_json("list", "--unstaged", "--json")
    assert [h["file"]["text"] for h in hunks] == ["latin1.txt"]

    latin1_repo.run_ok("list", "--unstaged")


def test_show_does_not_crash_on_non_utf8_content(latin1_repo: GitHunkCLI) -> None:
    latin1_repo.run_ok("show", "--unstaged")


def test_stage_preserves_non_utf8_bytes(latin1_repo: GitHunkCLI) -> None:
    hunk_id = latin1_repo.run_list_json("list", "--unstaged", "--json")[0]["id"]
    latin1_repo.run_ok("stage", hunk_id)

    staged = subprocess.run(
        ["git", "show", ":latin1.txt"],
        capture_output=True,
        cwd=latin1_repo.repo.path,
    ).stdout
    assert staged == _AFTER
