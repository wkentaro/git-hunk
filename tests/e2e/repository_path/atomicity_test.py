from pathlib import Path

import pytest

from .conftest import MutationRepoFactory
from .conftest import get_hunk_id
from .conftest import snapshot_repository


def test_mixed_selection_applies_changes_across_repository(
    make_mutation_repo: MutationRepoFactory,
) -> None:
    cli = make_mutation_repo("sibling/change.txt", b"sibling old\n", b"sibling new\n")
    (Path(cli.repo.path) / "sub" / "keep.txt").write_bytes(b"sub new\n")
    sibling_id = get_hunk_id(cli, path="sibling/change.txt")
    before = snapshot_repository(cli)

    result = cli.run("stage", sibling_id, "sub/keep.txt", subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert after.head_id == before.head_id
    assert after.head == before.head
    assert after.worktree == before.worktree
    assert after.index.keys() == before.index.keys()
    assert after.index["unrelated.txt"] == before.index["unrelated.txt"]
    assert after.index["sibling/change.txt"].content == b"sibling new\n"
    assert after.index["sub/keep.txt"].content == b"sub new\n"
    assert after.worktree["unrelated.txt"].content == b"unrelated new\n"
    assert after.status == b"M  sibling/change.txt\0M  sub/keep.txt\0 M unrelated.txt\0"


def test_mixed_text_and_whole_file_selection_applies_both_legs(
    make_mutation_repo: MutationRepoFactory,
) -> None:
    # _apply_selection runs the text hunks through git apply and the whole-file
    # hunks through git add, so only a selection spanning both exercises the
    # two legs together.
    cli = make_mutation_repo("sibling/change.txt", b"sibling old\n", b"sibling new\n")
    (Path(cli.repo.path) / "sibling" / "change.bin").write_bytes(b"\x00old\xff")
    # Stage only the new file: the factory left change.txt dirty on purpose.
    cli.repo.git("add", "sibling/change.bin")
    cli.repo.git("commit", "-m", "add binary")
    (Path(cli.repo.path) / "sibling" / "change.bin").write_bytes(b"\x00new\xfe")
    text_id = get_hunk_id(cli, path="sibling/change.txt")
    before = snapshot_repository(cli)

    result = cli.run("stage", text_id, "sibling/change.bin", subdir="sub")

    assert result.returncode == 0
    after = snapshot_repository(cli)
    assert after.head_id == before.head_id
    assert after.head == before.head
    assert after.worktree == before.worktree
    assert after.index["sibling/change.txt"].content == b"sibling new\n"
    assert after.index["sibling/change.bin"].content == b"\x00new\xfe"
    assert after.index["unrelated.txt"] == before.index["unrelated.txt"]


@pytest.mark.parametrize("command", ["stage", "unstage", "discard", "commit"])
@pytest.mark.parametrize("operand", ["../same.txt", "absolute"])
def test_operand_outside_repository_path_space_changes_nothing(
    make_mutation_repo: MutationRepoFactory, command: str, operand: str
) -> None:
    cli = make_mutation_repo("sibling/change.txt", b"old\n", b"new\n")
    if operand == "absolute":
        operand = str(Path(cli.repo.path) / "sibling" / "change.txt")
    before = snapshot_repository(cli)

    args = (
        ["commit", "-m", "msg", operand] if command == "commit" else [command, operand]
    )
    result = cli.run(*args, subdir="sub")

    assert result.returncode != 0
    assert "repository path" in result.stderr
    assert snapshot_repository(cli) == before


def test_invalid_mixed_selection_changes_nothing(
    make_mutation_repo: MutationRepoFactory,
) -> None:
    cli = make_mutation_repo("sibling/change.txt", b"old\n", b"new\n")
    valid_id = get_hunk_id(cli, path="sibling/change.txt")
    before = snapshot_repository(cli)

    result = cli.run("stage", valid_id, "missing.txt", subdir="sub")

    assert result.returncode != 0
    assert "staged" not in result.stderr
    assert snapshot_repository(cli) == before
