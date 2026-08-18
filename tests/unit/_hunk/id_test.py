import re

from git_hunk._hunk import Hunk
from git_hunk._hunk import _compute_text_hunk_id
from git_hunk._hunk import _compute_whole_file_hunk_id
from git_hunk._hunk import _hash_id
from git_hunk._hunk import assign_hunk_ids
from git_hunk._hunk import count_changes


def _make_hunk(
    *,
    hunk_id: str,
    header: str = "@@ -1 +1 @@",
    status: str = "unstaged",
) -> Hunk:
    return Hunk(
        id="",
        file="f.py",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header=header,
        context_before=None,
        additions=1,
        deletions=0,
        diff=f"{header}\n+same",
        status=status,
        base_id=hunk_id,
    )


def test_body_id_is_full_sha256() -> None:
    hunk_id = _compute_text_hunk_id("f.py", "@@ -1 +1 @@\n+added")

    assert re.fullmatch(r"[0-9a-f]{64}", hunk_id)


def test_body_id_excludes_range_and_section_heading() -> None:
    first = "@@ -1,3 +1,4 @@ def first():\n ctx\n+added\n ctx2"
    shifted = "@@ -10,3 +10,4 @@ def second():\n ctx\n+added\n ctx2"

    assert _compute_text_hunk_id("f.py", first) == _compute_text_hunk_id(
        "f.py", shifted
    )


def test_body_id_includes_repository_path_context_and_newline_state() -> None:
    base = "@@ -1 +1,2 @@\n context\n+added"

    assert _compute_text_hunk_id("a.py", base) != _compute_text_hunk_id("b.py", base)
    assert _compute_text_hunk_id("a.py", base) != _compute_text_hunk_id(
        "a.py", "@@ -1 +1,2 @@\n other context\n+added"
    )
    assert _compute_text_hunk_id("a.py", base) != _compute_text_hunk_id(
        "a.py", base + "\n\\ No newline at end of file"
    )


def test_whole_file_id_includes_modes_and_object_ids() -> None:
    base = _compute_whole_file_hunk_id(
        "f.bin",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        a_object_id="a" * 40,
        b_object_id="b" * 40,
    )

    assert base != _compute_whole_file_hunk_id(
        "f.bin",
        change_kind="M",
        a_mode="100644",
        b_mode="100755",
        a_object_id="a" * 40,
        b_object_id="b" * 40,
    )
    assert base != _compute_whole_file_hunk_id(
        "f.bin",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        a_object_id="a" * 40,
        b_object_id="c" * 40,
    )


def test_duplicate_group_gets_unique_conditional_ids() -> None:
    base_id = "a" * 64
    hunks = [
        _make_hunk(hunk_id=base_id),
        _make_hunk(hunk_id=base_id, header="@@ -20 +20 @@"),
    ]

    result = assign_hunk_ids(hunks)

    assert result[0].id != result[1].id
    assert {hunk.id_stability for hunk in result} == {"conditional"}


def test_conditional_ids_follow_duplicate_order_across_status_changes() -> None:
    base_id = "a" * 64
    before = assign_hunk_ids(
        [
            _make_hunk(hunk_id=base_id),
            _make_hunk(hunk_id=base_id, header="@@ -20 +20 @@"),
        ]
    )
    after = assign_hunk_ids(
        [
            _make_hunk(
                hunk_id=base_id,
                header="@@ -1 +1 @@",
                status="staged",
            ),
            _make_hunk(hunk_id=base_id, header="@@ -21 +21 @@"),
        ]
    )

    assert [hunk.id for hunk in after] == [hunk.id for hunk in before]


def test_staged_position_reads_a_peer_start_from_its_pre_image_side() -> None:
    # A staged member's own position is still in index coordinates, so the walk must
    # place each unstaged peer by its pre-image start. The last peer straddles the
    # staged member's start (pre-image 20 < 25 < post-image 30), so only the correct
    # reading counts its +5: the staged member lands at 25 + 10 + 5 = 40, behind its
    # group peer at 37, instead of at 35, ahead of it.
    group_id = "a" * 64
    staged = _make_hunk(hunk_id=group_id, header="@@ -25 +25 @@", status="staged")
    peer_in_group = _make_hunk(hunk_id=group_id, header="@@ -22 +37 @@")
    earlier_peer = _make_hunk(hunk_id="b" * 64, header="@@ -5 +5,11 @@")
    straddling_peer = _make_hunk(hunk_id="c" * 64, header="@@ -20 +30,6 @@")

    result = assign_hunk_ids([staged, peer_in_group, earlier_peer, straddling_peer])

    # Ordinals spelled out, not reread from a second assignment run: an oracle that
    # shares the sort cancels out the ordering under test.
    assert result[0].id == _hash_id("conditional", group_id, "1")
    assert result[1].id == _hash_id("conditional", group_id, "0")


def test_single_group_member_uses_stable_base_id() -> None:
    base_id = "a" * 64
    hunk = _make_hunk(hunk_id=base_id)

    [result] = assign_hunk_ids([hunk])

    assert result.id == base_id
    assert result.id_stability == "stable"


def test_human_prefix_extends_until_ids_are_unique() -> None:
    hunks = [
        _make_hunk(hunk_id="abcdefg0" + "0" * 56),
        _make_hunk(hunk_id="abcdefg1" + "1" * 56, header="@@ -20 +20 @@"),
        _make_hunk(hunk_id="1234567" + "2" * 57, header="@@ -40 +40 @@"),
    ]

    result = assign_hunk_ids(hunks)

    assert [hunk.id_prefix_length for hunk in result] == [8, 8, 7]


def test_count_changes_mixed() -> None:
    lines = [" ctx", "+add1", "+add2", "-del1", " ctx2"]

    assert count_changes(lines) == (2, 1)


def test_count_changes_empty() -> None:
    assert count_changes([]) == (0, 0)


def test_count_changes_context_only() -> None:
    assert count_changes([" a", " b"]) == (0, 0)
