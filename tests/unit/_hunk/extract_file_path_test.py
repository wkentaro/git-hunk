from git_hunk._hunk import extract_file_path
from git_hunk._hunk import parse_diff


def test_plain_path() -> None:
    assert extract_file_path("diff --git a/src/foo.py b/src/foo.py") == "src/foo.py"


def test_non_ascii_path_unquoted() -> None:
    assert extract_file_path("diff --git a/файл.txt b/файл.txt") == "файл.txt"


def test_c_quoted_path_with_octal_escaped_control_char() -> None:
    # ESC (0x1b) has no single-letter C escape, so git falls back to a 3-digit
    # octal escape even under core.quotePath=false.
    line = r'diff --git "a/f\033x.txt" "b/f\033x.txt"'
    assert extract_file_path(line) == "f\x1bx.txt"


def test_path_containing_b_slash_substring() -> None:
    line = "diff --git a/a b/c.txt b/a b/c.txt"
    assert extract_file_path(line) == "a b/c.txt"


def test_uses_only_the_first_line() -> None:
    file_diff = (
        "diff --git a/файл.txt b/файл.txt\n"
        "index 422c2b7..55dce13 100644\n"
        "--- a/файл.txt\n"
        "+++ b/файл.txt\n"
    )
    assert extract_file_path(file_diff) == "файл.txt"


def test_no_match_returns_none() -> None:
    assert extract_file_path("index abc..def 100644") is None


def test_parse_diff_uses_b_slash_path() -> None:
    diff = (
        "diff --git a/a b/c.txt b/a b/c.txt\n"
        "index b77b4eb..7061c57 100644\n"
        "--- a/a b/c.txt\t\n"
        "+++ b/a b/c.txt\t\n"
        "@@ -1,2 +1,2 @@\n"
        " x\n"
        "-y\n"
        "+Y\n"
    )
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].file == "a b/c.txt"
