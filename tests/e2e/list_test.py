from .conftest import GitHunkCLI


def test_no_changes_returns_empty_list(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "hello\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    hunks = cli.run_json("list", "--json")
    assert hunks == []


def test_single_file_single_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "line1\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "LINE1\nline2\nline3\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"] == "f.py"
    assert hunks[0]["additions"] == 1
    assert hunks[0]["deletions"] == 1
    assert "id" in hunks[0]


def test_single_file_multiple_hunks(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 2
    assert all(h["file"] == "f.py" for h in hunks)


def test_multi_file_changes(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 2
    files = {h["file"] for h in hunks}
    assert files == {"a.py", "b.py"}


def test_list_staged(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    hunks = cli.run_json("list", "--staged", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"] == "f.py"


def test_list_file_filter(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_json("list", "--json", "a.py")
    assert len(hunks) == 1
    assert hunks[0]["file"] == "a.py"


def test_list_new_file(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("new.py", "brand new\n")
    cli.repo.git("add", "new.py")

    hunks = cli.run_json("list", "--staged", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"] == "new.py"
    assert int(hunks[0]["additions"]) >= 1
    assert hunks[0]["deletions"] == 0


def test_list_default_shows_staged_and_unstaged(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "staged\n")
    cli.repo.git("add", "f.py")
    cli.repo.write_file("f.py", "unstaged\n")

    hunks = cli.run_json("list", "--json")
    statuses = {h["status"] for h in hunks}
    assert statuses == {"staged", "unstaged"}


def test_list_default_shows_untracked(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("untracked.py", "new\n")

    hunks = cli.run_json("list", "--json")
    untracked = [h for h in hunks if h["status"] == "untracked"]
    assert len(untracked) == 1
    assert untracked[0]["file"] == "untracked.py"


def test_list_unstaged_filter(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "staged\n")
    cli.repo.git("add", "f.py")
    cli.repo.write_file("f.py", "unstaged\n")

    hunks = cli.run_json("list", "--unstaged", "--json")
    assert all(h["status"] == "unstaged" for h in hunks)
    assert len(hunks) == 1


def test_list_staged_and_unstaged_mutual_exclusion(cli: GitHunkCLI) -> None:
    r = cli.run("list", "--staged", "--unstaged")
    assert r.returncode != 0


def test_list_status_field_in_json(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_json("list", "--json")
    assert all("status" in h for h in hunks)
    assert hunks[0]["status"] == "unstaged"
