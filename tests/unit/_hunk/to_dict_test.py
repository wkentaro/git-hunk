from git_hunk._hunk import Hunk


def _text_hunk(*, context_before: str | None) -> Hunk:
    return Hunk(
        id="abc1234",
        file="f.py",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header="@@ -1,3 +1,3 @@",
        context_before=context_before,
        additions=1,
        deletions=1,
        diff="@@ -1,3 +1,3 @@ def foo():\n ctx\n-a\n+b",
    )


def test_to_dict_wraps_context_before_in_text_union() -> None:
    serialized = _text_hunk(context_before="def foo():").to_dict()
    assert serialized["context_before"] == {"text": "def foo():"}


def test_to_dict_context_before_null_when_absent() -> None:
    serialized = _text_hunk(context_before=None).to_dict()
    assert serialized["context_before"] is None


def test_to_dict_typed_fields_and_byte_safe_file() -> None:
    serialized = _text_hunk(context_before=None).to_dict()
    assert serialized["file"] == {"text": "f.py"}
    assert serialized["change_kind"] == "M"
    assert serialized["a_mode"] == "100644"
    assert serialized["b_mode"] == "100644"
    assert serialized["binary"] is False
    assert serialized["header"] == "@@ -1,3 +1,3 @@"


def test_to_dict_omits_lines_by_default() -> None:
    assert "lines" not in _text_hunk(context_before=None).to_dict()


def test_to_dict_includes_structured_lines_when_requested() -> None:
    serialized = _text_hunk(context_before=None).to_dict(include_lines=True)
    assert serialized["lines"] == [
        {"n": 1, "op": " ", "content": {"text": "ctx"}},
        {"n": 2, "op": "-", "content": {"text": "a"}},
        {"n": 3, "op": "+", "content": {"text": "b"}},
    ]


def test_to_dict_lines_carry_no_newline_flag() -> None:
    hunk = Hunk(
        id="abc1234",
        file="f.txt",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header="@@ -1 +1 @@",
        context_before=None,
        additions=1,
        deletions=1,
        diff=(
            "@@ -1 +1 @@\n"
            "-a\n"
            "\\ No newline at end of file\n"
            "+b\n"
            "\\ No newline at end of file"
        ),
    )
    lines = hunk.to_dict(include_lines=True)["lines"]
    assert lines == [
        {"n": 1, "op": "-", "content": {"text": "a"}, "no_newline": True},
        {"n": 2, "op": "+", "content": {"text": "b"}, "no_newline": True},
    ]


def test_to_dict_whole_file_hunk_has_empty_lines_and_null_header() -> None:
    hunk = Hunk(
        id="abc1234",
        file="logo.png",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=True,
        header=None,
        context_before=None,
        additions=0,
        deletions=0,
        diff="",
    )
    serialized = hunk.to_dict(include_lines=True)
    assert serialized["header"] is None
    assert serialized["binary"] is True
    assert serialized["lines"] == []


def test_to_dict_byte_safe_content_falls_back_to_bytes() -> None:
    # 0xe9 is invalid standalone UTF-8; it survives decode as a lone surrogate.
    hunk = Hunk(
        id="abc1234",
        file="f.txt",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header="@@ -1 +1 @@",
        context_before=None,
        additions=1,
        deletions=0,
        diff="@@ -1 +1 @@\n+x\udce9y",
    )
    content = hunk.to_dict(include_lines=True)["lines"][0]["content"]
    assert content == {"bytes": "eOl5"}
