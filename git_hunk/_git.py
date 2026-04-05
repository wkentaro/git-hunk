import subprocess


def is_git_repo() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "true"


def run_git(*args: str, input: str | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        input=input.encode() if input is not None else None,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.decode().strip()}"
        )
    return result.stdout.decode()


def get_diff(staged: bool = False, files: list[str] | None = None) -> str:
    args = ["diff"]
    if staged:
        args.append("--cached")
    args.append("--")
    if files:
        args.extend(files)
    return run_git(*args)


def get_untracked_files() -> list[str]:
    output = run_git("ls-files", "--others", "--exclude-standard")
    return [f for f in output.strip().split("\n") if f]


def apply_patch(patch: str, *, cached: bool = False, reverse: bool = False) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if cached:
        args.append("--cached")
    if reverse:
        args.append("--reverse")
    run_git(*args, input=patch)


def stage_files(files: list[str]) -> None:
    run_git("add", "--", *files)


def unstage_files(files: list[str]) -> None:
    run_git("restore", "--staged", "--", *files)


def discard_files(files: list[str]) -> None:
    run_git("restore", "--", *files)
