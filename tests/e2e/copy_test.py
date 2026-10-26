from pathlib import Path
from typing import Final

import pytest

from .conftest import GitHunkCLI

CONTENT: Final = "one\ntwo\nthree\nfour\nfive\n"


@pytest.fixture
def copied_file(*, cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.git("config", "core.autocrlf", "false")
    root = Path(cli.repo.path)
    (root / "source.txt").write_bytes(CONTENT.encode())
    cli.repo.write_file("other.txt", "before\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (root / "copy.txt").write_bytes(CONTENT.encode())
    return cli


@pytest.mark.parametrize("edit_source", [False, True])
@pytest.mark.parametrize("edit_copy", [False, True])
def test_staged_copy_is_an_addition_with_copy_detection_configured(
    *, copied_file: GitHunkCLI, edit_source: bool, edit_copy: bool
) -> None:
    cli = copied_file
    cli.repo.git("config", "diff.renames", "copies")
    if edit_source:
        (Path(cli.repo.path) / "source.txt").write_bytes((CONTENT + "six\n").encode())
    content = CONTENT.replace("two", "two changed") if edit_copy else CONTENT
    (Path(cli.repo.path) / "copy.txt").write_bytes(content.encode())
    cli.repo.git("add", "source.txt", "copy.txt")
    assert "copy from source.txt" in cli.repo.git(
        "diff", "--cached", "--find-copies", "--find-copies-harder"
    )

    hunks = cli.run_list_json("show", "copy.txt", "--staged", "--json")

    assert len(hunks) == 1
    assert hunks[0]["change_kind"] == "A"
    assert hunks[0]["a_mode"] is None
    assert hunks[0]["additions"] == len(content.splitlines())
    assert hunks[0]["deletions"] == 0
    assert all(line["op"] == "+" for line in hunks[0]["lines"])


@pytest.mark.parametrize("intent_to_add", [False, True])
def test_stage_and_unstage_copy_preserve_its_source_and_worktree(
    *, copied_file: GitHunkCLI, intent_to_add: bool
) -> None:
    cli = copied_file
    if intent_to_add:
        cli.repo.git("add", "--intent-to-add", "copy.txt")
    source_index = cli.repo.git("ls-files", "--stage", "--", "source.txt")

    cli.run_ok("stage", "copy.txt")

    assert cli.repo.git("diff", "--cached", "--name-only") == "copy.txt\n"
    assert cli.repo.git("show", ":copy.txt") == CONTENT
    cli.run_ok("unstage", "copy.txt")
    assert cli.repo.git("diff", "--cached") == ""
    assert (Path(cli.repo.path) / "copy.txt").read_bytes() == CONTENT.encode()
    assert (Path(cli.repo.path) / "source.txt").read_bytes() == CONTENT.encode()
    assert cli.repo.git("ls-files", "--stage", "--", "source.txt") == source_index


@pytest.mark.parametrize("intent_to_add", [False, True])
def test_commit_copy_leaves_source_unchanged(
    *, copied_file: GitHunkCLI, intent_to_add: bool
) -> None:
    cli = copied_file
    if intent_to_add:
        cli.repo.git("add", "--intent-to-add", "copy.txt")
    source_id = cli.repo.git("rev-parse", "HEAD:source.txt")

    cli.run_ok("commit", "copy.txt", "-m", "feat: add a copy")

    assert cli.repo.git("show", "HEAD:copy.txt") == CONTENT
    assert cli.repo.git("rev-parse", "HEAD:source.txt") == source_id
    assert cli.repo.git("diff", "HEAD~", "HEAD", "--name-only") == "copy.txt\n"
    assert cli.repo.git("status", "--porcelain") == ""


@pytest.mark.parametrize("staged", [False, True])
def test_copy_does_not_block_inspecting_an_unrelated_path(
    *, copied_file: GitHunkCLI, staged: bool
) -> None:
    cli = copied_file
    cli.repo.git("add", *([] if staged else ["--intent-to-add"]), "copy.txt")
    cli.repo.write_file("other.txt", "after\n")

    hunks = cli.run_list_json("list", "other.txt", "--json")

    assert [h["file"]["text"] for h in hunks] == ["other.txt"]
    assert "+after" in cli.run_ok("show", "other.txt")


def test_discard_intent_to_add_copy_preserves_source(
    *, copied_file: GitHunkCLI
) -> None:
    cli = copied_file
    cli.repo.git("add", "--intent-to-add", "copy.txt")
    source_index = cli.repo.git("ls-files", "--stage", "--", "source.txt")

    cli.run_ok("discard", "copy.txt")

    assert not (Path(cli.repo.path) / "copy.txt").exists()
    assert (Path(cli.repo.path) / "source.txt").read_bytes() == CONTENT.encode()
    assert cli.repo.git("ls-files", "--stage", "--", "source.txt") == source_index


def test_binary_copy_can_be_staged_and_unstaged(*, cli: GitHunkCLI) -> None:
    cli.repo.git("config", "core.autocrlf", "false")
    root = Path(cli.repo.path)
    content = b"\x00one\ntwo\nthree\nfour\nfive\n"
    (root / "source.bin").write_bytes(content)
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (root / "copy.bin").write_bytes(content)
    cli.repo.git("add", "--intent-to-add", "copy.bin")

    cli.run_ok("stage", "copy.bin")
    cli.run_ok("unstage", "copy.bin")

    assert cli.repo.git("diff", "--cached") == ""
    assert (root / "source.bin").read_bytes() == content
    assert (root / "copy.bin").read_bytes() == content
