from git_hunk._hunk import NO_NEWLINE_MARKER
from git_hunk._hunk import parse_diff

_DIFF = (
    "diff --git a/f.txt b/f.txt\n"
    "index 1c943a9..5de31a1 100644\n"
    "--- a/f.txt\n"
    "+++ b/f.txt\n"
    "@@ -1,3 +1,3 @@\n"
    " a\n"
    " b\n"
    "-c\n"
    f"{NO_NEWLINE_MARKER}\n"
    "+cX\n"
    f"{NO_NEWLINE_MARKER}\n"
)


def test_preserves_no_newline_marker_in_diff() -> None:
    hunks = parse_diff(_DIFF)
    assert len(hunks) == 1
    assert hunks[0].diff.count(NO_NEWLINE_MARKER) == 2
    assert hunks[0].diff.endswith(NO_NEWLINE_MARKER)


def test_marker_not_counted_as_change() -> None:
    hunks = parse_diff(_DIFF)
    assert hunks[0].additions == 1
    assert hunks[0].deletions == 1


def test_split_keeps_marker_and_correct_counts() -> None:
    # Two change regions far enough apart to split; the file ends with no
    # newline, so the last sub-hunk must carry the marker without it leaking
    # into the @@ line counts.
    body = "".join(
        [" line1\n", "-old\n", "+new\n"]
        + [f" line{i}\n" for i in range(2, 10)]
        + ["-last\n", f"{NO_NEWLINE_MARKER}\n", "+lastX\n", f"{NO_NEWLINE_MARKER}\n"]
    )
    diff = (
        "diff --git a/f.txt b/f.txt\n"
        "index 1c943a9..5de31a1 100644\n"
        "--- a/f.txt\n"
        "+++ b/f.txt\n"
        "@@ -1,11 +1,11 @@\n" + body
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 2
    tail = hunks[-1]
    assert tail.diff.count(NO_NEWLINE_MARKER) == 2
    assert tail.diff.endswith(NO_NEWLINE_MARKER)
    # Marker lines must not inflate the @@ header line counts.
    assert tail.header == "@@ -8,4 +8,4 @@"
