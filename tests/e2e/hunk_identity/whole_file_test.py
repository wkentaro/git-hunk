import os
import sys
from pathlib import Path

import pytest

from ..conftest import GitHunkCLI


def test_binary_id_includes_content_and_survives_complete_move(
    cli: GitHunkCLI,
) -> None:
    path = Path(cli.repo.path) / "f.bin"
    path.write_bytes(b"\x00base")
    cli.repo.git("add", "f.bin")
    cli.repo.git("commit", "-m", "init")
    path.write_bytes(b"\x00first")
    [first] = cli.run_list_json("list", "--json")

    cli.run_ok("stage", first["id"])
    [staged] = cli.run_list_json("list", "--json")
    cli.run_ok("unstage", first["id"])
    path.write_bytes(b"\x00second")
    [second] = cli.run_list_json("list", "--json")

    assert staged["id"] == first["id"]
    assert second["id"] != first["id"]


@pytest.mark.skipif(
    os.name == "nt", reason="git does not track the executable bit on Windows"
)
def test_mode_id_includes_transition_direction(cli: GitHunkCLI) -> None:
    cli.repo.git("config", "core.fileMode", "true")
    path = Path(cli.repo.path) / "f.sh"
    path.write_text("echo hi\n")
    path.chmod(0o644)
    cli.repo.git("add", "f.sh")
    cli.repo.git("commit", "-m", "init")
    path.chmod(0o755)
    [made_executable] = cli.run_list_json("list", "--json")

    cli.repo.git("add", "f.sh")
    cli.repo.git("commit", "-m", "executable")
    path.chmod(0o644)
    [made_plain] = cli.run_list_json("list", "--json")

    assert made_plain["id"] != made_executable["id"]


@pytest.mark.skipif(
    sys.platform == "win32", reason="git does not track symlinks on Windows"
)
def test_type_id_includes_changed_object_content(cli: GitHunkCLI) -> None:
    path = Path(cli.repo.path) / "f.txt"
    path.write_text("file\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    path.unlink()
    path.symlink_to("first-target")
    [first] = cli.run_list_json("list", "--json")

    path.unlink()
    path.symlink_to("second-target")
    [second] = cli.run_list_json("list", "--json")

    assert second["id"] != first["id"]
