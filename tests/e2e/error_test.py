from collections import Counter
from pathlib import Path

import pytest

from tests.conftest import GitRepo

from .conftest import GitHunkCLI


def test_missing_git_binary_reports_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "git executable not found" in r.stderr
    assert "Traceback" not in r.stderr


def test_not_a_git_repo(tmp_path: Path) -> None:
    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr


def test_bare_repo(tmp_path: Path) -> None:
    repo = GitRepo(str(tmp_path))
    repo.run("git", "init", "--bare")
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr


def test_version(cli: GitHunkCLI) -> None:
    r = cli.run("--version")
    assert r.returncode == 0
    assert "git-hunk" in r.stderr


def test_help(cli: GitHunkCLI) -> None:
    r = cli.run("--help")
    assert r.returncode == 0
    assert "Examples:" in r.stderr
    assert "git-hunk stage d161935" in r.stderr


def test_unknown_command(cli: GitHunkCLI) -> None:
    r = cli.run("bogus")
    assert r.returncode != 0


def test_stage_missing_id(cli: GitHunkCLI) -> None:
    r = cli.run("stage")
    assert r.returncode != 0


def test_stage_nonexistent_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("stage", "deadbee")
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_empty_hunk_id_rejected(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("discard", "")
    assert r.returncode != 0
    assert "must not be empty" in r.stderr
    # The empty id must never match a hunk: the change is left untouched.
    assert cli.repo.git("diff").strip() != ""


def test_empty_hunk_id_rejected_on_show(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("show", "")
    assert r.returncode != 0
    assert "must not be empty" in r.stderr


def test_ambiguous_hunk_id_rejected(cli: GitHunkCLI) -> None:
    # IDs are 7-char hex prefixes; with more than 16 hunks two must share a
    # leading hex char (pigeonhole), so a single-char prefix is ambiguous.
    for i in range(20):
        cli.repo.write_file(f"f{i:02d}.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    for i in range(20):
        cli.repo.write_file(f"f{i:02d}.py", "new\n")

    ids = [h["id"] for h in cli.run_list_json("list", "--unstaged", "--json")]
    first_char_counts = Counter(hunk_id[0] for hunk_id in ids)
    prefix = next(
        (char for char, count in first_char_counts.items() if count > 1), None
    )
    assert prefix is not None  # pigeonhole guarantees a collision for >16 hunks

    r = cli.run("stage", prefix)
    assert r.returncode != 0
    assert "ambiguous" in r.stderr
    # An ambiguous id must stage nothing.
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_malformed_line_spec_rejected(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "A\nb\nC\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    r = cli.run("stage", hunk_id, "-l", "1-2-3")
    assert r.returncode != 0
    assert "1-2-3" in r.stderr
    assert "expected start-end" in r.stderr  # readable message, not raw int() error


def test_empty_line_spec_rejected(cli: GitHunkCLI) -> None:
    # An empty -l must error, not silently fall through and stage the whole hunk.
    cli.repo.write_file("f.py", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "A\nb\nC\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    r = cli.run("stage", hunk_id, "-l", "")
    assert r.returncode != 0
    assert "empty line specification" in r.stderr
    assert cli.repo.git("show", ":f.py") == "a\nb\nc\n"  # nothing staged


def test_line_spec_with_multiple_hunks_fails(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2

    r = cli.run("stage", hunks[0]["id"], hunks[1]["id"], "-l", "1")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr
