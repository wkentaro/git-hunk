import os
from pathlib import Path
from typing import Final

import pytest

from tests.e2e.conftest import GitHunkCLI

from .conftest import MutationRepoFactory
from .conftest import assert_only_head_entry_changed
from .conftest import assert_only_index_entry_changed
from .conftest import assert_only_worktree_entry_changed
from .conftest import get_target
from .conftest import snapshot_repository

_PATH: Final = "sibling/change.txt"
_BEFORE: Final = b"regular old\n"

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="git does not track symlinks on Windows"
)


@pytest.fixture
def type_change_cli(make_mutation_repo: MutationRepoFactory) -> GitHunkCLI:
    # git emits a file -> symlink type change as a delete + add pair, which
    # git-hunk merges into one "T" whole-file Hunk. Drive it from sub/ so the
    # changed file sits outside the invocation directory.
    cli = make_mutation_repo(_PATH, _BEFORE, _BEFORE)
    path = Path(cli.repo.path) / _PATH
    path.unlink()
    path.symlink_to("target")
    return cli


@pytest.mark.parametrize("selection", ["file", "id"])
def test_stage_type_change_hunk_from_subdirectory(
    type_change_cli: GitHunkCLI, selection: str
) -> None:
    cli = type_change_cli
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("stage", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=_PATH)
    assert after.index[_PATH].mode == "120000"
    assert after.index[_PATH].content == b"target"
    assert after.status == b"T  sibling/change.txt\0 M unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_unstage_type_change_hunk_from_subdirectory(
    type_change_cli: GitHunkCLI, selection: str
) -> None:
    cli = type_change_cli
    cli.repo.git("add", _PATH, "unrelated.txt")
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection, staged=True)

    result = cli.run("unstage", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=_PATH)
    assert after.index[_PATH] == after.head[_PATH]
    assert after.status == b" T sibling/change.txt\0M  unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_discard_type_change_hunk_from_subdirectory(
    type_change_cli: GitHunkCLI, selection: str
) -> None:
    cli = type_change_cli
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("discard", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_worktree_entry_changed(before=before, after=after, path=_PATH)
    assert after.worktree[_PATH].mode == "100644"
    assert after.worktree[_PATH].content == _BEFORE
    assert after.status == b" M unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_commit_type_change_hunk_from_subdirectory(
    type_change_cli: GitHunkCLI, selection: str
) -> None:
    cli = type_change_cli
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("commit", target, "-m", "change selected type", subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert_only_head_entry_changed(before=before, after=after, path=_PATH)
    assert after.head[_PATH].mode == "120000"
    assert after.head[_PATH].content == b"target"
    assert after.status == b" M unrelated.txt\0"
    assert cli.repo.git("rev-list", "--count", "HEAD").strip() == "2"
    assert cli.repo.git("log", "-1", "--format=%s").strip() == "change selected type"
