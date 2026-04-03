"""Tests for automatic hunk splitting."""

from git_hunk.hunk import _split_hunk, parse_diff
from git_hunk.patch import build_patch


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
        assert any(line.startswith("+") for line in result[0]["body_lines"])
        assert "+add1" in result[0]["body_lines"]
        assert "+add2" in result[1]["body_lines"]

    def test_three_regions_two_gaps_splits(self):
        """Three change regions with two large gaps — should split into 3."""
        header = "@@ -1,30 +1,33 @@ def foo():"
        body = [
            " ctx",
            "+add1",
            " g1",
            " g2",
            " g3",
            " g4",
            " g5",
            " g6",
            " g7",
            "+add2",
            " g8",
            " g9",
            " g10",
            " g11",
            " g12",
            " g13",
            " g14",
            "+add3",
            " ctx_end",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 3

    def test_split_preserves_context_around_changes(self):
        header = "@@ -1,16 +1,18 @@ def foo():"
        body = [
            " c1",
            " c2",
            "+add1",
            " g1",
            " g2",
            " g3",
            " g4",
            " g5",
            " g6",
            " g7",
            "+add2",
            " c3",
            " c4",
        ]
        result = _split_hunk("f.py", header, body)
        assert len(result) == 2
        first_body = result[0]["body_lines"]
        assert first_body[0] == " c1"
        assert "+add1" in first_body
        assert len([line for line in first_body if not line.startswith("+")]) <= 5

    def test_split_header_line_numbers(self):
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
        assert result[0]["header"].startswith("@@ -1,")
        assert "-6," in result[1]["header"] or "-5," in result[1]["header"]

    def test_deletions_handled(self):
        header = "@@ -1,14 +1,12 @@"
        body = [
            " ctx1",
            "-del1",
            " g1",
            " g2",
            " g3",
            " g4",
            " g5",
            " g6",
            " g7",
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


class TestParseDiffSplit:
    def test_parse_diff_splits_large_hunk(self):
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


class TestSplitIntegration:
    def test_split_hunks_stage_independently(self, git_repo):
        lines = [f"line{i}" for i in range(1, 21)]
        git_repo.write_file("f.py", "\n".join(lines) + "\n")
        git_repo.git("add", ".")
        git_repo.git("commit", "-m", "init")

        lines[1] = "CHANGED2"
        lines[17] = "CHANGED18"
        git_repo.write_file("f.py", "\n".join(lines) + "\n")

        diff = git_repo.git("diff")
        hunks = parse_diff(diff)
        assert len(hunks) == 2, f"Expected 2 hunks, got {len(hunks)}"

        patch = build_patch([hunks[0]], diff)
        r = git_repo.run(
            "git",
            "apply",
            "--cached",
            "--whitespace=nowarn",
            input=patch,
        )
        assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

        staged = git_repo.git("diff", "--cached")
        assert "CHANGED2" in staged
        assert "CHANGED18" not in staged

        unstaged = git_repo.git("diff")
        assert "CHANGED18" in unstaged

    def test_split_hunks_stage_second_only(self, git_repo):
        lines = [f"line{i}" for i in range(1, 21)]
        git_repo.write_file("f.py", "\n".join(lines) + "\n")
        git_repo.git("add", ".")
        git_repo.git("commit", "-m", "init")

        lines[1] = "CHANGED2"
        lines[17] = "CHANGED18"
        git_repo.write_file("f.py", "\n".join(lines) + "\n")

        diff = git_repo.git("diff")
        hunks = parse_diff(diff)
        assert len(hunks) == 2

        patch = build_patch([hunks[1]], diff)
        r = git_repo.run(
            "git",
            "apply",
            "--cached",
            "--whitespace=nowarn",
            input=patch,
        )
        assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

        staged = git_repo.git("diff", "--cached")
        assert "CHANGED18" in staged
        assert "CHANGED2" not in staged
