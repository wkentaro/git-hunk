from pathlib import Path

import pytest
from pytest import MonkeyPatch

from .conftest import GitHunkCLI


@pytest.mark.parametrize("driver", ["diff.external", "GIT_EXTERNAL_DIFF", "textconv"])
def test_diff_driver_cannot_hide_inventory_or_mutations(
    *, cli: GitHunkCLI, monkeypatch: MonkeyPatch, driver: str
) -> None:
    cli.repo.write_file("changed.txt", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("changed.txt", "new\n")

    report_args = (["list"], ["show"], ["list", "--json"], ["show", "--json"])
    expected_reports = [cli.run_ok(*args) for args in report_args]
    assert all("changed.txt" in output for output in expected_reports)

    if driver == "diff.external":
        cli.repo.git("config", "diff.external", "git --version")
    elif driver == "GIT_EXTERNAL_DIFF":
        monkeypatch.setenv("GIT_EXTERNAL_DIFF", "git --version")
    else:
        cli.repo.write_file(".git/info/attributes", "*.txt diff=test\n")
        cli.repo.git("config", "diff.test.textconv", "git --version")

    assert [cli.run_ok(*args) for args in report_args] == expected_reports

    hunk_id = cli.get_only_hunk_id("--unstaged")
    cli.run_ok("stage", hunk_id)
    assert cli.get_only_hunk_id("--staged") == hunk_id
    assert cli.run_list_json("show", "--staged", "--json")[0]["id"] == hunk_id

    cli.run_ok("unstage", hunk_id)
    assert cli.get_only_hunk_id("--unstaged") == hunk_id
    cli.run_ok("discard", hunk_id)
    assert Path(cli.repo.path, "changed.txt").read_text() == "old\n"

    cli.repo.write_file("changed.txt", "committed\n")
    cli.run_ok("commit", "changed.txt", "-m", "change tracked file")
    assert cli.repo.git("show", "HEAD:changed.txt") == "committed\n"
    assert cli.repo.git("status", "--porcelain") == ""
