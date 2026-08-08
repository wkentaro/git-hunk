import argparse
import dataclasses
import datetime
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eval.config import MODEL
from eval.config import TASK_SCHEMA_VERSION
from eval.environment import EvalEnvironment
from eval.environment import resolve_environment
from eval.grader import Result
from eval.harness import run_and_grade
from eval.model import TraceUsage
from eval.model import TranscriptReporter
from eval.model import aggregate_usage
from eval.model import build_command_flags
from eval.model import format_usage
from eval.model import make_claude_solver
from eval.model import read_trace_usage
from eval.scenario import Scenario
from eval.tasks import SCENARIOS


@dataclasses.dataclass(frozen=True)
class TaskRun:
    scenario: Scenario
    result: Result
    trace_path: Path
    transcript_path: Path
    usage: TraceUsage | None


def main(argv: list[str] | None = None) -> int:
    task_names = tuple(scenario.task.name for scenario in SCENARIOS)
    parser = argparse.ArgumentParser(prog="python -m eval")
    parser.add_argument(
        "--task",
        action="append",
        choices=task_names,
        metavar="NAME",
        help="run one named task",
    )
    args = parser.parse_args(argv)

    try:
        environment = resolve_environment()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    selected_names = set(args.task or task_names)
    selected = tuple(
        scenario for scenario in SCENARIOS if scenario.task.name in selected_names
    )
    return _run_scenarios(environment=environment, scenarios=selected)


def _run_scenarios(
    *,
    environment: EvalEnvironment,
    scenarios: tuple[Scenario, ...],
) -> int:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    run_directory_prefix = (
        f"git-hunk-agent-eval-{started_at:%Y%m%dT%H%M%SZ}-{environment.commit[:7]}-"
    )
    run_dir = Path(tempfile.mkdtemp(prefix=run_directory_prefix))
    print(
        f"eval: model={MODEL} "
        f"claude={environment.claude_code_version.split()[0]} "
        f"commit={environment.commit[:7]} dirty={str(environment.dirty).lower()}",
        flush=True,
    )
    results: list[TaskRun] = []
    multiple_tasks = len(scenarios) > 1

    for index, scenario in enumerate(scenarios, start=1):
        name = scenario.task.name
        progress = f" {index}/{len(scenarios)}" if multiple_tasks else ""
        print(f"running{progress}: {name}", flush=True)
        trace_path = run_dir / f"{name}.jsonl"
        transcript_path = run_dir / f"{name}.transcript.txt"
        solver = make_claude_solver(
            task=scenario.task,
            trace_path=trace_path,
            transcript_path=transcript_path,
        )
        result = run_and_grade(task=scenario.task, solver=solver)
        usage = read_trace_usage(trace_path=trace_path)
        mark = "PASS" if result.passed else "FAIL"
        detail = f": {result.reason}: {result.detail}" if result.detail else ""
        result_line = f"{mark} {name}{detail}"
        usage_line = (
            format_usage(usage=usage) if usage is not None else "usage: unavailable"
        )
        with transcript_path.open("a", encoding="utf-8") as transcript:
            TranscriptReporter(transcript=transcript).report_result(
                result_line=result_line,
                usage_line=usage_line,
            )
        results.append(
            TaskRun(
                scenario=scenario,
                result=result,
                trace_path=trace_path,
                transcript_path=transcript_path,
                usage=usage,
            )
        )

    passed = sum(run.result.passed for run in results)
    run_passed = passed == len(results)
    exit_code = 0 if run_passed else 1
    duration_seconds = time.monotonic() - started_clock
    reported_usages = tuple(run.usage for run in results if run.usage is not None)
    total_usage = aggregate_usage(usages=reported_usages)
    manifest = _make_manifest(
        environment=environment,
        results=results,
        started_at=started_at,
        duration_seconds=duration_seconds,
        exit_code=exit_code,
        passed=run_passed,
        usage=total_usage,
    )
    (run_dir / "run.json").write_text(
        f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    if multiple_tasks:
        overall_mark = "PASS" if run_passed else "FAIL"
        print(f"overall: {overall_mark} {passed}/{len(results)}")
        if total_usage is None:
            print("usage: unavailable")
        else:
            total_usage_line = format_usage(usage=total_usage)
            if len(reported_usages) != len(results):
                total_usage_line += (
                    f" ({len(reported_usages)}/{len(results)} tasks reported)"
                )
            print(total_usage_line)
    print(f"artifacts: {run_dir}")
    return exit_code


def _make_manifest(
    *,
    environment: EvalEnvironment,
    results: list[TaskRun],
    started_at: datetime.datetime,
    duration_seconds: float,
    exit_code: int,
    passed: bool,
    usage: TraceUsage | None,
) -> dict[str, Any]:
    task_results = []
    for run in results:
        trace_hash = None
        if run.trace_path.exists():
            trace_hash = hashlib.sha256(run.trace_path.read_bytes()).hexdigest()
        transcript_hash = None
        if run.transcript_path.exists():
            transcript_hash = hashlib.sha256(
                run.transcript_path.read_bytes()
            ).hexdigest()
        task_results.append(
            {
                "name": run.scenario.task.name,
                "passed": run.result.passed,
                "reason": run.result.reason,
                "detail": run.result.detail,
                "usage": run.usage.to_dict() if run.usage is not None else None,
                "trace": run.trace_path.name,
                "trace_sha256": trace_hash,
                "transcript": run.transcript_path.name,
                "transcript_sha256": transcript_hash,
            }
        )
    return {
        "task_schema_version": TASK_SCHEMA_VERSION,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": duration_seconds,
        "commit": environment.commit,
        "clean_worktree": not environment.dirty,
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
        "passed": passed,
        "usage": usage.to_dict() if usage is not None else None,
        "tasks": task_results,
        "exit_code": exit_code,
    }


if __name__ == "__main__":
    raise SystemExit(main())
