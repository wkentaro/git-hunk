import pytest

from .conftest import GitHunkCLI

REPORTS = (["list"], ["show"], ["list", "--json"])


# color.ui and color.diff reach git's diff colorization through different
# config lookups, so each key gets its own case. Both keys at once run in the
# hostile diff config of the repository_path suite, which also covers the
# mutation commands.
@pytest.mark.parametrize("key", ["color.ui", "color.diff"])
def test_forced_color_leaves_the_reports_unchanged(cli: GitHunkCLI, key: str) -> None:
    # `always` makes git colorize into a pipe too, so the ANSI escapes land in
    # the diff git-hunk parses rather than on a terminal.
    cli.repo.write_file("changed.txt", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("changed.txt", "a\nCHANGED\nc\n")

    plain = [cli.run_ok(*args) for args in REPORTS]
    # Guards the comparison below against holding for two empty inventories,
    # which is the very failure it exists to catch.
    assert all("changed.txt" in output for output in plain)
    cli.repo.git("config", key, "always")
    assert [cli.run_ok(*args) for args in REPORTS] == plain
