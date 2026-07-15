from git_hunk._hunk import parse_diff


def test_one_section_maps_to_one_hunk() -> None:
    # Each @@ section becomes exactly one hunk. git's own -U3 hunking is what
    # separates distant changes into different sections; git-hunk never splits
    # within a section.
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
    assert len(hunks) == 1
    assert hunks[0].additions == 2
    assert hunks[0].change_kind == "M"
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode == "100644"
    assert hunks[0].binary is False
    # The JSON header is the bare range; the heading lives in context_before.
    assert hunks[0].header == "@@ -1,14 +1,16 @@"
    assert hunks[0].context_before == "def foo():"
    # The internal diff keeps git's verbatim @@ line (heading included).
    assert hunks[0].diff.startswith("@@ -1,14 +1,16 @@ def foo():\n")
    assert "+added_top" in hunks[0].diff
    assert "+added_bottom" in hunks[0].diff


def test_binary_file() -> None:
    diff = (
        "diff --git a/foo.qm b/foo.qm\n"
        "index abc1234..def5678 100644\n"
        "Binary files a/foo.qm and b/foo.qm differ\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "foo.qm"
    assert hunks[0].binary is True
    assert hunks[0].change_kind == "M"
    assert hunks[0].header is None
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
    assert hunks[0].binary is True
    assert hunks[1].file == "bar.py"
    assert hunks[1].binary is False
    assert hunks[1].additions == 1


def test_deleted_binary_distinguished() -> None:
    diff = (
        "diff --git a/d.bin b/d.bin\n"
        "deleted file mode 100644\n"
        "index 885b32b..0000000\n"
        "Binary files a/d.bin and /dev/null differ\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].binary is True
    assert hunks[0].change_kind == "D"
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode is None
    assert hunks[0].diff == ""


def test_added_binary_distinguished() -> None:
    diff = (
        "diff --git a/n.bin b/n.bin\n"
        "new file mode 100644\n"
        "index 0000000..abc1234\n"
        "Binary files /dev/null and b/n.bin differ\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].binary is True
    assert hunks[0].change_kind == "A"
    assert hunks[0].a_mode is None
    assert hunks[0].b_mode == "100644"


def test_mode_only_change_surfaced() -> None:
    diff = "diff --git a/m.sh b/m.sh\nold mode 100644\nnew mode 100755\n"
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "m.sh"
    assert hunks[0].change_kind == "M"
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode == "100755"
    assert hunks[0].binary is False
    assert hunks[0].header is None
    assert hunks[0].additions == 0
    assert hunks[0].deletions == 0
    assert hunks[0].diff == ""


def test_mode_and_content_change_together() -> None:
    # A chmod plus an edit to the same file is one diff block carrying both the
    # old/new mode headers and an @@ body. The content hunk must carry the mode
    # metadata, not collapse to the whole-file mode-only path.
    diff = (
        "diff --git a/m.sh b/m.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index abc..def\n"
        "--- a/m.sh\n"
        "+++ b/m.sh\n"
        "@@ -1 +1 @@\n"
        "-line one\n"
        "+line one changed\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "m.sh"
    assert hunks[0].change_kind == "M"
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode == "100755"
    assert hunks[0].binary is False
    assert hunks[0].header == "@@ -1 +1 @@"
    assert hunks[0].additions == 1
    assert hunks[0].deletions == 1
    assert hunks[0].diff == "@@ -1 +1 @@\n-line one\n+line one changed"


def test_typechange_is_single_whole_file_hunk() -> None:
    # git emits a file -> symlink type change as a delete block followed by an
    # add block for the same path; parse_diff merges them into one "T" hunk.
    diff = (
        "diff --git a/link b/link\n"
        "deleted file mode 100644\n"
        "index ce01362..0000000\n"
        "--- a/link\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-hello\n"
        "diff --git a/link b/link\n"
        "new file mode 120000\n"
        "index 0000000..1de5659\n"
        "--- /dev/null\n"
        "+++ b/link\n"
        "@@ -0,0 +1 @@\n"
        "+target\n"
        "\\ No newline at end of file\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "link"
    assert hunks[0].change_kind == "T"
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode == "120000"
    assert hunks[0].binary is False
    assert hunks[0].header is None
    assert hunks[0].diff == ""


def test_typechange_from_binary_is_marked_binary() -> None:
    # A binary file replaced by a symlink: the delete block is binary, so the
    # merged "T" hunk must report binary=True (either side being binary counts).
    diff = (
        "diff --git a/x b/x\n"
        "deleted file mode 100644\n"
        "index abc1234..0000000\n"
        "Binary files a/x and /dev/null differ\n"
        "diff --git a/x b/x\n"
        "new file mode 120000\n"
        "index 0000000..1de5659\n"
        "--- /dev/null\n"
        "+++ b/x\n"
        "@@ -0,0 +1 @@\n"
        "+target\n"
        "\\ No newline at end of file\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].change_kind == "T"
    assert hunks[0].binary is True
    assert hunks[0].a_mode == "100644"
    assert hunks[0].b_mode == "120000"
