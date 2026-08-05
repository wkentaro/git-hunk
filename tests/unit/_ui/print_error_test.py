import pytest

from git_hunk._ui import print_error


def test_escapes_brackets_in_message(capsys: pytest.CaptureFixture[str]) -> None:
    print_error("hunk '[id]' not found")
    assert "[id]" in capsys.readouterr().err


def test_escapes_brackets_in_tip(capsys: pytest.CaptureFixture[str]) -> None:
    print_error("not found", tip="try [foo] instead")
    assert "[foo]" in capsys.readouterr().err


def test_usage_block_renders_with_help_hint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_error("unrecognized subcommand", usage="Usage: git-hunk <COMMAND>")
    err = capsys.readouterr().err
    assert "Usage: git-hunk <COMMAND>" in err
    assert "For more information, try '--help'." in err
