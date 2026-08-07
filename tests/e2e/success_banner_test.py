from collections.abc import Callable

import pytest

from .conftest import GitHunkCLI


def _unstaged_hunk_id(cli: GitHunkCLI) -> str:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "aX\nb\nc\n")
    return cli.run_list_json("list", "--unstaged", "--json")[0]["id"]


def _staged_hunk_id(cli: GitHunkCLI) -> str:
    cli.run_ok("stage", _unstaged_hunk_id(cli))
    return cli.run_list_json("list", "--staged", "--json")[0]["id"]


def _two_unstaged_hunk_ids(cli: GitHunkCLI) -> list[str]:
    cli.repo.write_file("a.txt", "a\n")
    cli.repo.write_file("b.txt", "b\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("a.txt", "aX\n")
    cli.repo.write_file("b.txt", "bX\n")
    ids = [h["id"] for h in cli.run_list_json("list", "--unstaged", "--json")]
    assert len(ids) == 2
    return ids


@pytest.mark.parametrize(
    ("command", "verb", "make_hunk_id"),
    [
        ("stage", "staged", _unstaged_hunk_id),
        ("unstage", "unstaged", _staged_hunk_id),
        ("discard", "discarded", _unstaged_hunk_id),
    ],
    ids=["stage", "unstage", "discard"],
)
def test_banner_reports_verb_id_file_header_and_stats(
    cli: GitHunkCLI,
    command: str,
    verb: str,
    make_hunk_id: Callable[[GitHunkCLI], str],
) -> None:
    hunk_id = make_hunk_id(cli)
    r = cli.run(command, hunk_id)
    assert r.returncode == 0
    assert r.stderr.splitlines() == [
        f"  {verb} {hunk_id[:7]}  f.txt  @@ -1,3 +1,3 @@  +1 -1"
    ]


def test_banner_reports_one_line_per_selected_hunk(cli: GitHunkCLI) -> None:
    ids = _two_unstaged_hunk_ids(cli)

    r = cli.run("stage", *ids)
    assert r.returncode == 0
    assert r.stderr.splitlines() == [
        f"  staged {ids[0][:7]}  a.txt  @@ -1 +1 @@  +1 -1",
        f"  staged {ids[1][:7]}  b.txt  @@ -1 +1 @@  +1 -1",
    ]


def test_commit_banner_reports_singular_count_and_subject(cli: GitHunkCLI) -> None:
    hunk_id = _unstaged_hunk_id(cli)
    r = cli.run("commit", hunk_id, "-m", "fix: change a")
    assert r.returncode == 0
    assert r.stderr.splitlines() == ["  committed 1 hunk  fix: change a"]


def test_commit_banner_reports_only_the_message_subject(cli: GitHunkCLI) -> None:
    hunk_id = _unstaged_hunk_id(cli)
    r = cli.run("commit", hunk_id, "-m", "fix: change a\n\nwhy a had to change\n")
    assert r.returncode == 0
    assert r.stderr.splitlines() == ["  committed 1 hunk  fix: change a"]


def test_commit_banner_pluralizes_multiple_hunks(cli: GitHunkCLI) -> None:
    ids = _two_unstaged_hunk_ids(cli)

    r = cli.run("commit", *ids, "-m", "fix: change both")
    assert r.returncode == 0
    assert r.stderr.splitlines() == ["  committed 2 hunks  fix: change both"]
