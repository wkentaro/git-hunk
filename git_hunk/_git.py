import subprocess
from dataclasses import dataclass
from typing import Final


class GitCommandError(RuntimeError):
    stderr: str

    def __init__(self, command: tuple[str, ...], stderr: str, /) -> None:
        self.stderr = stderr
        super().__init__(f"git {' '.join(command)} failed: {stderr}")


@dataclass(frozen=True)
class UnsupportedChange:
    kind: str
    source: str
    destination: str


def run_git(*args: str, worktree_root: str | None, input: str | None = None) -> str:
    # A missing root is only for the bootstrap query that discovers both
    # repository coordinates. Every later call anchors there.
    # Git output and input may contain bytes that are not valid UTF-8 (e.g. a
    # Latin-1 source file). surrogateescape round-trips those bytes losslessly
    # so a rebuilt patch hands git back exactly what it emitted.
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false"] + list(args),
            capture_output=True,
            cwd=worktree_root,
            input=input.encode(errors="surrogateescape") if input is not None else None,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found on PATH") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="surrogateescape").strip()
        raise GitCommandError(args, stderr)
    return result.stdout.decode(errors="surrogateescape")


def get_diff(*, worktree_root: str, staged: bool) -> str:
    # Pin -U3 (git's default) explicitly: parse_diff treats each @@ section as
    # one hunk, which only holds at 3 lines of context, so don't leave the
    # boundaries to git's default in case it is ever overridden.
    # --src-prefix/--dst-prefix override diff.noprefix and diff.mnemonicPrefix
    # the same way --default-prefix does, but predate it, so the supported git
    # floor stays at --no-relative's 2.28 instead of --default-prefix's 2.41.
    # --no-color: a color.diff or color.ui set to always emits ANSI escapes
    # even into a pipe, and the parse would find nothing.
    # Display drivers can replace source patches with transformed or empty
    # output, while inventory and mutation need the canonical source bytes.
    args = [
        "diff",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        # Copies are additions; the separate rename guard rejects two-path changes.
        "--no-renames",
        "--no-relative",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--full-index",
        "-U3",
    ]
    if staged:
        args.append("--cached")
    return run_git(*args, worktree_root=worktree_root)


def get_worktree_context() -> tuple[str, str]:
    # Ask Git for this coordinate because Windows can give Git and Python
    # different spellings for the same directory.
    output = run_git(
        "rev-parse", "--show-toplevel", "--show-prefix", worktree_root=None
    )
    worktree_root, invocation_prefix = output.removesuffix("\n").split("\n", 1)
    return worktree_root, invocation_prefix.removesuffix("/")


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
        "-l0",
        "--diff-filter=R",
    ]
    if staged:
        args.append("--cached")
    output = run_git(*args, worktree_root=worktree_root)
    fields = output.removesuffix("\0").split("\0") if output else []
    if len(fields) % 3 != 0:
        raise RuntimeError("cannot parse git rename status")
    return [
        UnsupportedChange(
            kind="rename",
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
    /,
    *,
    worktree_root: str,
    cached: bool,
    reverse: bool,
    dry_run: bool,
) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if cached:
        args.append("--cached")
    if reverse:
        args.append("--reverse")
    if dry_run:
        args.append("--check")
    run_git(*args, worktree_root=worktree_root, input=patch)


# These file-level commands hand git paths as pathspecs, so they ask for literal
# ones. Setting this globally would also change how a commit hook interprets its
# own pathspecs.
_LITERAL_PATHSPECS: Final = "--literal-pathspecs"


def stage_files(files: list[str], /, *, worktree_root: str, dry_run: bool) -> None:
    args = [_LITERAL_PATHSPECS, "add"]
    if dry_run:
        args.append("--dry-run")
    run_git(
        *args,
        "--",
        *files,
        worktree_root=worktree_root,
    )


def get_index_conflicts(files: list[str], /, *, worktree_root: str) -> list[str]:
    # Index entries that block adding these paths: one below a path (it is a
    # tracked directory) or one at a parent directory (it is a tracked file).
    # A literal pathspec matches both the entry itself and entries below it.
    parents = {f[:i] for f in files for i, char in enumerate(f) if char == "/"}
    output = run_git(
        _LITERAL_PATHSPECS,
        "ls-files",
        "-z",
        "--",
        *files,
        *sorted(parents),
        worktree_root=worktree_root,
    )
    return [
        entry
        for entry in output.split("\0")
        if entry and (entry in parents or any(entry.startswith(f"{f}/") for f in files))
    ]


def add_untracked_files(files: list[str], /, *, worktree_root: str) -> None:
    # Unlike git add, update-index refuses a path that would replace a tracked
    # directory instead of also staging that directory's deletion.
    run_git("update-index", "--add", "--", *files, worktree_root=worktree_root)


def unstage_added_files(
    files: list[str], /, *, worktree_root: str, dry_run: bool
) -> None:
    args = [_LITERAL_PATHSPECS, "rm", "--cached", "--force"]
    if dry_run:
        args.append("--dry-run")
    run_git(
        *args,
        "--",
        *files,
        worktree_root=worktree_root,
    )


def unstage_files(files: list[str], /, *, worktree_root: str) -> None:
    run_git(
        _LITERAL_PATHSPECS,
        "restore",
        "--staged",
        "--",
        *files,
        worktree_root=worktree_root,
    )


def discard_files(files: list[str], /, *, worktree_root: str) -> None:
    run_git(
        _LITERAL_PATHSPECS,
        "restore",
        "--",
        *files,
        worktree_root=worktree_root,
    )


def commit(
    message: str, /, *, amend: bool, fixup: str | None, worktree_root: str
) -> None:
    args = ["commit"]
    if amend:
        args.append("--amend")
    if fixup is not None:
        args.append(f"--fixup={fixup}")
    if message:
        # Pass the message on stdin, not as -m: a failure reports the command
        # line, and a hook rejection would otherwise repeat the whole message.
        run_git(*args, "--file=-", worktree_root=worktree_root, input=message)
    else:
        # --no-edit keeps the existing or generated message, and stops git from
        # opening an editor that nobody can answer.
        run_git(*args, "--no-edit", worktree_root=worktree_root)


def get_head_subject(*, worktree_root: str) -> str:
    return run_git("log", "-1", "--format=%s", worktree_root=worktree_root).strip()
