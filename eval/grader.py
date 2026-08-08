import dataclasses
import os
import stat
from typing import Final
from typing import Literal
from typing import cast

from eval.repo import GitRepo
from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import FileMode
from eval.task import FileState
from eval.task import Task

FailureReason = Literal[
    "partition",
    "order",
    "final-tree",
    "leftover-index",
    "leftover-worktree",
    "leftover-untracked",
    "solver-error",
]

SOLVER_ERROR: Final[FailureReason] = "solver-error"


@dataclasses.dataclass(frozen=True)
class Result:
    passed: bool
    reason: FailureReason | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.passed != (self.reason is None):
            raise ValueError("a Result has a failure reason if and only if it failed")


def grade(repo: GitRepo, task: Task, base: str) -> Result:
    shas = repo.git("rev-list", "--reverse", f"{base}..HEAD").split()
    if len(shas) != len(task.commits):
        return _fail(
            reason="partition",
            detail=f"expected {len(task.commits)} commits, got {len(shas)}",
        )

    spec_by_changes = {spec.changes: spec for spec in task.commits}
    matched: list[CommitSpec] = []
    for sha in shas:
        changes = _extract_changes(repo=repo, sha=sha)
        spec = spec_by_changes.get(changes)
        if spec is None:
            formatted_changes = _format_changes(changes)
            return _fail(
                reason="partition",
                detail=f"commit {sha} has unexpected changes: {formatted_changes}",
            )
        matched.append(spec)

    expected_labels = {spec.label for spec in task.commits}
    actual_labels = {spec.label for spec in matched}
    if actual_labels != expected_labels:
        sorted_expected = sorted(expected_labels)
        sorted_actual = sorted(actual_labels)
        return _fail(
            reason="partition",
            detail=f"expected labels {sorted_expected}, got {sorted_actual}",
        )

    position = {spec.label: index for index, spec in enumerate(matched)}
    for before, after in task.order_constraints:
        if position[before] >= position[after]:
            return _fail(
                reason="order",
                detail=f"{before!r} must precede {after!r}",
            )

    actual_head = _read_head(repo=repo)
    if actual_head != task.expected_state.head:
        return _state_failure(
            reason="final-tree",
            expected=task.expected_state.head,
            actual=actual_head,
        )

    head_tree = repo.git("rev-parse", "HEAD^{tree}").strip()
    index_tree = repo.git("write-tree").strip()
    head_paths = frozenset(file.path for file in actual_head)
    index_paths = _read_index_paths(repo=repo)
    if index_tree != head_tree or index_paths != head_paths:
        return _fail(
            reason="leftover-index",
            detail=(
                f"expected tree {head_tree} and paths {sorted(head_paths)!r}, "
                f"got tree {index_tree} and paths {sorted(index_paths)!r}"
            ),
        )

    actual_worktree = _read_tracked_worktree(repo=repo, head=actual_head)
    if actual_worktree != task.expected_state.worktree:
        return _state_failure(
            reason="leftover-worktree",
            expected=task.expected_state.worktree,
            actual=actual_worktree,
        )

    actual_untracked = _read_untracked(repo=repo)
    if actual_untracked != task.expected_state.untracked:
        return _state_failure(
            reason="leftover-untracked",
            expected=task.expected_state.untracked,
            actual=actual_untracked,
        )

    return Result(passed=True)


def _extract_changes(repo: GitRepo, sha: str) -> frozenset[ChangedLine]:
    diff = repo.git("diff", "--no-color", "--no-renames", f"{sha}^", sha)
    return _parse_changes(diff)


def _parse_changes(diff: str) -> frozenset[ChangedLine]:
    changes: set[ChangedLine] = set()
    file_path = ""
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            if line.startswith(("--- a/", "+++ b/")):
                file_path = line[6:].removesuffix("\t")
            continue
        if line.startswith("+"):
            changes.add(ChangedLine(path=file_path, op="+", content=line[1:]))
        elif line.startswith("-"):
            changes.add(ChangedLine(path=file_path, op="-", content=line[1:]))
    return frozenset(changes)


def _read_head(repo: GitRepo) -> frozenset[FileState]:
    listing = repo.git_bytes("ls-tree", "-rz", "--full-tree", "HEAD")
    files: set[FileState] = set()
    for record in listing.rstrip(b"\0").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        raw_mode, object_type, object_id = metadata.split(b" ")
        if object_type != b"blob":
            raise RuntimeError(f"unsupported tree object type {object_type.decode()!r}")
        content = repo.git_bytes("cat-file", "blob", object_id.decode())
        files.add(
            FileState(
                path=os.fsdecode(raw_path),
                content=content,
                mode=_parse_mode(raw_mode),
            )
        )
    return frozenset(files)


def _read_tracked_worktree(
    repo: GitRepo, head: frozenset[FileState]
) -> frozenset[FileState]:
    files = {
        state
        for expected in head
        if (state := _read_worktree_file(repo=repo, path=expected.path)) is not None
    }
    return frozenset(files)


def _read_index_paths(repo: GitRepo) -> frozenset[str]:
    listing = repo.git_bytes("ls-files", "-z")
    return frozenset(
        os.fsdecode(raw_path)
        for raw_path in listing.rstrip(b"\0").split(b"\0")
        if raw_path
    )


def _read_untracked(repo: GitRepo) -> frozenset[FileState]:
    listing = repo.git_bytes("ls-files", "--others", "-z")
    files: set[FileState] = set()
    for raw_path in listing.rstrip(b"\0").split(b"\0"):
        if not raw_path:
            continue
        file_state = _read_worktree_file(repo=repo, path=os.fsdecode(raw_path))
        if file_state is None:
            raise RuntimeError(f"untracked path disappeared: {os.fsdecode(raw_path)!r}")
        files.add(file_state)
    return frozenset(files)


def _read_worktree_file(repo: GitRepo, path: str) -> FileState | None:
    file_path = repo.path / path
    try:
        file_stat = file_path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(file_stat.st_mode):
        return FileState(
            path=path,
            content=os.fsencode(os.readlink(file_path)),
            mode="120000",
        )
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError(f"unsupported worktree file type: {path!r}")
    mode: FileMode = "100755" if file_stat.st_mode & stat.S_IXUSR else "100644"
    return FileState(path=path, content=file_path.read_bytes(), mode=mode)


def _parse_mode(raw_mode: bytes) -> FileMode:
    mode = raw_mode.decode()
    if mode not in {"100644", "100755", "120000"}:
        raise RuntimeError(f"unsupported Git mode {mode!r}")
    return cast("FileMode", mode)


def _fail(*, reason: FailureReason, detail: str) -> Result:
    return Result(passed=False, reason=reason, detail=detail)


def _state_failure(
    *,
    reason: FailureReason,
    expected: frozenset[FileState],
    actual: frozenset[FileState],
) -> Result:
    return _fail(
        reason=reason,
        detail=f"expected {_format_files(expected)}, got {_format_files(actual)}",
    )


def _format_changes(changes: frozenset[ChangedLine]) -> str:
    return repr(
        sorted(changes, key=lambda change: (change.path, change.op, change.content))
    )


def _format_files(files: frozenset[FileState]) -> str:
    return repr(sorted(files, key=lambda file: file.path))
