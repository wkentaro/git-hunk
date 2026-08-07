from ..conftest import GitHunkCLI


def test_partial_operation_creates_new_hunk_ids(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nfirst\nb\nc\nsecond\n")
    [original] = cli.run_list_json("show", "--unstaged", "--json")
    first_line = next(
        line["n"] for line in original["lines"] if line["content"] == {"text": "first"}
    )

    cli.run_ok("stage", original["id"], "-l", str(first_line))

    results = cli.run_list_json("list", "--json")
    assert {hunk["status"] for hunk in results} == {"staged", "unstaged"}
    assert original["id"] not in {hunk["id"] for hunk in results}
    assert len({hunk["id"] for hunk in results}) == 2
    stale = cli.run("stage", original["id"])
    assert stale.returncode == 1
    assert "not found" in stale.stderr

    remainder = next(hunk for hunk in results if hunk["status"] == "unstaged")
    cli.run_ok("stage", remainder["id"])
    assert cli.repo.git("diff") == ""
