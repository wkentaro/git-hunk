from collections.abc import Callable

from git_hunk._hunk import NO_NEWLINE_MARKER
from git_hunk._hunk import Hunk
from git_hunk._lines import filter_hunk_lines


def test_drops_old_marker_when_selected_deletion_has_later_old_line(
    make_hunk: Callable[[str], Hunk],
) -> None:
    diff = f"@@ -1,2 +1,2 @@\n a\n-b\n{NO_NEWLINE_MARKER}\n+B"

    result = filter_hunk_lines(
        make_hunk(diff), {2}, exclude=False, reverse=True, allow_one_sided=True
    )

    assert result.diff == "@@ -1,3 +1,2 @@\n a\n-b\n B"


def test_drops_new_marker_when_selected_addition_has_later_new_line(
    make_hunk: Callable[[str], Hunk],
) -> None:
    diff = f"@@ -1,2 +1,2 @@\n a\n+b\n{NO_NEWLINE_MARKER}\n-B"

    result = filter_hunk_lines(
        make_hunk(diff), {2}, exclude=False, allow_one_sided=True
    )

    assert result.diff == "@@ -1,2 +1,3 @@\n a\n+b\n B"
