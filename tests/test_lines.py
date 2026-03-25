"""Tests for line-level filtering."""

import os
import subprocess
import tempfile

import pytest

from git_hunk.hunk import Hunk, parse_diff
from git_hunk.lines import filter_hunk_lines, parse_line_spec


# ---------------------------------------------------------------------------
# parse_line_spec
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# filter_hunk_lines
# ---------------------------------------------------------------------------


def _make_hunk(diff: str, **kwargs) -> Hunk:
    defaults = dict(
        id="abc1234",
        file="test.py",
        index=0,
        header=diff.split("\n")[0],
        additions=0,
        deletions=0,
        context_before="",
    )
    defaults.update(kwargs)
    body = diff.split("\n")[1:]
    defaults["additions"] = sum(1 for l in body if l.startswith("+"))
    defaults["deletions"] = sum(1 for l in body if l.startswith("-"))
    return Hunk(diff=diff, **defaults)


class TestFilterHunkLines:
    def test_include_additions(self):
        diff = (
            "@@ -1,3 +1,5 @@ def foo():\n"
            " ctx1\n"
            "+add1\n"
            "+add2\n"
            " ctx2\n"
            "+add3"
        )
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {2}, exclude=False)
        # Line 2 is +add1 (selected), lines 3,5 are +add2,+add3 (dropped)
        assert result.additions == 1
        assert result.deletions == 0
        assert "+add1" in result.diff
        assert "add2" not in result.diff  # dropped
        assert "add3" not in result.diff  # dropped

    def test_include_deletions(self):
        diff = (
            "@@ -1,4 +1,2 @@ def foo():\n"
            " ctx1\n"
            "-del1\n"
            "-del2\n"
            " ctx2"
        )
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {2}, exclude=False)
        # Line 2 is -del1 (selected), line 3 is -del2 (becomes context)
        assert result.deletions == 1
        assert "-del1" in result.diff
        assert " del2" in result.diff  # unselected deletion → context

    def test_exclude_mode(self):
        diff = (
            "@@ -1,3 +1,5 @@ def foo():\n"
            " ctx1\n"
            "+add1\n"
            "+add2\n"
            " ctx2\n"
            "+add3"
        )
        hunk = _make_hunk(diff)
        result = filter_hunk_lines(hunk, {3}, exclude=True)
        # Exclude line 3 (+add2), keep lines 2,5 (+add1, +add3)
        assert result.additions == 2
        assert "+add1" in result.diff
        assert "add2" not in result.diff  # excluded addition → dropped
        assert "+add3" in result.diff

    def test_no_changes_remain_errors(self):
        diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
        hunk = _make_hunk(diff)
        with pytest.raises(ValueError, match="no changes remain"):
            filter_hunk_lines(hunk, {2}, exclude=True)  # exclude the only change

    def test_out_of_range_errors(self):
        diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
        hunk = _make_hunk(diff)
        with pytest.raises(ValueError, match="out of range"):
            filter_hunk_lines(hunk, {99}, exclude=False)

    def test_header_recalculated(self):
        diff = (
            "@@ -1,4 +1,5 @@ def foo():\n"
            " ctx1\n"
            "-del1\n"
            "+add1\n"
            "+add2\n"
            " ctx2"
        )
        hunk = _make_hunk(diff)
        # Include only line 3 (+add1); -del1 (line 2) → context, +add2 (line 4) → dropped
        result = filter_hunk_lines(hunk, {3}, exclude=False)
        assert result.additions == 1
        assert result.deletions == 0
        # old side: ctx1 + del1(→ctx) + ctx2 = 3; new side: ctx1 + del1(→ctx) + add1 + ctx2 = 4
        assert "-1,3" in result.header
        assert "+1,4" in result.header

    def test_mixed_changes(self):
        diff = (
            "@@ -1,3 +1,4 @@ def foo():\n"
            " ctx\n"
            "-old\n"
            "+new1\n"
            "+new2"
        )
        hunk = _make_hunk(diff)
        # Include line 3 (+new1) only; -old (line 2) → context, +new2 (line 4) → dropped
        result = filter_hunk_lines(hunk, {3}, exclude=False)
        assert result.additions == 1
        assert result.deletions == 0
        assert "+new1" in result.diff
        assert " old" in result.diff  # -old → context (unselected deletion)
        assert "new2" not in result.diff  # +new2 → dropped


# ---------------------------------------------------------------------------
# Integration: stage with line filtering in a real git repo
# ---------------------------------------------------------------------------


class TestIntegration:
    def _run(self, *args, cwd, input=None):
        result = subprocess.run(
            list(args), capture_output=True, text=True, cwd=cwd, input=input
        )
        return result

    def _git(self, *args, cwd):
        r = self._run("git", *args, cwd=cwd)
        assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
        return r.stdout

    def test_stage_partial_lines(self):
        with tempfile.TemporaryDirectory() as repo:
            # Init repo with a file
            self._git("init", cwd=repo)
            self._git("config", "user.email", "test@test.com", cwd=repo)
            self._git("config", "user.name", "Test", cwd=repo)

            filepath = os.path.join(repo, "test.py")
            with open(filepath, "w") as f:
                f.write("line1\nline2\nline3\n")
            self._git("add", ".", cwd=repo)
            self._git("commit", "-m", "init", cwd=repo)

            # Make changes: modify multiple lines in one hunk
            with open(filepath, "w") as f:
                f.write("LINE1\nline2\nLINE3\n")

            # Parse the diff
            diff = self._git("diff", cwd=repo)
            hunks = parse_diff(diff)
            assert len(hunks) == 1

            # Filter to include only the first change (-line1/+LINE1 = lines 1,2)
            from git_hunk.lines import filter_hunk_lines
            from git_hunk.patch import build_patch

            filtered = filter_hunk_lines(hunks[0], {1, 2}, exclude=False)
            patch = build_patch([filtered], diff)

            # Apply
            r = self._run(
                "git", "apply", "--cached", "--whitespace=nowarn",
                cwd=repo, input=patch,
            )
            assert r.returncode == 0, f"git apply failed: {r.stderr}"

            # Verify: staged diff should only have line1->LINE1
            staged = self._git("diff", "--cached", cwd=repo)
            assert "LINE1" in staged
            assert "LINE3" not in staged

            # Unstaged diff should still have line3->LINE3
            unstaged = self._git("diff", cwd=repo)
            assert "LINE3" in unstaged
