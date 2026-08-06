import subprocess
import sys

import pytest

from .conftest import GitHunkCLI


@pytest.mark.parametrize("spec", ["1-999999999", "^1-999999999"])
def test_large_range_fails_promptly_and_atomically(cli: GitHunkCLI, spec: str) -> None:
    cli.repo.write_file("f.txt", "old\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "new\n")
    hunk_id = cli.get_only_hunk_id("--unstaged")
    before = (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("show", ":f.txt"),
        cli.repo.git("diff"),
    )

    # A real subprocess, not the in-process cli fixture, so the timeout can fail
    # the test if the range is expanded before it is bounds-checked (#131).
    result = subprocess.run(
        [sys.executable, "-m", "git_hunk", "stage", hunk_id, "-l", spec],
        capture_output=True,
        text=True,
        cwd=cli.repo.path,
        timeout=2,
    )

    assert result.returncode == 1
    assert f"line number out of range (hunk has 2 lines): {spec}" in result.stderr
    assert (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("show", ":f.txt"),
        cli.repo.git("diff"),
    ) == before
