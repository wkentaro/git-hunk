import os
import sys
from pathlib import Path

import pytest

from .conftest import GitHunkCLI


def _id_for(cli: GitHunkCLI, path: str, *flags: str) -> str:
    hunks = cli.run_list_json("list", *flags, "--json")
    return next(h["id"] for h in hunks if h["file"]["text"] == path)


@pytest.fixture
def modified_binary(cli: GitHunkCLI) -> GitHunkCLI:
    path = Path(cli.repo.path) / "a.bin"
    path.write_bytes(b"\x00\x01bin\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.write_bytes(b"\x00\x02BIN\xfe")
    return cli


def test_list_distinguishes_modified_and_deleted_binary(cli: GitHunkCLI) -> None:
    root = Path(cli.repo.path)
    (root / "a.bin").write_bytes(b"\x00\x01a\xff")
    (root / "d.bin").write_bytes(b"\x00\x01d\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (root / "a.bin").write_bytes(b"\x00\x02A\xfe")
    (root / "d.bin").unlink()

    by_file = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    assert by_file["a.bin"]["binary"] is True
    assert by_file["a.bin"]["change_kind"] == "M"
    assert by_file["a.bin"]["header"] is None
    assert by_file["d.bin"]["binary"] is True
    assert by_file["d.bin"]["change_kind"] == "D"


def test_show_binary_has_no_blank_numbered_line(modified_binary: GitHunkCLI) -> None:
    out = modified_binary.run_ok(
        "show", _id_for(modified_binary, "a.bin", "--unstaged")
    )
    assert "Binary file (modified)" in out
    assert "  1 " not in out  # no numbered line from an empty diff body


def test_stage_unstage_discard_modified_binary(modified_binary: GitHunkCLI) -> None:
    cli = modified_binary
    cli.run_ok("stage", _id_for(cli, "a.bin", "--unstaged"))
    assert "a.bin" in cli.repo.git("diff", "--cached", "--name-only")

    cli.run_ok("unstage", _id_for(cli, "a.bin", "--staged"))
    assert cli.repo.git("diff", "--cached").strip() == ""

    cli.run_ok("discard", _id_for(cli, "a.bin", "--unstaged"))
    assert cli.repo.git("diff").strip() == ""


def test_line_selection_rejected_on_binary(modified_binary: GitHunkCLI) -> None:
    cli = modified_binary
    r = cli.run("stage", _id_for(cli, "a.bin", "--unstaged"), "-l", "1")
    assert r.returncode != 0
    assert "not supported for binary, mode, or type changes" in r.stderr


def test_stage_deleted_binary(cli: GitHunkCLI) -> None:
    path = Path(cli.repo.path) / "d.bin"
    path.write_bytes(b"\x00\x01del\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.unlink()

    cli.run_ok("stage", _id_for(cli, "d.bin", "--unstaged"))
    assert "D\td.bin" in cli.repo.git("diff", "--cached", "--name-status")

    cli.run_ok("unstage", _id_for(cli, "d.bin", "--staged"))
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_stage_added_binary(cli: GitHunkCLI) -> None:
    # A new binary is untracked; stage it, then it shows as an added binary.
    (Path(cli.repo.path) / "keep.txt").write_text("x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (Path(cli.repo.path) / "n.bin").write_bytes(b"\x00new\xff")

    cli.repo.git("add", "n.bin")
    staged = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--staged", "--json")
    }
    assert staged["n.bin"]["binary"] is True
    assert staged["n.bin"]["change_kind"] == "A"

    cli.run_ok("unstage", _id_for(cli, "n.bin", "--staged"))
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_stage_and_unstage_text_and_binary_hunk_together(cli: GitHunkCLI) -> None:
    # git-hunk's pitch is grouping hunks by intent, so a single command may mix a
    # text hunk (applied via a patch) with a whole-file binary hunk (staged whole).
    root = Path(cli.repo.path)
    (root / "t.txt").write_text("hello\n")
    (root / "a.bin").write_bytes(b"\x00\x01bin\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    (root / "t.txt").write_text("hello\nworld\n")
    (root / "a.bin").write_bytes(b"\x00\x02BIN\xfe")

    unstaged = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    cli.run_ok("stage", unstaged["t.txt"]["id"], unstaged["a.bin"]["id"])
    assert sorted(cli.repo.git("diff", "--cached", "--name-only").split()) == [
        "a.bin",
        "t.txt",
    ]
    assert cli.repo.git("diff", "--name-only").strip() == ""

    staged = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--staged", "--json")
    }
    cli.run_ok("unstage", staged["t.txt"]["id"], staged["a.bin"]["id"])
    assert cli.repo.git("diff", "--cached").strip() == ""


@pytest.mark.skipif(
    sys.platform == "win32", reason="git does not track symlinks on Windows"
)
def test_typechange_stage_unstage_discard(cli: GitHunkCLI) -> None:
    # git emits a file -> symlink type change as a delete + add pair; git-hunk
    # surfaces it as a single "T" whole-file hunk staged whole.
    path = Path(cli.repo.path) / "tc.txt"
    path.write_text("hello\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.unlink()
    path.symlink_to("target")

    by_file = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    assert by_file["tc.txt"]["change_kind"] == "T"
    assert by_file["tc.txt"]["a_mode"] == "100644"
    assert by_file["tc.txt"]["b_mode"] == "120000"
    assert by_file["tc.txt"]["header"] is None
    # The human label is derived from the typed fields at display time.
    assert "Type change (100644 -> 120000)" in cli.run_ok("list", "--unstaged")

    cli.run_ok("stage", _id_for(cli, "tc.txt", "--unstaged"))
    assert "T\ttc.txt" in cli.repo.git("diff", "--cached", "--name-status")

    cli.run_ok("unstage", _id_for(cli, "tc.txt", "--staged"))
    assert cli.repo.git("diff", "--cached").strip() == ""

    cli.run_ok("discard", _id_for(cli, "tc.txt", "--unstaged"))
    assert cli.repo.git("diff").strip() == ""


@pytest.mark.skipif(
    sys.platform == "win32", reason="git does not track unix file modes on Windows"
)
def test_stage_and_discard_mode_only_change(cli: GitHunkCLI) -> None:
    cli.repo.git("config", "core.fileMode", "true")
    path = Path(cli.repo.path) / "m.sh"
    path.write_text("plain\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    os.chmod(path, 0o755)

    by_file = {
        h["file"]["text"]: h for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    assert by_file["m.sh"]["change_kind"] == "M"
    assert by_file["m.sh"]["binary"] is False
    assert by_file["m.sh"]["header"] is None
    assert by_file["m.sh"]["a_mode"] != by_file["m.sh"]["b_mode"]
    # The human label is derived from the typed fields at display time.
    assert "Mode 100644 -> 100755" in cli.run_ok("list", "--unstaged")

    cli.run_ok("stage", _id_for(cli, "m.sh", "--unstaged"))
    assert "m.sh" in cli.repo.git("diff", "--cached", "--name-only")

    cli.run_ok("unstage", _id_for(cli, "m.sh", "--staged"))
    cli.run_ok("discard", _id_for(cli, "m.sh", "--unstaged"))
    assert cli.repo.git("diff").strip() == ""
