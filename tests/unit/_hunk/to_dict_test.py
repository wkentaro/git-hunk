from git_hunk._hunk import Hunk


def test_to_dict_includes_context_before() -> None:
    hunk = Hunk(
        id="abc1234",
        file="f.py",
        header="@@ -1,3 +1,3 @@ def foo():",
        additions=1,
        deletions=1,
        context_before="def foo():",
        diff="@@ -1,3 +1,3 @@ def foo():\n-a\n+b",
    )
    assert hunk.to_dict()["context_before"] == "def foo():"


def test_to_dict_context_before_empty_when_no_context() -> None:
    hunk = Hunk(
        id="abc1234",
        file="f.txt",
        header="@@ -1,3 +1,3 @@",
        additions=1,
        deletions=1,
        context_before="",
        diff="@@ -1,3 +1,3 @@\n-a\n+b",
    )
    serialized = hunk.to_dict()
    assert "context_before" in serialized
    assert serialized["context_before"] == ""
