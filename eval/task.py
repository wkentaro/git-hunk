import dataclasses
from collections.abc import Callable
from typing import Literal

from eval.repo import GitRepo

FileMode = Literal["100644", "100755", "120000"]


@dataclasses.dataclass(frozen=True)
class ChangedLine:
    path: str
    op: Literal["+", "-"]
    content: str


@dataclasses.dataclass(frozen=True)
class CommitSpec:
    label: str
    changes: frozenset[ChangedLine]


@dataclasses.dataclass(frozen=True)
class FileState:
    path: str
    content: bytes
    mode: FileMode = "100644"


@dataclasses.dataclass(frozen=True)
class RepositoryState:
    head: frozenset[FileState]
    worktree: frozenset[FileState]
    untracked: frozenset[FileState] = frozenset()


@dataclasses.dataclass(frozen=True)
class Task:
    name: str
    build: Callable[[GitRepo], None]
    commits: tuple[CommitSpec, ...]
    expected_state: RepositoryState
    prompt: str = ""
    order_constraints: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        labels = [spec.label for spec in self.commits]
        if len(set(labels)) != len(labels):
            raise ValueError(f"task {self.name!r} has duplicate commit labels")
        if len({spec.changes for spec in self.commits}) != len(labels):
            raise ValueError(f"task {self.name!r} has identical commit change sets")
        for before, after in self.order_constraints:
            for label in (before, after):
                if label not in labels:
                    raise ValueError(
                        f"task {self.name!r} order constraint references "
                        f"unknown label {label!r}"
                    )


def make_file(
    *, path: str, content: str | bytes, mode: FileMode = "100644"
) -> FileState:
    data = content.encode() if isinstance(content, str) else content
    return FileState(path=path, content=data, mode=mode)
