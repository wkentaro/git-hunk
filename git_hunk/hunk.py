import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import replace
from typing import Any
from typing import TypedDict


@dataclass(frozen=True)
class Hunk:
    id: str
    file: str
    header: str
    additions: int
    deletions: int
    context_before: str
    diff: str
    status: str = "unstaged"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "status": self.status,
            "header": self.header,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff": self.diff,
        }


def count_changes(lines: list[str]) -> tuple[int, int]:
    additions = sum(1 for line in lines if line.startswith("+"))
    deletions = sum(1 for line in lines if line.startswith("-"))
    return additions, deletions


def _body_id(filepath: str, diff_content: str) -> str:
    """Stable across partial staging: ignores @@ headers that shift."""
    body = "\n".join(
        line for line in diff_content.split("\n") if not line.startswith("@@")
    )
    return hashlib.sha256(f"{filepath}:{body}".encode()).hexdigest()[:7]


def _full_id(filepath: str, diff_content: str) -> str:
    """Fallback for identical changed lines — includes @@ line numbers."""
    return hashlib.sha256(f"{filepath}:{diff_content}".encode()).hexdigest()[:7]


def _with_stable_ids(hunks: list[Hunk]) -> list[Hunk]:
    # Pass 1: body-only IDs (stable across staging).
    # Pass 2: for colliding IDs, upgrade to full IDs to disambiguate.
    with_body_ids = [replace(h, id=_body_id(h.file, h.diff)) for h in hunks]

    counts = Counter(h.id for h in with_body_ids)
    return [
        replace(h, id=_full_id(h.file, h.diff)) if counts[h.id] > 1 else h
        for h in with_body_ids
    ]


class _SubHunk(TypedDict):
    header: str
    body_lines: list[str]


_CONTEXT_LINES = 3


def _is_change(line: str) -> bool:
    return line.startswith("+") or line.startswith("-")


def _find_change_regions(body_lines: list[str]) -> list[tuple[int, int]]:
    regions = []
    i = 0
    while i < len(body_lines):
        if _is_change(body_lines[i]):
            start = i
            while i < len(body_lines) and _is_change(body_lines[i]):
                i += 1
            regions.append((start, i - 1))
        else:
            i += 1
    return regions


def _find_split_points(regions: list[tuple[int, int]]) -> list[int]:
    MIN_GAP = 2 * _CONTEXT_LINES + 1
    return [
        r
        for r in range(1, len(regions))
        if regions[r][0] - regions[r - 1][1] - 1 >= MIN_GAP
    ]


def _advance_offsets(
    body_lines: list[str], start: int, end: int, old: int, new: int
) -> tuple[int, int]:
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


def _build_sub_hunks(
    header_line: str,
    body_lines: list[str],
    regions: list[tuple[int, int]],
    split_points: list[int],
) -> list[_SubHunk]:
    m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", header_line)
    if not m:
        return [_SubHunk(header=header_line, body_lines=body_lines)]

    old_start = int(m.group(1))
    new_start = int(m.group(2))
    tail = m.group(3)

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

        body_start = max(0, first_region[0] - _CONTEXT_LINES)
        body_end = min(len(body_lines), last_region[1] + _CONTEXT_LINES + 1)

        running_old, running_new = _advance_offsets(
            body_lines, prev_body_end, body_start, running_old, running_new
        )

        sub_body = body_lines[body_start:body_end]
        additions, deletions = count_changes(sub_body)
        ctx = sum(1 for line in sub_body if not _is_change(line))
        old_count = ctx + deletions
        new_count = ctx + additions

        sub_header = (
            f"@@ -{running_old},{old_count} +{running_new},{new_count} @@{tail}"
        )
        sub_hunks.append(_SubHunk(header=sub_header, body_lines=sub_body))

        running_old, running_new = _advance_offsets(
            body_lines, body_start, body_end, running_old, running_new
        )
        prev_body_end = body_end

    return sub_hunks


def _split_hunk(
    filepath: str,
    header_line: str,
    body_lines: list[str],
) -> list[_SubHunk]:
    regions = _find_change_regions(body_lines)
    if len(regions) <= 1:
        return [_SubHunk(header=header_line, body_lines=body_lines)]

    split_points = _find_split_points(regions)
    if not split_points:
        return [_SubHunk(header=header_line, body_lines=body_lines)]

    return _build_sub_hunks(header_line, body_lines, regions, split_points)


def _extract_context_before(header: str) -> str:
    match = re.search(r"@@.*@@\s*(.*)", header)
    return match.group(1).strip() if match and match.group(1).strip() else ""


def parse_diff(diff_output: str) -> list[Hunk]:
    if not diff_output.strip():
        return []

    hunks = []
    file_diffs = re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)

    for file_diff in file_diffs:
        if not file_diff.strip():
            continue

        m = re.match(r"diff --git a/(.*?) b/(.*)", file_diff)
        if not m:
            continue
        filepath = m.group(2)

        if re.search(r"^Binary files .* differ$", file_diff, flags=re.MULTILINE):
            hunks.append(
                Hunk(
                    id="",
                    file=filepath,
                    header="Binary file",
                    additions=0,
                    deletions=0,
                    context_before="",
                    diff="",
                )
            )
            continue

        parts = re.split(r"(?=^@@)", file_diff, flags=re.MULTILINE)

        for part in parts[1:]:
            lines = part.split("\n")
            header_line = lines[0]
            body_lines = [
                line for line in lines[1:] if line != "\\ No newline at end of file"
            ]

            while body_lines and body_lines[-1] == "":
                body_lines = body_lines[:-1]

            for sub in _split_hunk(filepath, header_line, body_lines):
                sub_body = sub["body_lines"]
                sub_header = sub["header"]
                hunk_diff = sub_header + "\n" + "\n".join(sub_body)
                additions, deletions = count_changes(sub_body)

                hunk = Hunk(
                    id="",
                    file=filepath,
                    header=sub_header,
                    additions=additions,
                    deletions=deletions,
                    context_before=_extract_context_before(sub_header),
                    diff=hunk_diff,
                )
                hunks.append(hunk)

    return _with_stable_ids(hunks)
