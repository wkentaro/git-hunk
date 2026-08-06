import os
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from typing import TypeVar

import pytest

from tests.e2e.conftest import GitHunkCLI


@dataclass(frozen=True)
class GitEntry:
    mode: str
    object_id: str
    content: bytes


@dataclass(frozen=True)
class WorktreeEntry:
    mode: str
    content: bytes


@dataclass(frozen=True)
class RepositoryState:
    head_id: str
    head: dict[str, GitEntry]
    index: dict[str, GitEntry]
    worktree: dict[str, WorktreeEntry]
    raw_index: bytes
    status: bytes


MutationRepoFactory = Callable[[str, bytes, bytes], GitHunkCLI]
TRACKED_LITERAL_PATH: Final = (
    "[literal]!.txt" if os.name == "nt" else ":literal[*]?!.txt"
)
UNTRACKED_LITERAL_PATH: Final = (
    "[untracked]!.txt" if os.name == "nt" else ":untracked[*]?!.txt"
)
_Entry = TypeVar("_Entry")


def run_git_bytes(cli: GitHunkCLI, *args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        cwd=cli.repo.path,
        input=input,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def get_object_id(cli: GitHunkCLI, content: bytes) -> str:
    return run_git_bytes(cli, "hash-object", "--stdin", input=content).decode().strip()


def assert_other_entries_unchanged(
    *, before: dict[str, _Entry], after: dict[str, _Entry], changed_path: str
) -> None:
    assert after.keys() == before.keys()
    for path, entry in before.items():
        if path == changed_path:
            continue
        assert after[path] == entry


def assert_only_index_entry_changed(
    *, before: RepositoryState, after: RepositoryState, path: str
) -> None:
    assert after.head_id == before.head_id
    assert after.head == before.head
    assert after.worktree == before.worktree
    assert_other_entries_unchanged(
        before=before.index, after=after.index, changed_path=path
    )


def assert_only_worktree_entry_changed(
    *, before: RepositoryState, after: RepositoryState, path: str
) -> None:
    assert after.head_id == before.head_id
    assert after.head == before.head
    assert after.index == before.index
    assert after.raw_index == before.raw_index
    assert_other_entries_unchanged(
        before=before.worktree, after=after.worktree, changed_path=path
    )


def assert_only_head_entry_changed(
    *, before: RepositoryState, after: RepositoryState, path: str
) -> None:
    assert after.head_id != before.head_id
    assert after.index == after.head
    assert after.worktree == before.worktree
    assert_other_entries_unchanged(
        before=before.head, after=after.head, changed_path=path
    )


def _parse_git_entries(cli: GitHunkCLI, output: bytes) -> dict[str, GitEntry]:
    entries = {}
    for record in output.rstrip(b"\0").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        fields = metadata.decode().split()
        mode = fields[0]
        object_id = fields[2] if fields[1] == "blob" else fields[1]
        path = raw_path.decode()
        content = run_git_bytes(cli, "cat-file", "blob", object_id)
        entries[path] = GitEntry(
            mode=mode,
            object_id=object_id,
            content=content,
        )
    return entries


def _get_worktree_mode(path: Path) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "120000"
    return "100755" if mode & 0o100 else "100644"


def _read_worktree_content(path: Path) -> bytes:
    # git stores a symlink's blob as its target string, so read the link rather
    # than following it: the target need not exist.
    if path.is_symlink():
        return os.readlink(path).encode()
    return path.read_bytes()


def snapshot_repository(cli: GitHunkCLI) -> RepositoryState:
    head_id = run_git_bytes(cli, "rev-parse", "HEAD").decode().strip()
    head = _parse_git_entries(cli, run_git_bytes(cli, "ls-tree", "-r", "-z", "HEAD"))
    raw_index = run_git_bytes(cli, "ls-files", "--stage", "-z")
    index = _parse_git_entries(cli, raw_index)
    root = Path(cli.repo.path)
    worktree = {
        path: WorktreeEntry(
            mode=_get_worktree_mode(root / path),
            content=_read_worktree_content(root / path),
        )
        for path in index
    }
    status = run_git_bytes(cli, "status", "--porcelain=v1", "-z")
    return RepositoryState(
        head_id=head_id,
        head=head,
        index=index,
        worktree=worktree,
        raw_index=raw_index,
        status=status,
    )


def get_hunk_id(cli: GitHunkCLI, *, path: str, staged: bool = False) -> str:
    flags = ["--staged"] if staged else ["--unstaged"]
    hunks = cli.run_list_json("list", *flags, "--json", subdir="sub")
    return next(hunk["id"] for hunk in hunks if hunk["file"]["text"] == path)


def get_target(
    cli: GitHunkCLI, *, path: str, selection: str, staged: bool = False
) -> str:
    if selection == "file":
        return path
    return get_hunk_id(cli, path=path, staged=staged)


def set_hostile_diff_config(cli: GitHunkCLI) -> None:
    # Each of these shifts git's own diff path basis. git-hunk must ignore all
    # three and still report stable Repository paths and Hunk IDs.
    cli.repo.git("config", "diff.relative", "true")
    cli.repo.git("config", "diff.noprefix", "true")
    cli.repo.git("config", "diff.mnemonicprefix", "true")


@pytest.fixture
def inventory_cli(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("same.txt", "root old\n")
    cli.repo.write_file("sub/same.txt", "sub old\n")
    cli.repo.write_file("sibling/change.txt", "sibling old\n")
    cli.repo.write_file(TRACKED_LITERAL_PATH, "literal old\n")
    (Path(cli.repo.path) / "sibling" / "change.bin").write_bytes(b"\x00old\xff")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("same.txt", "root new\n")
    cli.repo.write_file("sub/same.txt", "sub new\n")
    cli.repo.write_file("sibling/change.txt", "sibling new\n")
    cli.repo.write_file(TRACKED_LITERAL_PATH, "literal new\n")
    (Path(cli.repo.path) / "sibling" / "change.bin").write_bytes(b"\x00new\xfe")
    cli.repo.write_file("new.txt", "root untracked\n")
    cli.repo.write_file("sub/new.txt", "sub untracked\n")
    cli.repo.write_file(UNTRACKED_LITERAL_PATH, "literal untracked\n")
    set_hostile_diff_config(cli)
    return cli


@pytest.fixture
def make_mutation_repo(cli: GitHunkCLI) -> MutationRepoFactory:
    def make(path: str, before: bytes, after: bytes) -> GitHunkCLI:
        root = Path(cli.repo.path)
        cli.repo.git("config", "core.autocrlf", "false")
        (root / "sub").mkdir(parents=True, exist_ok=True)
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / "sub" / "keep.txt").write_bytes(b"keep\n")
        (root / path).write_bytes(before)
        (root / "unrelated.txt").write_bytes(b"unrelated old\n")
        cli.repo.git("add", ".")
        cli.repo.git("commit", "-m", "init")

        (root / path).write_bytes(after)
        (root / "unrelated.txt").write_bytes(b"unrelated new\n")
        set_hostile_diff_config(cli)
        return cli

    return make
