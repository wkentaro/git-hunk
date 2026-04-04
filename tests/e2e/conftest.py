import json
import subprocess
import sys

import pytest

from tests.conftest import GitRepo


class GitHunkCLI:
    def __init__(self, repo: GitRepo) -> None:
        self.repo = repo

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "git_hunk", *args],
            capture_output=True,
            text=True,
            cwd=self.repo.path,
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
