"""Reconstruct patches from hunks."""

import re

from .hunk import Hunk


def _get_file_header(diff_output: str, filepath: str) -> str:
    """Extract the file-level diff header for a given file."""
    file_diffs = re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)
    for file_diff in file_diffs:
        m = re.match(r"diff --git a/(.*?) b/(.*)", file_diff)
        if m and m.group(2) == filepath:
            # Return everything up to the first @@ line
            parts = re.split(r"(?=^@@)", file_diff, flags=re.MULTILINE)
            return parts[0]
    raise ValueError(f"File header not found for {filepath}")


def build_patch(hunks: list[Hunk], diff_output: str) -> str:
    """Build a patch from selected hunks, grouped by file."""
    # Group hunks by file, preserving order
    files = {}
    for hunk in hunks:
        files.setdefault(hunk.file, []).append(hunk)

    patches = []
    for filepath, file_hunks in files.items():
        header = _get_file_header(diff_output, filepath)
        hunk_diffs = "\n".join(h.diff for h in file_hunks)
        patches.append(header + hunk_diffs + "\n")

    return "".join(patches)
