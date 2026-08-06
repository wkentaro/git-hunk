import pytest

from ..conftest import GitHunkCLI


@pytest.mark.parametrize("command", ["show", "stage", "unstage", "discard", "commit"])
def test_commands_accept_case_insensitive_hunk_id_prefix(
    modified_text_hunk: GitHunkCLI, command: str
) -> None:
    cli = modified_text_hunk
    if command == "unstage":
        cli.repo.git("add", "f.txt")
    [hunk] = cli.run_list_json("list", "--json")
    args = [command, hunk["id"][:7].upper()]
    if command == "commit":
        args += ["-m", "change"]

    cli.run_ok(*args)

    if command == "show":
        assert cli.repo.git("diff") != ""
    elif command == "stage":
        assert cli.repo.git("show", ":f.txt") == "new\n"
    elif command == "unstage":
        assert cli.repo.git("show", ":f.txt") == "old\n"
    elif command == "discard":
        assert cli.repo.git("diff") == ""
    else:
        assert cli.repo.git("show", "HEAD:f.txt") == "new\n"
