import pytest

from eval.task import ChangedLine
from eval.task import CommitSpec
from eval.task import RepositoryState
from eval.task import Task


def _make_spec(*, label: str, content: str) -> CommitSpec:
    return CommitSpec(
        label=label,
        changes=frozenset({ChangedLine(path="a.py", op="+", content=content)}),
    )


def _make_state() -> RepositoryState:
    return RepositoryState(head=frozenset(), worktree=frozenset())


def test_rejects_duplicate_commit_labels() -> None:
    with pytest.raises(ValueError, match="duplicate commit labels"):
        Task(
            name="duplicate",
            build=lambda repo: None,
            commits=(
                _make_spec(label="a", content="1"),
                _make_spec(label="a", content="2"),
            ),
            expected_state=_make_state(),
        )


def test_rejects_identical_change_sets() -> None:
    with pytest.raises(ValueError, match="identical commit change sets"):
        Task(
            name="identical",
            build=lambda repo: None,
            commits=(
                _make_spec(label="a", content="1"),
                _make_spec(label="b", content="1"),
            ),
            expected_state=_make_state(),
        )


def test_rejects_unknown_order_constraint_label() -> None:
    with pytest.raises(ValueError, match="unknown label"):
        Task(
            name="unknown-order",
            build=lambda repo: None,
            commits=(_make_spec(label="a", content="1"),),
            expected_state=_make_state(),
            order_constraints=(("a", "missing"),),
        )
