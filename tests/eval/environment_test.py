import subprocess
from pathlib import Path

import pytest

from eval.config import CLAUDE_CODE_VERSION
from eval.environment import _require_current_skill
from eval.environment import _run
from eval.environment import require_claude_version
from eval.repo import init_repo


def test_accepts_exact_claude_code_version() -> None:
    require_claude_version(version_output=f"{CLAUDE_CODE_VERSION} (Claude Code)")


def test_rejects_claude_code_version_mismatch() -> None:
    with pytest.raises(RuntimeError, match="must be "):
        require_claude_version(version_output="0.0.0 (Claude Code)")


def test_git_commands_ignore_inherited_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout_path = tmp_path / "checkout"
    decoy_path = tmp_path / "decoy"
    checkout_path.mkdir()
    decoy_path.mkdir()
    checkout = init_repo(path=checkout_path)
    decoy = init_repo(path=decoy_path)
    monkeypatch.setenv("GIT_DIR", str(decoy.path / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy.path))

    result = _run(
        command=["git", "rev-parse", "--show-toplevel"],
        cwd=checkout.path,
    )

    assert Path(result.stdout.strip()) == checkout.path


def test_git_commands_ignore_global_status_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout_path = tmp_path / "checkout"
    checkout_path.mkdir()
    checkout = init_repo(path=checkout_path)
    checkout.write_file(name="untracked.txt", content="work\n")
    global_config = tmp_path / "gitconfig"
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(global_config),
            "status.showUntrackedFiles",
            "no",
        ],
        capture_output=True,
        check=True,
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))

    result = _run(
        command=["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=checkout.path,
    )

    assert result.stdout == "?? untracked.txt\n"


def test_rejects_skill_that_does_not_match_imported_package(
    tmp_path: Path,
) -> None:
    imported_package = tmp_path / "git_hunk" / "__init__.py"
    stale_skill = tmp_path / ".venv" / "git_hunk" / "skills" / "core" / "SKILL.md"

    with pytest.raises(RuntimeError, match="does not match imported package skill"):
        _require_current_skill(
            path=stale_skill,
            imported_package=imported_package,
            name="core",
        )
