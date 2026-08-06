import subprocess
from typing import Final


class GitCommandError(RuntimeError):
    def __init__(self, command: tuple[str, ...], stderr: str) -> None:
        self.stderr = stderr
        super().__init__(f"git {' '.join(command)} failed: {stderr}")


def run_git(*args: str, worktree_root: str | None, input: str | None = None) -> str:
    # worktree_root=None is for bootstrap only: the rev-parse that discovers
    # the root runs in the invocation directory. Every other call anchors there.
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
    args = ["diff", "--no-relative", "--src-prefix=a/", "--dst-prefix=b/", "-U3"]
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


def apply_patch(
    patch: str,
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


# These three are the only calls that hand git a path as a pathspec, so they are
# the only ones that ask for literal ones. Setting it globally would also export
# GIT_LITERAL_PATHSPECS=1 to every child process, which silently changes how a
# commit hook's own pathspecs behave.
_LITERAL_PATHSPECS: Final = "--literal-pathspecs"


def stage_files(files: list[str], *, worktree_root: str) -> None:
    run_git(
        _LITERAL_PATHSPECS,
        "add",
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
