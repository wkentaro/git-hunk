"""Line-level filtering for partial hunk staging."""

import re
from dataclasses import replace
from typing import Set, Tuple

from .hunk import Hunk


def parse_line_spec(spec: str) -> Tuple[Set[int], bool]:
    """Parse a line specification string into a set of line numbers and mode.

    Returns (line_numbers, exclude) where exclude=True means "all EXCEPT these".

    Examples:
        "3,5-7"   -> ({3, 5, 6, 7}, False)  — include mode
        "^3,^5-7" -> ({3, 5, 6, 7}, True)   — exclude mode
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


def filter_hunk_lines(hunk: Hunk, lines: Set[int], exclude: bool) -> Hunk:
    """Return a new Hunk with only the selected lines as changes.

    Unselected '+' lines are removed; unselected '-' lines become context.
    This matches git add -p edit mode semantics.
    The @@ header is recalculated.
    """
    diff_lines = hunk.diff.split("\n")

    # First line is the @@ header
    header = diff_lines[0]
    body = diff_lines[1:]

    # Strip trailing empty strings from split
    while body and body[-1] == "":
        body.pop()

    total = len(body)

    # Validate line numbers
    all_requested = lines
    out_of_range = {n for n in all_requested if n < 1 or n > total}
    if out_of_range:
        bad = ", ".join(str(n) for n in sorted(out_of_range))
        raise ValueError(f"line numbers out of range (hunk has {total} lines): {bad}")

    # Determine which lines are "selected" (will keep their change status)
    if exclude:
        selected = {i for i in range(1, total + 1) if i not in lines}
    else:
        selected = lines

    new_body = []
    for i, line in enumerate(body, start=1):
        if i in selected:
            new_body.append(line)
        elif line.startswith("+"):
            # Drop unselected addition (don't stage this new line)
            continue
        elif line.startswith("-"):
            # Convert unselected deletion to context (keep the old line as-is)
            new_body.append(" " + line[1:])
        else:
            # Context line — always keep
            new_body.append(line)

    # Count changes in new body
    additions = sum(1 for l in new_body if l.startswith("+"))
    deletions = sum(1 for l in new_body if l.startswith("-"))

    if additions == 0 and deletions == 0:
        raise ValueError("no changes remain after line filtering")

    # Recalculate @@ header
    context_count = sum(1 for l in new_body if not l.startswith("+") and not l.startswith("-"))
    old_count = context_count + deletions
    new_count = context_count + additions

    # Parse original header for start lines
    m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", header)
    if not m:
        raise ValueError(f"cannot parse hunk header: {header}")

    old_start = m.group(1)
    new_start = m.group(2)
    tail = m.group(3)
    new_header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{tail}"

    new_diff = new_header + "\n" + "\n".join(new_body)

    return replace(
        hunk,
        diff=new_diff,
        header=new_header,
        additions=additions,
        deletions=deletions,
    )
