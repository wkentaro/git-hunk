import contextlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import eval.__main__ as eval_main
from eval.environment import EvalEnvironment
from eval.grader import Result
from eval.model import EvalVariant
from eval.repo import GitRepo
from eval.scenario import Solver
from eval.task import Task
from eval.tasks import SCENARIOS


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


@pytest.mark.parametrize("scenario_count", [1, 2])
def test_run_reports_context_usage_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scenario_count: int,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result_event: dict[str, Any] = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 22670,
        "duration_api_ms": 22618,
        "num_turns": 8,
        "total_cost_usd": 0.0891406,
        "usage": {
            "input_tokens": 16,
            "cache_creation_input_tokens": 8434,
            "cache_read_input_tokens": 59782,
            "output_tokens": 1327,
        },
        "modelUsage": {},
    }

    def make_solver(
        *,
        task: Task,
        variant: EvalVariant,
        trace_path: Path,
        transcript_path: Path,
    ) -> Solver:
        del task

        def solve(repo: GitRepo) -> None:
            del repo
            print(f"variant: {variant.name}")
            trace_path.write_text(
                f"{json.dumps(result_event)}\n",
                encoding="utf-8",
            )
            transcript_path.write_text(
                f"variant: {variant.name}\n",
                encoding="utf-8",
            )

        return solve

    class PreparedTask:
        def run_and_grade(self, solver: Solver) -> Result:
            solver(GitRepo(tmp_path))
            return Result(passed=True)

    def prepare_task(task: Task) -> contextlib.AbstractContextManager[PreparedTask]:
        del task
        return contextlib.nullcontext(PreparedTask())

    monkeypatch.setattr(eval_main.tempfile, "mkdtemp", lambda **kwargs: str(run_dir))
    monkeypatch.setattr(eval_main, "make_claude_solver", make_solver)
    monkeypatch.setattr(eval_main, "prepare_task", prepare_task)
    monotonic_values = iter((100.0, 122.67))
    monkeypatch.setattr(eval_main.time, "monotonic", lambda: next(monotonic_values))
    environment = EvalEnvironment(
        checkout=tmp_path,
        commit="61e2c1911d58abe1e6030b0d3e552c94dc067c39",
        dirty=True,
        git_hunk_executable=tmp_path / "git-hunk",
        imported_package=tmp_path / "git_hunk/__init__.py",
        skill_paths={},
        skill_sha256={},
        claude_code_version="2.1.226 (Claude Code)",
    )

    exit_code = eval_main._run_scenarios(
        environment=environment,
        scenarios=SCENARIOS[:scenario_count],
    )

    expected_usage = (
        "usage: 22.7s · 8 turns · tokens 16 input / 8.4k cache-write / "
        "59.8k cache-read / 1.3k output · $0.0891"
    )
    output = capsys.readouterr()
    assert exit_code == 0
    assert output.err == ""
    expected_lines = [
        "eval: model=claude-sonnet-5 claude=2.1.226 commit=61e2c19 dirty=true",
    ]
    for index, scenario in enumerate(SCENARIOS[:scenario_count], start=1):
        progress = f" {index}/{scenario_count}" if scenario_count > 1 else ""
        expected_lines.append(f"running{progress}: {scenario.task.name}")
        for variant in ("git-hunk", "bare-git"):
            expected_lines.append("")
            expected_lines += [
                f"variant: {variant}",
                "result:",
                f"  PASS {scenario.task.name} [{variant}]",
                f"  {expected_usage}",
            ]
    run_count = scenario_count * 2
    expected_lines += [
        f"overall: PASS {run_count}/{run_count}",
        f"usage: {run_count * 22.67:.1f}s · {run_count * 8} turns · "
        f"tokens {run_count * 16} input / "
        f"{run_count * 8434 / 1000:.1f}k cache-write / "
        f"{run_count * 59782 / 1000:.1f}k cache-read / "
        f"{run_count * 1327 / 1000:.1f}k output · ${run_count * 0.0891406:.4f}",
    ]
    expected_lines.append(f"artifacts: {run_dir}")
    assert output.out.splitlines() == expected_lines
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["clean_worktree"] is False
    assert manifest["passed"] is True
    assert "selected_run" not in manifest
    assert "complete" not in manifest
    assert "qualifying" not in manifest
    assert "retried" not in manifest
    assert len(manifest["tasks"]) == run_count
    assert [task["variant"] for task in manifest["tasks"]] == [
        variant for _ in range(scenario_count) for variant in ("git-hunk", "bare-git")
    ]
    assert manifest["usage"]["cost_usd"] == pytest.approx(0.0891406 * run_count)
    assert manifest["tasks"][0]["usage"]["tokens"]["output"] == 1327
    assert manifest["tasks"][0]["transcript"] == (
        "split_refactor_vs_feature.git-hunk.transcript.txt"
    )
    assert manifest["tasks"][0]["transcript_sha256"]
    transcript = (run_dir / manifest["tasks"][0]["transcript"]).read_text(
        encoding="utf-8"
    )
    assert transcript.splitlines()[-3:] == [
        "result:",
        "  PASS split_refactor_vs_feature [git-hunk]",
        f"  {expected_usage}",
    ]
