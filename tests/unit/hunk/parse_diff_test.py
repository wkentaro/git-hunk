from git_hunk.hunk import parse_diff


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
