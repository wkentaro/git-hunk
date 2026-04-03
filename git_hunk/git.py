"""Git subprocess helpers."""

import subprocess


def run_git(*args: str, input: str | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        text=True,
        input=input,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def get_diff(staged: bool = False, files: list[str] | None = None) -> str:
    args = ["diff"]
    if staged:
        args.append("--cached")
    args.append("--")
    if files:
        args.extend(files)
    return run_git(*args)


def apply_patch(patch: str, *, cached: bool = False, reverse: bool = False) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if cached:
        args.append("--cached")
    if reverse:
        args.append("--reverse")
    run_git(*args, input=patch)
