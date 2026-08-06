import ntpath
import os
from typing import Final

import pytest

from git_hunk import _cli
from git_hunk._cli import CliError
from git_hunk._cli import _make_repository_path

_WORKTREE_ROOT: Final = "/repo"


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("foo.py", "foo.py"),
        ("./foo.py", "foo.py"),
        ("sub/nested.py", "sub/nested.py"),
        ("./sub/../foo.py", "foo.py"),
    ],
)
def test_make_repository_path_collapses_to_git_form(arg: str, expected: str) -> None:
    assert _make_repository_path(arg, worktree_root=_WORKTREE_ROOT) == expected


def test_make_repository_path_translates_windows_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_cli.os, "sep", "\\")
    assert os.sep == "\\"
    path = _make_repository_path("sub\\nested.py", worktree_root=_WORKTREE_ROOT)
    assert path == "sub/nested.py"


@pytest.mark.parametrize("arg", ["/repo/file.py", "/"])
def test_make_repository_path_rejects_absolute_path(arg: str) -> None:
    with pytest.raises(CliError, match="repository path must be relative"):
        _make_repository_path(arg, worktree_root=_WORKTREE_ROOT)


@pytest.mark.parametrize("arg", ["..", "../file.py", "sub/../../file.py"])
def test_make_repository_path_rejects_path_that_escapes_worktree(arg: str) -> None:
    with pytest.raises(CliError, match="repository path escapes the worktree"):
        _make_repository_path(arg, worktree_root=_WORKTREE_ROOT)


def test_make_repository_path_rejects_windows_drive_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_cli.os.path, "splitdrive", ntpath.splitdrive)
    with pytest.raises(CliError, match="repository path must be relative"):
        _make_repository_path("C:foo.py", worktree_root=_WORKTREE_ROOT)


def test_make_repository_path_rejection_tip_names_the_worktree_root() -> None:
    with pytest.raises(CliError) as excinfo:
        _make_repository_path("/elsewhere/file.py", worktree_root=_WORKTREE_ROOT)
    assert excinfo.value.tip is not None
    assert _WORKTREE_ROOT in excinfo.value.tip
