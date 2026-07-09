import pytest

from git_hunk._cli import cli as cli_group

from .conftest import GitHunkCLI

SUBCOMMAND_HELP = [
    ("list", "List hunks"),
    ("show", "Show the diff for one or more hunks"),
    ("stage", "Stage one or more specific hunks"),
    ("unstage", "Unstage one or more specific hunks"),
    ("discard", "Discard unstaged changes for one or more specific hunks"),
    ("commit", "Stage one or more specific hunks and commit them in one step"),
    ("skills", "List and retrieve bundled skill content"),
]


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize(
    ("command", "expected"),
    SUBCOMMAND_HELP,
    ids=[command for command, _ in SUBCOMMAND_HELP],
)
def test_subcommand_help(
    cli: GitHunkCLI, command: str, flag: str, expected: str
) -> None:
    r = cli.run(command, flag)
    assert r.returncode == 0
    assert expected in r.stderr


def test_subcommand_help_covers_every_command() -> None:
    assert {command for command, _ in SUBCOMMAND_HELP} == set(cli_group.commands)
