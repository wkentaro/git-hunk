import re

from ._hunk import Hunk
from ._hunk import extract_file_path
from ._hunk import split_file_diffs


def _extract_file_headers(diff_output: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for file_diff in split_file_diffs(diff_output):
        filepath = extract_file_path(file_diff)
        if filepath is None:
            continue
        headers[filepath] = re.split(
            r"(?=^@@)", file_diff, maxsplit=1, flags=re.MULTILINE
        )[0]
    return headers


def build_patch(hunks: list[Hunk], diff_output: str) -> str:
    files: dict[str, list[Hunk]] = {}
    for hunk in hunks:
        files.setdefault(hunk.file, []).append(hunk)

    headers = _extract_file_headers(diff_output)

    patches = []
    for filepath, file_hunks in files.items():
        if filepath not in headers:
            raise ValueError(f"File header not found for {filepath}")
        hunk_diffs = "\n".join(h.diff for h in file_hunks)
        patches.append(headers[filepath] + hunk_diffs + "\n")

    return "".join(patches)
