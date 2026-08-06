import re
from collections.abc import Sequence
from dataclasses import replace
from typing import NamedTuple

from ._hunk import NO_NEWLINE_MARKER
from ._hunk import Hunk
from ._hunk import count_changes
from ._hunk import is_no_newline_marker
from ._hunk import split_diff_body


def _parse_line_number(token: str) -> int:
    token = token.strip()
    if not re.fullmatch(r"[0-9]+", token):
        raise ValueError(f"invalid line number: '{token}'")
    n = int(token)
    if n < 1:
        raise ValueError(f"line numbers must be positive: '{token}'")
    return n


def parse_line_spec(spec: str, *, total: int) -> tuple[set[int], bool]:
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
            if lo > total or hi > total:
                raise ValueError(
                    f"line number out of range (hunk has {total} lines): {part}"
                )
            lines.update(range(lo, hi + 1))
        else:
            line = _parse_line_number(raw)
            if line > total:
                raise ValueError(
                    f"line number out of range (hunk has {total} lines): {part}"
                )
            lines.add(line)

    return lines, exclude


class _BodyLine(NamedTuple):
    prefix: str  # rendered side: ' ' context, '-' old, '+' new
    text: str
    old_no_newline: bool
    new_no_newline: bool


def _parse_body_lines(body: list[str]) -> list[_BodyLine]:
    parsed: list[_BodyLine] = []
    for line in body:
        if not is_no_newline_marker(line):
            parsed.append(
                _BodyLine(
                    prefix=line[:1],
                    text=line[1:],
                    old_no_newline=False,
                    new_no_newline=False,
                )
            )
            continue

        previous = parsed[-1]
        parsed[-1] = previous._replace(
            old_no_newline=previous.prefix in (" ", "-"),
            new_no_newline=previous.prefix in (" ", "+"),
        )
    return parsed


def count_hunk_body_lines(hunk: Hunk) -> int:
    body = split_diff_body(diff=hunk.diff)
    return len(_parse_body_lines(body))


def _select_body_lines(
    body: list[_BodyLine],
    selected: set[int],
    *,
    keep_prefix: str,
) -> list[_BodyLine]:
    kept: list[_BodyLine] = []
    for line_num, line in enumerate(body, start=1):
        if line.prefix == " " or line_num in selected:
            kept.append(line)
            continue
        if line.prefix != keep_prefix:
            continue
        # The line becomes context, so it now sits on both patch sides. A change
        # line only ever carries a marker at its own side's EOF, so if it ends
        # without a newline on one side it ends without one on both. Widen the
        # flag; _render_body_lines drops it again on whichever side a later kept
        # line extends past it.
        no_newline = line.old_no_newline or line.new_no_newline
        kept.append(
            line._replace(
                prefix=" ",
                old_no_newline=no_newline,
                new_no_newline=no_newline,
            )
        )
    return kept


def _render_body_lines(kept: list[_BodyLine]) -> list[str]:
    # A no-newline marker is valid only while its line is last on the side it
    # belongs to: ' ' context on both, '-' on old, '+' on new. Filtering can
    # leave a marked line with a later kept line on the same side, which makes
    # the marker stale and would merge the two lines on apply. Recompute each
    # side's final line and emit a marker only there.
    last_old_index = max(
        (index for index, line in enumerate(kept) if line.prefix in (" ", "-")),
        default=-1,
    )
    last_new_index = max(
        (index for index, line in enumerate(kept) if line.prefix in (" ", "+")),
        default=-1,
    )
    rendered: list[str] = []
    for index, line in enumerate(kept):
        old_marker = line.old_no_newline and index == last_old_index
        new_marker = line.new_no_newline and index == last_new_index
        if line.prefix == " " and old_marker != new_marker:
            # The sides disagree, which no single context line can express, so
            # split it into the '-'/'+' pair that carries a marker per side.
            rendered.append("-" + line.text)
            if old_marker:
                rendered.append(NO_NEWLINE_MARKER)
            rendered.append("+" + line.text)
            if new_marker:
                rendered.append(NO_NEWLINE_MARKER)
            continue
        rendered.append(line.prefix + line.text)
        if old_marker or new_marker:
            rendered.append(NO_NEWLINE_MARKER)
    return rendered


def _validate_group(group: list[tuple[int, str]], selected: set[int]) -> None:
    """Reject a partial subset of a grouped replacement.

    Git pairs no old line with any new line inside a run of changed lines, so a
    subset of a replacement wider than one-for-one has no defined meaning. Pure
    additions, pure deletions, and one-for-one replacements stay unrestricted.
    """
    deletions = sum(prefix == "-" for _, prefix in group)
    additions = sum(prefix == "+" for _, prefix in group)
    if not deletions or not additions:
        return
    if deletions == 1 and additions == 1:
        return
    selected_count = sum(number in selected for number, _ in group)
    if selected_count in (0, len(group)):
        return
    raise ValueError(
        f"cannot partially select lines {group[0][0]}-{group[-1][0]}: "
        f"grouped replacement (deletions: {deletions}, additions: {additions}); "
        "select all or none"
    )


def _validate_group_selection(body: list[_BodyLine], selected: set[int]) -> None:
    group: list[tuple[int, str]] = []
    for line_num, line in enumerate(body, start=1):
        if line.prefix in ("+", "-"):
            group.append((line_num, line.prefix))
            continue
        _validate_group(group, selected)
        group = []
    _validate_group(group, selected)


def resolve_matching_lines(
    hunk: Hunk, patterns: Sequence[str], *, regex: bool
) -> set[int]:
    """Return 1-based body line numbers of changed lines matching any pattern.

    Patterns are OR'd. Only changed ('+'/'-') lines are considered, matched
    against their content (the text after the prefix). Raises if nothing matches,
    so a typo'd pattern never silently selects nothing or everything.

    An empty pattern is rejected: it would match every changed line and silently
    select the whole hunk, mirroring how an empty -l spec errors rather than
    falling through to select everything.
    """
    if "" in patterns:
        raise ValueError("empty match pattern")

    compiled: list[re.Pattern[str]] | None = None
    if regex:
        try:
            compiled = [re.compile(p) for p in patterns]
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc

    selected: set[int] = set()
    body = _parse_body_lines(split_diff_body(diff=hunk.diff))
    for line_num, line in enumerate(body, start=1):
        if line.prefix not in ("+", "-"):
            continue
        if compiled is not None:
            matched = any(pattern.search(line.text) for pattern in compiled)
        else:
            matched = any(pattern in line.text for pattern in patterns)
        if matched:
            selected.add(line_num)

    if not selected:
        joined = ", ".join(repr(p) for p in patterns)
        raise ValueError(f"no changed line matches {joined}")
    return selected


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
    body = _parse_body_lines(split_diff_body(diff=hunk.diff))
    total = len(body)

    out_of_range = [n for n in lines if n < 1 or n > total]
    if out_of_range:
        raise ValueError(
            f"line number out of range (hunk has {total} lines): {min(out_of_range)}"
        )

    if exclude:
        selected = {i for i in range(1, total + 1) if i not in lines}
    else:
        selected = lines

    _validate_group_selection(body, selected)
    # A forward apply matches OLD content, so unselected '-' lines become
    # context and unselected '+' lines drop. A reverse apply matches NEW
    # content, so the two sides swap.
    keep_prefix = "+" if reverse else "-"
    kept = _select_body_lines(body, selected, keep_prefix=keep_prefix)
    new_body = _render_body_lines(kept)

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

    # Git writes start 0 only for an empty side. Filtering can give an added
    # file's old side (or a deleted file's new side) context lines, so the side
    # is no longer empty and its start must become the first real line.
    old_start = 1 if m.group(1) == "0" and old_count else int(m.group(1))
    new_start = 1 if m.group(2) == "0" and new_count else int(m.group(2))
    range_header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
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
