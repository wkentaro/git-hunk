from .conftest import GitHunkCLI


def test_discard_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 1

    cli.run_ok("discard", hunks[0]["id"])

    after = cli.run_list_json("list", "--json")
    assert len(after) == 0

    content = cli.repo.run("cat", "f.py").stdout
    assert content == "old\n"


def test_discard_one_of_multiple(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2

    cli.run_ok("discard", hunks[0]["id"])

    after = cli.run_list_json("list", "--json")
    assert len(after) == 1

    content = cli.repo.run("cat", "f.py").stdout
    assert "CHANGED18" in content


def test_discard_restores_from_index_not_head(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "line1\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "STAGED\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.write_file("f.py", "STAGED\nline2\nUNSTAGED\n")

    unstaged = cli.run_list_json("list", "--unstaged", "--json")
    assert len(unstaged) == 1

    cli.run_ok("discard", unstaged[0]["id"])

    content = cli.repo.run("cat", "f.py").stdout
    assert content == "STAGED\nline2\nline3\n"
