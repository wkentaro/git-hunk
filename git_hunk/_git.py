import subprocess


def is_git_repo() -> bool:
    return run_git("rev-parse", "--is-inside-work-tree", check=False).strip() == "true"


def run_git(*args: str, input: str | None = None, check: bool = True) -> str:
    # Git output and input may contain bytes that are not valid UTF-8 (e.g. a
    # Latin-1 source file). surrogateescape round-trips those bytes losslessly
    # so a rebuilt patch hands git back exactly what it emitted.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false"] + list(args),
        capture_output=True,
        input=input.encode(errors="surrogateescape") if input is not None else None,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode(errors="surrogateescape").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout.decode(errors="surrogateescape")


def get_diff(staged: bool = False, files: list[str] | None = None) -> str:
    # Pin -U3 (git's default) explicitly: parse_diff treats each @@ section as
    # one hunk, which only holds at 3 lines of context, so don't leave the
    # boundaries to git's default in case it is ever overridden.
    args = ["diff", "-U3"]
    if staged:
        args.append("--cached")
    args.append("--")
    if files:
        args.extend(files)
    return run_git(*args)


def get_repo_root() -> str:
    return run_git("rev-parse", "--show-toplevel").strip()


def get_untracked_files(files: list[str] | None = None) -> list[str]:
    # --full-name yields repo-root-relative paths, matching get_diff's basis, so
    # untracked and tracked hunks report `file` consistently from a subdirectory.
    # files is a pathspec git resolves relative to cwd, exactly as get_diff does.
    args = ["ls-files", "--others", "--exclude-standard", "--full-name", "-z", "--"]
    if files:
        args.extend(files)
    output = run_git(*args)
    return [f for f in output.split("\0") if f]


def apply_patch(
    patch: str,
    *,
    cached: bool = False,
    reverse: bool = False,
    dry_run: bool = False,
) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if cached:
        args.append("--cached")
    if reverse:
        args.append("--reverse")
    if dry_run:
        args.append("--check")
    run_git(*args, input=patch)


def stage_files(files: list[str]) -> None:
    run_git("add", "--", *files)


def unstage_files(files: list[str]) -> None:
    run_git("restore", "--staged", "--", *files)


def discard_files(files: list[str]) -> None:
    run_git("restore", "--", *files)


def commit(message: str) -> None:
    run_git("commit", "-m", message)
