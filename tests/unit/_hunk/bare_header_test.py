import pytest

from git_hunk._hunk import _bare_header


def test_strips_git_heading() -> None:
    assert _bare_header("@@ -1,3 +1,3 @@ def foo():") == "@@ -1,3 +1,3 @@"


def test_keeps_bare_header_unchanged() -> None:
    assert _bare_header("@@ -1,3 +1,3 @@") == "@@ -1,3 +1,3 @@"


def test_single_line_ranges_without_count() -> None:
    assert _bare_header("@@ -1 +1 @@ def foo():") == "@@ -1 +1 @@"


def test_raises_when_header_does_not_match() -> None:
    with pytest.raises(ValueError, match="cannot parse hunk header"):
        _bare_header("diff --git a/f.py b/f.py")
