import base64
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import replace
from typing import Any
from typing import Final

NO_NEWLINE_MARKER: Final = "\\ No newline at end of file"


def is_no_newline_marker(line: str) -> bool:
    return line == NO_NEWLINE_MARKER


def _byte_safe(text: str) -> dict[str, str]:
    # git output is decoded with surrogateescape (see _git.run_git), so non-UTF-8
    # bytes survive as lone surrogates. Emit valid UTF-8 as {"text": ...} and
    # anything else as {"bytes": base64}, so strict JSON parsers never choke on a
    # lone surrogate. The ripgrep --json idiom; always an object so consumers have
    # one code path.
    raw = text.encode("utf-8", "surrogateescape")
    try:
        return {"text": raw.decode("utf-8")}
    except UnicodeDecodeError:
        return {"bytes": base64.b64encode(raw).decode("ascii")}


@dataclass(frozen=True)
class Hunk:
    id: str
    file: str
    change_kind: str
    a_mode: str | None
    b_mode: str | None
    binary: bool
    header: str | None
    context_before: str | None
    additions: int
    deletions: int
    diff: str
    status: str = "unstaged"

    def to_dict(self, *, include_lines: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "file": _byte_safe(self.file),
            "status": self.status,
            "change_kind": self.change_kind,
            "a_mode": self.a_mode,
            "b_mode": self.b_mode,
            "binary": self.binary,
            "header": self.header,
            "context_before": (
                _byte_safe(self.context_before)
                if self.context_before is not None
                else None
            ),
            "additions": self.additions,
            "deletions": self.deletions,
        }
        if include_lines:
            data["lines"] = _body_lines(self.diff)
        return data


def _body_lines(diff: str) -> list[dict[str, Any]]:
    if not diff:
        return []
    _, *body = diff.split("\n")
    body = strip_trailing_empty_lines(body)
    lines: list[dict[str, Any]] = []
    for line in body:
        if is_no_newline_marker(line):
            if lines:
                lines[-1]["no_newline"] = True
            continue
        lines.append(
            {"n": len(lines) + 1, "op": line[:1], "content": _byte_safe(line[1:])}
        )
    return lines


def count_changes(lines: list[str]) -> tuple[int, int]:
    additions = sum(1 for line in lines if line.startswith("+"))
    deletions = sum(1 for line in lines if line.startswith("-"))
    return additions, deletions


def strip_trailing_empty_lines(lines: list[str]) -> list[str]:
    while lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def _body_id(filepath: str, diff_content: str) -> str:
    """Stable across partial staging: ignores @@ headers that shift."""
    body = "\n".join(
        line for line in diff_content.split("\n") if not line.startswith("@@")
    )
    # surrogateescape mirrors _git.run_git's decode so non-UTF-8 bytes hash.
    data = f"{filepath}:{body}".encode(errors="surrogateescape")
    return hashlib.sha256(data).hexdigest()[:7]


def _full_id(filepath: str, diff_content: str) -> str:
    """Fallback for identical changed lines — includes @@ line numbers."""
    data = f"{filepath}:{diff_content}".encode(errors="surrogateescape")
    return hashlib.sha256(data).hexdigest()[:7]


def _with_stable_ids(hunks: list[Hunk]) -> list[Hunk]:
    # Pass 1: body-only IDs (stable across staging).
    # Pass 2: for colliding IDs, upgrade to full IDs to disambiguate.
    with_body_ids = [replace(h, id=_body_id(h.file, h.diff)) for h in hunks]

    counts = Counter(h.id for h in with_body_ids)
    return [
        replace(h, id=_full_id(h.file, h.diff)) if counts[h.id] > 1 else h
        for h in with_body_ids
    ]


def split_file_diffs(diff_output: str) -> list[str]:
    return re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)


def split_at_hunk_headers(file_diff: str, *, maxsplit: int = 0) -> list[str]:
    return re.split(r"(?=^@@)", file_diff, maxsplit=maxsplit, flags=re.MULTILINE)


def _unquote_c_path(path: str) -> str:
    C_ESCAPES: Final = {
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        '"': '"',
    }
    chars = []
    i = 0
    while i < len(path):
        if path[i] != "\\":
            chars.append(path[i])
            i += 1
            continue
        escape = path[i + 1]
        if escape in C_ESCAPES:
            chars.append(C_ESCAPES[escape])
            i += 2
        else:
            chars.append(chr(int(path[i + 1 : i + 4], 8)))
            i += 4
    return "".join(chars)


def extract_file_path(file_diff: str) -> str | None:
    first_line = file_diff.split("\n", 1)[0]
    # git double-quotes and C-escapes the header when a path contains a tab,
    # newline, backslash, or double-quote (regardless of core.quotePath). Both
    # halves are identical for non-renames; decode the logical path.
    m = re.match(r'diff --git "a/(.+)" "b/\1"$', first_line)
    if m:
        return _unquote_c_path(m.group(1))
    # For non-renames git emits `diff --git a/<path> b/<path>` with both halves
    # identical; the backreference resolves paths that contain " b/".
    m = re.match(r"diff --git a/(.+) b/\1$", first_line)
    if m:
        return m.group(1)
    m = re.match(r"diff --git a/(.*?) b/(.*)", first_line)
    return m.group(2) if m else None


def _bare_header(at_line: str) -> str:
    # "@@ -1,3 +1,3 @@ def foo():" -> "@@ -1,3 +1,3 @@" (strip git's heading; the
    # heading is carried separately in context_before).
    m = re.match(r"(@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@)", at_line)
    return m.group(1) if m else at_line


def _extract_context_before(header: str) -> str | None:
    match = re.search(r"@@.*?@@\s*(.*)", header)
    if not match:
        return None
    return match.group(1).strip() or None


def _whole_file_hunk(
    filepath: str,
    *,
    change_kind: str,
    a_mode: str | None,
    b_mode: str | None,
    binary: bool,
) -> Hunk:
    """A change applied by staging the whole file (binary, mode-only, type)."""
    return Hunk(
        id="",
        file=filepath,
        change_kind=change_kind,
        a_mode=a_mode,
        b_mode=b_mode,
        binary=binary,
        header=None,
        context_before=None,
        additions=0,
        deletions=0,
        diff="",
    )


def _block_modes(file_diff: str) -> tuple[str, str | None, str | None]:
    """Derive (change_kind, a_mode, b_mode) from one file diff's header lines."""
    new_file = re.search(r"^new file mode (\d+)", file_diff, flags=re.MULTILINE)
    if new_file:
        return "A", None, new_file.group(1)
    deleted = re.search(r"^deleted file mode (\d+)", file_diff, flags=re.MULTILINE)
    if deleted:
        return "D", deleted.group(1), None
    old_mode = re.search(r"^old mode (\d+)", file_diff, flags=re.MULTILINE)
    new_mode = re.search(r"^new mode (\d+)", file_diff, flags=re.MULTILINE)
    if old_mode and new_mode:
        return "M", old_mode.group(1), new_mode.group(1)
    index = re.search(
        r"^index [0-9a-f]+\.\.[0-9a-f]+ (\d+)", file_diff, flags=re.MULTILINE
    )
    if index:
        return "M", index.group(1), index.group(1)
    return "M", None, None


def _is_binary(file_diff: str) -> bool:
    return (
        re.search(r"^Binary files .* differ$", file_diff, flags=re.MULTILINE)
        is not None
    )


def parse_diff(diff_output: str) -> list[Hunk]:
    if not diff_output.strip():
        return []

    file_diffs = [fd for fd in split_file_diffs(diff_output) if fd.strip()]

    hunks = []
    i = 0
    while i < len(file_diffs):
        file_diff = file_diffs[i]
        filepath = extract_file_path(file_diff)
        if filepath is None:
            i += 1
            continue

        change_kind, a_mode, b_mode = _block_modes(file_diff)

        # git emits a type change (e.g. file -> symlink) as two consecutive blocks
        # for the same path: a delete of the old type then an add of the new one.
        next_diff = file_diffs[i + 1] if i + 1 < len(file_diffs) else None
        if change_kind == "D" and next_diff is not None:
            next_kind, _, new_b_mode = _block_modes(next_diff)
            if next_kind == "A" and extract_file_path(next_diff) == filepath:
                hunks.append(
                    _whole_file_hunk(
                        filepath,
                        change_kind="T",
                        a_mode=a_mode,
                        b_mode=new_b_mode,
                        binary=_is_binary(file_diff) or _is_binary(next_diff),
                    )
                )
                i += 2
                continue

        if _is_binary(file_diff):
            hunks.append(
                _whole_file_hunk(
                    filepath,
                    change_kind=change_kind,
                    a_mode=a_mode,
                    b_mode=b_mode,
                    binary=True,
                )
            )
            i += 1
            continue

        parts = split_at_hunk_headers(file_diff)

        if len(parts) == 1:
            # No text hunks: surface a pure mode change (chmod) that would
            # otherwise be dropped silently. An empty new/deleted file (A/D with
            # no @@ body) is left out, matching git-hunk's prior behavior.
            if change_kind == "M" and a_mode != b_mode:
                hunks.append(
                    _whole_file_hunk(
                        filepath,
                        change_kind=change_kind,
                        a_mode=a_mode,
                        b_mode=b_mode,
                        binary=False,
                    )
                )
            i += 1
            continue

        # Each @@ section is one hunk. get_diff pins -U3, where git already
        # separates changes more than 6 context lines apart into their own @@
        # section, so there is nothing finer to split here (use -l for that).
        for part in parts[1:]:
            header_line, *body_lines = part.split("\n")
            body_lines = strip_trailing_empty_lines(body_lines)

            additions, deletions = count_changes(body_lines)
            hunks.append(
                Hunk(
                    id="",
                    file=filepath,
                    change_kind=change_kind,
                    a_mode=a_mode,
                    b_mode=b_mode,
                    binary=False,
                    header=_bare_header(header_line),
                    context_before=_extract_context_before(header_line),
                    additions=additions,
                    deletions=deletions,
                    diff=header_line + "\n" + "\n".join(body_lines),
                )
            )
        i += 1

    return _with_stable_ids(hunks)
