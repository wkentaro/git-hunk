from typing import NoReturn

from click.testing import CliRunner

from git_hunk._cli import CliGroup


def test_keyboard_interrupt_exits_130() -> None:
    group = CliGroup()

    @group.command()
    def boom() -> NoReturn:
        raise KeyboardInterrupt

    result = CliRunner().invoke(group, ["boom"])

    assert result.exit_code == 130
