from collections.abc import Callable
from typing import Final

import pytest

from git_hunk._hunk import Hunk
from git_hunk._lines import filter_hunk_lines


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("diff", "selected"),
    [
        ("@@ -1 +1,3 @@\n a\n+b\n+c", {2}),
        ("@@ -1,3 +1 @@\n a\n-b\n-c", {2}),
        ("@@ -1,2 +1,2 @@\n a\n-b\n+B", {2, 3}),
        ("@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C", {2, 3, 4, 5}),
    ],
)
def test_allows_unambiguous_group_selection(
    *,
    make_hunk: Callable[[str], Hunk],
    diff: str,
    selected: set[int],
    reverse: bool,
) -> None:
    result = filter_hunk_lines(
        make_hunk(diff), selected, exclude=False, reverse=reverse
    )

    assert result.additions + result.deletions > 0


_ONE_FOR_ONE: Final = "@@ -1,2 +1,2 @@\n a\n-b\n+B"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("selected", [{2}, {3}])
def test_rejects_one_sided_one_for_one_replacement_by_default(
    *,
    make_hunk: Callable[[str], Hunk],
    selected: set[int],
    reverse: bool,
) -> None:
    with pytest.raises(ValueError, match="cannot select one side of lines 2-3"):
        filter_hunk_lines(
            make_hunk(_ONE_FOR_ONE), selected, exclude=False, reverse=reverse
        )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("selected", [{2}, {3}])
def test_allows_one_sided_one_for_one_replacement_when_opted_in(
    *,
    make_hunk: Callable[[str], Hunk],
    selected: set[int],
    reverse: bool,
) -> None:
    result = filter_hunk_lines(
        make_hunk(_ONE_FOR_ONE),
        selected,
        exclude=False,
        reverse=reverse,
        allow_one_sided=True,
    )

    assert result.additions + result.deletions == 1


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("selected", [{2}, {3}])
def test_exclude_selection_rejects_the_other_side_of_a_pair(
    *,
    make_hunk: Callable[[str], Hunk],
    selected: set[int],
    reverse: bool,
) -> None:
    # Excluding one side of the pair still leaves the other side alone.
    with pytest.raises(ValueError, match="cannot select one side of lines 2-3"):
        filter_hunk_lines(
            make_hunk(_ONE_FOR_ONE), selected, exclude=True, reverse=reverse
        )


def test_one_for_one_error_names_both_lines_and_the_override(
    *,
    make_hunk: Callable[[str], Hunk],
) -> None:
    with pytest.raises(ValueError) as excinfo:
        filter_hunk_lines(make_hunk(_ONE_FOR_ONE), {2}, exclude=False)

    assert str(excinfo.value) == (
        "cannot select one side of lines 2-3: one-for-one replacement; "
        "match text both lines share, select both lines, or pass --allow-one-sided"
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("diff", "selected", "message"),
    [
        ("@@ -1,2 +1,3 @@\n a\n-b\n+B\n+C", {2}, "deletions: 1, additions: 2"),
        ("@@ -1,3 +1,2 @@\n a\n-b\n-c\n+B", {2}, "deletions: 2, additions: 1"),
        (
            "@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C",
            {2, 4},
            "deletions: 2, additions: 2",
        ),
    ],
)
def test_rejects_partial_composite_replacement(
    *,
    make_hunk: Callable[[str], Hunk],
    diff: str,
    selected: set[int],
    message: str,
    reverse: bool,
) -> None:
    with pytest.raises(ValueError, match=message):
        filter_hunk_lines(make_hunk(diff), selected, exclude=False, reverse=reverse)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("diff", "selected"),
    [
        ("@@ -1,2 +1,3 @@\n a\n-b\n+B\n+C", {2}),
        ("@@ -1,3 +1,2 @@\n a\n-b\n-c\n+B", {2}),
        ("@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C", {2, 4}),
    ],
)
def test_allow_one_sided_does_not_relax_the_wider_group_rule(
    *,
    make_hunk: Callable[[str], Hunk],
    diff: str,
    selected: set[int],
    reverse: bool,
) -> None:
    with pytest.raises(ValueError, match="cannot partially select"):
        filter_hunk_lines(
            make_hunk(diff),
            selected,
            exclude=False,
            reverse=reverse,
            allow_one_sided=True,
        )


@pytest.mark.parametrize("reverse", [False, True])
def test_allows_unselected_composite_group_when_another_group_changes(
    *, make_hunk: Callable[[str], Hunk], reverse: bool
) -> None:
    diff = "@@ -1,4 +1,5 @@\n a\n-b\n-c\n+B\n+C\n x\n+tail"

    result = filter_hunk_lines(make_hunk(diff), {7}, exclude=False, reverse=reverse)

    assert result.additions + result.deletions > 0


@pytest.mark.parametrize("reverse", [False, True])
def test_exclude_selection_uses_the_same_group_rule(
    *, make_hunk: Callable[[str], Hunk], reverse: bool
) -> None:
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C"

    with pytest.raises(ValueError, match="cannot partially select"):
        filter_hunk_lines(make_hunk(diff), {2, 5}, exclude=True, reverse=reverse)


@pytest.mark.parametrize(
    ("reverse", "selected", "expected_diff"),
    [
        # Staging takes every deletion and replaces the old run with only the
        # selected addition; the unselected addition stays behind.
        (False, {2, 3, 4}, "@@ -1,3 +1,2 @@\n a\n-b\n-c\n+B"),
        # Unstaging or discarding takes every addition and restores only the
        # selected deletion; the unselected deletion stays applied.
        (True, {2, 4, 5}, "@@ -1,2 +1,3 @@\n a\n-b\n+B\n+C"),
    ],
)
def test_allows_partial_group_that_takes_the_whole_consumed_side(
    *,
    make_hunk: Callable[[str], Hunk],
    reverse: bool,
    selected: set[int],
    expected_diff: str,
) -> None:
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C"

    result = filter_hunk_lines(
        make_hunk(diff), selected, exclude=False, reverse=reverse
    )

    assert result.diff == expected_diff


@pytest.mark.parametrize(
    ("reverse", "selected"),
    [(False, {2, 4, 5}), (True, {2, 3, 4})],
)
def test_rejects_partial_group_that_takes_only_the_other_whole_side(
    *, make_hunk: Callable[[str], Hunk], reverse: bool, selected: set[int]
) -> None:
    # Taking the whole side the apply does not consume leaves an unselected
    # line as context, and nothing says whether it goes before or after.
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C"
    side = "addition" if reverse else "deletion"

    with pytest.raises(ValueError, match=f"or every {side} plus the lines to keep"):
        filter_hunk_lines(make_hunk(diff), selected, exclude=False, reverse=reverse)


def test_context_line_does_not_change_group_classification(
    *,
    make_hunk: Callable[[str], Hunk],
) -> None:
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+C"

    result = filter_hunk_lines(make_hunk(diff), {1, 2, 3, 4, 5}, exclude=False)

    assert result.additions == 2
    assert result.deletions == 2
