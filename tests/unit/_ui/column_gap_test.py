from git_hunk._ui import _column_gap


def test_widest_entry_gets_the_bare_gutter() -> None:
    assert _column_gap("stage", 5) == "  "


def test_shorter_entry_is_padded_to_align_the_next_column() -> None:
    assert _column_gap("show", 6) == "    "


def test_text_plus_gap_reaches_the_same_column_offset() -> None:
    width = 8
    for text in ["a", "commit", "discard!"]:
        assert len(text) + len(_column_gap(text, width)) == width + 2
