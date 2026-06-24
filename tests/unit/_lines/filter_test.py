from collections.abc import Callable

import pytest

from git_hunk._hunk import NO_NEWLINE_MARKER
from git_hunk._hunk import Hunk
from git_hunk._lines import filter_hunk_lines


def test_include_additions(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
    hunk = make_hunk(diff)
    result = filter_hunk_lines(hunk, {2}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "+add1" in result.diff
    assert "add2" not in result.diff
    assert "add3" not in result.diff


def test_include_deletions(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,4 +1,2 @@ def foo():\n ctx1\n-del1\n-del2\n ctx2"
    hunk = make_hunk(diff)
    result = filter_hunk_lines(hunk, {2}, exclude=False)
    assert result.deletions == 1
    assert "-del1" in result.diff
    assert " del2" in result.diff


def test_exclude_mode(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,3 +1,5 @@ def foo():\n ctx1\n+add1\n+add2\n ctx2\n+add3"
    hunk = make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=True)
    assert result.additions == 2
    assert "+add1" in result.diff
    assert "add2" not in result.diff
    assert "+add3" in result.diff


def test_no_changes_remain_errors(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
    hunk = make_hunk(diff)
    with pytest.raises(ValueError, match="no changes remain"):
        filter_hunk_lines(hunk, {2}, exclude=True)


def test_out_of_range_errors(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,2 +1,3 @@ def foo():\n ctx1\n+add1\n ctx2"
    hunk = make_hunk(diff)
    with pytest.raises(ValueError, match="out of range"):
        filter_hunk_lines(hunk, {99}, exclude=False)


def test_header_recalculated(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,4 +1,5 @@ def foo():\n ctx1\n-del1\n+add1\n+add2\n ctx2"
    hunk = make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "-1,3" in result.header
    assert "+1,4" in result.header


def test_mixed_changes(make_hunk: Callable[[str], Hunk]) -> None:
    diff = "@@ -1,3 +1,4 @@ def foo():\n ctx\n-old\n+new1\n+new2"
    hunk = make_hunk(diff)
    result = filter_hunk_lines(hunk, {3}, exclude=False)
    assert result.additions == 1
    assert result.deletions == 0
    assert "+new1" in result.diff
    assert " old" in result.diff
    assert "new2" not in result.diff


_TWO_GROUP = "@@ -1,4 +1,4 @@\n a\n-b\n+B\n c\n-d\n+D"


def test_reverse_include_drops_unselected_deletion_keeps_addition(
    make_hunk: Callable[[str], Hunk],
) -> None:
    # Reverse (unstage/discard): unselected '+' becomes context, '-' drops.
    hunk = make_hunk(_TWO_GROUP)
    result = filter_hunk_lines(hunk, {2, 3}, exclude=False, reverse=True)
    assert result.additions == 1
    assert result.deletions == 1
    assert "-b" in result.diff
    assert "+B" in result.diff
    assert " D" in result.diff  # unselected +D kept as NEW context
    assert "-d" not in result.diff  # unselected -d dropped


def test_reverse_exclude_first_group(make_hunk: Callable[[str], Hunk]) -> None:
    hunk = make_hunk(_TWO_GROUP)
    result = filter_hunk_lines(hunk, {2, 3}, exclude=True, reverse=True)
    assert result.additions == 1
    assert result.deletions == 1
    assert "-d" in result.diff
    assert "+D" in result.diff
    assert " B" in result.diff  # excluded +B kept as NEW context
    assert "-b" not in result.diff  # excluded -b dropped


_NO_NEWLINE_TO_NEWLINE = f"@@ -1,2 +1,2 @@\n a\n-b\n{NO_NEWLINE_MARKER}\n+B"


def test_keep_addition_splits_stale_no_newline_context(
    make_hunk: Callable[[str], Hunk],
) -> None:
    # The unselected '-b' (no trailing newline) survives as context, but the
    # kept '+B' now follows it: it must split into -b/+b so the marker stays on
    # the old side and 'b' gains a newline rather than merging with 'B'.
    hunk = make_hunk(_NO_NEWLINE_TO_NEWLINE)
    result = filter_hunk_lines(hunk, {3}, exclude=False)
    assert result.diff == (f"@@ -1,2 +1,3 @@\n a\n-b\n{NO_NEWLINE_MARKER}\n+b\n+B")
    assert result.additions == 2
    assert result.deletions == 1


def test_keep_deletion_drops_no_newline_marker_from_dropped_addition(
    make_hunk: Callable[[str], Hunk],
) -> None:
    # Keeping only '-b' drops '+B' and its marker; 'b' keeps no trailing newline
    # as the old side's final line, the new side ends at the ' a' context.
    hunk = make_hunk(_NO_NEWLINE_TO_NEWLINE)
    result = filter_hunk_lines(hunk, {2}, exclude=False)
    assert result.diff == f"@@ -1,2 +1,1 @@\n a\n-b\n{NO_NEWLINE_MARKER}"
    assert result.additions == 0
    assert result.deletions == 1


_REVERSE_NEW_SIDE_NO_NEWLINE = (
    f"@@ -1,4 +1,4 @@\n a\n-b\n+B\n c\n-d\n+D\n{NO_NEWLINE_MARKER}"
)


def test_reverse_keeps_no_newline_new_context_without_split(
    make_hunk: Callable[[str], Hunk],
) -> None:
    # Reverse keeps the unselected '+D' (new-side EOF, no trailing newline) as
    # context. It is always the last body line, so its marker stays put and it
    # never splits: the '+'-origin split branch of _render_body_lines is dead.
    hunk = make_hunk(_REVERSE_NEW_SIDE_NO_NEWLINE)
    result = filter_hunk_lines(hunk, {3}, exclude=False, reverse=True)
    assert result.diff == (f"@@ -1,3 +1,4 @@\n a\n+B\n c\n D\n{NO_NEWLINE_MARKER}")
    assert result.additions == 1
    assert result.deletions == 0
