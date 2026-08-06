import os
from typing import Final

import pytest

from .conftest import MutationRepoFactory
from .conftest import assert_only_head_entry_changed
from .conftest import assert_only_index_entry_changed
from .conftest import assert_only_worktree_entry_changed
from .conftest import assert_other_entries_unchanged
from .conftest import get_object_id
from .conftest import get_target
from .conftest import snapshot_repository

_PATH: Final = "sibling/change.bin"
_BEFORE: Final = b"\x00binary old\xff"
_AFTER: Final = b"\x00binary new\xfe"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_stage_binary_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, selection: str
) -> None:
    cli = make_mutation_repo(_PATH, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("stage", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=_PATH)
    assert after.index[_PATH].content == _AFTER
    assert after.index[_PATH].mode == "100644"
    assert after.index[_PATH].object_id == get_object_id(cli, _AFTER)
    assert after.status == b"M  sibling/change.bin\0 M unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_unstage_binary_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, selection: str
) -> None:
    cli = make_mutation_repo(_PATH, _BEFORE, _AFTER)
    cli.repo.git("add", _PATH, "unrelated.txt")
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection, staged=True)

    result = cli.run("unstage", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=_PATH)
    assert after.index[_PATH] == after.head[_PATH]
    assert after.status == b" M sibling/change.bin\0M  unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_discard_binary_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, selection: str
) -> None:
    cli = make_mutation_repo(_PATH, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("discard", target, subdir="sub")

    assert result.returncode == 0
    assert _PATH in result.stderr
    after = snapshot_repository(cli)
    assert_only_worktree_entry_changed(before=before, after=after, path=_PATH)
    assert after.worktree[_PATH].content == _BEFORE
    assert after.worktree[_PATH].mode == "100644"
    assert after.status == b" M unrelated.txt\0"


@pytest.mark.parametrize("selection", ["file", "id"])
def test_commit_binary_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, selection: str
) -> None:
    cli = make_mutation_repo(_PATH, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=_PATH, selection=selection)

    result = cli.run("commit", target, "-m", "change selected binary", subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert_only_head_entry_changed(before=before, after=after, path=_PATH)
    assert after.head[_PATH].content == _AFTER
    assert after.head[_PATH].mode == "100644"
    assert after.head[_PATH].object_id == get_object_id(cli, _AFTER)
    assert after.status == b" M unrelated.txt\0"
    assert cli.repo.git("rev-list", "--count", "HEAD").strip() == "2"
    assert cli.repo.git("log", "-1", "--format=%s").strip() == (
        "change selected binary"
    )


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow this file name")
def test_stage_binary_repository_path_with_pathspec_punctuation(
    make_mutation_repo: MutationRepoFactory,
) -> None:
    path = ":literal[*]?!.bin"
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    before = snapshot_repository(cli)

    result = cli.run("stage", path, subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert_other_entries_unchanged(
        before=before.index, after=after.index, changed_path=path
    )
    assert after.index[path].content == _AFTER
    assert after.index[path].mode == "100644"
    assert after.index[path].object_id == get_object_id(cli, _AFTER)
    assert after.status == b"M  :literal[*]?!.bin\0 M unrelated.txt\0"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow this file name")
@pytest.mark.parametrize("command", ["unstage", "discard"])
def test_reverse_binary_repository_path_with_pathspec_punctuation(
    make_mutation_repo: MutationRepoFactory, command: str
) -> None:
    # A whole-file mutation hands Hunk.file to git add/restore, the only calls
    # that pass a path as a pathspec. Without --literal-pathspecs git reads the
    # punctuation as pathspec magic and matches nothing.
    path = ":literal[*]?!.bin"
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    if command == "unstage":
        cli.run_ok("stage", path, subdir="sub")
    before = snapshot_repository(cli)

    result = cli.run(command, path, subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    # Both land the same way: unstage moves the index back off _AFTER, discard
    # moves the worktree back onto the index. Either way _BEFORE wins.
    assert after.index[path].content == _BEFORE
    expected_worktree = _AFTER if command == "unstage" else _BEFORE
    assert after.worktree[path].content == expected_worktree
    assert_other_entries_unchanged(
        before=before.index, after=after.index, changed_path=path
    )
