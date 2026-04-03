import os
import subprocess
import tempfile
from collections.abc import Generator

import pytest


class GitRepo:
    def __init__(self, path: str) -> None:
        self.path = path

    def run(
        self, *args: str, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            cwd=self.path,
            input=input,
        )

    def git(self, *args: str) -> str:
        r = self.run("git", *args)
        assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
        return r.stdout

    def write_file(self, name: str, content: str) -> str:
        filepath = os.path.join(self.path, name)
        with open(filepath, "w") as f:
            f.write(content)
        return filepath


@pytest.fixture
def git_repo() -> Generator[GitRepo]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = GitRepo(tmpdir)
        repo.git("init")
        repo.git("config", "user.email", "test@test.com")
        repo.git("config", "user.name", "Test")
        yield repo
