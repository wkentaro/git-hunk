from pathlib import Path

import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def grouped_replacement(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nB\nC\n")
    return cli


def _capture_repo_state(cli: GitHunkCLI) -> tuple[str, str, bytes, str]:
    return (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("show", ":f.txt"),
        (Path(cli.repo.path) / "f.txt").read_bytes(),
        cli.repo.git("status", "--short"),
    )


def _assert_group_error(returncode: int, stderr: str) -> None:
    assert returncode == 1
    assert "grouped replacement" in stderr
    assert "lines 2-5" in stderr


@pytest.mark.parametrize("spec", ["2,4", "^3,^5"])
def test_stage_rejection_is_atomic(grouped_replacement: GitHunkCLI, spec: str) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli)

    result = cli.run("stage", cli.only_hunk_id("--unstaged"), "-l", spec)

    _assert_group_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


def test_unstage_rejection_is_atomic(grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    cli.run_ok("stage", cli.only_hunk_id("--unstaged"))
    before = _capture_repo_state(cli)

    result = cli.run("unstage", cli.only_hunk_id("--staged"), "-l", "3,5")

    _assert_group_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


def test_discard_rejection_is_atomic(grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli)

    result = cli.run("discard", cli.only_hunk_id("--unstaged"), "-l", "2,4")

    _assert_group_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


def test_commit_rejection_is_atomic(grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli)

    result = cli.run(
        "commit",
        cli.only_hunk_id("--unstaged"),
        "-l",
        "2,4",
        "-m",
        "partial",
    )

    _assert_group_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


@pytest.mark.parametrize(
    "selector",
    [
        ("--include-matching", "b", "--include-matching", "B"),
        ("--exclude-matching", "c", "--exclude-matching", "C"),
    ],
)
def test_matching_selection_uses_group_validation(
    grouped_replacement: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli)

    result = cli.run("stage", cli.only_hunk_id("--unstaged"), *selector)

    _assert_group_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before
