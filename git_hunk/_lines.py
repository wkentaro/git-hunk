import re
from collections.abc import Sequence
from dataclasses import replace
from typing import NamedTuple

from ._hunk import NO_NEWLINE_MARKER
from ._hunk import Hunk
from ._hunk import count_changes
from ._hunk import is_no_newline_marker
from ._hunk import strip_trailing_empty_lines


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


class _BodyLine(NamedTuple):
    prefix: str  # rendered side: ' ' context, '-' old, '+' new
    text: str
    no_newline: bool  # the line it represents has no trailing newline


def _select_body_lines(
    body: list[str],
    selected: set[int],
    *,
    keep_prefix: str,
) -> list[_BodyLine]:
    """Apply the line selection, folding each no-newline marker onto its line."""
    kept: list[_BodyLine] = []
    line_num = 0
    dropped_last = False
    for line in body:
        if is_no_newline_marker(line):
            if not dropped_last:
                kept[-1] = kept[-1]._replace(no_newline=True)
            continue
        line_num += 1
        prefix, text = line[:1], line[1:]
        if prefix == " " or line_num in selected:
            kept.append(_BodyLine(prefix=prefix, text=text, no_newline=False))
        elif prefix == keep_prefix:  # unselected change survives as context
            kept.append(_BodyLine(prefix=" ", text=text, no_newline=False))
        else:
            dropped_last = True
            continue
        dropped_last = False
    return kept


def _render_body_lines(kept: list[_BodyLine]) -> list[str]:
    # A no-newline marker is valid only on the final line of the side it
    # describes. A kept change line always sits at its side's EOF, and a context
    # marker on the very last body line ends both sides. The remaining case is an
    # old-side line kept as context that now has lines after it: it was the old
    # EOF (no trailing newline) but the new side continues past it, so split it
    # back into a '-'/'+' pair, keeping the marker on the old side while the new
    # side gains a newline. The mirror (a new-side no-newline line kept as context
    # under reverse) cannot reach here: a new-side EOF line never has kept lines
    # after it, so it is always the last body line and takes the branch above.
    last_index = len(kept) - 1
    rendered = []
    for index, line in enumerate(kept):
        if not line.no_newline:
            rendered.append(line.prefix + line.text)
        elif line.prefix != " " or index == last_index:
            rendered.append(line.prefix + line.text)
            rendered.append(NO_NEWLINE_MARKER)
        else:
            rendered.append("-" + line.text)
            rendered.append(NO_NEWLINE_MARKER)
            rendered.append("+" + line.text)
    return rendered


def _body_lines(hunk: Hunk) -> list[str]:
    return strip_trailing_empty_lines(hunk.diff.split("\n")[1:])


def resolve_matching_lines(
    hunk: Hunk, patterns: Sequence[str], *, regex: bool
) -> set[int]:
    """Return 1-based body line numbers of changed lines matching any pattern.

    Patterns are OR'd. Only changed ('+'/'-') lines are considered, matched
    against their content (the text after the prefix). Raises if nothing matches,
    so a typo'd pattern never silently selects nothing or everything.
    """
    compiled: list[re.Pattern[str]] | None = None
    if regex:
        try:
            compiled = [re.compile(p) for p in patterns]
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc

    selected: set[int] = set()
    line_num = 0
    for line in _body_lines(hunk):
        if is_no_newline_marker(line):
            continue
        line_num += 1
        if not line.startswith(("+", "-")):
            continue
        content = line[1:]
        if compiled is not None:
            matched = any(pattern.search(content) for pattern in compiled)
        else:
            matched = any(pattern in content for pattern in patterns)
        if matched:
            selected.add(line_num)

    if not selected:
        joined = ", ".join(repr(p) for p in patterns)
        raise ValueError(f"no changed line matches {joined}")
    return selected


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
    keep_prefix = "+" if reverse else "-"
    kept = _select_body_lines(body, selected, keep_prefix=keep_prefix)
    return _render_body_lines(kept)


def filter_hunk_lines(
    hunk: Hunk, lines: set[int], *, exclude: bool, reverse: bool = False
) -> Hunk:
    """Return a new Hunk with only the selected lines as changes.

    Unselected changes on the side the apply consumes become context; the other
    side drops. A forward apply keeps unselected '-' lines and drops '+';
    reverse=True (unstage, discard) swaps those so the patch applies against the
    NEW content the index or working tree already holds.
    """
    header = hunk.diff.split("\n", 1)[0]
    body = _body_lines(hunk)

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

    range_header = f"@@ -{m.group(1)},{old_count} +{m.group(2)},{new_count} @@"
    # diff keeps git's verbatim @@ line (heading included) for git apply / show;
    # the JSON header field is the bare range (heading lives in context_before).
    new_diff = range_header + m.group(3) + "\n" + "\n".join(new_body)

    return replace(
        hunk,
        diff=new_diff,
        header=range_header,
        additions=additions,
        deletions=deletions,
    )
