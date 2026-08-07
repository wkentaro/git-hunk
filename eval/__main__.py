import argparse
import datetime
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eval.config import MODEL
from eval.config import TASK_NAMES
from eval.config import TASK_SCHEMA_VERSION
from eval.environment import EvalEnvironment
from eval.environment import resolve_environment
from eval.grader import Result
from eval.harness import run_and_grade
from eval.model import build_command_flags
from eval.model import make_claude_solver
from eval.scenario import Scenario
from eval.tasks import SCENARIOS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval")
    parser.add_argument(
        "--task",
        action="append",
        choices=TASK_NAMES,
        metavar="NAME",
        help="run one named task; a selected-task run is nonqualifying",
    )
    args = parser.parse_args(argv)

    if tuple(scenario.task.name for scenario in SCENARIOS) != TASK_NAMES:
        print("error: the configured task set is incomplete", file=sys.stderr)
        return 2
    try:
        environment = resolve_environment()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    selected_names = set(args.task or TASK_NAMES)
    selected = tuple(
        scenario for scenario in SCENARIOS if scenario.task.name in selected_names
    )
    return _run_scenarios(
        environment=environment,
        scenarios=selected,
        selected_run=args.task is not None,
    )


def _run_scenarios(
    *,
    environment: EvalEnvironment,
    scenarios: tuple[Scenario, ...],
    selected_run: bool,
) -> int:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    run_directory_prefix = (
        f"git-hunk-agent-eval-{started_at:%Y%m%dT%H%M%SZ}-{environment.commit[:7]}-"
    )
    run_dir = Path(tempfile.mkdtemp(prefix=run_directory_prefix))
    results: list[tuple[Scenario, Result, Path]] = []

    for index, scenario in enumerate(scenarios, start=1):
        name = scenario.task.name
        print(f"running {index}/{len(scenarios)}: {name}", flush=True)
        trace_path = run_dir / f"{name}.jsonl"
        solver = make_claude_solver(task=scenario.task, trace_path=trace_path)
        result = run_and_grade(task=scenario.task, solver=solver)
        results.append((scenario, result, trace_path))
        mark = "PASS" if result.passed else "FAIL"
        detail = f": {result.reason}: {result.detail}" if result.detail else ""
        print(f"{mark} {name}{detail}", flush=True)

    complete = tuple(scenario.task.name for scenario in scenarios) == TASK_NAMES
    qualifying = _is_run_qualifying(
        selected_run=selected_run,
        complete=complete,
        results=tuple(result for _, result, _ in results),
    )
    exit_code = 0 if qualifying else 1
    duration_seconds = time.monotonic() - started_clock
    manifest = _make_manifest(
        environment=environment,
        results=results,
        started_at=started_at,
        duration_seconds=duration_seconds,
        exit_code=exit_code,
        complete=complete,
        selected_run=selected_run,
        qualifying=qualifying,
    )
    (run_dir / "run.json").write_text(
        f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    print(f"overall: {sum(result.passed for _, result, _ in results)}/{len(results)}")
    if selected_run:
        print("selected-task run cannot qualify", file=sys.stderr)
    elif not complete:
        print("run is incomplete and cannot qualify", file=sys.stderr)
    print(f"raw run: {run_dir}")
    return exit_code


def _make_manifest(
    *,
    environment: EvalEnvironment,
    results: list[tuple[Scenario, Result, Path]],
    started_at: datetime.datetime,
    duration_seconds: float,
    exit_code: int,
    complete: bool,
    selected_run: bool,
    qualifying: bool,
) -> dict[str, Any]:
    task_results = []
    for scenario, result, trace_path in results:
        trace_hash = None
        if trace_path.exists():
            trace_hash = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        task_results.append(
            {
                "name": scenario.task.name,
                "passed": result.passed,
                "reason": result.reason,
                "detail": result.detail,
                "trace": trace_path.name,
                "trace_sha256": trace_hash,
            }
        )
    return {
        "task_schema_version": TASK_SCHEMA_VERSION,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": duration_seconds,
        "commit": environment.commit,
        "clean_worktree": True,
        "git_hunk_executable": str(environment.git_hunk_executable),
        "imported_package": str(environment.imported_package),
        "skill_paths": {
            name: str(path) for name, path in environment.skill_paths.items()
        },
        "skill_sha256": environment.skill_sha256,
        "claude_code_version": environment.claude_code_version,
        "requested_model": MODEL,
        "command_flags": build_command_flags(),
        "permission_policy": "Bash only; git-hunk and git commands only",
        "complete": complete,
        "selected_run": selected_run,
        "qualifying": qualifying,
        "retried": False,
        "tasks": task_results,
        "exit_code": exit_code,
    }


def _is_run_qualifying(
    *,
    selected_run: bool,
    complete: bool,
    results: tuple[Result, ...],
) -> bool:
    return not selected_run and complete and all(result.passed for result in results)


if __name__ == "__main__":
    raise SystemExit(main())
