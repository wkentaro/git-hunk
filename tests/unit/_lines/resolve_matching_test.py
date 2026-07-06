from collections.abc import Callable

import pytest

from git_hunk._hunk import NO_NEWLINE_MARKER
from git_hunk._hunk import Hunk
from git_hunk._lines import resolve_matching_lines

_TWO_GROUP = "@@ -1,4 +1,4 @@\n a\n-b\n+B\n c\n-d\n+D"


def test_literal_matches_changed_line_content(
    make_hunk: Callable[[str], Hunk],
) -> None:
    assert resolve_matching_lines(make_hunk(_TWO_GROUP), ["B"], regex=False) == {3}


def test_literal_ignores_context_lines(make_hunk: Callable[[str], Hunk]) -> None:
    # 'a' and 'c' are context; only the changed +/- lines are matchable.
    with pytest.raises(ValueError, match="no changed line matches"):
        resolve_matching_lines(make_hunk(_TWO_GROUP), ["a"], regex=False)


def test_multiple_patterns_are_ored(make_hunk: Callable[[str], Hunk]) -> None:
    result = resolve_matching_lines(make_hunk(_TWO_GROUP), ["b", "D"], regex=False)
    assert result == {2, 6}


def test_literal_is_case_sensitive(make_hunk: Callable[[str], Hunk]) -> None:
    hunk = make_hunk(_TWO_GROUP)
    assert resolve_matching_lines(hunk, ["b"], regex=False) == {2}
    assert resolve_matching_lines(hunk, ["B"], regex=False) == {3}


def test_literal_treats_metacharacters_literally(
    make_hunk: Callable[[str], Hunk],
) -> None:
    hunk = make_hunk("@@ -1,1 +1,2 @@\n ctx\n+value = items[0].get('x')")
    assert resolve_matching_lines(hunk, ["[0]"], regex=False) == {2}
    with pytest.raises(ValueError, match="no changed line matches"):
        resolve_matching_lines(hunk, ["x.y"], regex=False)


def test_regex_search(make_hunk: Callable[[str], Hunk]) -> None:
    hunk = make_hunk("@@ -1,1 +1,3 @@\n ctx\n+foo123\n+bar")
    assert resolve_matching_lines(hunk, [r"\d+"], regex=True) == {2}


def test_regex_metacharacters_are_special(make_hunk: Callable[[str], Hunk]) -> None:
    hunk = make_hunk("@@ -1,1 +1,3 @@\n ctx\n+value = items[0]\n+plain")
    assert resolve_matching_lines(hunk, [r"items\[0\]"], regex=True) == {2}


def test_invalid_regex_errors(make_hunk: Callable[[str], Hunk]) -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        resolve_matching_lines(make_hunk(_TWO_GROUP), ["("], regex=True)


def test_zero_matches_errors_with_pattern_in_message(
    make_hunk: Callable[[str], Hunk],
) -> None:
    with pytest.raises(ValueError, match="nonexistent"):
        resolve_matching_lines(make_hunk(_TWO_GROUP), ["nonexistent"], regex=False)


def test_interleaved_no_newline_marker_does_not_consume_a_line_number(
    make_hunk: Callable[[str], Hunk],
) -> None:
    # The marker sits between '-old' (line 2) and '+new'; it must be skipped
    # without incrementing the count, so '+new' stays line 3, matching -l's
    # numbering (context counted, markers excluded).
    hunk = make_hunk(f"@@ -1,2 +1,2 @@\n a\n-old\n{NO_NEWLINE_MARKER}\n+new")
    assert resolve_matching_lines(hunk, ["old"], regex=False) == {2}
    assert resolve_matching_lines(hunk, ["new"], regex=False) == {3}


def test_trailing_no_newline_marker_does_not_shift_line_numbers(
    make_hunk: Callable[[str], Hunk],
) -> None:
    hunk = make_hunk(f"{_TWO_GROUP}\n{NO_NEWLINE_MARKER}")
    assert resolve_matching_lines(hunk, ["D"], regex=False) == {6}
