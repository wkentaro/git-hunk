from pathlib import Path

from .conftest import GitHunkCLI


def test_partial_unstage_of_added_file_keeps_a_smaller_added_file(
    cli: GitHunkCLI,
) -> None:
    cli.repo.git("commit", "--allow-empty", "-m", "init")
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    worktree_path = Path(cli.repo.path) / "f.txt"
    worktree_before = worktree_path.read_bytes()
    cli.repo.git("add", "f.txt")
    hunk = cli.run_list_json("list", "--staged", "--json")[0]

    cli.run_ok("unstage", hunk["id"], "-l", "2")

    assert cli.repo.run("git", "cat-file", "-e", "HEAD:f.txt").returncode == 128
    assert cli.repo.git("show", ":f.txt").encode() == b"a\nc\n"
    assert worktree_path.read_bytes() == worktree_before
    assert cli.repo.git("ls-files", "--stage", "f.txt").split()[0] == "100644"
    assert cli.repo.git("status", "--short") == "AM f.txt\n"


def test_partial_stage_of_deleted_file_keeps_a_smaller_tracked_file(
    cli: GitHunkCLI,
) -> None:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    (Path(cli.repo.path) / "f.txt").unlink()
    hunk = cli.run_list_json("list", "--unstaged", "--json")[0]

    cli.run_ok("stage", hunk["id"], "-l", "2")

    assert cli.repo.git("show", "HEAD:f.txt").encode() == b"a\nb\nc\n"
    assert cli.repo.git("show", ":f.txt").encode() == b"a\nc\n"
    assert not (Path(cli.repo.path) / "f.txt").exists()
    assert cli.repo.git("ls-files", "--stage", "f.txt").split()[0] == "100644"
    assert cli.repo.git("status", "--short") == "MD f.txt\n"
