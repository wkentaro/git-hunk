import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final


class GitCommandError(RuntimeError):
    def __init__(self, command: tuple[str, ...], stderr: str) -> None:
        self.stderr = stderr
        super().__init__(f"git {' '.join(command)} failed: {stderr}")


@dataclass(frozen=True)
class UnsupportedChange:
    kind: str
    source: str
    destination: str


def run_git_bytes(
    *args: str,
    worktree_root: str | None,
    input: bytes | None = None,
    env: Mapping[str, str] | None = None,
) -> bytes:
    # worktree_root=None is for bootstrap only: the rev-parse that discovers
    # the root runs in the invocation directory. Every other call anchors there.
    # env holds overrides layered onto the ambient environment (e.g. the
    # GIT_INDEX_FILE that points a command at a scratch index), never a
    # replacement for it: git still needs PATH, HOME, and the caller's config.
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false"] + list(args),
            capture_output=True,
            cwd=worktree_root,
            input=input,
            env={**os.environ, **env} if env is not None else None,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found on PATH") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="surrogateescape").strip()
        raise GitCommandError(args, stderr)
    return result.stdout


def run_git(
    *args: str,
    worktree_root: str | None,
    input: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    # Git output and input may contain bytes that are not valid UTF-8 (e.g. a
    # Latin-1 source file). surrogateescape round-trips those bytes losslessly
    # so a rebuilt patch hands git back exactly what it emitted.
    stdout = run_git_bytes(
        *args,
        worktree_root=worktree_root,
        input=input.encode(errors="surrogateescape") if input is not None else None,
        env=env,
    )
    return stdout.decode(errors="surrogateescape")


def get_diff(*, worktree_root: str, staged: bool) -> str:
    # Pin -U3 (git's default) explicitly: parse_diff treats each @@ section as
    # one hunk, which only holds at 3 lines of context, so don't leave the
    # boundaries to git's default in case it is ever overridden.
    # --src-prefix/--dst-prefix override diff.noprefix and diff.mnemonicPrefix
    # the same way --default-prefix does, but predate it, so the supported git
    # floor stays at --no-relative's 2.28 instead of --default-prefix's 2.41.
    args = [
        "diff",
        "--no-relative",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--full-index",
        "-U3",
    ]
    if staged:
        args.append("--cached")
    return run_git(*args, worktree_root=worktree_root)


def get_worktree_root() -> str:
    output = run_git("rev-parse", "--show-toplevel", worktree_root=None)
    return output.removesuffix("\n")


def get_untracked_files(*, worktree_root: str) -> list[str]:
    # --full-name yields Repository paths, matching get_diff's basis, so
    # untracked and tracked Hunks use one coordinate system.
    output = run_git(
        "ls-files",
        "--others",
        "--exclude-standard",
        "--full-name",
        "-z",
        worktree_root=worktree_root,
    )
    return [f for f in output.split("\0") if f]


def get_unsupported_changes(
    *, worktree_root: str, staged: bool
) -> list[UnsupportedChange]:
    args = [
        "diff",
        "--no-relative",
        "--name-status",
        "-z",
        "--find-renames=50%",
        "--find-copies=50%",
        "--find-copies-harder",
        "-l0",
        "--diff-filter=RC",
    ]
    if staged:
        args.append("--cached")
    output = run_git(*args, worktree_root=worktree_root)
    fields = output.removesuffix("\0").split("\0") if output else []
    if len(fields) % 3 != 0:
        raise RuntimeError("cannot parse git rename/copy status")
    return [
        UnsupportedChange(
            kind="rename" if fields[i].startswith("R") else "copy",
            source=fields[i + 1],
            destination=fields[i + 2],
        )
        for i in range(0, len(fields), 3)
    ]


def get_unmerged_files(*, worktree_root: str) -> list[str]:
    output = run_git(
        "ls-files",
        "--unmerged",
        "--full-name",
        "-z",
        worktree_root=worktree_root,
    )
    paths: list[str] = []
    seen: set[str] = set()
    for record in output.split("\0"):
        if not record:
            continue
        _, separator, path = record.partition("\t")
        if not separator:
            raise RuntimeError("cannot parse git unmerged index")
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def apply_patch(
    patch: str,
    *,
    worktree_root: str,
    cached: bool,
    reverse: bool,
    dry_run: bool,
    env: Mapping[str, str] | None = None,
) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if cached:
        args.append("--cached")
    if reverse:
        args.append("--reverse")
    if dry_run:
        args.append("--check")
    run_git(*args, worktree_root=worktree_root, input=patch, env=env)


@contextlib.contextmanager
def scratch_index(*, worktree_root: str) -> Iterator[Mapping[str, str]]:
    """Yield an env overlay aiming git at a throwaway copy of the index.

    Commands run with the overlay read the current index content but write only
    to the copy, so the real index and working tree are never touched. Objects
    they create still land in the repository's object database, unreferenced
    until `git gc` reclaims them.
    """
    index_path = os.path.join(
        worktree_root,
        run_git(
            "rev-parse", "--git-path", "index", worktree_root=worktree_root
        ).removesuffix("\n"),
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch_path = os.path.join(tmpdir, "index")
        # A repository whose index has never been written has no index file
        # yet; leaving the copy absent gives git the same empty starting point.
        # Tolerate a concurrent writer replacing it between the two calls.
        try:
            shutil.copyfile(index_path, scratch_path)
        except FileNotFoundError:
            pass
        yield {"GIT_INDEX_FILE": scratch_path}


# The commands below hand git a path as a pathspec, so they ask for a literal
# one. Setting this globally would also change how a commit hook interprets its
# own pathspecs.
_LITERAL_PATHSPECS: Final = "--literal-pathspecs"


def read_index_blob(
    path: str, *, worktree_root: str, env: Mapping[str, str] | None = None
) -> bytes | None:
    """Return the bytes an index entry holds, or None when it has no entry.

    Reads the blob through ls-files rather than a `:<path>` revision so the
    Repository path stays a literal pathspec instead of gaining `git show`'s
    cwd-relative quirks.
    """
    output = run_git(
        _LITERAL_PATHSPECS,
        "ls-files",
        "--stage",
        "--full-name",
        "-z",
        "--",
        path,
        worktree_root=worktree_root,
        env=env,
    )
    records = [record for record in output.split("\0") if record]
    if not records:
        return None
    # One path yields several records only when it is unmerged, and then no
    # single record is "the" content; refuse rather than return a merge stage.
    if len(records) != 1:
        raise RuntimeError(f"unmerged index entry for '{path}'")
    metadata, separator, _ = records[0].partition("\t")
    fields = metadata.split(" ")
    if not separator or len(fields) != 3:
        raise RuntimeError("cannot parse git index entry")
    mode, object_id, _ = fields
    # A gitlink entry points at a commit, not a blob (see _hunk.is_submodule_hunk).
    if mode == "160000":
        raise RuntimeError(f"'{path}' is a submodule, not a file")
    return run_git_bytes(
        "cat-file", "blob", object_id, worktree_root=worktree_root, env=env
    )


def stage_files(files: list[str], *, worktree_root: str, dry_run: bool) -> None:
    args = [_LITERAL_PATHSPECS, "add"]
    if dry_run:
        args.append("--dry-run")
    run_git(
        *args,
        "--",
        *files,
        worktree_root=worktree_root,
    )


def unstage_added_files(files: list[str], *, worktree_root: str, dry_run: bool) -> None:
    args = [_LITERAL_PATHSPECS, "rm", "--cached", "--force"]
    if dry_run:
        args.append("--dry-run")
    run_git(
        *args,
        "--",
        *files,
        worktree_root=worktree_root,
    )


def unstage_files(files: list[str], *, worktree_root: str) -> None:
    run_git(
        _LITERAL_PATHSPECS,
        "restore",
        "--staged",
        "--",
        *files,
        worktree_root=worktree_root,
    )


def discard_files(files: list[str], *, worktree_root: str) -> None:
    run_git(
        _LITERAL_PATHSPECS,
        "restore",
        "--",
        *files,
        worktree_root=worktree_root,
    )


def commit(message: str, *, worktree_root: str) -> None:
    run_git("commit", "-m", message, worktree_root=worktree_root)
