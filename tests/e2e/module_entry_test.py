import runpy
import sys

import pytest


# `python -m git_hunk` runs __main__.py, which the CliRunner-based tests never
# import; this proves that entry point delegates to cli() and exits cleanly.
def test_python_m_git_hunk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["git-hunk", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("git_hunk", run_name="__main__")

    assert excinfo.value.code == 0
