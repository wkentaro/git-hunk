from git_hunk.hunk import parse_diff
from git_hunk.lines import filter_hunk_lines
from git_hunk.patch import build_patch

from .conftest import GitRepo


def test_stage_partial_lines(git_repo: GitRepo) -> None:
    git_repo.write_file("test.py", "line1\nline2\nline3\n")
    git_repo.git("add", ".")
    git_repo.git("commit", "-m", "init")

    git_repo.write_file("test.py", "LINE1\nline2\nLINE3\n")

    diff = git_repo.git("diff")
    hunks = parse_diff(diff)
    assert len(hunks) == 1

    filtered = filter_hunk_lines(hunks[0], {1, 2}, exclude=False)
    patch = build_patch([filtered], diff)

    r = git_repo.run(
        "git",
        "apply",
        "--cached",
        "--whitespace=nowarn",
        input=patch,
    )
    assert r.returncode == 0, f"git apply failed: {r.stderr}"

    staged = git_repo.git("diff", "--cached")
    assert "LINE1" in staged
    assert "LINE3" not in staged

    unstaged = git_repo.git("diff")
    assert "LINE3" in unstaged
