from collections import Counter
from pathlib import Path

import pytest

from tests.conftest import GitRepo

from .conftest import GitHunkCLI


def test_missing_git_binary_reports_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "git executable not found" in r.stderr
    assert "Traceback" not in r.stderr


def test_not_a_git_repo(tmp_path: Path) -> None:
    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr


def test_not_a_git_repo_with_non_caller_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("list", "/etc/hosts"),
        ("stage", "/etc/hosts"),
        ("unstage", "../escape.txt"),
        ("discard", ""),
        ("commit", "-m", "x", "/etc/hosts"),
    ],
)
def test_not_a_git_repo_outranks_a_bad_repository_path(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    # A Repository path only has meaning inside a worktree, so the missing
    # repository is the error to report, not the shape of the operand.
    repo = GitRepo(str(tmp_path))
    cli = GitHunkCLI(repo)
    r = cli.run(*args)
    assert r.returncode != 0
    assert "not a git repository" in r.stderr
    assert "repository path" not in r.stderr


def test_bare_repo(tmp_path: Path) -> None:
    repo = GitRepo(str(tmp_path))
    repo.run("git", "init", "--bare")
    cli = GitHunkCLI(repo)
    r = cli.run("list")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr
    # git's own message says which of the several causes this was, so it is
    # passed through as the tip rather than classified and discarded.
    assert "work tree" in r.stderr


def test_version(cli: GitHunkCLI) -> None:
    r = cli.run("--version")
    assert r.returncode == 0
    assert "git-hunk" in r.stderr


def test_help(cli: GitHunkCLI) -> None:
    r = cli.run("--help")
    assert r.returncode == 0
    assert "Examples:" in r.stderr
    assert "git-hunk stage d161935" in r.stderr


def test_version_short_circuits_subcommand(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "one\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "CHANGED\n")

    r = cli.run("-V", "list")
    assert r.returncode == 0
    assert "git-hunk" in r.stderr
    assert "f.py" not in r.stdout


def test_help_short_circuits_subcommand(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "one\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "CHANGED\n")

    r = cli.run("-h", "stage", "f.py")
    assert r.returncode == 0
    assert "Examples:" in r.stderr
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_help_omits_unsupported_matching_options(cli: GitHunkCLI) -> None:
    r = cli.run("commit", "--help")
    assert r.returncode == 0
    assert "-m" in r.stderr
    assert "-l" in r.stderr
    assert "--include-matching" not in r.stderr
    assert "--exclude-matching" not in r.stderr
    assert "--regex" not in r.stderr


def test_commit_rejects_matching_options(cli: GitHunkCLI) -> None:
    r = cli.run("commit", "d161935", "--include-matching", "x", "-m", "msg")
    assert r.returncode != 0


def test_stage_help_advertises_matching_options(cli: GitHunkCLI) -> None:
    r = cli.run("stage", "--help")
    assert r.returncode == 0
    assert "-l" in r.stderr
    assert "--include-matching" in r.stderr
    assert "--exclude-matching" in r.stderr
    assert "--regex" in r.stderr


def test_unknown_command(cli: GitHunkCLI) -> None:
    r = cli.run("bogus")
    assert r.returncode != 0


def test_stage_missing_id(cli: GitHunkCLI) -> None:
    r = cli.run("stage")
    assert r.returncode != 0


def test_stage_nonexistent_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("stage", "deadbee")
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_empty_operand_rejected(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("discard", "")
    assert r.returncode != 0
    assert "repository path must not be empty" in r.stderr
    # The empty operand must never match a hunk: the change is untouched.
    assert cli.repo.git("diff").strip() != ""


@pytest.fixture
def unstaged_change(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    return cli


# `stage`, `unstage`, `discard` and `commit` route an operand through
# _make_repository_path, so each must refuse to touch its own state.
# `show` is ID-only and keeps the separate hunk-id guard below.
def test_empty_operand_rejected_on_stage(unstaged_change: GitHunkCLI) -> None:
    r = unstaged_change.run("stage", "")
    assert r.returncode != 0
    assert "repository path must not be empty" in r.stderr
    assert unstaged_change.repo.git("diff", "--cached").strip() == ""


def test_empty_operand_rejected_on_unstage(unstaged_change: GitHunkCLI) -> None:
    unstaged_change.repo.git("add", ".")
    r = unstaged_change.run("unstage", "")
    assert r.returncode != 0
    assert "repository path must not be empty" in r.stderr
    assert unstaged_change.repo.git("diff", "--cached").strip() != ""


def test_empty_operand_rejected_on_commit(unstaged_change: GitHunkCLI) -> None:
    head = unstaged_change.repo.git("rev-parse", "HEAD")
    r = unstaged_change.run("commit", "-m", "msg", "")
    assert r.returncode != 0
    assert "repository path must not be empty" in r.stderr
    assert unstaged_change.repo.git("rev-parse", "HEAD") == head


def test_empty_hunk_id_rejected_on_show(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("show", "")
    assert r.returncode != 0
    assert "hunk id must not be empty" in r.stderr


def test_ambiguous_hunk_id_rejected(cli: GitHunkCLI) -> None:
    # IDs are 7-char hex prefixes; with more than 16 hunks two must share a
    # leading hex char (pigeonhole), so a single-char prefix is ambiguous.
    for i in range(20):
        cli.repo.write_file(f"f{i:02d}.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    for i in range(20):
        cli.repo.write_file(f"f{i:02d}.py", "new\n")

    ids = [h["id"] for h in cli.run_list_json("list", "--unstaged", "--json")]
    first_char_counts = Counter(hunk_id[0] for hunk_id in ids)
    prefix = next(
        (char for char, count in first_char_counts.items() if count > 1), None
    )
    assert prefix is not None  # pigeonhole guarantees a collision for >16 hunks

    r = cli.run("stage", prefix)
    assert r.returncode != 0
    assert "ambiguous" in r.stderr
    # An ambiguous id must stage nothing.
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_malformed_line_spec_rejected(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "A\nb\nC\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    r = cli.run("stage", hunk_id, "-l", "1-2-3")
    assert r.returncode != 0
    assert "1-2-3" in r.stderr
    assert "expected start-end" in r.stderr  # readable message, not raw int() error


def test_empty_line_spec_rejected(cli: GitHunkCLI) -> None:
    # An empty -l must error, not silently fall through and stage the whole hunk.
    cli.repo.write_file("f.py", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "A\nb\nC\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    r = cli.run("stage", hunk_id, "-l", "")
    assert r.returncode != 0
    assert "empty line specification" in r.stderr
    assert cli.repo.git("show", ":f.py") == "a\nb\nc\n"  # nothing staged


def test_git_apply_failure_becomes_clean_error(
    cli: GitHunkCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A low-level git failure during apply must surface as a clean CLI error,
    # not a raw traceback. _apply_selection rebuilds the patch fresh from the
    # working tree each run, so a genuine `git apply` failure is not practically
    # reproducible here; inject one at the apply boundary instead.
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunk_id = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]

    def _fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("git apply refused the patch")

    monkeypatch.setattr("git_hunk._cli.apply_patch", _fail)

    r = cli.run("stage", hunk_id)
    assert r.returncode == 1
    assert "git apply refused the patch" in r.stderr


def test_line_spec_with_multiple_hunks_fails(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2

    r = cli.run("stage", hunks[0]["id"], hunks[1]["id"], "-l", "1")
    assert r.returncode != 0
    assert "exactly one hunk" in r.stderr


def test_pathspec_magic_is_not_expanded(cli: GitHunkCLI) -> None:
    r = cli.run("list", ":(bogus)x")
    assert r.returncode == 0
    assert r.stderr == "No hunks.\n"
