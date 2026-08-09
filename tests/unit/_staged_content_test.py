"""`materialize_staged_content` produces staged bytes without staging them."""

import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

from git_hunk._git import apply_patch
from git_hunk._git import get_diff
from git_hunk._hunk import Hunk
from git_hunk._hunk import parse_diff
from git_hunk._lines import count_hunk_body_lines
from git_hunk._lines import filter_hunk_lines
from git_hunk._lines import parse_line_spec
from git_hunk._patch import build_patch
from git_hunk._staged_content import StagedContentError
from git_hunk._staged_content import materialize_staged_content
from tests.conftest import GitRepo


@pytest.fixture
def repo(git_repo: GitRepo) -> Generator[GitRepo]:
    # Exact bytes are compared, so keep git from rewriting line endings on
    # Windows.
    git_repo.git("config", "core.autocrlf", "false")
    yield git_repo


def _write(repo: GitRepo, name: str, content: bytes) -> None:
    # Byte-for-byte writes: GitRepo.write_file opens in text mode, which turns
    # every LF into CRLF on Windows and would make these expectations
    # platform-dependent.
    path = Path(repo.path) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _commit(repo: GitRepo, message: str = "init") -> None:
    repo.git("add", "-A")
    repo.git("commit", "-m", message)


def _index_bytes(repo: GitRepo, path: str) -> bytes:
    # GitRepo.git decodes with universal newlines, so it cannot say what bytes
    # the index actually holds; read them as bytes instead.
    result = subprocess.run(
        ["git", "--literal-pathspecs", "show", f":{path}"],
        capture_output=True,
        cwd=repo.path,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _unstaged(repo: GitRepo) -> tuple[list[Hunk], str]:
    diff_output = get_diff(worktree_root=repo.path, staged=False)
    return parse_diff(diff_output), diff_output


def _select(hunks: list[Hunk], line_spec: str | None) -> list[Hunk]:
    if line_spec is None:
        return hunks
    assert len(hunks) == 1
    lines, exclude = parse_line_spec(line_spec, total=count_hunk_body_lines(hunks[0]))
    return [filter_hunk_lines(hunks[0], lines, exclude=exclude, reverse=False)]


def _materialize(repo: GitRepo, line_spec: str | None = None) -> bytes:
    hunks, diff_output = _unstaged(repo)
    return materialize_staged_content(
        _select(hunks, line_spec), diff_output, worktree_root=repo.path
    )


def _stage(repo: GitRepo, line_spec: str | None = None) -> None:
    hunks, diff_output = _unstaged(repo)
    apply_patch(
        build_patch(_select(hunks, line_spec), diff_output, reverse=False),
        worktree_root=repo.path,
        cached=True,
        reverse=False,
        dry_run=False,
    )


@pytest.fixture
def modified(repo: GitRepo) -> GitRepo:
    _write(repo, "f.py", b"a = 1\nb = 2\nc = 3\n")
    _commit(repo)
    _write(repo, "f.py", b"a = 10\nb = 2\nc = 30\n")
    return repo


def _state(repo: GitRepo) -> tuple[str, str, bytes]:
    return (
        repo.git("diff", "--cached"),
        repo.git("diff"),
        (Path(repo.path) / "f.py").read_bytes(),
    )


def test_whole_hunk_materializes_the_worktree_content(modified: GitRepo) -> None:
    assert _materialize(modified) == b"a = 10\nb = 2\nc = 30\n"


def test_line_selection_materializes_the_partial_result(modified: GitRepo) -> None:
    # Body: 1=-a 2=+a10 3= b 4=-c 5=+c30. Take only the first change.
    assert _materialize(modified, "1,2") == b"a = 10\nb = 2\nc = 3\n"


def test_exclude_line_selection_materializes_the_partial_result(
    modified: GitRepo,
) -> None:
    assert _materialize(modified, "^4,^5") == b"a = 10\nb = 2\nc = 3\n"


def test_the_real_index_and_worktree_stay_untouched(modified: GitRepo) -> None:
    before = _state(modified)

    _materialize(modified, "1,2")

    assert _state(modified) == before


@pytest.mark.parametrize(
    "line_spec", [None, "1,2", "^4,^5"], ids=["whole-hunk", "include", "exclude"]
)
def test_result_matches_the_content_a_real_stage_produces(
    modified: GitRepo, line_spec: str | None
) -> None:
    materialized = _materialize(modified, line_spec)

    _stage(modified, line_spec)

    assert _index_bytes(modified, "f.py") == materialized


def test_result_builds_on_what_is_already_staged(repo: GitRepo) -> None:
    # The scratch index is a copy of the current index, not of HEAD, so an
    # earlier partial stage of the same file must show through in the result.
    body = [f"line {number}" for number in range(1, 31)]
    _write(repo, "f.txt", ("\n".join(body) + "\n").encode())
    _commit(repo)
    changed = body[:]
    changed[1] = "changed 2"
    changed[27] = "changed 28"
    _write(repo, "f.txt", ("\n".join(changed) + "\n").encode())

    hunks, diff_output = _unstaged(repo)
    assert len(hunks) == 2
    apply_patch(
        build_patch(hunks[:1], diff_output, reverse=False),
        worktree_root=repo.path,
        cached=True,
        reverse=False,
        dry_run=False,
    )

    materialized = _materialize(repo)

    assert materialized == ("\n".join(changed) + "\n").encode()


def test_works_before_the_first_commit(repo: GitRepo) -> None:
    # An unborn HEAD: every hunk is an addition and the scratch index is copied
    # from an index that holds nothing but the intent-to-add entry.
    _write(repo, "new.txt", b"x\ny\n")
    repo.git("add", "-N", "new.txt")

    assert _materialize(repo, "1") == b"x\n"


def test_is_byte_exact_for_non_utf8_content_without_a_trailing_newline(
    repo: GitRepo,
) -> None:
    # 0xe9 is "e-acute" in Latin-1 and an invalid standalone UTF-8 byte.
    _write(repo, "latin1.txt", b"pass\xe9\ntail")
    _commit(repo)
    _write(repo, "latin1.txt", b"PASS\xe9\ntail")

    assert _materialize(repo) == b"PASS\xe9\ntail"


def test_is_byte_exact_for_crlf_content(repo: GitRepo) -> None:
    _write(repo, "crlf.txt", b"one\r\ntwo\r\nthree\r\n")
    _commit(repo)
    _write(repo, "crlf.txt", b"ONE\r\ntwo\r\nTHREE\r\n")

    assert _materialize(repo, "1,2") == b"ONE\r\ntwo\r\nthree\r\n"


def test_a_binary_change_is_rejected(repo: GitRepo) -> None:
    _write(repo, "a.bin", b"\x00\x01bin\xff")
    _commit(repo)
    _write(repo, "a.bin", b"\x00\x02BIN\xfe")

    with pytest.raises(StagedContentError, match="binary or type changes"):
        _materialize(repo)


@pytest.mark.skipif(
    os.name == "nt", reason="git does not track the executable bit on Windows"
)
def test_a_mode_only_change_is_rejected(repo: GitRepo) -> None:
    _write(repo, "m.sh", b"m\n")
    _commit(repo)
    (Path(repo.path) / "m.sh").chmod(0o755)

    with pytest.raises(StagedContentError, match="empty tracked file additions"):
        _materialize(repo)


def test_an_empty_added_file_is_rejected(repo: GitRepo) -> None:
    _write(repo, "seed.txt", b"seed\n")
    _commit(repo)
    _write(repo, "empty.txt", b"")
    repo.git("add", "-N", "empty.txt")

    with pytest.raises(StagedContentError, match="empty tracked file additions"):
        _materialize(repo)


def test_hunks_from_two_files_are_rejected(repo: GitRepo) -> None:
    _write(repo, "one.txt", b"1\n")
    _write(repo, "two.txt", b"2\n")
    _commit(repo)
    _write(repo, "one.txt", b"1X\n")
    _write(repo, "two.txt", b"2X\n")

    hunks, diff_output = _unstaged(repo)
    assert len(hunks) == 2

    with pytest.raises(StagedContentError, match="exactly one file"):
        materialize_staged_content(hunks, diff_output, worktree_root=repo.path)


def test_a_selection_that_removes_the_file_from_the_index_is_rejected(
    repo: GitRepo,
) -> None:
    _write(repo, "gone.txt", b"p\nq\nr\n")
    _commit(repo)
    (Path(repo.path) / "gone.txt").unlink()

    with pytest.raises(StagedContentError, match="removes 'gone.txt' from the index"):
        _materialize(repo)


@pytest.mark.skipif(
    os.name == "nt", reason="git does not track the executable bit on Windows"
)
def test_a_mode_change_alongside_text_edits_materializes_the_text(
    modified: GitRepo,
) -> None:
    # A mode hunk carries no content, so it must not veto the file's text.
    (Path(modified.path) / "f.py").chmod(0o755)

    hunks, diff_output = _unstaged(modified)
    assert len(hunks) == 2

    assert (
        materialize_staged_content(hunks, diff_output, worktree_root=modified.path)
        == b"a = 10\nb = 2\nc = 30\n"
    )
