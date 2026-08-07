from collections.abc import Generator
from pathlib import Path

import pytest

from eval.repo import GitRepo
from eval.repo import init_repo


@pytest.fixture
def eval_repo(tmp_path: Path) -> Generator[GitRepo]:
    repo = init_repo(path=tmp_path)
    yield repo
