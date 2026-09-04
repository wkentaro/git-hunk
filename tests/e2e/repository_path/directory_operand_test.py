import os
from pathlib import Path

import pytest

from .conftest import MutationRepoFactory
from .conftest import snapshot_repository


@pytest.mark.parametrize("command", ["stage", "unstage", "discard", "commit"])
def test_changed_directory_operand_explains_exact_paths(
    *, make_mutation_repo: MutationRepoFactory, command: str
) -> None:
    cli = make_mutation_repo("changed/file.txt", b"old\n", b"new\n")
    if command == "unstage":
        cli.repo.git("add", "changed/file.txt")
    before = snapshot_repository(cli)
    args = (
        ["commit", "-m", "message", "changed"]
        if command == "commit"
        else [command, "changed"]
    )

    result = cli.run(*args)

    assert result.returncode != 0
    assert "directory operands are not expanded: 'changed'" in result.stderr
    assert "pass exact Repository paths" in result.stderr
    assert "shell-expanded glob" in result.stderr
    assert "git add" not in result.stderr
    assert snapshot_repository(cli) == before


@pytest.mark.parametrize("command", ["stage", "unstage", "discard", "commit"])
def test_directory_without_eligible_descendants_keeps_no_match_error(
    *, make_mutation_repo: MutationRepoFactory, command: str
) -> None:
    cli = make_mutation_repo("sibling/change.txt", b"old\n", b"new\n")
    cli.repo.write_file("unchanged/untracked.txt", "content\n")
    before = snapshot_repository(cli)
    args = (
        ["commit", "-m", "message", "unchanged"]
        if command == "commit"
        else [command, "unchanged"]
    )

    result = cli.run(*args)

    assert result.returncode != 0
    assert "no changed file matches 'unchanged'" in result.stderr
    assert "tip: run 'git-hunk list' to see changed files and hunk ids" in result.stderr
    assert snapshot_repository(cli) == before


@pytest.mark.skipif(os.name == "nt", reason="git does not track symlinks on Windows")
def test_directory_symlink_outside_worktree_keeps_no_match_error(
    *, make_mutation_repo: MutationRepoFactory, tmp_path: Path
) -> None:
    cli = make_mutation_repo("changed/file.txt", b"old\n", b"new\n")
    changed = Path(cli.repo.path) / "changed"
    (tmp_path / "external").mkdir()
    changed.joinpath("file.txt").unlink()
    changed.rmdir()
    changed.symlink_to(tmp_path / "external", target_is_directory=True)
    before = cli.repo.git("status", "--short")

    result = cli.run("stage", "changed")

    assert result.returncode != 0
    assert "no changed file matches 'changed'" in result.stderr
    assert "tip: run 'git-hunk list' to see changed files and hunk ids" in result.stderr
    assert cli.repo.git("status", "--short") == before
