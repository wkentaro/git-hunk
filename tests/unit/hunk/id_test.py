from git_hunk.hunk import Hunk
from git_hunk.hunk import _body_id
from git_hunk.hunk import _full_id
from git_hunk.hunk import _with_stable_ids
from git_hunk.hunk import count_changes


def test_body_id_ignores_header_line_numbers() -> None:
    diff_a = "@@ -1,3 +1,4 @@\n ctx\n+added\n ctx2"
    diff_b = "@@ -10,3 +10,4 @@\n ctx\n+added\n ctx2"
    assert _body_id("f.py", diff_a) == _body_id("f.py", diff_b)


def test_body_id_differs_for_different_content() -> None:
    diff_a = "@@ -1,3 +1,4 @@\n ctx\n+added_A\n ctx2"
    diff_b = "@@ -1,3 +1,4 @@\n ctx\n+added_B\n ctx2"
    assert _body_id("f.py", diff_a) != _body_id("f.py", diff_b)


def test_body_id_differs_for_different_files() -> None:
    diff = "@@ -1,3 +1,4 @@\n ctx\n+added\n ctx2"
    assert _body_id("a.py", diff) != _body_id("b.py", diff)


def test_full_id_includes_header() -> None:
    diff_a = "@@ -1,3 +1,4 @@\n ctx\n+added\n ctx2"
    diff_b = "@@ -10,3 +10,4 @@\n ctx\n+added\n ctx2"
    assert _full_id("f.py", diff_a) != _full_id("f.py", diff_b)


def _make_hunk(*, file: str, diff: str) -> Hunk:
    return Hunk(
        id="",
        file=file,
        header="",
        additions=0,
        deletions=0,
        context_before="",
        diff=diff,
    )


def test_stable_ids_unique_hunks() -> None:
    hunks = [
        _make_hunk(file="f.py", diff="@@ -1,1 +1,2 @@\n+A"),
        _make_hunk(file="f.py", diff="@@ -10,1 +10,2 @@\n+B"),
    ]
    result = _with_stable_ids(hunks)
    assert result[0].id != result[1].id
    assert result[0].id == _body_id("f.py", hunks[0].diff)


def test_stable_ids_collision_falls_back_to_full_id() -> None:
    same_body = "@@ -1,1 +1,2 @@\n+same"
    same_body_shifted = "@@ -20,1 +20,2 @@\n+same"
    hunks = [
        _make_hunk(file="f.py", diff=same_body),
        _make_hunk(file="f.py", diff=same_body_shifted),
    ]
    assert _body_id("f.py", same_body) == _body_id("f.py", same_body_shifted)

    result = _with_stable_ids(hunks)
    assert result[0].id != result[1].id
    assert result[0].id == _full_id("f.py", same_body)
    assert result[1].id == _full_id("f.py", same_body_shifted)


def test_count_changes_mixed() -> None:
    lines = [" ctx", "+add1", "+add2", "-del1", " ctx2"]
    additions, deletions = count_changes(lines)
    assert additions == 2
    assert deletions == 1


def test_count_changes_empty() -> None:
    assert count_changes([]) == (0, 0)


def test_count_changes_context_only() -> None:
    assert count_changes([" a", " b"]) == (0, 0)
