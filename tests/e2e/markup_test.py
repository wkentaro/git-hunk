import pytest

from .conftest import GitHunkCLI

# A path like a Next.js/SvelteKit route; the brackets must not be read as Rich
# markup tags.
_PATH = "src/[id].tsx"


@pytest.fixture
def bracket_repo(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file(_PATH, "a\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file(_PATH, "A\n")
    return cli


def test_list_renders_bracketed_path_verbatim(bracket_repo: GitHunkCLI) -> None:
    assert _PATH in bracket_repo.run_ok("list")


def test_show_renders_bracketed_path_verbatim(bracket_repo: GitHunkCLI) -> None:
    assert _PATH in bracket_repo.run_ok("show")


def test_list_renders_bracketed_untracked_path_verbatim(cli: GitHunkCLI) -> None:
    cli.repo.write_file("keep.txt", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file(_PATH, "new\n")  # left untracked

    assert _PATH in cli.run_ok("list")


def test_error_renders_bracketed_value_verbatim(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.txt", "a\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "A\n")

    r = cli.run("stage", "[bogus]")
    assert r.returncode != 0
    assert "no changed file matches '[bogus]'" in r.stderr
