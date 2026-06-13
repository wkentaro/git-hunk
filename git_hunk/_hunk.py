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
            "context_before": self.context_before,
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


def extract_file_path(file_diff: str) -> str | None:
    first_line = file_diff.split("\n", 1)[0]
    # For non-renames git emits `diff --git a/<path> b/<path>` with both halves
    # identical; the backreference resolves paths that contain " b/".
    m = re.match(r"diff --git a/(.+) b/\1$", first_line)
    if m:
        return m.group(1)
    m = re.match(r"diff --git a/(.*?) b/(.*)", first_line)
    return m.group(2) if m else None


def _extract_context_before(header: str) -> str:
    match = re.search(r"@@.*@@\s*(.*)", header)
    return match.group(1).strip() if match and match.group(1).strip() else ""


def _whole_file_hunk(filepath: str, header: str) -> Hunk:
    """A change applied by staging the whole file (binary or mode-only)."""
    return Hunk(
        id="",
        file=filepath,
        header=header,
        additions=0,
        deletions=0,
        context_before="",
        diff="",
    )


def _binary_file_header(file_diff: str) -> str:
    if re.search(r"^deleted file mode ", file_diff, flags=re.MULTILINE):
        return "Binary file (deleted)"
    if re.search(r"^new file mode ", file_diff, flags=re.MULTILINE):
        return "Binary file (added)"
    return "Binary file (modified)"


def _mode_change_header(file_diff: str) -> str | None:
    old = re.search(r"^old mode (\d+)$", file_diff, flags=re.MULTILINE)
    new = re.search(r"^new mode (\d+)$", file_diff, flags=re.MULTILINE)
    if not (old and new):
        return None
    return f"Mode {old.group(1)} -> {new.group(1)}"


def parse_diff(diff_output: str) -> list[Hunk]:
    if not diff_output.strip():
        return []

    hunks = []
    file_diffs = re.split(r"(?=^diff --git )", diff_output, flags=re.MULTILINE)

    for file_diff in file_diffs:
        if not file_diff.strip():
            continue

        filepath = extract_file_path(file_diff)
        if filepath is None:
            continue

        if re.search(r"^Binary files .* differ$", file_diff, flags=re.MULTILINE):
            hunks.append(_whole_file_hunk(filepath, _binary_file_header(file_diff)))
            continue

        parts = re.split(r"(?=^@@)", file_diff, flags=re.MULTILINE)

        if len(parts) == 1:
            # No text hunks: surface a pure mode change (chmod) that would
            # otherwise be dropped silently.
            mode_header = _mode_change_header(file_diff)
            if mode_header is not None:
                hunks.append(_whole_file_hunk(filepath, mode_header))
            continue

        # Each @@ section is one hunk. get_diff pins -U3, where git already
        # separates changes more than 6 context lines apart into their own @@
        # section, so there is nothing finer to split here (use -l for that).
        for part in parts[1:]:
            header_line, *body_lines = part.split("\n")

            while body_lines and body_lines[-1] == "":
                body_lines = body_lines[:-1]

            additions, deletions = count_changes(body_lines)
            hunks.append(
                Hunk(
                    id="",
                    file=filepath,
                    header=header_line,
                    additions=additions,
                    deletions=deletions,
                    context_before=_extract_context_before(header_line),
                    diff=header_line + "\n" + "\n".join(body_lines),
                )
            )

    return _with_stable_ids(hunks)
