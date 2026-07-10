import json
import os
import subprocess
from typing import Any
from typing import cast

import pytest
from click.testing import CliRunner

from git_hunk._cli import cli as git_hunk_cli
from tests.conftest import GitRepo


class GitHunkCLI:
    def __init__(self, repo: GitRepo) -> None:
        self.repo = repo

    def run(
        self, *args: str, subdir: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        runner = CliRunner()
        old_cwd = os.getcwd()
        cwd = os.path.join(self.repo.path, subdir) if subdir else self.repo.path
        try:
            os.chdir(cwd)
            result = runner.invoke(git_hunk_cli, list(args))
        finally:
            os.chdir(old_cwd)

        if result.exception and not isinstance(result.exception, SystemExit):
            raise result.exception

        return subprocess.CompletedProcess(
            args=["git-hunk", *args],
            returncode=result.exit_code,
            stdout=result.output or "",
            stderr=result.stderr or "",
        )

    def run_ok(self, *args: str, subdir: str | None = None) -> str:
        r = self.run(*args, subdir=subdir)
        assert r.returncode == 0, f"git-hunk {' '.join(args)} failed: {r.stderr}"
        return r.stdout

    def run_json(self, *args: str) -> list[dict[str, Any]]:
        # For commands whose --json output is a bare array (e.g. `skills`).
        # `list --json` returns an envelope; use run_list_json for that.
        return cast("list[dict[str, Any]]", json.loads(self.run_ok(*args)))

    def run_list_envelope(
        self, *args: str, subdir: str | None = None
    ) -> dict[str, Any]:
        return cast("dict[str, Any]", json.loads(self.run_ok(*args, subdir=subdir)))

    def run_list_json(
        self, *args: str, subdir: str | None = None
    ) -> list[dict[str, Any]]:
        # `list --json` (and `show --json`) wrap the hunks in a versioned
        # envelope; tests that only need the hunks call this to unwrap it.
        envelope = self.run_list_envelope(*args, subdir=subdir)
        return cast("list[dict[str, Any]]", envelope["hunks"])


@pytest.fixture
def cli(git_repo: GitRepo) -> GitHunkCLI:
    return GitHunkCLI(git_repo)
