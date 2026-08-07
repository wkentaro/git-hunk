import subprocess
import sys
from pathlib import Path

from eval.__main__ import _is_run_qualifying
from eval.config import TASK_NAMES
from eval.grader import Result


def test_runner_rejects_model_override_before_running_tasks() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "eval", "--model", "opus"],
        capture_output=True,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --model opus" in result.stderr


def test_selected_run_cannot_qualify_with_all_task_names() -> None:
    results = tuple(Result(passed=True) for _ in TASK_NAMES)

    assert not _is_run_qualifying(
        selected_run=True,
        complete=True,
        results=results,
    )
