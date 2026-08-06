import os
from pathlib import Path
from typing import Final

import pytest

from .conftest import MutationRepoFactory
from .conftest import assert_only_head_entry_changed
from .conftest import assert_only_index_entry_changed
from .conftest import assert_only_worktree_entry_changed
from .conftest import get_object_id
from .conftest import get_target
from .conftest import snapshot_repository

_BEFORE: Final = b"text old\n"
_AFTER: Final = b"text new\n"
_CASES: Final = [
    ("sibling/change.txt", "file"),
    ("sibling/change.txt", "id"),
    ("same.txt", "file"),
    ("sub/same.txt", "id"),
]


@pytest.mark.parametrize(("path", "selection"), _CASES)
def test_stage_text_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, path: str, selection: str
) -> None:
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=path, selection=selection)

    result = cli.run("stage", target, subdir="sub")

    assert result.returncode == 0
    assert path in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=path)
    assert after.index[path].content == _AFTER
    assert after.index[path].mode == "100644"
    assert after.index[path].object_id == get_object_id(cli, _AFTER)
    assert after.status == f"M  {path}\0 M unrelated.txt\0".encode()


@pytest.mark.parametrize(("path", "selection"), _CASES)
def test_unstage_text_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, path: str, selection: str
) -> None:
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    cli.repo.git("add", path, "unrelated.txt")
    before = snapshot_repository(cli)
    target = get_target(cli, path=path, selection=selection, staged=True)

    result = cli.run("unstage", target, subdir="sub")

    assert result.returncode == 0
    assert path in result.stderr
    after = snapshot_repository(cli)
    assert_only_index_entry_changed(before=before, after=after, path=path)
    assert after.index[path] == after.head[path]
    assert after.status == f" M {path}\0M  unrelated.txt\0".encode()


@pytest.mark.parametrize(("path", "selection"), _CASES)
def test_discard_text_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, path: str, selection: str
) -> None:
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=path, selection=selection)

    result = cli.run("discard", target, subdir="sub")

    assert result.returncode == 0
    assert path in result.stderr
    after = snapshot_repository(cli)
    assert_only_worktree_entry_changed(before=before, after=after, path=path)
    assert after.worktree[path].content == _BEFORE
    assert after.worktree[path].mode == "100644"
    assert after.status == b" M unrelated.txt\0"


@pytest.mark.parametrize(("path", "selection"), _CASES)
def test_commit_text_hunk_from_subdirectory(
    make_mutation_repo: MutationRepoFactory, path: str, selection: str
) -> None:
    cli = make_mutation_repo(path, _BEFORE, _AFTER)
    before = snapshot_repository(cli)
    target = get_target(cli, path=path, selection=selection)

    result = cli.run("commit", target, "-m", "change selected text", subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert_only_head_entry_changed(before=before, after=after, path=path)
    assert after.head[path].content == _AFTER
    assert after.head[path].mode == "100644"
    assert after.head[path].object_id == get_object_id(cli, _AFTER)
    assert after.status == b" M unrelated.txt\0"
    assert cli.repo.git("rev-list", "--count", "HEAD").strip() == "2"
    assert cli.repo.git("log", "-1", "--format=%s").strip() == "change selected text"


@pytest.mark.parametrize(
    ("operand", "selected", "untouched"),
    [
        ("same.txt", "same.txt", "sub/same.txt"),
        ("sub/same.txt", "sub/same.txt", "same.txt"),
    ],
)
def test_colliding_name_selects_the_repository_path_not_the_cwd_sibling(
    make_mutation_repo: MutationRepoFactory,
    operand: str,
    selected: str,
    untouched: str,
) -> None:
    # Both files are dirty at once, so the operand alone decides which is
    # staged. Run from sub/, where git's own pathspec would pick sub/same.txt.
    cli = make_mutation_repo("same.txt", _BEFORE, _AFTER)
    root = Path(cli.repo.path)
    (root / "sub" / "same.txt").write_bytes(_BEFORE)
    # Stage only the new file: the factory left root same.txt dirty on purpose.
    cli.repo.git("add", "sub/same.txt")
    cli.repo.git("commit", "-m", "add colliding name")
    (root / "sub" / "same.txt").write_bytes(_AFTER)
    before = snapshot_repository(cli)

    result = cli.run("stage", operand, subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert after.index[selected].content == _AFTER
    assert after.index[untouched] == before.index[untouched]


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow this file name")
def test_stage_whitespace_only_repository_path(
    make_mutation_repo: MutationRepoFactory,
) -> None:
    path = "   "
    cli = make_mutation_repo(path, _BEFORE, _AFTER)

    result = cli.run("stage", path, subdir="sub")

    assert result.returncode == 0
    assert snapshot_repository(cli).index[path].content == _AFTER
