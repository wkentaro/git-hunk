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

    headers = {
        h["file"]["text"]: h["header"]["text"]
        for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    assert headers["a.bin"] == "Binary file (modified)"
    assert headers["d.bin"] == "Binary file (deleted)"


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
    assert "not supported for binary or mode-only" in r.stderr


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
        h["file"]["text"]: h["header"]["text"]
        for h in cli.run_list_json("list", "--staged", "--json")
    }
    assert staged["n.bin"] == "Binary file (added)"

    cli.run_ok("unstage", _id_for(cli, "n.bin", "--staged"))
    assert cli.repo.git("diff", "--cached").strip() == ""


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

    headers = {
        h["file"]["text"]: h["header"]["text"]
        for h in cli.run_list_json("list", "--unstaged", "--json")
    }
    assert headers["m.sh"].startswith("Mode ")

    cli.run_ok("stage", _id_for(cli, "m.sh", "--unstaged"))
    assert "m.sh" in cli.repo.git("diff", "--cached", "--name-only")

    cli.run_ok("unstage", _id_for(cli, "m.sh", "--staged"))
    cli.run_ok("discard", _id_for(cli, "m.sh", "--unstaged"))
    assert cli.repo.git("diff").strip() == ""
