from .conftest import GitHunkCLI


def test_unstage_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    staged = cli.run_list_json("list", "--staged", "--json")
    assert len(staged) == 1

    cli.run_ok("unstage", staged[0]["id"])

    after_staged = cli.run_list_json("list", "--staged", "--json")
    assert len(after_staged) == 0

    unstaged = cli.run_list_json("list", "--json")
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

    staged = cli.run_list_json("list", "--staged", "--json")
    assert len(staged) == 2

    cli.run_ok("unstage", staged[0]["id"])

    after = cli.run_list_json("list", "--staged", "--json")
    assert len(after) == 1


def test_unstage_two_hunks_keeps_unselected_insertion_staged(
    cli: GitHunkCLI,
) -> None:
    original = [f"line {number}" for number in range(1, 61)]
    cli.repo.write_file("f.py", "\n".join(original) + "\n")
    cli.repo.git("add", "f.py")
    cli.repo.git("commit", "-m", "init")

    changed = original[:]
    changed.insert(changed.index("line 3"), "selected insertion")
    changed.insert(changed.index("line 30"), "kept insertion")
    changed[changed.index("line 55")] = "selected replacement"
    cli.repo.write_file("f.py", "\n".join(changed) + "\n")
    cli.repo.git("add", "f.py")
    staged = cli.run_list_json("list", "--staged", "--json")
    assert len(staged) == 3

    cli.run_ok("unstage", staged[2]["id"], staged[0]["id"])

    expected_index = original[:]
    expected_index.insert(expected_index.index("line 30"), "kept insertion")
    assert cli.repo.git("show", ":f.py") == "\n".join(expected_index) + "\n"
    assert cli.repo.run("cat", "f.py").stdout == "\n".join(changed) + "\n"
