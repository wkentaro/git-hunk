from pathlib import Path

from .conftest import GitHunkCLI


def _init(cli: GitHunkCLI, files: dict[str, str]) -> None:
    for name, content in files.items():
        cli.repo.write_file(name, content)
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")


def _commit_count(cli: GitHunkCLI) -> int:
    return int(cli.repo.git("rev-list", "--count", "HEAD").strip())


def _unstaged_ids(cli: GitHunkCLI) -> list[str]:
    return [h["id"] for h in cli.run_json("list", "--unstaged", "--json")]


def test_commit_single_hunk(cli: GitHunkCLI) -> None:
    _init(cli, {"f.txt": "a\nb\nc\n"})
    cli.repo.write_file("f.txt", "aX\nb\nc\n")

    before = _commit_count(cli)
    cli.run_ok("commit", _unstaged_ids(cli)[0], "-m", "fix: change a")

    assert _commit_count(cli) == before + 1
    assert cli.repo.git("log", "-1", "--format=%s").strip() == "fix: change a"
    assert "aX" in cli.repo.git("show", "HEAD:f.txt")
    assert cli.repo.git("status", "--porcelain").strip() == ""


def test_commit_multiple_hunks(cli: GitHunkCLI) -> None:
    _init(cli, {"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.write_file("b.txt", "BBB\n")

    ids = _unstaged_ids(cli)
    assert len(ids) == 2
    cli.run_ok("commit", ids[0], ids[1], "-m", "chore: update both")

    head = cli.repo.git("show", "HEAD")
    assert "AAA" in head
    assert "BBB" in head
    assert cli.repo.git("status", "--porcelain").strip() == ""


def test_commit_partial_lines_leaves_remainder_unstaged(cli: GitHunkCLI) -> None:
    _init(cli, {"f.txt": "a\nb\nc\n"})
    cli.repo.write_file("f.txt", "aX\nb\ncX\n")

    # Body: 1=-a 2=+aX 3= b 4=-c 5=+cX. Commit only the a->aX change.
    cli.run_ok("commit", _unstaged_ids(cli)[0], "-l", "1,2", "-m", "fix: only a")

    assert "aX" in cli.repo.git("show", "HEAD:f.txt")
    assert "cX" not in cli.repo.git("show", "HEAD:f.txt")
    # The c->cX change is still in the working tree, unstaged.
    assert "cX" in cli.repo.git("diff")


def test_commit_by_file_path(cli: GitHunkCLI) -> None:
    _init(cli, {"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "A1\nA2\nA3\n")
    cli.repo.write_file("b.txt", "BBB\n")

    cli.run_ok("commit", "a.txt", "-m", "feat: rewrite a")

    assert "A1" in cli.repo.git("show", "HEAD:a.txt")
    # b.txt was not named, so it stays out of the commit and in the working tree.
    assert cli.repo.git("show", "HEAD:b.txt").strip() == "b"
    assert "BBB" in cli.repo.git("diff")


def test_commit_requires_message(cli: GitHunkCLI) -> None:
    _init(cli, {"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    before = _commit_count(cli)
    r = cli.run("commit", _unstaged_ids(cli)[0])
    assert r.returncode != 0
    assert "message" in r.stderr
    assert _commit_count(cli) == before
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_unknown_id_makes_no_commit(cli: GitHunkCLI) -> None:
    _init(cli, {"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    before = _commit_count(cli)
    r = cli.run("commit", "deadbee", "-m", "nope")
    assert r.returncode != 0
    assert _commit_count(cli) == before
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_failure_leaves_hunk_staged(cli: GitHunkCLI) -> None:
    _init(cli, {"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    hook = Path(cli.repo.path) / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    before = _commit_count(cli)
    r = cli.run("commit", _unstaged_ids(cli)[0], "-m", "fix: blocked by hook")
    assert r.returncode != 0
    assert _commit_count(cli) == before
    # The hunk is left staged so the user can retry, not silently lost.
    assert "AAA" in cli.repo.git("diff", "--cached")


def test_commit_aborts_when_index_already_has_staged_changes(cli: GitHunkCLI) -> None:
    _init(cli, {"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.write_file("b.txt", "BBB\n")
    cli.repo.git("add", "a.txt")  # pre-stage an unrelated change

    before = _commit_count(cli)
    b_id = next(h["id"] for h in cli.run_json("list", "--unstaged", "--json"))
    r = cli.run("commit", b_id, "-m", "feat: only b")
    assert r.returncode != 0
    assert "already staged" in r.stderr
    assert _commit_count(cli) == before
    # The pre-staged change is untouched; nothing new was committed or staged.
    assert cli.repo.git("diff", "--cached", "--name-only").strip() == "a.txt"
