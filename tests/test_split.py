"""Tests for automatic hunk splitting."""

import os
import subprocess
import tempfile

from git_hunk.hunk import Hunk, _split_hunk, parse_diff
from git_hunk.patch import build_patch


# ---------------------------------------------------------------------------
# _split_hunk unit tests
# ---------------------------------------------------------------------------


class TestSplitHunk:
    def test_single_region_no_split(self):
        header = "@@ -1,5 +1,6 @@ def foo():"
        body = [" ctx1", " ctx2", "+added", " ctx3", " ctx4"]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 1

    def test_two_regions_small_gap_no_split(self):
        """Gap of 5 context lines (< 2*3+1=7) — should NOT split."""
        header = "@@ -1,12 +1,14 @@ def foo():"
        body = [
            " ctx1",
            "+add1",
            " ctx2",
            " ctx3",
            " ctx4",
            " ctx5",
            " ctx6",
            "+add2",
            " ctx7",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 1

    def test_two_regions_large_gap_splits(self):
        """Gap of 7 context lines (>= 2*3+1=7) — should split into 2."""
        header = "@@ -1,14 +1,16 @@ def foo():"
        body = [
            " ctx1",
            "+add1",
            " g1",
            " g2",
            " g3",
            " g4",
            " g5",
            " g6",
            " g7",
            "+add2",
            " ctx2",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 2
        # First sub-hunk should contain +add1
        assert any(l.startswith("+") for l in result[0]["body_lines"])
        assert "+add1" in result[0]["body_lines"]
        # Second sub-hunk should contain +add2
        assert "+add2" in result[1]["body_lines"]

    def test_three_regions_two_gaps_splits(self):
        """Three change regions with two large gaps — should split into 3."""
        header = "@@ -1,30 +1,33 @@ def foo():"
        body = [
            " ctx",
            "+add1",
            " g1", " g2", " g3", " g4", " g5", " g6", " g7",
            "+add2",
            " g8", " g9", " g10", " g11", " g12", " g13", " g14",
            "+add3",
            " ctx_end",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 3

    def test_split_preserves_context_around_changes(self):
        """Each sub-hunk gets up to 3 lines of context on each side."""
        header = "@@ -1,16 +1,18 @@ def foo():"
        body = [
            " c1",
            " c2",
            "+add1",
            " g1", " g2", " g3", " g4", " g5", " g6", " g7",
            "+add2",
            " c3",
            " c4",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 2
        # First sub-hunk: context before (c1, c2) + add1 + 3 lines after
        first_body = result[0]["body_lines"]
        assert first_body[0] == " c1"
        assert "+add1" in first_body
        # Should have up to 3 context lines after the change
        assert len([l for l in first_body if not l.startswith("+")]) <= 5

    def test_split_header_line_numbers(self):
        """Sub-hunk headers should have correct line numbers."""
        header = "@@ -1,14 +1,16 @@ def foo():"
        body = [
            " ctx1",       # old:1, new:1
            "+add1",       # new:2
            " g1",         # old:2, new:3
            " g2",         # old:3, new:4
            " g3",         # old:4, new:5
            " g4",         # old:5, new:6
            " g5",         # old:6, new:7
            " g6",         # old:7, new:8
            " g7",         # old:8, new:9
            "+add2",       # new:10
            " ctx2",       # old:9, new:11
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 2
        # First sub-hunk starts at old:1, new:1
        assert result[0]["header"].startswith("@@ -1,")
        # Second sub-hunk: old starts at 6 (g5), new starts at 7 (g5 in new)
        assert "-6," in result[1]["header"] or "-5," in result[1]["header"]

    def test_deletions_handled(self):
        """Splitting works with deletion regions too."""
        header = "@@ -1,14 +1,12 @@"
        body = [
            " ctx1",
            "-del1",
            " g1", " g2", " g3", " g4", " g5", " g6", " g7",
            "-del2",
            " ctx2",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 2
        assert "-del1" in result[0]["body_lines"]
        assert "-del2" in result[1]["body_lines"]

    def test_no_body_lines(self):
        header = "@@ -1,0 +1,0 @@"
        result = _split_hunk("f.py", header, [])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# parse_diff integration — splits produce valid hunks
# ---------------------------------------------------------------------------


class TestParseDiffSplit:
    def test_parse_diff_splits_large_hunk(self):
        """A diff with one hunk containing two distant changes gets split."""
        diff = (
            "diff --git a/f.py b/f.py\n"
            "index abc..def 100644\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,14 +1,16 @@ def foo():\n"
            " line1\n"
            "+added_top\n"
            " line2\n"
            " line3\n"
            " line4\n"
            " line5\n"
            " line6\n"
            " line7\n"
            " line8\n"
            "+added_bottom\n"
            " line9\n"
        )
        hunks = parse_diff(diff)
        assert len(hunks) == 2
        assert hunks[0].additions == 1
        assert hunks[1].additions == 1
        assert "+added_top" in hunks[0].diff
        assert "+added_bottom" in hunks[1].diff

    def test_parse_diff_no_split_when_close(self):
        """Changes close together stay as one hunk."""
        diff = (
            "diff --git a/f.py b/f.py\n"
            "index abc..def 100644\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,7 +1,9 @@ def foo():\n"
            " line1\n"
            "+added_top\n"
            " line2\n"
            " line3\n"
            "+added_bottom\n"
            " line4\n"
        )
        hunks = parse_diff(diff)
        assert len(hunks) == 1


# ---------------------------------------------------------------------------
# Integration: split hunks produce valid patches in a real git repo
# ---------------------------------------------------------------------------


class TestSplitIntegration:
    def _run(self, *args, cwd, input=None):
        return subprocess.run(
            list(args), capture_output=True, text=True, cwd=cwd, input=input
        )

    def _git(self, *args, cwd):
        r = self._run("git", *args, cwd=cwd)
        assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
        return r.stdout

    def test_split_hunks_stage_independently(self):
        """Each split sub-hunk can be staged as a valid patch."""
        with tempfile.TemporaryDirectory() as repo:
            self._git("init", cwd=repo)
            self._git("config", "user.email", "test@test.com", cwd=repo)
            self._git("config", "user.name", "Test", cwd=repo)

            # Create a file with enough lines to produce a large gap
            filepath = os.path.join(repo, "f.py")
            lines = [f"line{i}" for i in range(1, 21)]
            with open(filepath, "w") as f:
                f.write("\n".join(lines) + "\n")
            self._git("add", ".", cwd=repo)
            self._git("commit", "-m", "init", cwd=repo)

            # Change line 2 and line 18 — far apart, should split
            lines[1] = "CHANGED2"
            lines[17] = "CHANGED18"
            with open(filepath, "w") as f:
                f.write("\n".join(lines) + "\n")

            diff = self._git("diff", cwd=repo)
            hunks = parse_diff(diff)
            assert len(hunks) == 2, f"Expected 2 hunks, got {len(hunks)}"

            # Stage only the first sub-hunk
            patch = build_patch([hunks[0]], diff)
            r = self._run(
                "git", "apply", "--cached", "--whitespace=nowarn",
                cwd=repo, input=patch,
            )
            assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

            staged = self._git("diff", "--cached", cwd=repo)
            assert "CHANGED2" in staged
            assert "CHANGED18" not in staged

            # Unstaged should still have the second change
            unstaged = self._git("diff", cwd=repo)
            assert "CHANGED18" in unstaged

    def test_split_hunks_stage_second_only(self):
        """Can stage the second split sub-hunk independently."""
        with tempfile.TemporaryDirectory() as repo:
            self._git("init", cwd=repo)
            self._git("config", "user.email", "test@test.com", cwd=repo)
            self._git("config", "user.name", "Test", cwd=repo)

            filepath = os.path.join(repo, "f.py")
            lines = [f"line{i}" for i in range(1, 21)]
            with open(filepath, "w") as f:
                f.write("\n".join(lines) + "\n")
            self._git("add", ".", cwd=repo)
            self._git("commit", "-m", "init", cwd=repo)

            lines[1] = "CHANGED2"
            lines[17] = "CHANGED18"
            with open(filepath, "w") as f:
                f.write("\n".join(lines) + "\n")

            diff = self._git("diff", cwd=repo)
            hunks = parse_diff(diff)
            assert len(hunks) == 2

            # Stage only the second sub-hunk
            patch = build_patch([hunks[1]], diff)
            r = self._run(
                "git", "apply", "--cached", "--whitespace=nowarn",
                cwd=repo, input=patch,
            )
            assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

            staged = self._git("diff", "--cached", cwd=repo)
            assert "CHANGED18" in staged
            assert "CHANGED2" not in staged
