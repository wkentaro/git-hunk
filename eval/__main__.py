import argparse
import datetime
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eval.config import EFFORT
from eval.config import MODEL
from eval.config import TASK_SCHEMA_VERSION
from eval.environment import EvalEnvironment
from eval.environment import resolve_environment
from eval.grader import SOLVER_ERROR
from eval.harness import PreparedTask
from eval.harness import prepare_task
from eval.model import VARIANTS
from eval.model import EvalVariant
from eval.model import TaskRun
from eval.model import TraceUsage
from eval.model import TranscriptReporter
from eval.model import aggregate_usage
from eval.model import build_command_flags
from eval.model import format_usage
from eval.model import make_claude_solver
from eval.model import read_trace_usage
from eval.scenario import Scenario
from eval.summary import render_summary
from eval.tasks import SCENARIOS


def main(argv: list[str] | None = None) -> int:
    task_names = tuple(scenario.task.name for scenario in SCENARIOS)
    task_list = "\n".join(f"  {name}" for name in task_names)
    parser = argparse.ArgumentParser(
        prog="python -m eval",
        epilog=f"available tasks:\n{task_list}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--task",
        action="append",
        choices=task_names,
        metavar="NAME",
        help="run one named task",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help=(
            "sample every selected task variant N times from the same prepared "
            "state, so the summary reports spread instead of one sample "
            "(default: 1)"
        ),
    )
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    try:
        environment = resolve_environment()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    selected_names = set(args.task or task_names)
    selected = tuple(
        scenario for scenario in SCENARIOS if scenario.task.name in selected_names
    )
    return _run_scenarios(
        environment=environment, scenarios=selected, repeats=args.repeat
    )


def _run_scenarios(
    *,
    environment: EvalEnvironment,
    scenarios: tuple[Scenario, ...],
    repeats: int,
) -> int:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    run_directory_prefix = (
        f"git-hunk-agent-eval-{started_at:%Y%m%dT%H%M%SZ}-{environment.commit[:7]}-"
    )
    run_dir = Path(tempfile.mkdtemp(prefix=run_directory_prefix))
    print(
        f"eval: model={MODEL} effort={EFFORT} "
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
        # One prepared task feeds every repeat, so the repeats differ only in
        # the model run and not in the initial Repository state.
        with prepare_task(scenario.task) as prepared:
            for repeat in range(1, repeats + 1):
                if repeats > 1:
                    print(f"repeat {repeat}/{repeats}: {name}", flush=True)
                results += [
                    _run_variant(
                        scenario=scenario,
                        variant=variant,
                        prepared=prepared,
                        run_dir=run_dir,
                        repeat=repeat,
                        repeats=repeats,
                    )
                    for variant in VARIANTS
                ]

    gate_passed = _gate_passed(results=results)
    exit_code = 0 if gate_passed else 1
    duration_seconds = time.monotonic() - started_clock
    reported_usages = tuple(run.usage for run in results if run.usage is not None)
    total_usage = aggregate_usage(usages=reported_usages)
    manifest = _make_manifest(
        environment=environment,
        results=results,
        repeats=repeats,
        started_at=started_at,
        duration_seconds=duration_seconds,
        exit_code=exit_code,
        gate_passed=gate_passed,
        usage=total_usage,
    )
    (run_dir / "run.json").write_text(
        f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    summary = render_summary(runs=results)
    if summary:
        print()
        print(summary)
        print()
    print(f"artifacts: {run_dir}")
    return exit_code


def _run_variant(
    *,
    scenario: Scenario,
    variant: EvalVariant,
    prepared: PreparedTask,
    run_dir: Path,
    repeat: int,
    repeats: int,
) -> TaskRun:
    print(flush=True)
    name = scenario.task.name
    artifact_stem = _artifact_stem(
        name=name, variant=variant.name, repeat=repeat, repeats=repeats
    )
    trace_path = run_dir / f"{artifact_stem}.jsonl"
    transcript_path = run_dir / f"{artifact_stem}.transcript.txt"
    solver = make_claude_solver(
        task=scenario.task,
        variant=variant,
        trace_path=trace_path,
        transcript_path=transcript_path,
    )
    result = prepared.run_and_grade(solver)
    usage = read_trace_usage(trace_path=trace_path)
    mark = "PASS" if result.passed else "FAIL"
    detail = f": {result.reason}" if result.reason else ""
    if result.detail:
        detail += f": {result.detail}"
    usage_line = (
        format_usage(usage=usage) if usage is not None else "usage: unavailable"
    )
    with transcript_path.open("a", encoding="utf-8") as transcript:
        TranscriptReporter(transcript=transcript).report_result(
            result_line=f"{mark} {name} [{variant.name}]{detail}",
            usage_line=usage_line,
        )
    return TaskRun(
        scenario=scenario,
        variant=variant,
        result=result,
        trace_path=trace_path,
        transcript_path=transcript_path,
        usage=usage,
        repeat=repeat,
    )


def _artifact_stem(*, name: str, variant: str, repeat: int, repeats: int) -> str:
    # A single-repeat run keeps the unsuffixed artifact names, so its printed
    # output and artifacts match runs made before repeats existed.
    suffix = f".r{repeat}" if repeats > 1 else ""
    return f"{name}.{variant}{suffix}"


def _gate_passed(*, results: list[TaskRun]) -> bool:
    if any(run.result.reason == SOLVER_ERROR for run in results):
        return False
    return all(run.result.passed for run in results if run.variant.subject_under_test)


def _make_manifest(
    *,
    environment: EvalEnvironment,
    results: list[TaskRun],
    repeats: int,
    started_at: datetime.datetime,
    duration_seconds: float,
    exit_code: int,
    gate_passed: bool,
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
                "variant": run.variant.name,
                "repeat": run.repeat,
                "passed": run.result.passed,
                "reason": run.result.reason,
                "detail": run.result.detail,
                "usage": run.usage.to_dict() if run.usage is not None else None,
                "trace": run.trace_path.name,
                "trace_sha256": trace_hash,
                "transcript": run.transcript_path.name,
                "transcript_sha256": transcript_hash,
                "command_flags": build_command_flags(variant=run.variant),
                "permission_policy": run.variant.permission_policy,
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
        "requested_effort": EFFORT,
        "repeats": repeats,
        "gate_passed": gate_passed,
        "usage": usage.to_dict() if usage is not None else None,
        "tasks": task_results,
        "exit_code": exit_code,
    }


if __name__ == "__main__":
    raise SystemExit(main())
