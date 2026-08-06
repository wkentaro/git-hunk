import pytest

from git_hunk import _lines
from git_hunk._lines import parse_line_spec


def test_single_line() -> None:
    lines, exclude = parse_line_spec("3", total=3)
    assert lines == {3}
    assert exclude is False


def test_multiple_lines() -> None:
    lines, exclude = parse_line_spec("1,3,5", total=5)
    assert lines == {1, 3, 5}
    assert exclude is False


def test_range() -> None:
    lines, exclude = parse_line_spec("2-5", total=5)
    assert lines == {2, 3, 4, 5}
    assert exclude is False


def test_mixed_range_and_single() -> None:
    lines, exclude = parse_line_spec("1,3-5,8", total=8)
    assert lines == {1, 3, 4, 5, 8}
    assert exclude is False


def test_exclude_single() -> None:
    lines, exclude = parse_line_spec("^3", total=3)
    assert lines == {3}
    assert exclude is True


def test_exclude_range() -> None:
    lines, exclude = parse_line_spec("^2-4,^7", total=7)
    assert lines == {2, 3, 4, 7}
    assert exclude is True


def test_mixed_include_exclude_errors() -> None:
    with pytest.raises(ValueError, match="cannot mix"):
        parse_line_spec("3,^5", total=5)


def test_empty_errors() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_line_spec("", total=1)


def test_non_positive_errors() -> None:
    with pytest.raises(ValueError, match="positive"):
        parse_line_spec("0", total=1)


def test_reversed_range_errors() -> None:
    with pytest.raises(ValueError, match="start > end"):
        parse_line_spec("5-3", total=5)


def test_range_with_too_many_parts_errors() -> None:
    with pytest.raises(ValueError, match="expected start-end"):
        parse_line_spec("1-2-3", total=3)


def test_non_numeric_token_errors() -> None:
    with pytest.raises(ValueError, match="invalid line number"):
        parse_line_spec("abc", total=1)


def test_open_ended_range_errors() -> None:
    with pytest.raises(ValueError, match="expected start-end"):
        parse_line_spec("1-", total=1)


def test_bare_caret_errors() -> None:
    with pytest.raises(ValueError, match="invalid token"):
        parse_line_spec("^", total=1)


def test_plus_prefixed_token_errors() -> None:
    with pytest.raises(ValueError, match="invalid line number"):
        parse_line_spec("+5", total=5)


def test_spaces_around_range_hyphen_allowed() -> None:
    lines, exclude = parse_line_spec("2 - 4", total=4)
    assert lines == {2, 3, 4}
    assert exclude is False


@pytest.mark.parametrize("spec", ["1-999999999", "^1-999999999"])
def test_range_endpoint_is_validated_before_expansion(
    monkeypatch: pytest.MonkeyPatch, spec: str
) -> None:
    def fail_range(*args: int) -> range:
        raise AssertionError(f"range expanded with {args}")

    monkeypatch.setattr(_lines, "range", fail_range, raising=False)
    with pytest.raises(
        ValueError,
        match=r"line number out of range \(hunk has 3 lines\)",
    ) as exc_info:
        parse_line_spec(spec, total=3)

    assert spec in str(exc_info.value)
