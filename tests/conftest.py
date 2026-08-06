import os
import subprocess
import tempfile
from collections.abc import Generator
from typing import Final

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
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)
        return filepath


@pytest.fixture(autouse=True, scope="session")
def _scrubbed_git_env() -> Generator[None]:
    # git exports GIT_DIR, GIT_INDEX_FILE, and friends to the commands it runs:
    # `rebase --exec`, hooks, `filter-branch`, `bisect run`. Those beat cwd, so
    # every git subprocess the suite starts (the fixtures' own, and the ones
    # git_hunk spawns) would target the outer repository instead of the
    # temporary one, and the tests would commit into the repository under test.
    # Drop all of it, except the config overrides a caller may set to shield
    # the suite from the machine's gitconfig (e.g. GIT_CONFIG_GLOBAL=/dev/null
    # in CI); those improve hermeticity rather than break it.
    KEEP: Final = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"}
    with pytest.MonkeyPatch.context() as monkeypatch:
        for name in list(os.environ):
            if name.startswith("GIT_") and name not in KEEP:
                monkeypatch.delenv(name)
        yield


@pytest.fixture
def git_repo() -> Generator[GitRepo]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = GitRepo(tmpdir)
        repo.git("init")
        repo.git("config", "user.email", "test@test.com")
        repo.git("config", "user.name", "Test")
        yield repo
