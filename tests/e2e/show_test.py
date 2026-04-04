from .conftest import GitHunkCLI


def test_show_hunk_by_full_id(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_json("list", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id)
    assert r.returncode == 0
    assert "-old" in r.stdout
    assert "+new" in r.stdout


def test_show_hunk_by_prefix(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_json("list", "--json")
    prefix = hunks[0]["id"][:4]

    r = cli.run("show", prefix)
    assert r.returncode == 0
    assert "@@" in r.stdout


def test_show_staged_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    hunks = cli.run_json("list", "--staged", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id, "--staged")
    assert r.returncode == 0
    assert "+new" in r.stdout
