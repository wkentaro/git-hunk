from pathlib import Path
from typing import Final

import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def grouped_replacement(*, cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nB\nC\n")
    return cli


def _capture_repo_state(*, cli: GitHunkCLI) -> tuple[str, str, bytes, str]:
    return (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("show", ":f.txt"),
        (Path(cli.repo.path) / "f.txt").read_bytes(),
        cli.repo.git("status", "--short"),
    )


def _assert_group_error(*, returncode: int, stderr: str) -> None:
    assert returncode == 1
    assert "grouped replacement" in stderr
    assert "lines 2-5" in stderr


@pytest.mark.parametrize("spec", ["2,4", "^3,^5"])
def test_stage_rejection_is_atomic(
    *, grouped_replacement: GitHunkCLI, spec: str
) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli=cli)

    result = cli.run("stage", cli.get_only_hunk_id("--unstaged"), "-l", spec)

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


def test_unstage_rejection_is_atomic(*, grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    before = _capture_repo_state(cli=cli)

    result = cli.run("unstage", cli.get_only_hunk_id("--staged"), "-l", "3,5")

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


def test_discard_rejection_is_atomic(*, grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli=cli)

    result = cli.run("discard", cli.get_only_hunk_id("--unstaged"), "-l", "2,4")

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


def test_commit_rejection_is_atomic(*, grouped_replacement: GitHunkCLI) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli=cli)

    result = cli.run(
        "commit",
        cli.get_only_hunk_id("--unstaged"),
        "-l",
        "2,4",
        "-m",
        "partial",
    )

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


@pytest.mark.parametrize("spec", ["2,4", "^3,^5"])
def test_allow_one_sided_does_not_relax_the_group_rule(
    *, grouped_replacement: GitHunkCLI, spec: str
) -> None:
    # --allow-one-sided covers a one-for-one pair only; a wider grouped
    # replacement stays a hard error.
    cli = grouped_replacement
    before = _capture_repo_state(cli=cli)

    result = cli.run(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", spec, "--allow-one-sided"
    )

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


@pytest.mark.parametrize(
    "selector",
    [
        ("--include-matching", "b", "--include-matching", "B"),
        ("--exclude-matching", "c", "--exclude-matching", "C"),
    ],
)
def test_matching_selection_uses_group_validation(
    *, grouped_replacement: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = grouped_replacement
    before = _capture_repo_state(cli=cli)

    result = cli.run("stage", cli.get_only_hunk_id("--unstaged"), *selector)

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


@pytest.mark.parametrize(
    "selector",
    [
        ("--include-matching", "b", "--include-matching", "B"),
        ("--exclude-matching", "c", "--exclude-matching", "C"),
    ],
)
def test_unstage_matching_selection_uses_group_validation(
    *, grouped_replacement: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = grouped_replacement
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    before = _capture_repo_state(cli=cli)

    result = cli.run("unstage", cli.get_only_hunk_id("--staged"), *selector)

    _assert_group_error(returncode=result.returncode, stderr=result.stderr)
    assert _capture_repo_state(cli=cli) == before


_FINAL_TOTAL: Final = (
    "def line_total(price, quantity):\n"
    "    if quantity <= 0:\n"
    '        raise ValueError("quantity must be positive")\n'
    "    return Decimal(price) * quantity\n"
)


@pytest.fixture
def mixed_replacement(*, cli: GitHunkCLI) -> GitHunkCLI:
    # One deleted line replaced by three added ones that carry two intents:
    # a Decimal switch and new validation.
    BASE: Final = (
        "def line_total(price, quantity):\n    return float(price) * quantity\n"
    )
    cli.repo.write_file("total.py", BASE)
    cli.repo.git("add", "total.py")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("total.py", _FINAL_TOTAL)
    return cli


def test_commit_splits_a_grouped_replacement_by_content(
    *, mixed_replacement: GitHunkCLI
) -> None:
    cli = mixed_replacement

    cli.run_ok(
        "commit",
        cli.get_only_hunk_id("--unstaged"),
        "--include-matching",
        "price",
        "-m",
        "use Decimal",
    )
    cli.run_ok("commit", "total.py", "-m", "validate quantity")

    DECIMAL_TOTAL: Final = (
        "def line_total(price, quantity):\n    return Decimal(price) * quantity\n"
    )
    assert cli.repo.git("show", "HEAD~1:total.py") == DECIMAL_TOTAL
    assert cli.repo.git("show", "HEAD:total.py") == _FINAL_TOTAL
    assert cli.repo.git("status", "--short") == ""


def test_discard_splits_a_grouped_replacement_by_content(
    *, mixed_replacement: GitHunkCLI
) -> None:
    # Discarding takes every added line and restores only the selected deleted
    # one, so it needs a group with two deletions to choose from.
    cli = mixed_replacement
    cli.repo.write_file("total.py", "a\nb\nc\n")
    cli.repo.git("commit", "-am", "abc")
    cli.repo.write_file("total.py", "a\nB\nC\n")

    cli.run_ok("discard", cli.get_only_hunk_id("--unstaged"), "-l", "2,4,5")

    assert (Path(cli.repo.path) / "total.py").read_text() == "a\nb\n"
