import base64

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
    assert hunk.to_dict()["context_before"] == {"text": "def foo():"}


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
    assert serialized["context_before"] == {"text": ""}


def test_to_dict_wraps_text_fields_and_keeps_scalars_plain() -> None:
    # Multi-byte UTF-8 (héllo) must stay {"text": ...}, not get base64'd.
    hunk = Hunk(
        id="abc1234",
        file="f.py",
        header="@@ -1,3 +1,4 @@ def héllo():",
        additions=2,
        deletions=1,
        context_before="def héllo():",
        diff="@@ -1,3 +1,4 @@ def héllo():\n-a\n+b\n+c",
    )
    serialized = hunk.to_dict()
    assert serialized["file"] == {"text": "f.py"}
    assert serialized["header"] == {"text": "@@ -1,3 +1,4 @@ def héllo():"}
    assert serialized["diff"] == {"text": "@@ -1,3 +1,4 @@ def héllo():\n-a\n+b\n+c"}
    assert serialized["id"] == "abc1234"
    assert serialized["status"] == "unstaged"
    assert serialized["additions"] == 2
    assert serialized["deletions"] == 1


def test_to_dict_encodes_non_utf8_file_as_bytes() -> None:
    # A non-UTF-8 byte in a path reaches to_dict as a lone surrogate (run_git
    # decodes with surrogateescape). The filesystem rejects such names on macOS,
    # so the path-bytes case is only reachable at this level, not via e2e.
    hunk = Hunk(
        id="abc1234",
        file=b"pass\xe9.txt".decode(errors="surrogateescape"),
        header="@@ -1,2 +1,2 @@",
        additions=1,
        deletions=1,
        context_before="",
        diff="@@ -1,2 +1,2 @@\n-a\n+b",
    )
    file_field = hunk.to_dict()["file"]
    assert set(file_field) == {"bytes"}
    assert base64.b64decode(file_field["bytes"]) == b"pass\xe9.txt"
