from git_hunk._ui import _safe


def test_identity_on_ascii() -> None:
    assert _safe(text="hello world") == "hello world"


def test_identity_on_valid_utf8() -> None:
    assert _safe(text="café — π") == "café — π"


def test_surrogates_become_strict_utf8_encodable() -> None:
    # 0xe9 decoded with surrogateescape becomes the lone surrogate U+DCE9.
    result = _safe(text="a\udce9b")
    # The point of _safe: the result can be written to a strict UTF-8 stream.
    result.encode("utf-8")
    assert "\udce9" not in result
