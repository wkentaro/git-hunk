from dataclasses import replace
from typing import Final

from ._hunk import Hunk
from ._hunk import extract_file_path
from ._hunk import format_hunk_range
from ._hunk import is_mode_hunk
from ._hunk import parse_hunk_range
from ._hunk import split_at_hunk_headers
from ._hunk import split_file_diffs

_MODE_LINE_PREFIXES: Final = ("old mode ", "new mode ")


def _extract_file_headers(diff_output: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for file_diff in split_file_diffs(diff_output):
        filepath = extract_file_path(file_diff)
        if filepath is None:
            continue
        headers[filepath] = split_at_hunk_headers(file_diff, maxsplit=1)[0]
    return headers


def _remove_mode_lines(header: str) -> str:
    return "".join(
        line
        for line in header.splitlines(keepends=True)
        if not line.startswith(_MODE_LINE_PREFIXES)
    )


def _make_mode_header(header: str) -> str:
    lines = header.splitlines(keepends=True)
    return "".join(
        [lines[0]]
        + [line for line in lines[1:] if line.startswith(_MODE_LINE_PREFIXES)]
    )


def _needs_modification_header(hunk: Hunk) -> bool:
    # Partial line selection turns unselected changes into context, so an added
    # file's patch gains an old side and a deleted file's patch gains a new one.
    # Its "/dev/null" header no longer describes the patch and git rejects it.
    if not hunk.diff:
        return False
    hunk_range = parse_hunk_range(hunk.diff.splitlines()[0])
    return (hunk.change_kind == "A" and hunk_range.old_count > 0) or (
        hunk.change_kind == "D" and hunk_range.new_count > 0
    )


def _make_modification_header(header: str) -> str:
    lines = header.rstrip("\n").split("\n")
    diff_line = lines[0]
    old_line = next(line for line in lines if line.startswith("--- "))
    new_line = next(line for line in lines if line.startswith("+++ "))

    if old_line == "--- /dev/null":
        if new_line.startswith("+++ b/"):
            old_line = "--- a/" + new_line.removeprefix("+++ b/")
        else:
            old_line = '--- "a/' + new_line.removeprefix('+++ "b/')
    if new_line == "+++ /dev/null":
        if old_line.startswith("--- a/"):
            new_line = "+++ b/" + old_line.removeprefix("--- a/")
        else:
            new_line = '+++ "b/' + old_line.removeprefix('--- "a/')
    return "\n".join((diff_line, old_line, new_line)) + "\n"


def _normalize_hunk_ranges(hunks: list[Hunk], *, reverse: bool) -> list[str]:
    parsed = []
    for hunk in hunks:
        header, separator, body = hunk.diff.partition("\n")
        hunk_range = parse_hunk_range(header)
        target_start = hunk_range.new_start if reverse else hunk_range.old_start
        parsed.append((target_start, hunk_range, separator, body))

    normalized = []
    selected_delta = 0
    for _, hunk_range, separator, body in sorted(parsed, key=lambda item: item[0]):
        if reverse:
            old_start = (
                hunk_range.new_start - selected_delta if hunk_range.old_count else 0
            )
            hunk_range = replace(hunk_range, old_start=old_start)
        else:
            new_start = (
                hunk_range.old_start + selected_delta if hunk_range.new_count else 0
            )
            hunk_range = replace(hunk_range, new_start=new_start)
        normalized.append(format_hunk_range(hunk_range) + separator + body)
        selected_delta += hunk_range.new_count - hunk_range.old_count
    return normalized


def build_patch(hunks: list[Hunk], diff_output: str, *, reverse: bool) -> str:
    files: dict[str, list[Hunk]] = {}
    for hunk in hunks:
        files.setdefault(hunk.file, []).append(hunk)

    headers = _extract_file_headers(diff_output)

    patches = []
    for filepath, file_hunks in files.items():
        if filepath not in headers:
            raise ValueError(f"File header not found for {filepath}")
        mode_selected = any(is_mode_hunk(hunk) for hunk in file_hunks)
        text_selected = any(hunk.diff for hunk in file_hunks)
        if mode_selected and not text_selected:
            header = _make_mode_header(headers[filepath])
        elif not mode_selected:
            header = _remove_mode_lines(headers[filepath])
        else:
            header = headers[filepath]
        if any(_needs_modification_header(hunk) for hunk in file_hunks):
            header = _make_modification_header(header)
        text_hunks = [hunk for hunk in file_hunks if hunk.diff]
        hunk_diffs = "\n".join(_normalize_hunk_ranges(text_hunks, reverse=reverse))
        patches.append(header + hunk_diffs + ("\n" if hunk_diffs else ""))

    return "".join(patches)
