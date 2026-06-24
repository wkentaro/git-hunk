from collections.abc import Callable

import pytest

from git_hunk._hunk import Hunk
from git_hunk._hunk import count_changes


@pytest.fixture
def make_hunk() -> Callable[[str], Hunk]:
    def _make(diff: str) -> Hunk:
        body = diff.split("\n")[1:]
        additions, deletions = count_changes(body)
        return Hunk(
            id="abc1234",
            file="test.py",
            header=diff.split("\n")[0],
            additions=additions,
            deletions=deletions,
            context_before="",
            diff=diff,
        )

    return _make
