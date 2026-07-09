import os

import pytest

from git_hunk import _cli
from git_hunk._cli import _normalize_path_arg


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("foo.py", "foo.py"),
        ("./foo.py", "foo.py"),
        ("sub/nested.py", "sub/nested.py"),
        ("./sub/../foo.py", "foo.py"),
    ],
)
def test_normalize_path_arg_collapses_to_git_form(arg: str, expected: str) -> None:
    assert _normalize_path_arg(arg) == expected


def test_normalize_path_arg_translates_windows_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_cli.os, "sep", "\\")
    assert os.sep == "\\"
    assert _normalize_path_arg("sub\\nested.py") == "sub/nested.py"
