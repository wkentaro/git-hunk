from .conftest import GitHunkCLI


def test_untracked_file_path_matches_tracked_basis_from_subdirectory(
    cli: GitHunkCLI,
) -> None:
    cli.repo.write_file("sub/tracked.py", "line1\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("sub/tracked.py", "line1\nline2\n")
    cli.repo.write_file("sub/untracked.py", "new\n")

    hunks = cli.run_list_json("list", "--json", subdir="sub")
    by_status = {h["status"]: h for h in hunks}
    assert by_status["unstaged"]["file"]["text"] == "sub/tracked.py"
    assert by_status["untracked"]["file"]["text"] == "sub/untracked.py"
    assert by_status["untracked"]["b_mode"] == "100644"


def test_untracked_file_filtered_by_relative_arg_from_subdirectory(
    cli: GitHunkCLI,
) -> None:
    cli.repo.write_file("sub/keep.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("sub/wanted.py", "new\n")
    cli.repo.write_file("sub/other.py", "new\n")

    hunks = cli.run_list_json("list", "--json", "wanted.py", subdir="sub")
    assert [h["file"]["text"] for h in hunks] == ["sub/wanted.py"]
    assert hunks[0]["status"] == "untracked"
