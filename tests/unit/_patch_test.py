import pytest

from git_hunk._hunk import Hunk
from git_hunk._hunk import whole_file_hunk
from git_hunk._patch import _extract_file_headers
from git_hunk._patch import build_patch

DIFF_SINGLE = (
    "diff --git a/f.py b/f.py\n"
    "index abc..def 100644\n"
    "--- a/f.py\n"
    "+++ b/f.py\n"
    "@@ -1,3 +1,4 @@\n"
    " line1\n"
    "+added\n"
    " line2\n"
    " line3\n"
)

DIFF_TWO_FILES = (
    "diff --git a/a.py b/a.py\n"
    "index 111..222 100644\n"
    "--- a/a.py\n"
    "+++ b/a.py\n"
    "@@ -1,2 +1,3 @@\n"
    " x\n"
    "+A\n"
    " y\n"
    "diff --git a/b.py b/b.py\n"
    "index 333..444 100644\n"
    "--- a/b.py\n"
    "+++ b/b.py\n"
    "@@ -1,2 +1,3 @@\n"
    " p\n"
    "+B\n"
    " q\n"
)


def _make_hunk(*, file: str, diff: str, change_kind: str = "M") -> Hunk:
    return Hunk(
        id="abc",
        file=file,
        change_kind=change_kind,
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header=None,
        context_before=None,
        additions=1,
        deletions=0,
        diff=diff,
    )


def test_extract_file_headers_stops_before_hunk() -> None:
    header = _extract_file_headers(DIFF_SINGLE)["f.py"]
    assert header.startswith("diff --git a/f.py b/f.py\n")
    assert "+++ b/f.py\n" in header
    assert "@@" not in header


def test_extract_file_headers_keys_every_file() -> None:
    headers = _extract_file_headers(DIFF_TWO_FILES)
    assert set(headers) == {"a.py", "b.py"}


def test_build_patch_missing_file_raises() -> None:
    hunk = _make_hunk(file="nonexistent.py", diff="")
    with pytest.raises(ValueError, match="not found"):
        build_patch([hunk], DIFF_SINGLE, reverse=False)


def test_build_patch_single_hunk() -> None:
    hunk = _make_hunk(
        file="f.py",
        diff="@@ -1,3 +1,4 @@\n line1\n+added\n line2\n line3",
    )
    patch = build_patch([hunk], DIFF_SINGLE, reverse=False)
    assert patch.startswith("diff --git a/f.py b/f.py\n")
    assert "+added" in patch


def test_build_patch_groups_by_file() -> None:
    hunk_a = _make_hunk(file="a.py", diff="@@ -1,2 +1,3 @@\n x\n+A\n y")
    hunk_b = _make_hunk(file="b.py", diff="@@ -1,2 +1,3 @@\n p\n+B\n q")
    patch = build_patch([hunk_a, hunk_b], DIFF_TWO_FILES, reverse=False)
    assert "diff --git a/a.py" in patch
    assert "diff --git a/b.py" in patch
    a_pos = patch.index("diff --git a/a.py")
    b_pos = patch.index("diff --git a/b.py")
    assert a_pos < b_pos


def test_build_patch_joins_hunks_of_same_file() -> None:
    diff_output = (
        "diff --git a/f.py b/f.py\n"
        "index abc..def 100644\n"
        "--- a/f.py\n"
        "+++ b/f.py\n"
        "@@ -1,2 +1,3 @@\n"
        " a\n"
        "+A\n"
        " b\n"
        "@@ -10,2 +11,3 @@\n"
        " c\n"
        "+C\n"
        " d\n"
    )
    hunk1 = _make_hunk(file="f.py", diff="@@ -1,2 +1,3 @@\n a\n+A\n b")
    hunk2 = _make_hunk(file="f.py", diff="@@ -10,2 +11,3 @@\n c\n+C\n d")
    patch = build_patch([hunk1, hunk2], diff_output, reverse=False)
    assert patch.count("diff --git a/f.py") == 1
    assert "+A" in patch
    assert "+C" in patch


def test_build_patch_text_hunk_omits_unselected_mode_change() -> None:
    diff_output = (
        "diff --git a/f.sh b/f.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index abc..def\n"
        "--- a/f.sh\n"
        "+++ b/f.sh\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    text_hunk = _make_hunk(file="f.sh", diff="@@ -1 +1 @@\n-old\n+new")

    patch = build_patch([text_hunk], diff_output, reverse=False)

    assert "old mode" not in patch
    assert "new mode" not in patch
    assert "@@ -1 +1 @@\n-old\n+new" in patch


def test_build_patch_mode_hunk_omits_unselected_text_change() -> None:
    diff_output = (
        "diff --git a/f.sh b/f.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index abc..def\n"
        "--- a/f.sh\n"
        "+++ b/f.sh\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    mode_hunk = whole_file_hunk(
        "f.sh",
        change_kind="M",
        a_mode="100644",
        b_mode="100755",
        binary=False,
        a_object_id=None,
        b_object_id=None,
    )

    patch = build_patch([mode_hunk], diff_output, reverse=False)

    assert patch == ("diff --git a/f.sh b/f.sh\nold mode 100644\nnew mode 100755\n")


def test_build_patch_combines_mode_and_text_without_blank_fragment() -> None:
    diff_output = (
        "diff --git a/f.sh b/f.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index abc..def\n"
        "--- a/f.sh\n"
        "+++ b/f.sh\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    mode_hunk = whole_file_hunk(
        "f.sh",
        change_kind="M",
        a_mode="100644",
        b_mode="100755",
        binary=False,
        a_object_id=None,
        b_object_id=None,
    )
    text_hunk = _make_hunk(file="f.sh", diff="@@ -1 +1 @@\n-old\n+new")

    patch = build_patch([mode_hunk, text_hunk], diff_output, reverse=False)

    assert "+++ b/f.sh\n@@ -1 +1 @@" in patch
    assert "+++ b/f.sh\n\n@@ -1 +1 @@" not in patch


def test_build_patch_converts_partial_added_file_to_modification() -> None:
    diff_output = (
        "diff --git a/f.txt b/f.txt\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/f.txt\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n"
        "+b\n"
    )
    hunk = _make_hunk(
        file="f.txt",
        change_kind="A",
        diff="@@ -1,1 +1,2 @@\n a\n+b",
    )

    patch = build_patch([hunk], diff_output, reverse=False)

    assert patch.startswith("diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n")
    assert "new file mode" not in patch
    assert "/dev/null" not in patch


def test_build_patch_converts_partial_deleted_file_to_modification() -> None:
    diff_output = (
        "diff --git a/f.txt b/f.txt\n"
        "deleted file mode 100644\n"
        "index 1111111..0000000\n"
        "--- a/f.txt\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-a\n"
        "-b\n"
    )
    hunk = _make_hunk(
        file="f.txt",
        change_kind="D",
        diff="@@ -1,2 +1,1 @@\n a\n-b",
    )

    patch = build_patch([hunk], diff_output, reverse=False)

    assert patch.startswith("diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n")
    assert "deleted file mode" not in patch
    assert "/dev/null" not in patch
