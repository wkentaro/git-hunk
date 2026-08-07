import datetime
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any
from typing import Final
from typing import cast

from eval.config import MODEL
from eval.repo import GitRepo
from eval.scenario import Solver
from eval.task import Task

DEFAULT_ALLOWED_TOOLS: Final = ("Bash(git-hunk:*)", "Bash(git:*)")


def build_prompt(*, task_prompt: str) -> str:
    preamble = (
        "There are uncommitted changes in this Git repository. Run "
        "`git-hunk skills get core logical-commits` and follow both skills. "
        "Organize the working tree into a clean series of focused commits."
    )
    if not task_prompt:
        return preamble
    return f"{preamble}\n\n{task_prompt}"


def build_command_flags(
    *, allowed_tools: tuple[str, ...] = DEFAULT_ALLOWED_TOOLS
) -> list[str]:
    return [
        "--model",
        MODEL,
        "--tools",
        "Bash",
        "--allowedTools",
        *allowed_tools,
        "--permission-mode",
        "dontAsk",
        "--safe-mode",
        "--no-session-persistence",
        "--no-chrome",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def build_command(
    *,
    prompt: str,
    allowed_tools: tuple[str, ...] = DEFAULT_ALLOWED_TOOLS,
    append_system_prompt: str | None = None,
) -> list[str]:
    command = [
        "claude",
        "-p",
        prompt,
        *build_command_flags(allowed_tools=allowed_tools),
    ]
    if append_system_prompt is not None:
        command.extend(["--append-system-prompt", append_system_prompt])
    return command


def make_claude_solver(*, task: Task, trace_path: Path) -> Solver:
    prompt = build_prompt(task_prompt=task.prompt)

    def solve(repo: GitRepo) -> None:
        run_claude(repo=repo, prompt=prompt, trace_path=trace_path)

    return solve


def run_claude(
    *,
    repo: GitRepo,
    prompt: str,
    trace_path: Path,
    allowed_tools: tuple[str, ...] = DEFAULT_ALLOWED_TOOLS,
    append_system_prompt: str | None = None,
) -> None:
    MODEL_TIMEOUT_SECONDS: Final = 30 * 60
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    try:
        result = repo.run(
            *build_command(
                prompt=prompt,
                allowed_tools=allowed_tools,
                append_system_prompt=append_system_prompt,
            ),
            timeout_seconds=MODEL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        duration_seconds = time.monotonic() - started_clock
        raw_trace = error.stdout or ""
        if isinstance(raw_trace, bytes):
            raw_trace = raw_trace.decode(errors="replace")
        raw_trace, incomplete_output = _separate_trace_output(raw_trace=raw_trace)
        _write_trace(
            trace_path=trace_path,
            raw_trace=raw_trace,
            started_at=started_at,
            duration_seconds=duration_seconds,
            exit_code=124,
            incomplete_output=incomplete_output,
        )
        raise RuntimeError(
            f"claude timed out after {MODEL_TIMEOUT_SECONDS} seconds"
        ) from error

    duration_seconds = time.monotonic() - started_clock
    _write_trace(
        trace_path=trace_path,
        raw_trace=result.stdout,
        started_at=started_at,
        duration_seconds=duration_seconds,
        exit_code=result.returncode,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}: {result.stderr.strip()}"
        )
    validate_trace(trace_path=trace_path)


def _write_trace(
    *,
    trace_path: Path,
    raw_trace: str,
    started_at: datetime.datetime,
    duration_seconds: float,
    exit_code: int,
    incomplete_output: str | None = None,
) -> None:
    metadata = {
        "type": "eval_metadata",
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": duration_seconds,
        "exit_code": exit_code,
    }
    if incomplete_output is not None:
        metadata["incomplete_output"] = incomplete_output
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_trace and not raw_trace.endswith("\n"):
        raw_trace += "\n"
    trace_path.write_text(
        f"{raw_trace}{json.dumps(metadata, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _separate_trace_output(*, raw_trace: str) -> tuple[str, str | None]:
    lines = raw_trace.splitlines()
    if not lines:
        return "", None
    try:
        json.loads(lines[-1])
    except json.JSONDecodeError:
        incomplete_output = lines.pop()
    else:
        incomplete_output = None
    return "\n".join(lines), incomplete_output


def validate_trace(*, trace_path: Path) -> None:
    events = read_trace_events(trace_path=trace_path)
    validate_trace_events(events=events)


def read_trace_events(*, trace_path: Path) -> list[dict[str, Any]]:
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError(f"missing trace {trace_path}: {error}") from error

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"malformed JSON in trace line {line_number}: {error.msg}"
            ) from error
        if not isinstance(event, dict):
            raise RuntimeError(f"trace line {line_number} is not a JSON object")
        events.append(cast("dict[str, Any]", event))

    return events


def validate_trace_events(*, events: list[dict[str, Any]]) -> None:
    assistant_events = [event for event in events if event.get("type") == "assistant"]
    if not assistant_events:
        raise RuntimeError("trace is missing assistant turns")

    reported_models = {
        model
        for event in assistant_events
        if isinstance((message := event.get("message")), dict)
        and isinstance((model := message.get("model")), str)
    }
    if reported_models != {MODEL}:
        raise RuntimeError(
            f"reported model must be {MODEL!r}, got {sorted(reported_models)!r}"
        )

    content_blocks = [
        block
        for event in assistant_events
        if isinstance((message := event.get("message")), dict)
        and isinstance((content := message.get("content")), list)
        for block in content
        if isinstance(block, dict)
    ]
    bash_tool_use_ids: set[str] = set()
    for block in content_blocks:
        if block.get("type") != "tool_use" or block.get("name") != "Bash":
            continue
        tool_use_id = block.get("id")
        tool_input = block.get("input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(tool_use_id, str) or not tool_use_id:
            raise RuntimeError("Bash tool input is missing its tool-use ID")
        if not isinstance(command, str) or not command.strip():
            raise RuntimeError("Bash tool input must contain a nonempty command")
        bash_tool_use_ids.add(tool_use_id)
    if not bash_tool_use_ids:
        raise RuntimeError("trace is missing Bash tool input")

    tool_result_ids = _read_tool_result_ids(events=events)
    missing_results = bash_tool_use_ids - tool_result_ids
    if missing_results:
        raise RuntimeError(
            f"trace is missing tool results for {sorted(missing_results)!r}"
        )

    result_events = [event for event in events if event.get("type") == "result"]
    if len(result_events) != 1:
        raise RuntimeError(
            f"trace must have one result event, got {len(result_events)}"
        )
    result_event = result_events[0]
    if result_event.get("subtype") != "success":
        raise RuntimeError(f"trace result is not successful: {result_event!r}")

    metadata_events = [
        event for event in events if event.get("type") == "eval_metadata"
    ]
    if len(metadata_events) != 1:
        raise RuntimeError(
            f"trace must have one eval metadata event, got {len(metadata_events)}"
        )
    metadata = metadata_events[0]
    raw_started_at = metadata.get("started_at")
    if not isinstance(raw_started_at, str):
        raise RuntimeError("trace metadata needs a UTC started_at")
    normalized_started_at = (
        f"{raw_started_at[:-1]}+00:00"
        if raw_started_at.endswith("Z")
        else raw_started_at
    )
    try:
        parsed_started_at = datetime.datetime.fromisoformat(normalized_started_at)
    except (TypeError, ValueError) as error:
        raise RuntimeError("trace metadata needs a UTC started_at") from error
    if (
        parsed_started_at.tzinfo is None
        or parsed_started_at.utcoffset() != datetime.timedelta(0)
    ):
        raise RuntimeError("trace metadata needs a UTC started_at")

    duration_seconds = metadata.get("duration_seconds")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or duration_seconds < 0
    ):
        raise RuntimeError("trace metadata needs a finite nonnegative duration")

    exit_code = metadata.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RuntimeError("trace metadata needs an integer exit code")
    if exit_code != 0:
        raise RuntimeError("trace metadata has a nonzero exit code")


def _read_tool_result_ids(*, events: list[dict[str, Any]]) -> set[str]:
    tool_result_ids: set[str] = set()
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")
            if isinstance(tool_use_id, str) and tool_use_id:
                tool_result_ids.add(tool_use_id)
    return tool_result_ids
