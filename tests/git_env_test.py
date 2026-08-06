import os
import subprocess
import sys
from pathlib import Path


def test_suite_ignores_an_inherited_git_environment(tmp_path: Path) -> None:
    """The suite must not write to whatever repository GIT_DIR names.

    Point GIT_DIR and friends at a decoy repository, run a slice of the suite,
    and assert the decoy stays empty. `_scrubbed_git_env` in conftest.py
    explains why the scrub exists.
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

    decoy_commits = subprocess.run(
        ["git", "-C", str(decoy), "rev-list", "--all", "--count"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert decoy_commits.stdout.strip() == "0"
