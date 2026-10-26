import subprocess
from pathlib import Path

import pytest

from .conftest import GitHunkCLI


def _init(*, cli: GitHunkCLI, files: dict[str, str]) -> None:
    for name, content in files.items():
        cli.repo.write_file(name, content)
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")


def _commit_count(*, cli: GitHunkCLI) -> int:
    return int(cli.repo.git("rev-list", "--count", "HEAD").strip())


def _unstaged_ids(*, cli: GitHunkCLI) -> list[str]:
    return [h["id"] for h in cli.run_list_json("list", "--unstaged", "--json")]


def test_commit_single_hunk(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\nb\nc\n"})
    cli.repo.write_file("f.txt", "aX\nb\nc\n")

    before = _commit_count(cli=cli)
    cli.run_ok("commit", _unstaged_ids(cli=cli)[0], "-m", "fix: change a")

    assert _commit_count(cli=cli) == before + 1
    assert cli.repo.git("log", "-1", "--format=%s").strip() == "fix: change a"
    assert "aX" in cli.repo.git("show", "HEAD:f.txt")
    assert cli.repo.git("status", "--porcelain").strip() == ""


def test_commit_multiple_hunks(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.write_file("b.txt", "BBB\n")

    ids = _unstaged_ids(cli=cli)
    assert len(ids) == 2
    cli.run_ok("commit", ids[0], ids[1], "-m", "chore: update both")

    head = cli.repo.git("show", "HEAD")
    assert "AAA" in head
    assert "BBB" in head
    assert cli.repo.git("status", "--porcelain").strip() == ""


def test_commit_partial_lines_leaves_remainder_unstaged(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\nb\nc\n"})
    cli.repo.write_file("f.txt", "aX\nb\ncX\n")

    # Body: 1=-a 2=+aX 3= b 4=-c 5=+cX. Commit only the a->aX change.
    cli.run_ok("commit", _unstaged_ids(cli=cli)[0], "-l", "1,2", "-m", "fix: only a")

    assert "aX" in cli.repo.git("show", "HEAD:f.txt")
    assert "cX" not in cli.repo.git("show", "HEAD:f.txt")
    # The c->cX change is still in the working tree, unstaged.
    assert "cX" in cli.repo.git("diff")


def test_commit_exclude_matching_leaves_remainder_unstaged(*, cli: GitHunkCLI) -> None:
    _init(
        cli=cli,
        files={
            "f.py": (
                "def process(items):\n"
                "    total = 0\n"
                "    for item in items:\n"
                "        total += item\n"
                "    return total\n"
            )
        },
    )
    cli.repo.write_file(
        "f.py",
        (
            "def process(items):\n"
            "    total = 0\n"
            "    for item in items:\n"
            '        print("DEBUG", item)\n'
            "        total += item\n"
            "    return total * 2\n"
        ),
    )

    cli.run_ok(
        "commit",
        _unstaged_ids(cli=cli)[0],
        "--exclude-matching",
        'print("DEBUG"',
        "-m",
        "Double item totals",
    )

    assert cli.repo.git("show", "HEAD:f.py") == (
        "def process(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item\n"
        "    return total * 2\n"
    )
    assert cli.repo.git("diff", "--cached") == ""
    assert 'print("DEBUG", item)' in cli.repo.git("diff")


def test_commit_by_file_path(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "A1\nA2\nA3\n")
    cli.repo.write_file("b.txt", "BBB\n")

    cli.run_ok("commit", "a.txt", "-m", "feat: rewrite a")

    assert "A1" in cli.repo.git("show", "HEAD:a.txt")
    # b.txt was not named, so it stays out of the commit and in the working tree.
    assert cli.repo.git("show", "HEAD:b.txt").strip() == "b"
    assert "BBB" in cli.repo.git("diff")


def test_commit_joins_repeated_messages_as_paragraphs(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    cli.run_ok(
        "commit",
        _unstaged_ids(cli=cli)[0],
        "-m",
        "feat: subject",
        "-m",
        "",
        "-m",
        "Body paragraph.",
    )

    body = cli.repo.git("log", "-1", "--format=%B").strip()
    assert body == "feat: subject\n\nBody paragraph."


@pytest.mark.parametrize("amend", [False, True])
def test_commit_reads_message_file_from_invocation_directory(
    *, cli: GitHunkCLI, amend: bool
) -> None:
    _init(cli=cli, files={"f.txt": "before\n"})
    cli.repo.write_file("f.txt", "after\n")
    message = 'feat: 日本語 and "quotes"\n\nKeep $variables and `commands` literal.\n'
    Path(cli.repo.write_file("sub/message.txt", "")).write_text(
        message, encoding="utf-8"
    )
    extra = ["--amend"] if amend else []

    cli.run_ok("commit", "f.txt", "-F", "message.txt", *extra, subdir="sub")

    body = subprocess.check_output(
        ["git", "log", "-1", "--format=%B"], cwd=cli.repo.path
    ).decode("utf-8")
    assert body.strip() == message.strip()
    assert cli.repo.git("show", "HEAD:f.txt") == "after\n"
    assert cli.repo.git("diff", "--cached") == ""
    assert cli.repo.git("ls-tree", "--name-only", "HEAD").splitlines() == ["f.txt"]


@pytest.mark.parametrize(
    ("content", "extra"),
    [
        ("", []),
        (" \n\t", ["--amend"]),
        ("feat: message\n", ["-m", "other"]),
        ("feat: message\n", ["--fixup", "HEAD"]),
    ],
    ids=["empty", "blank-amend", "with-m", "with-fixup"],
)
def test_commit_rejects_invalid_message_file_options_before_staging(
    *, cli: GitHunkCLI, content: str, extra: list[str], tmp_path: Path
) -> None:
    _init(cli=cli, files={"f.txt": "before\n"})
    cli.repo.write_file("f.txt", "after\n")
    message_file = tmp_path / "message.txt"
    message_file.write_text(content, encoding="utf-8")
    head = cli.repo.git("rev-parse", "HEAD")

    result = cli.run("commit", "f.txt", "-F", str(message_file), *extra)

    assert result.returncode == 2
    assert cli.repo.git("rev-parse", "HEAD") == head
    assert cli.repo.git("diff", "--cached") == ""


def test_commit_missing_message_file_leaves_index_unchanged(
    *, cli: GitHunkCLI, tmp_path: Path
) -> None:
    _init(cli=cli, files={"f.txt": "before\n"})
    cli.repo.write_file("f.txt", "after\n")

    result = cli.run("commit", "f.txt", "-F", str(tmp_path / "missing.txt"))

    assert result.returncode == 2
    assert "does not exist" in result.stderr
    assert _commit_count(cli=cli) == 1
    assert cli.repo.git("diff", "--cached") == ""


def test_commit_requires_message(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    before = _commit_count(cli=cli)
    r = cli.run("commit", _unstaged_ids(cli=cli)[0])
    assert r.returncode != 0
    assert "message" in r.stderr
    assert _commit_count(cli=cli) == before
    assert cli.repo.git("diff", "--cached").strip() == ""


@pytest.mark.parametrize(
    "m_args",
    [["-m", ""], ["-m", "   "], ["-m", "", "-m", "   "]],
    ids=["empty", "whitespace", "all-repeated-blank"],
)
def test_commit_rejects_blank_message(*, cli: GitHunkCLI, m_args: list[str]) -> None:
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    before = _commit_count(cli=cli)
    r = cli.run("commit", _unstaged_ids(cli=cli)[0], *m_args)
    assert r.returncode != 0
    assert "message" in r.stderr
    assert _commit_count(cli=cli) == before
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_unknown_id_makes_no_commit(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    before = _commit_count(cli=cli)
    r = cli.run("commit", "deadbee", "-m", "nope")
    assert r.returncode != 0
    assert _commit_count(cli=cli) == before
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_failure_leaves_hunk_staged(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")

    hook = Path(cli.repo.path) / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho lint failed >&2\nexit 1\n")
    hook.chmod(0o755)

    before = _commit_count(cli=cli)
    r = cli.run(
        "commit",
        _unstaged_ids(cli=cli)[0],
        "-m",
        "fix: blocked by hook",
        "-m",
        "Body paragraph.",
    )
    assert r.returncode != 0
    assert "lint failed" in r.stderr
    assert "still staged" in r.stderr
    # The error names the command, not the message it was given.
    assert "blocked by hook" not in r.stderr
    assert "Body paragraph." not in r.stderr
    assert _commit_count(cli=cli) == before
    # The hunk is left staged so the user can retry, not silently lost.
    assert "AAA" in cli.repo.git("diff", "--cached")


def test_commit_aborts_when_index_already_has_staged_changes(
    *, cli: GitHunkCLI
) -> None:
    _init(cli=cli, files={"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.write_file("b.txt", "BBB\n")
    cli.repo.git("add", "a.txt")  # pre-stage an unrelated change

    before = _commit_count(cli=cli)
    b_id = next(h["id"] for h in cli.run_list_json("list", "--unstaged", "--json"))
    r = cli.run("commit", b_id, "-m", "feat: only b")
    assert r.returncode != 0
    assert "already staged" in r.stderr
    assert _commit_count(cli=cli) == before
    # The pre-staged change is untouched; nothing new was committed or staged.
    assert cli.repo.git("diff", "--cached", "--name-only").strip() == "a.txt"


def test_commit_reports_clean_error_when_staged_diff_fails(*, cli: GitHunkCLI) -> None:
    # A git failure while checking for already-staged changes must surface as a
    # clean CLI error, not a raw Python traceback. A corrupt index makes
    # `git diff --cached` fail while the repo still looks like a work tree.
    _init(cli=cli, files={"f.txt": "a\n"})
    cli.repo.write_file("f.txt", "AAA\n")
    (Path(cli.repo.path) / ".git" / "index").write_bytes(b"garbage")

    r = cli.run("commit", "deadbeef", "-m", "fix: x")
    assert r.returncode != 0
    assert r.stderr.startswith("error:")


def test_commit_amend_keeps_head_message(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.git("commit", "-qam", "feat: a")
    cli.repo.write_file("b.txt", "BBB\n")

    before = _commit_count(cli=cli)
    r = cli.run("commit", "b.txt", "--amend")
    assert r.returncode == 0, r.stderr
    assert "feat: a" in r.stderr

    assert _commit_count(cli=cli) == before
    assert cli.repo.git("log", "-1", "--format=%B").strip() == "feat: a"
    assert "BBB" in cli.repo.git("show", "HEAD:b.txt")
    assert cli.repo.git("status", "--porcelain").strip() == ""


def test_commit_amend_with_message_rewords_head(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.git("commit", "-qam", "feat: a")
    cli.repo.write_file("a.txt", "AAAA\n")

    cli.run_ok("commit", "a.txt", "--amend", "-m", "feat: more a", "-m", "Body.")

    assert cli.repo.git("log", "-1", "--format=%B").strip() == "feat: more a\n\nBody."


def test_commit_fixup_targets_earlier_commit(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n", "b.txt": "b\n"})
    cli.repo.write_file("a.txt", "AAA\n")
    cli.repo.git("commit", "-qam", "feat: a")
    cli.repo.write_file("b.txt", "BBB\n")
    cli.repo.git("commit", "-qam", "feat: b")
    cli.repo.write_file("a.txt", "AAAA\n")

    before = _commit_count(cli=cli)
    r = cli.run("commit", "a.txt", "--fixup", "HEAD~1")
    assert r.returncode == 0, r.stderr
    assert "fixup! feat: a" in r.stderr

    assert _commit_count(cli=cli) == before + 1
    assert cli.repo.git("log", "-1", "--format=%s").strip() == "fixup! feat: a"
    assert cli.repo.git("status", "--porcelain").strip() == ""


@pytest.mark.parametrize(
    "extra",
    [
        ["--amend", "--fixup", "HEAD"],
        ["--fixup", "HEAD", "-m", "x"],
        ["--amend", "-m", " "],
        ["--fixup", "reword:HEAD"],
    ],
    ids=[
        "amend-and-fixup",
        "fixup-with-message",
        "amend-blank-message",
        "fixup-reword",
    ],
)
def test_commit_rejects_invalid_amend_fixup_options(
    *, cli: GitHunkCLI, extra: list[str]
) -> None:
    _init(cli=cli, files={"a.txt": "a\n"})
    cli.repo.write_file("a.txt", "AAA\n")

    head = cli.repo.git("rev-parse", "HEAD")
    r = cli.run("commit", "a.txt", *extra)
    assert r.returncode != 0
    assert cli.repo.git("rev-parse", "HEAD") == head
    assert cli.repo.git("diff", "--cached").strip() == ""


def test_commit_fixup_failure_tip_keeps_fixup(*, cli: GitHunkCLI) -> None:
    _init(cli=cli, files={"a.txt": "a\n"})
    cli.repo.write_file("a.txt", "AAA\n")

    hook = Path(cli.repo.path) / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    r = cli.run("commit", "a.txt", "--fixup", "HEAD^{/init}")
    assert r.returncode == 1
    # Quoted, so the tip can be pasted into a shell as is.
    assert "retry with: git commit --fixup='HEAD^{/init}'" in r.stderr
