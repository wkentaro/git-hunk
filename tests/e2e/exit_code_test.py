import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def cli_with_change(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.py", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "A\nb\nC\n")
    return cli


# A caller that got the invocation wrong exits 2 and is shown how to invoke it;
# a caller that invoked correctly but named something unresolvable exits 1. The
# two halves are one decision in CliGroup.invoke, so they are pinned together.


@pytest.mark.parametrize(
    "args",
    [
        ("bogus",),
        ("stage",),
        ("stage", "--regex"),
        ("stage", "-l", "1", "--include-matching", "x"),
        ("commit", "f.py"),
    ],
    ids=[
        "unknown-subcommand",
        "stage-without-target",
        "regex-without-pattern",
        "conflicting-selectors",
        "commit-without-message",
    ],
)
def test_usage_error_exits_2_with_usage_block(
    cli: GitHunkCLI, args: tuple[str, ...]
) -> None:
    # These are rejected before any repo lookup, so a bare repo is enough.
    r = cli.run(*args)
    assert r.returncode == 2
    assert "Usage:" in r.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("stage", "deadbee"),
        ("stage", ""),
        ("show", ""),
        ("stage", "f.py", "-l", "1-2-3"),
    ],
    ids=[
        "unknown-hunk-id",
        "empty-target",
        "empty-id-on-show",
        "malformed-line-spec",
    ],
)
def test_domain_error_exits_1_without_usage_block(
    cli_with_change: GitHunkCLI, args: tuple[str, ...]
) -> None:
    r = cli_with_change.run(*args)
    assert r.returncode == 1
    assert "Usage:" not in r.stderr
