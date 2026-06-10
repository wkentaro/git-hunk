import re
from dataclasses import replace

from ._hunk import Hunk
from ._hunk import count_changes
from ._hunk import is_no_newline_marker


def _parse_line_number(token: str) -> int:
    token = token.strip()
    if not re.fullmatch(r"[0-9]+", token):
        raise ValueError(f"invalid line number: '{token}'")
    n = int(token)
    if n < 1:
        raise ValueError(f"line numbers must be positive: '{token}'")
    return n


def parse_line_spec(spec: str) -> tuple[set[int], bool]:
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
    lines: set[int] = set()

    for part in parts:
        raw = part.lstrip("^")
        if not raw:
            raise ValueError(f"invalid token in -l spec: '{part}'")
        if "-" in raw:
            bounds = raw.split("-")
            if len(bounds) != 2 or not all(b.strip() for b in bounds):
                raise ValueError(f"invalid range: '{part}' (expected start-end)")
            lo = _parse_line_number(bounds[0])
            hi = _parse_line_number(bounds[1])
            if lo > hi:
                raise ValueError(f"invalid range (start > end): {part}")
            lines.update(range(lo, hi + 1))
        else:
            lines.add(_parse_line_number(raw))

    return lines, exclude


def _filter_body_lines(
    body: list[str],
    selected: set[int],
    *,
    reverse: bool,
) -> list[str]:
    # Unselected changes must survive as context in the form the apply direction
    # expects. A forward (stage) apply matches OLD content, so unselected '-'
    # lines become context and unselected '+' lines drop; a reverse (unstage,
    # discard) apply matches NEW content, so the two sides swap.
    drop_prefix = "-" if reverse else "+"
    keep_prefix = "+" if reverse else "-"
    new_body = []
    line_num = 0
    prev_kept = False
    for line in body:
        if is_no_newline_marker(line):
            if prev_kept:
                new_body.append(line)
            continue
        line_num += 1
        if line_num in selected:
            new_body.append(line)
            prev_kept = True
        elif line.startswith(drop_prefix):
            prev_kept = False
        elif line.startswith(keep_prefix):
            new_body.append(" " + line[1:])
            prev_kept = True
        else:
            new_body.append(line)
            prev_kept = True
    return new_body


def filter_hunk_lines(
    hunk: Hunk, lines: set[int], *, exclude: bool, reverse: bool = False
) -> Hunk:
    """Return a new Hunk with only the selected lines as changes.

    Unselected changes on the side the apply consumes become context; the other
    side drops. A forward apply keeps unselected '-' lines and drops '+';
    reverse=True (unstage, discard) swaps those so the patch applies against the
    NEW content the index or working tree already holds.
    """
    diff_lines = hunk.diff.split("\n")
    header = diff_lines[0]
    body = diff_lines[1:]

    while body and body[-1] == "":
        body = body[:-1]

    total = sum(1 for line in body if not is_no_newline_marker(line))

    out_of_range = {n for n in lines if n < 1 or n > total}
    if out_of_range:
        bad = ", ".join(str(n) for n in sorted(out_of_range))
        raise ValueError(f"line numbers out of range (hunk has {total} lines): {bad}")

    if exclude:
        selected = {i for i in range(1, total + 1) if i not in lines}
    else:
        selected = lines

    new_body = _filter_body_lines(body, selected, reverse=reverse)

    additions, deletions = count_changes(new_body)
    if additions == 0 and deletions == 0:
        raise ValueError("no changes remain after line filtering")

    markers = sum(1 for line in new_body if is_no_newline_marker(line))
    context_count = len(new_body) - additions - deletions - markers
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
