import pytest

from ..conftest import GitHunkCLI


@pytest.fixture
def modified_text_hunk(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.txt", "old\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "new\n")
    return cli


@pytest.fixture
def duplicate_hunks(cli: GitHunkCLI) -> GitHunkCLI:
    block = ["A", "B", "C", "target", "D", "E", "F"]
    separator = [f"separator {number}" for number in range(30)]
    cli.repo.write_file("f.txt", "\n".join(block + separator + block) + "\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file(
        "f.txt", "\n".join(block + separator + block).replace("target", "TARGET") + "\n"
    )
    return cli
