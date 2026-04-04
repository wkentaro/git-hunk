import pytest

from git_hunk.hunk import Hunk
from git_hunk.patch import _get_file_header
from git_hunk.patch import build_patch

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
        header="",
        additions=1,
        deletions=0,
        context_before="",
        diff=diff,
    )


def test_get_file_header_extracts_up_to_hunk() -> None:
    header = _get_file_header(DIFF_SINGLE, "f.py")
    assert header.startswith("diff --git a/f.py b/f.py\n")
    assert "+++ b/f.py\n" in header
    assert "@@" not in header


def test_get_file_header_missing_file_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        _get_file_header(DIFF_SINGLE, "nonexistent.py")


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
