import pytest

from git_hunk.hunk import Hunk
from git_hunk.hunk import parse_diff
from git_hunk.patch import build_patch

from .conftest import GitRepo


@pytest.fixture()
def two_hunk_repo(git_repo: GitRepo) -> tuple[GitRepo, str, list[Hunk]]:
    lines = [f"line{i}" for i in range(1, 21)]
    git_repo.write_file("f.py", "\n".join(lines) + "\n")
    git_repo.git("add", ".")
    git_repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    git_repo.write_file("f.py", "\n".join(lines) + "\n")

    diff = git_repo.git("diff")
    hunks = parse_diff(diff)
    assert len(hunks) == 2
    return git_repo, diff, hunks


def test_stage_first_hunk_only(two_hunk_repo: tuple[GitRepo, str, list[Hunk]]) -> None:
    git_repo, diff, hunks = two_hunk_repo

    patch = build_patch([hunks[0]], diff)
    r = git_repo.run(
        "git",
        "apply",
        "--cached",
        "--whitespace=nowarn",
        input=patch,
    )
    assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

    staged = git_repo.git("diff", "--cached")
    assert "CHANGED2" in staged
    assert "CHANGED18" not in staged

    unstaged = git_repo.git("diff")
    assert "CHANGED18" in unstaged


def test_stage_second_hunk_only(two_hunk_repo: tuple[GitRepo, str, list[Hunk]]) -> None:
    git_repo, diff, hunks = two_hunk_repo

    patch = build_patch([hunks[1]], diff)
    r = git_repo.run(
        "git",
        "apply",
        "--cached",
        "--whitespace=nowarn",
        input=patch,
    )
    assert r.returncode == 0, f"git apply failed: {r.stderr}\npatch:\n{patch}"

    staged = git_repo.git("diff", "--cached")
    assert "CHANGED18" in staged
    assert "CHANGED2" not in staged
