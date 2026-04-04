import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from git_hunk.cli import cli as git_hunk_cli
from tests.conftest import GitRepo


class GitHunkCLI:
    def __init__(self, repo: GitRepo) -> None:
        self.repo = repo

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        runner = CliRunner()
        old_cwd = os.getcwd()
        try:
            os.chdir(self.repo.path)
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

    def run_ok(self, *args: str) -> str:
        r = self.run(*args)
        assert r.returncode == 0, f"git-hunk {' '.join(args)} failed: {r.stderr}"
        return r.stdout

    def run_json(self, *args: str) -> list[dict[str, str]]:
        return json.loads(self.run_ok(*args))  # type: ignore[no-any-return]


@pytest.fixture
def cli(git_repo: GitRepo) -> GitHunkCLI:
    return GitHunkCLI(git_repo)
