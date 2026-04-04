from .conftest import GitHunkCLI


def test_unstage_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    staged = cli.run_json("list", "--staged", "--json")
    assert len(staged) == 1

    cli.run_ok("unstage", staged[0]["id"])

    after_staged = cli.run_json("list", "--staged", "--json")
    assert len(after_staged) == 0

    unstaged = cli.run_json("list", "--json")
    assert len(unstaged) == 1


def test_unstage_one_of_multiple(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", "f.py")

    staged = cli.run_json("list", "--staged", "--json")
    assert len(staged) == 2

    cli.run_ok("unstage", staged[0]["id"])

    after = cli.run_json("list", "--staged", "--json")
    assert len(after) == 1
