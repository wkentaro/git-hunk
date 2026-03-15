"""Hunk dataclass and diff parsing."""

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Hunk:
    id: str
    file: str
    index: int
    header: str
    additions: int
    deletions: int
    context_before: str
    diff: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "index": self.index,
            "header": self.header,
            "additions": self.additions,
            "deletions": self.deletions,
            "context_before": self.context_before,
            "diff": self.diff,
        }


def _make_id(filepath: str, diff_content: str) -> str:
    return hashlib.sha256(f"{filepath}:{diff_content}".encode()).hexdigest()[:7]


def _count_changes(lines: List[str]) -> tuple:
    additions = sum(1 for l in lines if l.startswith("+"))
    deletions = sum(1 for l in lines if l.startswith("-"))
    return additions, deletions


def _extract_context_before(header: str) -> str:
    """Extract the function/class context from the @@ header."""
    match = re.search(r"@@.*@@\s*(.*)", header)
    return match.group(1).strip() if match and match.group(1).strip() else ""


def parse_diff(diff_output: str) -> List[Hunk]:
    """Parse git diff output into a list of Hunk objects."""
    if not diff_output.strip():
        return []

    hunks = []
    # Split into per-file diffs
    file_diffs = re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)

    for file_diff in file_diffs:
        if not file_diff.strip():
            continue

        # Extract filename
        m = re.match(r"diff --git a/(.*?) b/(.*)", file_diff)
        if not m:
            continue
        filepath = m.group(2)

        # Split into header and hunks on @@ lines
        parts = re.split(r"(?=^@@)", file_diff, flags=re.MULTILINE)
        file_header = parts[0]

        for idx, part in enumerate(parts[1:]):
            lines = part.split("\n")
            header_line = lines[0]
            # The hunk body is everything after the @@ line
            body_lines = [l for l in lines[1:] if l != "\\ No newline at end of file"]

            # Remove trailing empty string from split
            while body_lines and body_lines[-1] == "":
                body_lines.pop()

            hunk_diff = header_line + "\n" + "\n".join(body_lines)
            additions, deletions = _count_changes(body_lines)
            context_before = _extract_context_before(header_line)

            hunk = Hunk(
                id=_make_id(filepath, hunk_diff),
                file=filepath,
                index=idx,
                header=header_line,
                additions=additions,
                deletions=deletions,
                context_before=context_before,
                diff=hunk_diff,
            )
            hunks.append(hunk)

    return hunks
