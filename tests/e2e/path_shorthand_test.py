import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def multi_hunk_repo(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("big.py", "\n".join(f"l{i}" for i in range(1, 11)) + "\n")
    cli.repo.write_file("b.py", "other\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    lines = [f"l{i}" for i in range(1, 11)]
    lines[0] = "L1"
    lines[9] = "L10"  # two change groups far enough apart to be two hunks
    cli.repo.write_file("big.py", "\n".join(lines) + "\n")
    cli.repo.write_file("b.py", "OTHER\n")
    return cli


def test_stage_whole_file_by_path(multi_hunk_repo: GitHunkCLI) -> None:
    cli = multi_hunk_repo
    hunks = cli.run_list_json("list", "--unstaged", "--json")
    assert len([h for h in hunks if h["file"]["text"] == "big.py"]) == 2

    cli.run_ok("stage", "big.py")
    assert cli.repo.git("diff", "--cached", "--name-only").split() == ["big.py"]
    assert cli.repo.git("diff", "--name-only").split() == ["b.py"]


def test_unstage_whole_file_by_path(multi_hunk_repo: GitHunkCLI) -> None:
    cli = multi_hunk_repo
    cli.run_ok("stage", "big.py")

    cli.run_ok("unstage", "big.py")
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_discard_whole_file_by_path(multi_hunk_repo: GitHunkCLI) -> None:
    cli = multi_hunk_repo
    cli.run_ok("discard", "big.py")
    assert "big.py" not in cli.repo.git("diff", "--name-only")
    assert "b.py" in cli.repo.git("diff", "--name-only")


def test_dot_slash_prefixed_path(multi_hunk_repo: GitHunkCLI) -> None:
    multi_hunk_repo.run_ok("stage", "./big.py")
    staged = multi_hunk_repo.repo.git("diff", "--cached", "--name-only").split()
    assert staged == ["big.py"]


def test_subdirectory_path(cli: GitHunkCLI) -> None:
    cli.repo.write_file("sub/nested.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("sub/nested.py", "new\n")

    cli.run_ok("stage", "sub/nested.py")
    staged = cli.repo.git("diff", "--cached", "--name-only").split()
    assert staged == ["sub/nested.py"]


def test_mixing_path_and_id(multi_hunk_repo: GitHunkCLI) -> None:
    cli = multi_hunk_repo
    hunks = cli.run_list_json("list", "--unstaged", "--json")
    b_id = next(h["id"] for h in hunks if h["file"]["text"] == "b.py")

    cli.run_ok("stage", "big.py", b_id)
    staged = sorted(cli.repo.git("diff", "--cached", "--name-only").split())
    assert staged == ["b.py", "big.py"]


def test_path_and_id_of_same_hunk_dedup(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "X\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    # Same hunk named twice (by path and by id) must apply once, not error.
    cli.run_ok("stage", "f.py", hunk_id)
    assert cli.repo.git("diff", "--cached", "--name-only").split() == ["f.py"]


def test_path_takes_precedence_over_id_lookalike(cli: GitHunkCLI) -> None:
    # A changed file whose name looks like a hunk id is treated as a path.
    cli.repo.write_file("a1b2c3d", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("a1b2c3d", "X\n")

    cli.run_ok("stage", "a1b2c3d")
    assert "a1b2c3d" in cli.repo.git("diff", "--cached", "--name-only")


def test_line_selection_rejected_for_multi_hunk_path(
    multi_hunk_repo: GitHunkCLI,
) -> None:
    r = multi_hunk_repo.run("stage", "big.py", "-l", "1")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr


def test_matching_selection_rejected_for_multi_hunk_path(
    multi_hunk_repo: GitHunkCLI,
) -> None:
    r = multi_hunk_repo.run("stage", "big.py", "--include-matching", "L")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr


def test_unknown_path_errors_clearly(multi_hunk_repo: GitHunkCLI) -> None:
    # A non-hex argument can only be a path, so the error names the file.
    r = multi_hunk_repo.run("stage", "does-not-exist.py")
    assert r.returncode != 0
    assert "no changed file matches 'does-not-exist.py'" in r.stderr
