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


def _is_change(line: str) -> bool:
    return line.startswith("+") or line.startswith("-")


def _advance_offsets(
    body_lines: List[str], start: int, end: int, old: int, new: int
) -> tuple:
    """Walk diff body lines and return updated (old_offset, new_offset)."""
    for j in range(start, end):
        line = body_lines[j]
        if line.startswith("+"):
            new += 1
        elif line.startswith("-"):
            old += 1
        else:
            old += 1
            new += 1
    return old, new


def _split_hunk(
    filepath: str, header_line: str, body_lines: List[str], context: int = 3
) -> List[dict]:
    """Split a single hunk into sub-hunks where change regions are separated
    by more than 2*context lines of pure context.

    Returns a list of dicts with keys: header, body_lines.
    If the hunk cannot be split further, returns a single-element list.
    """
    # Find change regions: contiguous runs of +/- lines
    regions = []  # list of (first_change_idx, last_change_idx)
    i = 0
    while i < len(body_lines):
        if _is_change(body_lines[i]):
            start = i
            while i < len(body_lines) and _is_change(body_lines[i]):
                i += 1
            regions.append((start, i - 1))
        else:
            i += 1

    if len(regions) <= 1:
        return [{"header": header_line, "body_lines": body_lines}]

    # Find split points: gaps between regions with > 2*context context lines
    min_gap = 2 * context + 1  # need at least this many context lines to split
    split_points = []  # indices into regions where we split *before* that region
    for r in range(1, len(regions)):
        gap = regions[r][0] - regions[r - 1][1] - 1
        if gap >= min_gap:
            split_points.append(r)

    if not split_points:
        return [{"header": header_line, "body_lines": body_lines}]

    # Parse old_start and new_start from header
    m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", header_line)
    if not m:
        return [{"header": header_line, "body_lines": body_lines}]

    old_start = int(m.group(1))
    new_start = int(m.group(2))
    tail = m.group(3)

    # Build region groups
    groups = []
    prev = 0
    for sp in split_points:
        groups.append((prev, sp))
        prev = sp
    groups.append((prev, len(regions)))

    sub_hunks = []
    prev_body_end = 0
    running_old = old_start
    running_new = new_start
    for g_start, g_end in groups:
        first_region = regions[g_start]
        last_region = regions[g_end - 1]

        body_start = max(0, first_region[0] - context)
        body_end = min(len(body_lines), last_region[1] + context + 1)

        running_old, running_new = _advance_offsets(
            body_lines, prev_body_end, body_start, running_old, running_new
        )

        sub_body = body_lines[body_start:body_end]
        additions, deletions = _count_changes(sub_body)
        ctx = sum(1 for line in sub_body if not _is_change(line))
        old_count = ctx + deletions
        new_count = ctx + additions

        sub_header = f"@@ -{running_old},{old_count} +{running_new},{new_count} @@{tail}"
        sub_hunks.append({"header": sub_header, "body_lines": sub_body})

        running_old, running_new = _advance_offsets(
            body_lines, body_start, body_end, running_old, running_new
        )
        prev_body_end = body_end

    return sub_hunks


def parse_diff(diff_output: str) -> List[Hunk]:
    """Parse git diff output into a list of Hunk objects.

    Hunks with multiple change regions separated by enough context lines
    are automatically split into smaller, more focused sub-hunks.
    """
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

        hunk_idx = 0
        for part in parts[1:]:
            lines = part.split("\n")
            header_line = lines[0]
            body_lines = [l for l in lines[1:] if l != "\\ No newline at end of file"]

            while body_lines and body_lines[-1] == "":
                body_lines.pop()

            for sub in _split_hunk(filepath, header_line, body_lines):
                sub_body = sub["body_lines"]
                sub_header = sub["header"]
                hunk_diff = sub_header + "\n" + "\n".join(sub_body)
                additions, deletions = _count_changes(sub_body)
                context_before = _extract_context_before(sub_header)

                hunk = Hunk(
                    id="",
                    file=filepath,
                    index=hunk_idx,
                    header=sub_header,
                    additions=additions,
                    deletions=deletions,
                    context_before=context_before,
                    diff=hunk_diff,
                )
                hunks.append(hunk)
                hunk_idx += 1

    _assign_ids(hunks)
    return hunks
