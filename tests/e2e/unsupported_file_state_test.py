import os
import subprocess

import pytest

from .conftest import GitHunkCLI


def _make_unmerged_file(cli: GitHunkCLI, stages: tuple[int, ...]) -> None:
    hashes = []
    for stage in (1, 2, 3):
        path = f"stage-{stage}.txt"
        full_path = cli.repo.write_file(path, f"stage {stage}\n")
        hashes.append(cli.repo.git("hash-object", "-w", path).strip())
        os.unlink(full_path)
    records = "0 0000000000000000000000000000000000000000\tconflict.txt\n"
    records += "".join(
        f"100644 {hashes[stage - 1]} {stage}\tconflict.txt\n" for stage in stages
    )
    result = subprocess.run(
        ["git", "update-index", "--index-info"],
        capture_output=True,
        cwd=cli.repo.path,
        input=records.encode(),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert "\tconflict.txt\0" in cli.repo.git("ls-files", "--unmerged", "-z")


def _commit_source(cli: GitHunkCLI, path: str = "old.txt") -> None:
    cli.repo.write_file(path, "one\ntwo\nthree\nfour\nfive\n")
    cli.repo.git("add", path)
    cli.repo.git("commit", "-m", "init")


def _make_staged_rename(
    cli: GitHunkCLI, old: str = "old.txt", new: str = "new.txt"
) -> None:
    _commit_source(cli, path=old)
    cli.repo.git("mv", old, new)


def _make_unstaged_rename(cli: GitHunkCLI) -> None:
    _commit_source(cli)
    os.rename(
        os.path.join(cli.repo.path, "old.txt"),
        os.path.join(cli.repo.path, "new.txt"),
    )
    cli.repo.git("add", "--intent-to-add", "new.txt")


def _make_unstaged_copy(cli: GitHunkCLI) -> None:
    _commit_source(cli, path="source.txt")
    cli.repo.write_file("copy.txt", "one\ntwo\nthree\nfour\nfive\n")
    cli.repo.git("add", "--intent-to-add", "copy.txt")


def _run_git_bytes(
    cli: GitHunkCLI, *args: bytes, input: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [b"git", *args],
        capture_output=True,
        cwd=os.fsencode(cli.repo.path),
        input=input,
    )


def _snapshot_repository(cli: GitHunkCLI) -> tuple[str, str, str, str, str]:
    return (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("ls-files", "--stage"),
        cli.repo.git("status", "--porcelain=v1", "-z"),
        cli.repo.git("diff", "--cached", "--raw"),
        cli.repo.git("diff", "--raw"),
    )


def test_list_rejects_staged_rename_before_json_output(cli: GitHunkCLI) -> None:
    _make_staged_rename(cli)

    result = cli.run("list", "--staged", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "rename" in result.stderr
    assert "old.txt" in result.stderr
    assert "new.txt" in result.stderr
    assert "tip: use Git directly for rename and copy changes" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("list", "--unstaged", "--json"),
        ("show", "--unstaged"),
        ("stage", "new.txt"),
        ("stage", "new.txt", "--dry-run"),
        ("discard", "new.txt"),
        ("discard", "new.txt", "--dry-run"),
        ("commit", "new.txt", "-m", "must reject"),
    ],
)
def test_commands_reject_unstaged_rename_before_output_or_mutation(
    cli: GitHunkCLI, args: tuple[str, ...]
) -> None:
    _make_unstaged_rename(cli)
    before = cli.repo.git("status", "--porcelain=v1", "-z")

    result = cli.run(*args)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "rename" in result.stderr
    assert cli.repo.git("status", "--porcelain=v1", "-z") == before


def test_unstage_rejects_staged_rename_before_mutation(cli: GitHunkCLI) -> None:
    _make_staged_rename(cli)
    before = cli.repo.git("diff", "--cached", "--raw")

    result = cli.run("unstage", "new.txt")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "rename" in result.stderr
    assert cli.repo.git("diff", "--cached", "--raw") == before


@pytest.mark.parametrize("edit", [False, True], ids=["unchanged", "edited"])
def test_list_rejects_staged_copy(cli: GitHunkCLI, edit: bool) -> None:
    _commit_source(cli, path="source.txt")
    content = (
        "one\ntwo changed\nthree\nfour\nfive\n"
        if edit
        else "one\ntwo\nthree\nfour\nfive\n"
    )
    cli.repo.write_file("copy.txt", content)
    cli.repo.git("add", "copy.txt")

    result = cli.run("list", "--staged", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "copy" in result.stderr
    assert "source.txt" in result.stderr
    assert "copy.txt" in result.stderr
    assert "tip: use Git directly for rename and copy changes" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("list", "--unstaged", "--json"),
        ("show", "--unstaged"),
        ("stage", "copy.txt"),
        ("stage", "copy.txt", "--dry-run"),
        ("discard", "copy.txt"),
        ("discard", "copy.txt", "--dry-run"),
        ("commit", "copy.txt", "-m", "must reject"),
    ],
)
def test_commands_reject_unstaged_copy_before_output_or_mutation(
    cli: GitHunkCLI, args: tuple[str, ...]
) -> None:
    _make_unstaged_copy(cli)
    before = cli.repo.git("status", "--porcelain=v1", "-z")

    result = cli.run(*args)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "copy" in result.stderr
    assert cli.repo.git("status", "--porcelain=v1", "-z") == before


def test_unstage_rejects_staged_copy_before_mutation(cli: GitHunkCLI) -> None:
    _commit_source(cli, path="source.txt")
    cli.repo.write_file("copy.txt", "one\ntwo\nthree\nfour\nfive\n")
    cli.repo.git("add", "copy.txt")
    before = cli.repo.git("diff", "--cached", "--raw")

    result = cli.run("unstage", "copy.txt")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "copy" in result.stderr
    assert cli.repo.git("diff", "--cached", "--raw") == before


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(
            "old\tname.txt",
            "new\tname.txt",
            marks=pytest.mark.skipif(
                os.name == "nt", reason="Windows does not allow this file name"
            ),
        ),
        pytest.param(
            "old\nname.txt",
            "new\nname.txt",
            marks=pytest.mark.skipif(
                os.name == "nt", reason="Windows does not allow this file name"
            ),
        ),
        pytest.param(
            "old\\name.txt",
            'new"name.txt',
            marks=pytest.mark.skipif(
                os.name == "nt", reason="Windows does not allow this file name"
            ),
        ),
        ("x b/y.txt", "z.txt"),
    ],
)
def test_list_rejects_quoted_and_ambiguous_renames(
    cli: GitHunkCLI, old: str, new: str
) -> None:
    _make_staged_rename(cli, old=old, new=new)
    cli.repo.write_file(new, "one\ntwo changed\nthree\nfour\nfive\n")
    cli.repo.git("add", new)

    result = cli.run("list", "--staged", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "rename" in result.stderr
    assert "y.txt b/z.txt" not in result.stderr


def test_rename_detection_ignores_weak_repository_configuration(
    cli: GitHunkCLI,
) -> None:
    _make_staged_rename(cli)
    cli.repo.git("config", "diff.renames", "false")
    cli.repo.git("config", "diff.renameLimit", "1")

    result = cli.run("list", "--staged", "--json")

    assert result.returncode != 0
    assert "rename" in result.stderr


def test_mixed_rename_selection_changes_nothing(cli: GitHunkCLI) -> None:
    cli.repo.write_file("ordinary.txt", "old\n")
    cli.repo.write_file("old.txt", "rename\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("ordinary.txt", "new\n")
    cli.repo.git("add", "ordinary.txt")
    cli.repo.git("mv", "old.txt", "new.txt")
    before = cli.repo.git("diff", "--cached", "--raw")

    result = cli.run("unstage", "ordinary.txt")

    assert result.returncode != 0
    assert "rename" in result.stderr
    assert cli.repo.git("diff", "--cached", "--raw") == before


@pytest.mark.skipif(os.name == "nt", reason="Windows paths do not accept these bytes")
def test_rename_error_handles_non_utf8_path_bytes(cli: GitHunkCLI) -> None:
    old = b"old_\xff.txt"
    new = b"new_\xff.txt"
    hash_result = _run_git_bytes(
        cli, b"hash-object", b"-w", b"--stdin", input=b"content\n"
    )
    assert hash_result.returncode == 0, hash_result.stderr
    oid = hash_result.stdout.strip()
    add_old = _run_git_bytes(
        cli, b"update-index", b"--add", b"--cacheinfo", b"100644," + oid + b"," + old
    )
    assert add_old.returncode == 0, add_old.stderr
    cli.repo.git("commit", "-m", "init")
    remove_old = _run_git_bytes(cli, b"update-index", b"--force-remove", b"--", old)
    assert remove_old.returncode == 0, remove_old.stderr
    add_new = _run_git_bytes(
        cli, b"update-index", b"--add", b"--cacheinfo", b"100644," + oid + b"," + new
    )
    assert add_new.returncode == 0, add_new.stderr

    result = cli.run("list", "--staged", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "rename" in result.stderr
    assert "\\udcff" in result.stderr


def test_list_rejects_unmerged_index_before_json_output(cli: GitHunkCLI) -> None:
    cli.repo.write_file("conflict.txt", "base\n")
    cli.repo.git("add", "conflict.txt")
    cli.repo.git("commit", "-m", "init")
    _make_unmerged_file(cli, stages=(1, 2, 3))

    result = cli.run("list", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unmerged" in result.stderr
    assert "conflict.txt" in result.stderr
    assert "tip: resolve the unmerged index with Git, then retry" in result.stderr


@pytest.mark.parametrize(
    "stages",
    [(1,), (2,), (3,), (1, 2), (1, 3), (2, 3), (1, 2, 3)],
)
def test_list_rejects_every_unmerged_stage_set(
    cli: GitHunkCLI, stages: tuple[int, ...]
) -> None:
    cli.repo.write_file("conflict.txt", "base\n")
    cli.repo.git("add", "conflict.txt")
    cli.repo.git("commit", "-m", "init")
    _make_unmerged_file(cli, stages=stages)

    result = cli.run("list", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unmerged" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("list", "ordinary.txt", "--json"),
        ("show",),
        ("stage", "ordinary.txt"),
        ("stage", "ordinary.txt", "--dry-run"),
        ("unstage", "ordinary.txt"),
        ("unstage", "ordinary.txt", "--dry-run"),
        ("discard", "ordinary.txt"),
        ("discard", "ordinary.txt", "--dry-run"),
        ("commit", "ordinary.txt", "-m", "must reject"),
    ],
)
def test_commands_reject_unmerged_index_before_output_or_mutation(
    cli: GitHunkCLI, args: tuple[str, ...]
) -> None:
    cli.repo.write_file("conflict.txt", "base\n")
    cli.repo.write_file("ordinary.txt", "base\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("ordinary.txt", "staged\n")
    cli.repo.git("add", "ordinary.txt")
    cli.repo.write_file("ordinary.txt", "unstaged\n")
    _make_unmerged_file(cli, stages=(1, 2, 3))
    before = _snapshot_repository(cli)

    result = cli.run(*args)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unmerged" in result.stderr
    assert "conflict.txt" in result.stderr
    assert _snapshot_repository(cli) == before


@pytest.mark.skipif(os.name == "nt", reason="Windows paths do not accept these bytes")
def test_unmerged_error_handles_non_utf8_path_bytes(cli: GitHunkCLI) -> None:
    hash_result = _run_git_bytes(
        cli, b"hash-object", b"-w", b"--stdin", input=b"content\n"
    )
    assert hash_result.returncode == 0, hash_result.stderr
    oid = hash_result.stdout.strip()
    update_result = _run_git_bytes(
        cli,
        b"update-index",
        b"--index-info",
        input=b"100644 " + oid + b" 1\tbad_\xff.txt\n",
    )
    assert update_result.returncode == 0, update_result.stderr

    result = cli.run("list", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unmerged" in result.stderr
    assert "\\udcff" in result.stderr
