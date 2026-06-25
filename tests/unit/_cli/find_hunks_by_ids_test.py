import pytest

from git_hunk._cli import CliError
from git_hunk._cli import _find_hunks_by_ids
from git_hunk._hunk import Hunk


def _make_hunk(*, hunk_id: str) -> Hunk:
    return Hunk(
        id=hunk_id,
        file="f.py",
        change_kind="M",
        a_mode="100644",
        b_mode="100644",
        binary=False,
        header=None,
        context_before=None,
        additions=0,
        deletions=0,
        diff="",
    )


@pytest.fixture
def hunks() -> list[Hunk]:
    return [_make_hunk(hunk_id="ab12cd0"), _make_hunk(hunk_id="ab34ef0")]


def test_unique_prefix_resolves_to_one_hunk(hunks: list[Hunk]) -> None:
    assert _find_hunks_by_ids(hunks, ["ab12"]) == [hunks[0]]


def test_multiple_ids_resolve_in_order(hunks: list[Hunk]) -> None:
    assert _find_hunks_by_ids(hunks, ["ab12", "ab34"]) == [hunks[0], hunks[1]]


def test_ambiguous_prefix_raises_with_matches_tip(hunks: list[Hunk]) -> None:
    with pytest.raises(CliError) as exc_info:
        _find_hunks_by_ids(hunks, ["ab"])
    assert str(exc_info.value) == "ambiguous hunk id 'ab'"
    assert exc_info.value.tip == "matches: ab12cd0, ab34ef0"


def test_unmatched_prefix_raises_not_found(hunks: list[Hunk]) -> None:
    with pytest.raises(CliError) as exc_info:
        _find_hunks_by_ids(hunks, ["ff"])
    assert str(exc_info.value) == "hunk 'ff' not found"
    assert exc_info.value.tip == "available hunk ids: ab12cd0, ab34ef0"


def test_not_found_with_empty_pool_has_no_tip() -> None:
    with pytest.raises(CliError) as exc_info:
        _find_hunks_by_ids([], ["ff"])
    assert str(exc_info.value) == "hunk 'ff' not found"
    assert exc_info.value.tip is None


@pytest.mark.parametrize("blank", ["", "  "])
def test_blank_id_rejected(hunks: list[Hunk], blank: str) -> None:
    with pytest.raises(CliError) as exc_info:
        _find_hunks_by_ids(hunks, [blank])
    assert str(exc_info.value) == "hunk id must not be empty or whitespace"
    assert exc_info.value.tip is None
