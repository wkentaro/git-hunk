from pathlib import Path

import pytest

from .conftest import GitHunkCLI


def _init(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("tracked.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")


def _untracked_id(*, cli: GitHunkCLI, path: str) -> str:
    [hunk] = [
        h
        for h in cli.run_list_json("list", "--json")
        if h["status"] == "untracked" and h["file"]["text"] == path
    ]
    return hunk["id"]


def test_untracked_id_changes_with_content(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "one\n")
    first = _untracked_id(cli=cli, path="new.py")

    assert _untracked_id(cli=cli, path="new.py") == first
    cli.repo.write_file("new.py", "two\n")
    assert _untracked_id(cli=cli, path="new.py") != first


@pytest.mark.parametrize("by", ["id", "path"])
def test_stage_untracked_file(*, cli: GitHunkCLI, by: str) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "new\n")
    target = _untracked_id(cli=cli, path="new.py") if by == "id" else "new.py"

    cli.run_ok("stage", target)

    assert cli.repo.git("diff", "--cached", "--name-status").strip() == "A\tnew.py"
    assert cli.repo.git("show", ":new.py") == "new\n"


def test_commit_untracked_file_with_tracked_hunk(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("tracked.py", "new\n")
    cli.repo.write_file("new.py", "new\n")

    cli.run_ok("commit", "tracked.py", "new.py", "-m", "feat: both")

    assert cli.repo.git("status", "--porcelain").strip() == ""
    assert cli.repo.git("show", "--name-status", "--format=", "HEAD").split() == [
        "A",
        "new.py",
        "M",
        "tracked.py",
    ]


def test_stage_dry_run_leaves_untracked_file_untracked(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "new\n")

    cli.run_ok("stage", "new.py", "--dry-run")

    assert cli.repo.git("status", "--porcelain").strip() == "?? new.py"


def test_discard_refuses_untracked_file(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "new\n")

    r = cli.run("discard", _untracked_id(cli=cli, path="new.py"))

    assert r.returncode != 0
    assert "cannot discard untracked files: 'new.py'" in r.stderr
    assert (Path(cli.repo.path) / "new.py").read_text() == "new\n"


def test_line_selection_rejects_untracked_file(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "a\nb\n")

    r = cli.run("stage", "new.py", "-l", "1")

    assert r.returncode != 0
    assert "untracked files" in r.stderr
    assert cli.repo.git("status", "--porcelain").strip() == "?? new.py"


def test_show_untracked_file_by_id(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "new\n")
    hunk_id = _untracked_id(cli=cli, path="new.py")

    [hunk] = cli.run_list_json("show", hunk_id, "--json")

    assert hunk["status"] == "untracked"
    assert "Untracked file" in cli.run_ok("show", hunk_id)


def test_show_without_ids_omits_untracked_files(*, cli: GitHunkCLI) -> None:
    _init(cli=cli)
    cli.repo.write_file("new.py", "new\n")

    assert cli.run_list_json("show", "--json") == []


def test_untracked_file_under_deleted_tracked_file_changes_nothing(
    *, cli: GitHunkCLI
) -> None:
    # The tracked file a is replaced by a directory: git would reject a/b only
    # after the tracked hunk was staged, so the conflict is found up front.
    cli.repo.write_file("a", "file\n")
    _init(cli=cli)
    Path(cli.repo.path, "a").unlink()
    cli.repo.write_file("a/b", "new\n")
    cli.repo.write_file("tracked.py", "new\n")
    before = cli.repo.git("status", "--porcelain")

    r = cli.run("stage", "tracked.py", "a/b")

    assert r.returncode != 0
    assert "conflict with tracked paths: 'a'" in r.stderr
    assert cli.repo.git("status", "--porcelain") == before
