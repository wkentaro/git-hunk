import pytest

from git_hunk._hunk import Hunk
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


def _make_hunk(*, file: str, diff: str) -> Hunk:
    return Hunk(
        id="abc",
        file=file,
        change_kind="M",
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
        build_patch([hunk], DIFF_SINGLE)


def test_build_patch_single_hunk() -> None:
    hunk = _make_hunk(
        file="f.py",
        diff="@@ -1,3 +1,4 @@\n line1\n+added\n line2\n line3",
    )
    patch = build_patch([hunk], DIFF_SINGLE)
    assert patch.startswith("diff --git a/f.py b/f.py\n")
    assert "+added" in patch


def test_build_patch_groups_by_file() -> None:
    hunk_a = _make_hunk(file="a.py", diff="@@ -1,2 +1,3 @@\n x\n+A\n y")
    hunk_b = _make_hunk(file="b.py", diff="@@ -1,2 +1,3 @@\n p\n+B\n q")
    patch = build_patch([hunk_a, hunk_b], DIFF_TWO_FILES)
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
    patch = build_patch([hunk1, hunk2], diff_output)
    assert patch.count("diff --git a/f.py") == 1
    assert "+A" in patch
    assert "+C" in patch
