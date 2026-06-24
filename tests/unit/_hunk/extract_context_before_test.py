from git_hunk._hunk import _extract_context_before


def test_returns_trailing_context() -> None:
    assert _extract_context_before("@@ -1,3 +1,4 @@ def foo():") == "def foo():"


def test_strips_surrounding_whitespace() -> None:
    assert _extract_context_before("@@ -1,3 +1,4 @@   def foo():  ") == "def foo():"


def test_anchors_to_first_at_at_pair() -> None:
    header = "@@ -1,3 +1,4 @@ class Foo:  # @@ tag"
    assert _extract_context_before(header) == "class Foo:  # @@ tag"


def test_none_when_no_trailing_context() -> None:
    assert _extract_context_before("@@ -1,3 +1,4 @@") is None


def test_none_when_trailing_context_is_whitespace_only() -> None:
    assert _extract_context_before("@@ -1,3 +1,4 @@   ") is None


def test_none_when_header_does_not_match() -> None:
    assert _extract_context_before("diff --git a/f.py b/f.py") is None
