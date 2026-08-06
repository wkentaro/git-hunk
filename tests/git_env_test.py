import os
import subprocess
import sys
from pathlib import Path


def test_suite_ignores_an_inherited_git_environment(tmp_path: Path) -> None:
    """The suite must not write to whatever repository GIT_DIR names.

    `git rebase --exec`, hooks, `filter-branch`, and `bisect run` all export
    GIT_DIR and GIT_INDEX_FILE to the command they run. Those beat cwd, so a
    suite that inherited them would commit into the repository under test.
    Point them at a decoy repository and assert it stays empty.
    """
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=decoy, check=True)

    repo_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["GIT_DIR"] = str(decoy / ".git")
    env["GIT_INDEX_FILE"] = str(decoy / ".git" / "index")
    env["GIT_WORK_TREE"] = str(decoy)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/stage_test.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    decoy_log = subprocess.run(
        ["git", "-C", str(decoy), "log", "--oneline"],
        capture_output=True,
        text=True,
    )
    assert decoy_log.stdout == ""
