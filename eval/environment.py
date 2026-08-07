import dataclasses
import hashlib
import shutil
import subprocess
from pathlib import Path

import git_hunk
from eval.config import CLAUDE_CODE_VERSION
from eval.repo import make_subprocess_env


@dataclasses.dataclass(frozen=True)
class EvalEnvironment:
    checkout: Path
    commit: str
    git_hunk_executable: Path
    imported_package: Path
    skill_paths: dict[str, Path]
    skill_sha256: dict[str, str]
    claude_code_version: str


def resolve_environment() -> EvalEnvironment:
    checkout = Path(__file__).resolve().parents[1]
    status = _run(
        command=["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=checkout,
    )
    if status.stdout:
        raise RuntimeError("the eval checkout must be clean")
    commit = _run(command=["git", "rev-parse", "HEAD"], cwd=checkout).stdout.strip()

    executable_name = shutil.which("git-hunk")
    if executable_name is None:
        raise RuntimeError("git-hunk is not on PATH")
    executable = Path(executable_name).resolve()
    _require_within(path=executable, parent=checkout, label="git-hunk executable")

    if git_hunk.__file__ is None:
        raise RuntimeError("git_hunk has no imported source path")
    imported_package = Path(git_hunk.__file__).resolve()
    _require_within(
        path=imported_package,
        parent=checkout,
        label="imported git_hunk package",
    )

    skill_paths: dict[str, Path] = {}
    skill_hashes: dict[str, str] = {}
    for name in ("core", "logical-commits"):
        result = _run(
            command=[str(executable), "skills", "path", name],
            cwd=checkout,
        )
        skill_dir = Path(result.stdout.strip()).resolve()
        _require_within(path=skill_dir, parent=checkout, label=f"{name} skill")
        skill_file = skill_dir / "SKILL.md"
        _require_current_skill(
            path=skill_file,
            imported_package=imported_package,
            name=name,
        )
        skill_paths[name] = skill_file
        skill_hashes[name] = hashlib.sha256(skill_file.read_bytes()).hexdigest()

    claude_version = _run(command=["claude", "--version"], cwd=checkout).stdout.strip()
    require_claude_version(version_output=claude_version)
    return EvalEnvironment(
        checkout=checkout,
        commit=commit,
        git_hunk_executable=executable,
        imported_package=imported_package,
        skill_paths=skill_paths,
        skill_sha256=skill_hashes,
        claude_code_version=claude_version,
    )


def require_claude_version(*, version_output: str) -> None:
    actual_version = version_output.split(maxsplit=1)[0] if version_output else ""
    if actual_version != CLAUDE_CODE_VERSION:
        raise RuntimeError(
            f"Claude Code must be {CLAUDE_CODE_VERSION}, got {version_output!r}"
        )


def _run(*, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        cwd=cwd,
        env=make_subprocess_env(),
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} failed with {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return result


def _require_within(*, path: Path, parent: Path, label: str) -> None:
    if not path.is_relative_to(parent):
        raise RuntimeError(f"{label} {path} is outside checkout {parent}")


def _require_current_skill(*, path: Path, imported_package: Path, name: str) -> None:
    expected = imported_package.parent / "skills" / name / "SKILL.md"
    if path != expected:
        raise RuntimeError(
            f"{name} skill {path} does not match imported package skill {expected}"
        )
