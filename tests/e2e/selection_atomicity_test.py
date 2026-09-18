"""A multi-target selection is resolved fully before anything is applied.

Every id and path is validated up front, so one bad target aborts the whole
command and the valid targets alongside it are left untouched. Without this,
reordering validation after the first apply would silently half-apply a
selection.
"""

from pathlib import Path

import pytest

import git_hunk._cli

from .conftest import GitHunkCLI


@pytest.fixture
def two_changed_files(*, cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f1.py", "a\n")
    cli.repo.write_file("f2.py", "b\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f1.py", "A\n")
    cli.repo.write_file("f2.py", "B\n")
    return cli


@pytest.fixture
def prepare_changed_text_and_binary(*, cli: GitHunkCLI) -> GitHunkCLI:
    root = Path(cli.repo.path)
    (root / "text.txt").write_text("before\n")
    (root / "whole.bin").write_bytes(b"\0before")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (root / "text.txt").write_text("after\n")
    (root / "whole.bin").write_bytes(b"\0after")
    return cli


def test_stage_with_one_unknown_id_stages_nothing(
    *,
    two_changed_files: GitHunkCLI,
) -> None:
    cli = two_changed_files
    valid_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]

    r = cli.run("stage", valid_id, "deadbee")

    assert r.returncode != 0
    assert "deadbee" in r.stderr  # the unknown target is named, not the valid one
    assert "not found" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_unstage_with_one_unknown_id_keeps_index(
    *, two_changed_files: GitHunkCLI
) -> None:
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
    *,
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
    *,
    two_changed_files: GitHunkCLI,
) -> None:
    cli = two_changed_files

    r = cli.run("stage", "f1.py", "nosuch.py")

    assert r.returncode != 0
    assert "no changed file matches 'nosuch.py'" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_unstage_text_and_empty_additions_in_unborn_repository(
    *,
    cli: GitHunkCLI,
) -> None:
    cli.repo.write_file("content.txt", "content\n")
    cli.repo.write_file("empty.txt", "")
    cli.repo.git("add", ".")
    hunks = cli.run_list_json("list", "--staged", "--json")
    targets = [str(hunk["id"]) for hunk in hunks]

    cli.run_ok("unstage", *targets)

    assert cli.repo.git("diff", "--cached") == ""
    assert cli.repo.git("status", "--short") == "?? content.txt\n?? empty.txt\n"


@pytest.mark.parametrize("command", ["discard", "unstage"])
def test_restore_failure_reports_the_partially_applied_selection(
    *,
    prepare_changed_text_and_binary: GitHunkCLI,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = prepare_changed_text_and_binary
    if command == "unstage":
        cli.repo.git("add", ".")
    status = "--staged" if command == "unstage" else "--unstaged"
    hunks = {
        hunk["file"]["text"]: hunk
        for hunk in cli.run_list_json("list", status, "--json")
    }

    def raise_restore_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(
        git_hunk._cli,
        "unstage_files" if command == "unstage" else "discard_files",
        raise_restore_failure,
    )
    result = cli.run(command, hunks["text.txt"]["id"], hunks["whole.bin"]["id"])

    assert result.returncode == 1
    root = Path(cli.repo.path)
    assert (root / "whole.bin").read_bytes() == b"\0after"
    if command == "unstage":
        assert (root / "text.txt").read_text() == "after\n"
        assert cli.repo.git("diff", "--cached", "--name-only") == "whole.bin\n"
        assert cli.repo.git("diff", "--name-only") == "text.txt\n"
    else:
        assert (root / "text.txt").read_text() == "before\n"
        assert cli.repo.git("diff", "--cached", "--name-only") == ""
        assert cli.repo.git("diff", "--name-only") == "whole.bin\n"
    assert "injected restore failure" in result.stderr
    assert "earlier changes were applied" in result.stderr
    assert "repository may be partially changed" in result.stderr
    assert "inspect its state before retrying" in result.stderr


def test_preflight_failure_does_not_report_or_apply_partial_mutation(
    *,
    prepare_changed_text_and_binary: GitHunkCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = prepare_changed_text_and_binary
    hunks = {
        hunk["file"]["text"]: hunk
        for hunk in cli.run_list_json("list", "--unstaged", "--json")
    }

    def raise_preflight_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected preflight failure")

    monkeypatch.setattr(git_hunk._cli, "apply_patch", raise_preflight_failure)
    result = cli.run("discard", hunks["text.txt"]["id"], hunks["whole.bin"]["id"])

    assert result.returncode == 1
    assert "injected preflight failure" in result.stderr
    assert "earlier changes were applied" not in result.stderr
    root = Path(cli.repo.path)
    assert (root / "text.txt").read_text() == "after\n"
    assert (root / "whole.bin").read_bytes() == b"\0after"
    assert cli.repo.git("diff", "--cached", "--name-only") == ""
    assert cli.repo.git("diff", "--name-only") == "text.txt\nwhole.bin\n"
