from git_hunk._hunk import Hunk
from git_hunk._ui import _whole_file_label


def _whole_file_hunk(
    *, change_kind: str, a_mode: str | None, b_mode: str | None, binary: bool
) -> Hunk:
    return Hunk(
        id="abc1234",
        file="x",
        change_kind=change_kind,
        a_mode=a_mode,
        b_mode=b_mode,
        binary=binary,
        header=None,
        context_before=None,
        additions=0,
        deletions=0,
        diff="",
    )


def test_type_change_label() -> None:
    hunk = _whole_file_hunk(
        change_kind="T", a_mode="100644", b_mode="120000", binary=False
    )
    assert _whole_file_label(hunk) == "Type change (100644 -> 120000)"


def test_binary_type_change_keeps_type_change_label() -> None:
    # A binary file replaced by a symlink: the typechange nature must win over the
    # binary flag, otherwise the UI hides that this is a type change.
    hunk = _whole_file_hunk(
        change_kind="T", a_mode="100644", b_mode="120000", binary=True
    )
    assert _whole_file_label(hunk) == "Type change (100644 -> 120000)"


def test_binary_added_label() -> None:
    hunk = _whole_file_hunk(change_kind="A", a_mode=None, b_mode="100644", binary=True)
    assert _whole_file_label(hunk) == "Binary file (added)"


def test_binary_deleted_label() -> None:
    hunk = _whole_file_hunk(change_kind="D", a_mode="100644", b_mode=None, binary=True)
    assert _whole_file_label(hunk) == "Binary file (deleted)"


def test_binary_modified_label() -> None:
    hunk = _whole_file_hunk(
        change_kind="M", a_mode="100644", b_mode="100644", binary=True
    )
    assert _whole_file_label(hunk) == "Binary file (modified)"


def test_mode_change_label() -> None:
    hunk = _whole_file_hunk(
        change_kind="M", a_mode="100644", b_mode="100755", binary=False
    )
    assert _whole_file_label(hunk) == "Mode 100644 -> 100755"
