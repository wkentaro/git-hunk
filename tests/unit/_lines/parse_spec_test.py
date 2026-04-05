import pytest

from git_hunk._lines import parse_line_spec


def test_single_line() -> None:
    lines, exclude = parse_line_spec("3")
    assert lines == {3}
    assert exclude is False


def test_multiple_lines() -> None:
    lines, exclude = parse_line_spec("1,3,5")
    assert lines == {1, 3, 5}
    assert exclude is False


def test_range() -> None:
    lines, exclude = parse_line_spec("2-5")
    assert lines == {2, 3, 4, 5}
    assert exclude is False


def test_mixed_range_and_single() -> None:
    lines, exclude = parse_line_spec("1,3-5,8")
    assert lines == {1, 3, 4, 5, 8}
    assert exclude is False


def test_exclude_single() -> None:
    lines, exclude = parse_line_spec("^3")
    assert lines == {3}
    assert exclude is True


def test_exclude_range() -> None:
    lines, exclude = parse_line_spec("^2-4,^7")
    assert lines == {2, 3, 4, 7}
    assert exclude is True


def test_mixed_include_exclude_errors() -> None:
    with pytest.raises(ValueError, match="cannot mix"):
        parse_line_spec("3,^5")


def test_empty_errors() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_line_spec("")


def test_non_positive_errors() -> None:
    with pytest.raises(ValueError, match="positive"):
        parse_line_spec("0")


def test_reversed_range_errors() -> None:
    with pytest.raises(ValueError, match="start > end"):
        parse_line_spec("5-3")
