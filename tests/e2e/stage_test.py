from .conftest import GitHunkCLI


def test_stage_single_hunk(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2

    cli.run_ok("stage", hunks[0]["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "CHANGED2" in staged
    assert "CHANGED18" not in staged

    unstaged = cli.repo.git("diff")
    assert "CHANGED18" in unstaged


def test_stage_hunk_by_uppercase_id(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    cli.run_ok("stage", hunks[0]["id"].upper())

    staged = cli.repo.git("diff", "--cached")
    assert "+new" in staged


def test_stage_multiple_hunks(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    cli.run_ok("stage", hunks[0]["id"], hunks[1]["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "CHANGED2" in staged
    assert "CHANGED18" in staged

    unstaged = cli.repo.git("diff")
    assert unstaged.strip() == ""


def test_stage_from_different_files(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_list_json("list", "--json")
    a_hunk = next(h for h in hunks if h["file"]["text"] == "a.py")

    cli.run_ok("stage", a_hunk["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "AAA" in staged
    assert "BBB" not in staged
