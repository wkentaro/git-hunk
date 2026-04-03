"""Tests for line-level filtering."""

import pytest

from git_hunk.hunk import Hunk, parse_diff
from git_hunk.lines import filter_hunk_lines, parse_line_spec
from git_hunk.patch import build_patch


class TestParseLineSpec:
    def test_single_line(self):
        lines, exclude = parse_line_spec("3")
        assert lines == {3}
        assert exclude is False

    def test_multiple_lines(self):
        lines, exclude = parse_line_spec("1,3,5")
        assert lines == {1, 3, 5}
        assert exclude is False

    def test_range(self):
        lines, exclude = parse_line_spec("2-5")
        assert lines == {2, 3, 4, 5}
        assert exclude is False

    def test_mixed_range_and_single(self):
        lines, exclude = parse_line_spec("1,3-5,8")
        assert lines == {1, 3, 4, 5, 8}
        assert exclude is False

    def test_exclude_single(self):
        lines, exclude = parse_line_spec("^3")
        assert lines == {3}
        assert exclude is True

    def test_exclude_range(self):
        lines, exclude = parse_line_spec("^2-4,^7")
        assert lines == {2, 3, 4, 7}
        assert exclude is True

    def test_mixed_include_exclude_errors(self):
        with pytest.raises(ValueError, match="cannot mix"):
            parse_line_spec("3,^5")

    def test_empty_errors(self):
        with pytest.raises(ValueError, match="empty"):
            parse_line_spec("")

    def test_non_positive_errors(self):
        with pytest.raises(ValueError, match="positive"):
            parse_line_spec("0")

    def test_reversed_range_errors(self):
        with pytest.raises(ValueError, match="start > end"):
            parse_line_spec("5-3")


def _make_hunk(diff: str) -> Hunk:
    lines = diff.split("\n")
    header = lines[0]
    body = lines[1:]
    additions = sum(1 for line in body if line.startswith("+"))
    deletions = sum(1 for line in body if line.startswith("-"))
    return Hunk(
        id="abc1234",
        file="test.py",
        index=0,
        header=header,
        additions=additions,
        deletions=deletions,
        context_before="",
        diff=diff,
    )


class TestFilterHunkLines:
    def test_include_additions(self):
        diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {2}, exclude=False)
        assert result.additions == 1
        assert result.deletions == 0
        assert "+add1" in result.diff
        assert "add2" not in result.diff
        assert "add3" not in result.diff

    def test_include_deletions(self):
        diff = "@@ -1,4 +1,2 @@ def foo():\n ctx1\n-del1\n-del2\n ctx2"
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {2}, exclude=False)
        assert result.deletions == 1
        assert "-del1" in result.diff
        assert " del2" in result.diff

    def test_exclude_mode(self):
        diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {3}, exclude=True)
        assert result.additions == 2
        assert "+add1" in result.diff
        assert "add2" not in result.diff
        assert "+add3" in result.diff

    def test_no_changes_remain_errors(self):
        diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
        hunk = _make_hunk(diff)
        with pytest.raises(ValueError, match="no changes remain"):
            filter_hunk_lines(hunk, {2}, exclude=True)

    def test_out_of_range_errors(self):
        diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
        hunk = _make_hunk(diff)
        with pytest.raises(ValueError, match="out of range"):
            filter_hunk_lines(hunk, {99}, exclude=False)

    def test_header_recalculated(self):
        diff = "@@ -1,4 +1,5 @@ def foo():\n ctx1\n-del1\n+add1\n+add2\n ctx2"
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {3}, exclude=False)
        assert result.additions == 1
        assert result.deletions == 0
        assert "-1,3" in result.header
        assert "+1,4" in result.header

    def test_mixed_changes(self):
        diff = "@@ -1,3 +1,4 @@ def foo():\n ctx\n-old\n+new1\n+new2"
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {3}, exclude=False)
        assert result.additions == 1
        assert result.deletions == 0
        assert "+new1" in result.diff
        assert " old" in result.diff
        assert "new2" not in result.diff


class TestIntegration:
    def test_stage_partial_lines(self, git_repo):
        git_repo.write_file("test.py", "line1\nline2\nline3\n")
        git_repo.git("add", ".")
        git_repo.git("commit", "-m", "init")

        git_repo.write_file("test.py", "LINE1\nline2\nLINE3\n")

        diff = git_repo.git("diff")
        hunks = parse_diff(diff)
        assert len(hunks) == 1

        filtered = filter_hunk_lines(hunks[0], {1, 2}, exclude=False)
        patch = build_patch([filtered], diff)

        r = git_repo.run(
            "git",
            "apply",
            "--cached",
            "--whitespace=nowarn",
            input=patch,
        )
        assert r.returncode == 0, f"git apply failed: {r.stderr}"

        staged = git_repo.git("diff", "--cached")
        assert "LINE1" in staged
        assert "LINE3" not in staged

        unstaged = git_repo.git("diff")
        assert "LINE3" in unstaged
