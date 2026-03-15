"""Hunk dataclass and diff parsing."""

import hashlib
import re
from collections import Counter
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


def _body_id(filepath: str, diff_content: str) -> str:
    """Hash based on changed lines only, excluding the @@ header.

    This makes IDs stable across partial staging: when hunk N is staged,
    the @@ line numbers of subsequent hunks shift, but their actual changed
    lines don't — so their IDs remain valid for the next operation.
    """
    body = "\n".join(
        line for line in diff_content.split("\n") if not line.startswith("@@")
    )
    return hashlib.sha256(f"{filepath}:{body}".encode()).hexdigest()[:7]


def _full_id(filepath: str, diff_content: str) -> str:
    """Hash including the @@ header (line numbers).

    Used only as a fallback to disambiguate two hunks whose changed lines
    are byte-for-byte identical (e.g. repeated identical edits in a file).
    In that edge case IDs will change when line numbers shift, but there is
    no stable alternative — the hunks are genuinely indistinguishable by
    content alone.
    """
    return hashlib.sha256(f"{filepath}:{diff_content}".encode()).hexdigest()[:7]


def _assign_ids(hunks: List[Hunk]) -> None:
    """Assign stable IDs to hunks in-place using a two-pass strategy.

    Pass 1: assign body-only IDs (stable across staging).
    Pass 2: for any colliding IDs (identical changed lines in the same parse),
            upgrade to full IDs (includes @@ line numbers) to disambiguate.
    """
    # Pass 1: body-only IDs
    for hunk in hunks:
        hunk.id = _body_id(hunk.file, hunk.diff)

    # Pass 2: resolve collisions
    counts = Counter(hunk.id for hunk in hunks)
    for hunk in hunks:
        if counts[hunk.id] > 1:
            hunk.id = _full_id(hunk.file, hunk.diff)


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
                id="",  # assigned below after all hunks are collected
                file=filepath,
                index=idx,
                header=header_line,
                additions=additions,
                deletions=deletions,
                context_before=context_before,
                diff=hunk_diff,
            )
            hunks.append(hunk)

    _assign_ids(hunks)
    return hunks
