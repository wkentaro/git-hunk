import re

from ._hunk import Hunk
from ._hunk import extract_file_path


def _get_file_header(diff_output: str, filepath: str) -> str:
    file_diffs = re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)
    for file_diff in file_diffs:
        if extract_file_path(file_diff) == filepath:
            # Return everything up to the first @@ line
            parts = re.split(r"(?=^@@)", file_diff, flags=re.MULTILINE)
            return parts[0]
    raise ValueError(f"File header not found for {filepath}")


def build_patch(hunks: list[Hunk], diff_output: str) -> str:
    files = {}
    for hunk in hunks:
        files.setdefault(hunk.file, []).append(hunk)

    patches = []
    for filepath, file_hunks in files.items():
        header = _get_file_header(diff_output, filepath)
        hunk_diffs = "\n".join(h.diff for h in file_hunks)
        patches.append(header + hunk_diffs + "\n")

    return "".join(patches)
