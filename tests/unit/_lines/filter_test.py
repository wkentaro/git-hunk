import pytest

from git_hunk._hunk import Hunk
from git_hunk._lines import filter_hunk_lines


def _make_hunk(diff: str) -> Hunk:
    lines = diff.split("\n")
    header = lines[0]
    body = lines[1:]
    additions = sum(1 for line in body if line.startswith("+"))
    deletions = sum(1 for line in body if line.startswith("-"))
    return Hunk(
        id="abc1234",
        file="test.py",
        header=header,
        additions=additions,
        deletions=deletions,
        context_before="",
        diff=diff,
    )


def test_include_additions() -> None:
    diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
    hunk = _make_hunk(diff)
    result = filter_hunk_lines(hunk, {2}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "+add1" in result.diff
    assert "add2" not in result.diff
    assert "add3" not in result.diff


def test_include_deletions() -> None:
    diff = "@@ -1,4 +1,2 @@ def foo():\n ctx1\n-del1\n-del2\n ctx2"
    hunk = _make_hunk(diff)
    result = filter_hunk_lines(hunk, {2}, exclude=False)
    assert result.deletions == 1
    assert "-del1" in result.diff
    assert " del2" in result.diff


def test_exclude_mode() -> None:
    diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
    hunk = _make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=True)
    assert result.additions == 2
    assert "+add1" in result.diff
    assert "add2" not in result.diff
    assert "+add3" in result.diff


def test_no_changes_remain_errors() -> None:
    diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
    hunk = _make_hunk(diff)
    with pytest.raises(ValueError, match="no changes remain"):
        filter_hunk_lines(hunk, {2}, exclude=True)


def test_out_of_range_errors() -> None:
    diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
    hunk = _make_hunk(diff)
    with pytest.raises(ValueError, match="out of range"):
        filter_hunk_lines(hunk, {99}, exclude=False)


def test_header_recalculated() -> None:
    diff = "@@ -1,4 +1,5 @@ def foo():\n ctx1\n-del1\n+add1\n+add2\n ctx2"
    hunk = _make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "-1,3" in result.header
    assert "+1,4" in result.header


def test_mixed_changes() -> None:
    diff = "@@ -1,3 +1,4 @@ def foo():\n ctx\n-old\n+new1\n+new2"
    hunk = _make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "+new1" in result.diff
    assert " old" in result.diff
    assert "new2" not in result.diff
