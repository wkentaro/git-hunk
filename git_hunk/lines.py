"""Line-level filtering for partial hunk staging."""

import re
from dataclasses import replace
from typing import Set
from typing import Tuple

from .hunk import Hunk
from .hunk import count_changes


def parse_line_spec(spec: str) -> Tuple[Set[int], bool]:
    """Parse "-l" value into (line_numbers, exclude_mode).

    "3,5-7"   -> ({3, 5, 6, 7}, False)
    "^3,^5-7" -> ({3, 5, 6, 7}, True)
    """
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ValueError("empty line specification")

    has_include = any(not p.startswith("^") for p in parts)
    has_exclude = any(p.startswith("^") for p in parts)
    if has_include and has_exclude:
        raise ValueError("cannot mix include and exclude (^) in the same -l spec")

    exclude = has_exclude
    lines: Set[int] = set()

    for part in parts:
        raw = part.lstrip("^")
        if "-" in raw:
            lo_s, hi_s = raw.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            if lo < 1 or hi < 1:
                raise ValueError(f"line numbers must be positive: {part}")
            if lo > hi:
                raise ValueError(f"invalid range (start > end): {part}")
            lines.update(range(lo, hi + 1))
        else:
            n = int(raw)
            if n < 1:
                raise ValueError(f"line numbers must be positive: {part}")
            lines.add(n)

    return lines, exclude


def _filter_body_lines(
    body: list,
    selected: Set[int],
) -> list:
    new_body = []
    for i, line in enumerate(body, start=1):
        if i in selected:
            new_body.append(line)
        elif line.startswith("+"):
            continue
        elif line.startswith("-"):
            new_body.append(" " + line[1:])
        else:
            new_body.append(line)
    return new_body


def filter_hunk_lines(hunk: Hunk, lines: Set[int], *, exclude: bool) -> Hunk:
    """Return a new Hunk with only the selected lines as changes.

    Unselected '+' lines are removed; unselected '-' lines become context.
    This matches git add -p edit mode semantics.
    """
    diff_lines = hunk.diff.split("\n")
    header = diff_lines[0]
    body = diff_lines[1:]

    while body and body[-1] == "":
        body.pop()

    total = len(body)

    out_of_range = {n for n in lines if n < 1 or n > total}
    if out_of_range:
        bad = ", ".join(str(n) for n in sorted(out_of_range))
        raise ValueError(f"line numbers out of range (hunk has {total} lines): {bad}")

    if exclude:
        selected = {i for i in range(1, total + 1) if i not in lines}
    else:
        selected = lines

    new_body = _filter_body_lines(body, selected)

    additions, deletions = count_changes(new_body)
    if additions == 0 and deletions == 0:
        raise ValueError("no changes remain after line filtering")

    context_count = len(new_body) - additions - deletions
    old_count = context_count + deletions
    new_count = context_count + additions

    m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", header)
    if not m:
        raise ValueError(f"cannot parse hunk header: {header}")

    new_header = (
        f"@@ -{m.group(1)},{old_count} +{m.group(2)},{new_count} @@{m.group(3)}"
    )
    new_diff = new_header + "\n" + "\n".join(new_body)

    return replace(
        hunk,
        diff=new_diff,
        header=new_header,
        additions=additions,
        deletions=deletions,
    )
