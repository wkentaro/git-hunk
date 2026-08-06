import os
from pathlib import Path

import pytest

from .conftest import GitHunkCLI

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="git does not track the executable bit on Windows"
)


@pytest.fixture
def mode_and_text_change(cli: GitHunkCLI) -> GitHunkCLI:
    path = Path(cli.repo.path) / "script.sh"
    path.write_text("old\n")
    cli.repo.git("add", "script.sh")
    cli.repo.git("commit", "-m", "init")
    path.write_text("new\n")
    path.chmod(0o755)
    return cli


@pytest.fixture
def mode_and_two_text_changes(cli: GitHunkCLI) -> GitHunkCLI:
    path = Path(cli.repo.path) / "script.sh"
    original = [f"line {number}" for number in range(1, 31)]
    path.write_text("\n".join(original) + "\n")
    cli.repo.git("add", "script.sh")
    cli.repo.git("commit", "-m", "init")
    changed = original[:]
    changed[1] = "changed 2"
    changed[27] = "changed 28"
    path.write_text("\n".join(changed) + "\n")
    path.chmod(0o755)
    return cli


def _get_hunks(
    cli: GitHunkCLI, *status: str
) -> tuple[dict[str, object], list[dict[str, object]]]:
    hunks = cli.run_list_json("list", *status, "--json")
    mode_hunk = next(hunk for hunk in hunks if hunk["header"] is None)
    text_hunks = [hunk for hunk in hunks if hunk["header"] is not None]
    return mode_hunk, text_hunks


def _get_repository_snapshot(cli: GitHunkCLI) -> tuple[str, str, int, str, str]:
    path = Path(cli.repo.path) / "script.sh"
    return (
        cli.repo.git("ls-files", "--stage", "script.sh"),
        cli.repo.git("show", ":script.sh"),
        path.stat().st_mode,
        path.read_text(),
        cli.repo.git("status", "--porcelain=v1", "-z"),
    )


def test_list_separates_mode_and_two_text_hunks(
    mode_and_two_text_changes: GitHunkCLI,
) -> None:
    mode_hunk, text_hunks = _get_hunks(mode_and_two_text_changes, "--unstaged")

    assert mode_hunk["a_mode"] == "100644"
    assert mode_hunk["b_mode"] == "100755"
    assert len(text_hunks) == 2
    assert len({mode_hunk["id"], *(hunk["id"] for hunk in text_hunks)}) == 3


def test_stage_mode_hunk_leaves_text_unstaged(
    mode_and_text_change: GitHunkCLI,
) -> None:
    cli = mode_and_text_change
    hunks = cli.run_list_json("list", "--unstaged", "--json")
    mode_hunk = next(hunk for hunk in hunks if hunk["header"] is None)

    cli.run_ok("stage", mode_hunk["id"])

    assert cli.repo.git("show", ":script.sh") == "old\n"
    assert "mode change 100644 => 100755" in cli.repo.git(
        "diff", "--cached", "--summary"
    )
    assert "+new" in cli.repo.git("diff")


def test_stage_text_hunk_leaves_mode_and_other_text_unstaged(
    mode_and_two_text_changes: GitHunkCLI,
) -> None:
    cli = mode_and_two_text_changes
    _, text_hunks = _get_hunks(cli, "--unstaged")

    cli.run_ok("stage", str(text_hunks[0]["id"]))

    staged = cli.repo.git("show", ":script.sh")
    assert "changed 2" in staged
    assert "line 28" in staged
    assert cli.repo.git("ls-files", "--stage", "script.sh").startswith("100644 ")
    assert "changed 28" in cli.repo.git("diff")


def test_stage_mode_and_one_text_hunk_leaves_other_text_unstaged(
    mode_and_two_text_changes: GitHunkCLI,
) -> None:
    cli = mode_and_two_text_changes
    mode_hunk, text_hunks = _get_hunks(cli, "--unstaged")

    cli.run_ok("stage", str(mode_hunk["id"]), str(text_hunks[0]["id"]))

    staged = cli.repo.git("show", ":script.sh")
    assert "changed 2" in staged
    assert "line 28" in staged
    assert cli.repo.git("ls-files", "--stage", "script.sh").startswith("100755 ")
    assert "changed 28" in cli.repo.git("diff")


def test_stage_file_path_applies_mode_and_all_text_hunks(
    mode_and_two_text_changes: GitHunkCLI,
) -> None:
    cli = mode_and_two_text_changes

    cli.run_ok("stage", "script.sh")

    assert cli.repo.git("diff") == ""
    assert cli.repo.git("ls-files", "--stage", "script.sh").startswith("100755 ")
    assert "changed 2" in cli.repo.git("show", ":script.sh")
    assert "changed 28" in cli.repo.git("show", ":script.sh")


def test_unstage_mode_hunk_leaves_text_staged(mode_and_text_change: GitHunkCLI) -> None:
    cli = mode_and_text_change
    cli.repo.git("add", "script.sh")
    mode_hunk, _ = _get_hunks(cli, "--staged")

    cli.run_ok("unstage", str(mode_hunk["id"]))

    assert cli.repo.git("show", ":script.sh") == "new\n"
    assert cli.repo.git("ls-files", "--stage", "script.sh").startswith("100644 ")
    assert "mode change 100644 => 100755" in cli.repo.git("diff", "--summary")


def test_discard_mode_hunk_leaves_text_unstaged(
    mode_and_text_change: GitHunkCLI,
) -> None:
    cli = mode_and_text_change
    mode_hunk, _ = _get_hunks(cli, "--unstaged")

    cli.run_ok("discard", str(mode_hunk["id"]))

    path = Path(cli.repo.path) / "script.sh"
    assert path.read_text() == "new\n"
    assert path.stat().st_mode & 0o111 == 0
    assert "+new" in cli.repo.git("diff")


def test_commit_text_hunk_leaves_mode_uncommitted(
    mode_and_text_change: GitHunkCLI,
) -> None:
    cli = mode_and_text_change
    _, [text_hunk] = _get_hunks(cli, "--unstaged")

    cli.run_ok("commit", str(text_hunk["id"]), "-m", "change text")

    assert cli.repo.git("show", "HEAD:script.sh") == "new\n"
    assert cli.repo.git("ls-tree", "HEAD", "script.sh").startswith("100644 ")
    assert "mode change 100644 => 100755" in cli.repo.git("diff", "--summary")


def test_commit_mode_hunk_leaves_text_uncommitted(
    mode_and_text_change: GitHunkCLI,
) -> None:
    cli = mode_and_text_change
    mode_hunk, _ = _get_hunks(cli, "--unstaged")

    cli.run_ok("commit", str(mode_hunk["id"]), "-m", "change mode")

    assert cli.repo.git("show", "HEAD:script.sh") == "old\n"
    assert cli.repo.git("ls-tree", "HEAD", "script.sh").startswith("100755 ")
    assert "+new" in cli.repo.git("diff")


@pytest.mark.parametrize("command", ["stage", "unstage", "discard"])
def test_mode_hunk_dry_run_changes_nothing(
    mode_and_text_change: GitHunkCLI, command: str
) -> None:
    cli = mode_and_text_change
    if command == "unstage":
        cli.repo.git("add", "script.sh")
        status = ("--staged",)
    else:
        status = ("--unstaged",)
    mode_hunk, _ = _get_hunks(cli, *status)
    before = _get_repository_snapshot(cli)

    cli.run_ok(command, str(mode_hunk["id"]), "--dry-run")

    assert _get_repository_snapshot(cli) == before


@pytest.mark.parametrize("command", ["stage", "unstage", "discard"])
def test_mode_and_text_hunks_dry_run_change_nothing(
    mode_and_text_change: GitHunkCLI, command: str
) -> None:
    cli = mode_and_text_change
    if command == "unstage":
        cli.repo.git("add", "script.sh")
        status = ("--staged",)
    else:
        status = ("--unstaged",)
    mode_hunk, [text_hunk] = _get_hunks(cli, *status)
    before = _get_repository_snapshot(cli)

    cli.run_ok(
        command,
        str(mode_hunk["id"]),
        str(text_hunk["id"]),
        "--dry-run",
    )

    assert _get_repository_snapshot(cli) == before
