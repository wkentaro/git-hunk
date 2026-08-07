import os
import stat
import subprocess
from pathlib import Path


class GitRepo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def run(
        self,
        *args: str,
        timeout_seconds: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            capture_output=True,
            cwd=self.path,
            env=make_subprocess_env(),
            text=True,
            timeout=timeout_seconds,
        )

    def run_bytes(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            list(args),
            capture_output=True,
            cwd=self.path,
            env=make_subprocess_env(),
        )

    def git(self, *args: str) -> str:
        result = self.run("git", *args)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def git_bytes(self, *args: str) -> bytes:
        result = self.run_bytes("git", *args)
        if result.returncode != 0:
            detail = result.stderr.decode(errors="surrogateescape")
            raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
        return result.stdout

    def write_file(
        self, name: str, content: str | bytes, *, executable: bool = False
    ) -> None:
        file_path = self.path / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        file_path.write_bytes(data)
        if executable:
            file_path.chmod(file_path.stat().st_mode | stat.S_IXUSR)


def init_repo(path: str | Path) -> GitRepo:
    repo = GitRepo(path)
    repo.git("init", "--quiet")
    repo.git("config", "user.email", "test@test.com")
    repo.git("config", "user.name", "Test")
    repo.git("config", "core.autocrlf", "false")
    repo.git("config", "core.quotePath", "false")
    return repo


def make_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("GIT_"):
            del env[name]
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env
