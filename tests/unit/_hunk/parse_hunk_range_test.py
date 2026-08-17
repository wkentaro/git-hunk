import pytest

from git_hunk._hunk import HunkRange
from git_hunk._hunk import parse_hunk_range


def test_parses_both_counts() -> None:
    assert parse_hunk_range("@@ -1,3 +4,5 @@") == HunkRange(1, 3, 4, 5)


def test_omitted_count_means_one() -> None:
    assert parse_hunk_range("@@ -1 +4 @@") == HunkRange(1, 1, 4, 1)


def test_zero_count_stays_zero() -> None:
    # git writes a 0,0 side for a created or deleted file; zero is a real
    # count, not the 1 an omitted count defaults to.
    assert parse_hunk_range("@@ -0,0 +1,3 @@") == HunkRange(0, 0, 1, 3)
    assert parse_hunk_range("@@ -1,3 +0,0 @@") == HunkRange(1, 3, 0, 0)


def test_keeps_git_heading_as_suffix() -> None:
    assert parse_hunk_range("@@ -1,3 +1,3 @@ def foo():").suffix == " def foo():"


@pytest.mark.parametrize(
    "header",
    [
        "diff --git a/f.py b/f.py",
        "@@ -a,3 +1,3 @@",
        "@@ -1,3 +1,3 @",
        "@@ -1,3 @@",
        " @@ -1,3 +1,3 @@",
    ],
)
def test_raises_when_header_does_not_match(header: str) -> None:
    with pytest.raises(ValueError, match="cannot parse hunk header"):
        parse_hunk_range(header)
