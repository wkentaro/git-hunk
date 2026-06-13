from pathlib import Path

from .conftest import GitHunkCLI


def _setup_modified(cli: GitHunkCLI) -> str:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "aX\nb\ncX\n")
    hunks = cli.run_json("list", "--unstaged", "--json")
    assert len(hunks) == 1
    return hunks[0]["id"]


def test_stage_dry_run_changes_nothing(cli: GitHunkCLI) -> None:
    hunk_id = _setup_modified(cli)

    r = cli.run("stage", hunk_id, "--dry-run")
    assert r.returncode == 0
    assert "would stage" in r.stderr

    assert cli.repo.git("diff", "--cached").strip() == ""
    assert cli.run_json("list", "--unstaged", "--json")[0]["id"] == hunk_id


def test_discard_dry_run_keeps_working_tree(cli: GitHunkCLI) -> None:
    hunk_id = _setup_modified(cli)

    r = cli.run("discard", hunk_id, "--dry-run")
    assert r.returncode == 0
    assert "would discard" in r.stderr

    assert cli.repo.git("diff").strip() != ""
    assert cli.run_json("list", "--unstaged", "--json")[0]["id"] == hunk_id


def test_unstage_dry_run_keeps_index(cli: GitHunkCLI) -> None:
    hunk_id = _setup_modified(cli)
    cli.run_ok("stage", hunk_id)
    staged_id = cli.run_json("list", "--staged", "--json")[0]["id"]

    r = cli.run("unstage", staged_id, "--dry-run")
    assert r.returncode == 0
    assert "would unstage" in r.stderr

    assert cli.repo.git("diff", "--cached").strip() != ""


def test_dry_run_line_selection_changes_nothing(cli: GitHunkCLI) -> None:
    hunk_id = _setup_modified(cli)

    # Body: 1=-a 2=+aX 3= b 4=-c 5=+cX. Preview staging just the first change.
    r = cli.run("stage", hunk_id, "-l", "1,2", "--dry-run")
    assert r.returncode == 0

    assert cli.repo.git("diff", "--cached").strip() == ""


def test_stage_dry_run_leaves_binary_unstaged(cli: GitHunkCLI) -> None:
    path = Path(cli.repo.path) / "a.bin"
    path.write_bytes(b"\x00\x01bin\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.write_bytes(b"\x00\x02BIN\xfe")

    hunk_id = cli.run_json("list", "--unstaged", "--json")[0]["id"]
    r = cli.run("stage", hunk_id, "--dry-run")
    assert r.returncode == 0
    assert "would stage" in r.stderr

    assert cli.repo.git("diff", "--cached").strip() == ""


def test_dry_run_unknown_id_exits_nonzero(cli: GitHunkCLI) -> None:
    _setup_modified(cli)

    r = cli.run("stage", "deadbee", "--dry-run")
    assert r.returncode != 0
    assert "deadbee" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""
