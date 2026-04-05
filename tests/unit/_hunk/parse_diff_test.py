from git_hunk._hunk import parse_diff


def test_splits_large_hunk() -> None:
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


def test_binary_file() -> None:
    diff = (
        "diff --git a/foo.qm b/foo.qm\n"
        "index abc1234..def5678 100644\n"
        "Binary files a/foo.qm and b/foo.qm differ\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "foo.qm"
    assert hunks[0].header == "Binary file"
    assert hunks[0].additions == 0
    assert hunks[0].deletions == 0
    assert hunks[0].diff == ""


def test_binary_file_mixed_with_text() -> None:
    diff = (
        "diff --git a/foo.qm b/foo.qm\n"
        "index abc1234..def5678 100644\n"
        "Binary files a/foo.qm and b/foo.qm differ\n"
        "diff --git a/bar.py b/bar.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/bar.py\n"
        "+++ b/bar.py\n"
        "@@ -1,3 +1,4 @@\n"
        " import os\n"
        "+import sys\n"
        " \n"
        " def main():\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 2
    assert hunks[0].file == "foo.qm"
    assert hunks[0].header == "Binary file"
    assert hunks[1].file == "bar.py"
    assert hunks[1].additions == 1


def test_no_split_when_close() -> None:
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
