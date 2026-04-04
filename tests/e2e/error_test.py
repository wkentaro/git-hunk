from .conftest import GitHunkCLI


def test_version(cli: GitHunkCLI) -> None:
    r = cli.run("--version")
    assert r.returncode == 0
    assert "git-hunk" in r.stderr


def test_help(cli: GitHunkCLI) -> None:
    r = cli.run("--help")
    assert r.returncode == 0


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

    r = cli.run("stage", "nonexistent")
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_line_spec_with_multiple_hunks_fails(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 2

    r = cli.run("stage", hunks[0]["id"], hunks[1]["id"], "-l", "1")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr
