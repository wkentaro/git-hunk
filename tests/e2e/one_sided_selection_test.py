from pathlib import Path

import pytest

from .conftest import GitHunkCLI

# Regression for #225. HEAD holds `return session.get(url)`; the working tree
# replaces it with `return session.get(url, timeout=30)`. That is one hunk whose
# body lines are 1=" def fetch(...)", 2="-...session.get(url)",
# 3="+...session.get(url, timeout=30)": a one-for-one replacement pair.

_HEAD: str = "def fetch(session, url):\n    return session.get(url)\n"
_WORKING: str = "def fetch(session, url):\n    return session.get(url, timeout=30)\n"

# `session.get(url)` matches only the deleted line: the added line continues
# with a comma, so it has no `url)` substring. That is exactly the trap #225
# describes.
_ONE_SIDED_PATTERN: str = "session.get(url)"
# `session.get(url` matches both sides of the pair.
_BOTH_SIDES_PATTERN: str = "session.get(url"

_ONE_SIDED_SELECTORS = pytest.mark.parametrize(
    "selector",
    [
        ("-l", "2"),
        ("-l", "3"),
        ("--include-matching", _ONE_SIDED_PATTERN),
        ("--exclude-matching", "timeout=30"),
    ],
    ids=["line-deletion", "line-addition", "include-matching", "exclude-matching"],
)


@pytest.fixture
def one_for_one(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("client.py", _HEAD)
    cli.repo.git("add", "client.py")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("client.py", _WORKING)
    return cli


def _capture_repo_state(cli: GitHunkCLI) -> tuple[str, str, str, str]:
    return (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("show", ":client.py"),
        (Path(cli.repo.path) / "client.py").read_text(),
        cli.repo.git("status", "--short"),
    )


def _assert_one_sided_error(returncode: int, stderr: str) -> None:
    assert returncode == 1
    assert "cannot select one side of lines 2-3" in stderr
    assert "one-for-one replacement" in stderr
    assert "--allow-one-sided" in stderr


@_ONE_SIDED_SELECTORS
def test_stage_rejects_one_sided_selection(
    one_for_one: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)

    result = cli.run("stage", cli.get_only_hunk_id("--unstaged"), *selector)

    _assert_one_sided_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


@_ONE_SIDED_SELECTORS
def test_commit_rejects_one_sided_selection(
    one_for_one: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)

    result = cli.run(
        "commit", cli.get_only_hunk_id("--unstaged"), *selector, "-m", "half"
    )

    _assert_one_sided_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


@_ONE_SIDED_SELECTORS
def test_unstage_rejects_one_sided_selection(
    one_for_one: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = one_for_one
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))
    before = _capture_repo_state(cli)

    result = cli.run("unstage", cli.get_only_hunk_id("--staged"), *selector)

    _assert_one_sided_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


@_ONE_SIDED_SELECTORS
def test_discard_rejects_one_sided_selection(
    one_for_one: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)

    result = cli.run("discard", cli.get_only_hunk_id("--unstaged"), *selector)

    _assert_one_sided_error(result.returncode, result.stderr)
    assert _capture_repo_state(cli) == before


@pytest.mark.parametrize(
    "selector",
    [
        ("-l", "2"),
        ("--include-matching", _ONE_SIDED_PATTERN),
        ("--exclude-matching", "timeout=30"),
    ],
    ids=["line-spec", "include-matching", "exclude-matching"],
)
def test_stage_allow_one_sided_stages_the_deletion_half(
    one_for_one: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = one_for_one

    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), *selector, "--allow-one-sided"
    )

    assert cli.repo.git("show", ":client.py") == "def fetch(session, url):\n"
    assert (Path(cli.repo.path) / "client.py").read_text() == _WORKING


def test_commit_allow_one_sided_commits_the_deletion_half(
    one_for_one: GitHunkCLI,
) -> None:
    cli = one_for_one

    cli.run_ok(
        "commit",
        cli.get_only_hunk_id("--unstaged"),
        "--include-matching",
        _ONE_SIDED_PATTERN,
        "--allow-one-sided",
        "-m",
        "drop the untimed call",
    )

    assert cli.repo.git("show", "HEAD:client.py") == "def fetch(session, url):\n"
    assert (Path(cli.repo.path) / "client.py").read_text() == _WORKING


def test_stage_allow_one_sided_stages_the_addition_half(
    one_for_one: GitHunkCLI,
) -> None:
    cli = one_for_one

    cli.run_ok(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    assert cli.repo.git("show", ":client.py") == (
        "def fetch(session, url):\n"
        "    return session.get(url)\n"
        "    return session.get(url, timeout=30)\n"
    )
    assert (Path(cli.repo.path) / "client.py").read_text() == _WORKING


def test_unstage_allow_one_sided_smoke(one_for_one: GitHunkCLI) -> None:
    cli = one_for_one
    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"))

    cli.run_ok(
        "unstage", cli.get_only_hunk_id("--staged"), "-l", "3", "--allow-one-sided"
    )

    assert cli.repo.git("show", ":client.py") == "def fetch(session, url):\n"


def test_discard_allow_one_sided_smoke(one_for_one: GitHunkCLI) -> None:
    cli = one_for_one

    cli.run_ok(
        "discard", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--allow-one-sided"
    )

    assert (Path(cli.repo.path) / "client.py").read_text() == (
        "def fetch(session, url):\n"
    )


def test_error_names_the_group_the_selection_lands_in(cli: GitHunkCLI) -> None:
    # Two one-for-one pairs separated by context. Body lines: 1=" alpha"
    # 2="-one" 3="+ONE" 4=" beta" 5="-two" 6="+TWO" 7=" gamma". A one-sided
    # selection in the second pair must name that pair, not the first.
    cli.repo.write_file("f.txt", "alpha\none\nbeta\ntwo\ngamma\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "alpha\nONE\nbeta\nTWO\ngamma\n")

    result = cli.run("stage", cli.get_only_hunk_id("--unstaged"), "-l", "5")

    assert result.returncode == 1
    assert "cannot select one side of lines 5-6" in result.stderr
    assert "lines 2-3" not in result.stderr
    assert cli.repo.git("show", ":f.txt") == "alpha\none\nbeta\ntwo\ngamma\n"


def test_dry_run_reports_the_rejection_instead_of_a_preview(
    one_for_one: GitHunkCLI,
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)

    result = cli.run(
        "stage", cli.get_only_hunk_id("--unstaged"), "-l", "3", "--dry-run"
    )

    _assert_one_sided_error(result.returncode, result.stderr)
    assert "would stage" not in result.stdout + result.stderr
    assert _capture_repo_state(cli) == before


def test_dry_run_with_allow_one_sided_previews_without_mutating(
    one_for_one: GitHunkCLI,
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)

    result = cli.run(
        "stage",
        cli.get_only_hunk_id("--unstaged"),
        "-l",
        "3",
        "--allow-one-sided",
        "--dry-run",
    )

    assert result.returncode == 0
    assert "would stage" in result.stdout + result.stderr
    assert _capture_repo_state(cli) == before


def test_pattern_matching_both_lines_needs_no_flag(one_for_one: GitHunkCLI) -> None:
    cli = one_for_one

    cli.run_ok(
        "stage",
        cli.get_only_hunk_id("--unstaged"),
        "--include-matching",
        _BOTH_SIDES_PATTERN,
    )

    assert cli.repo.git("show", ":client.py") == _WORKING


def test_full_pair_line_selection_needs_no_flag(one_for_one: GitHunkCLI) -> None:
    cli = one_for_one

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "2,3")

    assert cli.repo.git("show", ":client.py") == _WORKING


def test_pure_addition_selection_needs_no_flag(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.txt", "keep\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "keep\nfirst\nsecond\n")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "2")

    assert cli.repo.git("show", ":f.txt") == "keep\nfirst\n"


def test_pure_deletion_selection_needs_no_flag(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.txt", "keep\nfirst\nsecond\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "keep\n")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "2")

    assert cli.repo.git("show", ":f.txt") == "keep\nsecond\n"


@pytest.mark.parametrize(
    "command",
    ["stage", "unstage", "discard", "commit"],
)
def test_allow_one_sided_without_a_selection_mechanism_is_a_usage_error(
    one_for_one: GitHunkCLI, command: str
) -> None:
    cli = one_for_one
    before = _capture_repo_state(cli)
    extra = ["-m", "half"] if command == "commit" else []

    result = cli.run(
        command, cli.get_only_hunk_id("--unstaged"), "--allow-one-sided", *extra
    )

    assert result.returncode == 2
    assert "--allow-one-sided requires" in result.stderr
    assert _capture_repo_state(cli) == before
