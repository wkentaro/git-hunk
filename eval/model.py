import dataclasses
import datetime
import json
import math
import subprocess
import time
from collections.abc import Iterable
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from typing import Final
from typing import TextIO
from typing import cast

from eval.config import MODEL
from eval.grader import Result
from eval.repo import GitRepo
from eval.scenario import Scenario
from eval.scenario import Solver
from eval.task import Task


@dataclasses.dataclass(frozen=True)
class EvalVariant:
    name: str
    tool_instruction: str
    allowed_tools: tuple[str, ...]
    permission_policy: str
    subject_under_test: bool


VARIANTS: Final = (
    EvalVariant(
        name="git-hunk",
        tool_instruction=(
            "Run `git-hunk skills get core logical-commits` and follow both skills."
        ),
        allowed_tools=("Bash(git-hunk:*)", "Bash(git:*)"),
        permission_policy="Bash only; git-hunk and git commands only",
        subject_under_test=True,
    ),
    EvalVariant(
        name="bare-git",
        tool_instruction="Use only Git commands; do not use `git-hunk`.",
        allowed_tools=("Bash(git:*)",),
        permission_policy="Bash only; git commands only",
        subject_under_test=False,
    ),
)


@dataclasses.dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int

    def to_dict(self) -> dict[str, int]:
        return {
            "input": self.input_tokens,
            "cache_creation_input": self.cache_creation_input_tokens,
            "cache_read_input": self.cache_read_input_tokens,
            "output": self.output_tokens,
        }

    @classmethod
    def total(cls, usages: list["TokenUsage"]) -> "TokenUsage":
        return cls(
            input_tokens=sum(usage.input_tokens for usage in usages),
            cache_creation_input_tokens=sum(
                usage.cache_creation_input_tokens for usage in usages
            ),
            cache_read_input_tokens=sum(
                usage.cache_read_input_tokens for usage in usages
            ),
            output_tokens=sum(usage.output_tokens for usage in usages),
        )


@dataclasses.dataclass(frozen=True)
class ModelUsage:
    tokens: TokenUsage
    web_search_requests: int
    cost_usd: float
    context_window: int
    max_output_tokens: int
    canonical_model: str | None
    provider: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens.to_dict(),
            "web_search_requests": self.web_search_requests,
            "cost_usd": self.cost_usd,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "canonical_model": self.canonical_model,
            "provider": self.provider,
        }


@dataclasses.dataclass(frozen=True)
class TraceUsage:
    duration_seconds: float
    api_duration_seconds: float
    turns: int
    tool_calls: int
    cost_usd: float
    tokens: TokenUsage
    models: dict[str, ModelUsage]

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "api_duration_seconds": self.api_duration_seconds,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "cost_usd": self.cost_usd,
            "tokens": self.tokens.to_dict(),
            "models": {name: usage.to_dict() for name, usage in self.models.items()},
        }


@dataclasses.dataclass(frozen=True)
class TaskRun:
    scenario: Scenario
    variant: EvalVariant
    result: Result
    trace_path: Path
    transcript_path: Path
    usage: TraceUsage | None
    # 1-based index of this sample within its task variant's repeats.
    repeat: int


def build_prompt(*, task_prompt: str, variant: EvalVariant) -> str:
    preamble = (
        "There are uncommitted changes in this Git repository. "
        f"{variant.tool_instruction} "
        "Organize the working tree into a clean series of focused commits."
    )
    if not task_prompt:
        return preamble
    return f"{preamble}\n\n{task_prompt}"


def build_command_flags(*, variant: EvalVariant) -> list[str]:
    return [
        "--model",
        MODEL,
        "--tools",
        "Bash",
        "--allowedTools",
        *variant.allowed_tools,
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


def build_command(*, prompt: str, variant: EvalVariant) -> list[str]:
    return ["claude", "-p", prompt, *build_command_flags(variant=variant)]


def make_claude_solver(
    *,
    task: Task,
    variant: EvalVariant,
    trace_path: Path,
    transcript_path: Path,
) -> Solver:
    prompt = build_prompt(task_prompt=task.prompt, variant=variant)

    def solve(repo: GitRepo) -> None:
        run_claude(
            repo=repo,
            prompt=prompt,
            variant=variant,
            trace_path=trace_path,
            transcript_path=transcript_path,
        )

    return solve


def run_claude(
    *,
    repo: GitRepo,
    prompt: str,
    variant: EvalVariant,
    trace_path: Path,
    transcript_path: Path,
) -> None:
    MODEL_TIMEOUT_SECONDS: Final = 30 * 60
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    with transcript_path.open("w", encoding="utf-8") as transcript:
        reporter = TranscriptReporter(transcript=transcript)
        reporter.report_variant(variant=variant)
        reporter.report_prompt(prompt=prompt)
        reporter.report_tool_calls_header()
        try:
            result = repo.run_stream(
                *build_command(prompt=prompt, variant=variant),
                timeout_seconds=MODEL_TIMEOUT_SECONDS,
                on_stdout_line=reporter.consume_line,
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


class TranscriptReporter:
    def __init__(self, *, transcript: TextIO) -> None:
        self._transcript = transcript

    def report_variant(self, *, variant: EvalVariant) -> None:
        self._emit(f"variant: {variant.name}")

    def report_prompt(self, *, prompt: str) -> None:
        self._emit("prompt:")
        for line in prompt.splitlines():
            self._emit(f"  {line}")

    def report_tool_calls_header(self) -> None:
        self._emit("tool calls:")

    def report_result(self, *, result_line: str, usage_line: str) -> None:
        self._emit("result:")
        self._emit(f"  {result_line}")
        self._emit(f"  {usage_line}")

    def consume_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        for block in _iter_message_blocks(events=[event]):
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                self._report_tool_use(block=block)

    def _report_tool_use(self, *, block: dict[str, Any]) -> None:
        tool_input = block.get("input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return
        command_lines = command.rstrip().splitlines()
        if not command_lines:
            return
        self._emit(f"  - {command_lines[0]}")
        for command_line in command_lines[1:]:
            self._emit(f"    {command_line}")

    def _emit(self, line: str) -> None:
        print(line, flush=True)
        self._transcript.write(f"{line}\n")
        self._transcript.flush()


def read_trace_usage(*, trace_path: Path) -> TraceUsage | None:
    try:
        events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
    except (OSError, json.JSONDecodeError):
        return None
    result_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "result"
    ]
    if len(result_events) != 1:
        return None
    return _parse_trace_usage(
        result_event=result_events[0],
        tool_calls=_count_tool_calls(events=events),
    )


def _iter_message_blocks(*, events: Iterable[Any]) -> Iterator[dict[str, Any]]:
    # The single place that knows how a trace nests content blocks inside its
    # stream events, so a schema change lands in one walk rather than four.
    for event in events:
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                yield cast("dict[str, Any]", block)


def _count_tool_calls(*, events: Iterable[Any]) -> int:
    assistant_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "assistant"
    ]
    # Identify a call by its tool-use ID so a re-streamed assistant message
    # cannot inflate the count.
    return len(
        {
            tool_use_id
            for block in _iter_message_blocks(events=assistant_events)
            if block.get("type") == "tool_use"
            and isinstance((tool_use_id := block.get("id")), str)
            and tool_use_id
        }
    )


def _parse_trace_usage(
    *, result_event: dict[str, Any], tool_calls: int
) -> TraceUsage | None:
    duration_ms = _nonnegative_number(result_event.get("duration_ms"))
    api_duration_ms = _nonnegative_number(result_event.get("duration_api_ms"))
    turns = _nonnegative_int(result_event.get("num_turns"))
    cost_usd = _nonnegative_number(result_event.get("total_cost_usd"))
    raw_usage = result_event.get("usage")
    if (
        duration_ms is None
        or api_duration_ms is None
        or turns is None
        or cost_usd is None
        or not isinstance(raw_usage, dict)
    ):
        return None
    tokens = _parse_token_usage(
        raw_usage=cast("dict[str, Any]", raw_usage),
        input_key="input_tokens",
        cache_creation_key="cache_creation_input_tokens",
        cache_read_key="cache_read_input_tokens",
        output_key="output_tokens",
    )
    if tokens is None:
        return None
    models = _parse_model_usage(result_event.get("modelUsage"))
    return TraceUsage(
        duration_seconds=duration_ms / 1000,
        api_duration_seconds=api_duration_ms / 1000,
        turns=turns,
        tool_calls=tool_calls,
        cost_usd=cost_usd,
        tokens=tokens,
        models=models,
    )


def _parse_token_usage(
    *,
    raw_usage: dict[str, Any],
    input_key: str,
    cache_creation_key: str,
    cache_read_key: str,
    output_key: str,
) -> TokenUsage | None:
    input_tokens = _nonnegative_int(raw_usage.get(input_key))
    cache_creation_input_tokens = _nonnegative_int(raw_usage.get(cache_creation_key))
    cache_read_input_tokens = _nonnegative_int(raw_usage.get(cache_read_key))
    output_tokens = _nonnegative_int(raw_usage.get(output_key))
    if (
        input_tokens is None
        or cache_creation_input_tokens is None
        or cache_read_input_tokens is None
        or output_tokens is None
    ):
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        output_tokens=output_tokens,
    )


def _parse_model_usage(raw_models: object) -> dict[str, ModelUsage]:
    if not isinstance(raw_models, dict):
        return {}
    models: dict[str, ModelUsage] = {}
    for name, raw_model_usage in cast("dict[object, object]", raw_models).items():
        if not isinstance(name, str) or not isinstance(raw_model_usage, dict):
            continue
        raw_usage = cast("dict[str, Any]", raw_model_usage)
        tokens = _parse_token_usage(
            raw_usage=raw_usage,
            input_key="inputTokens",
            cache_creation_key="cacheCreationInputTokens",
            cache_read_key="cacheReadInputTokens",
            output_key="outputTokens",
        )
        web_search_requests = _nonnegative_int(raw_usage.get("webSearchRequests"))
        cost_usd = _nonnegative_number(raw_usage.get("costUSD"))
        context_window = _nonnegative_int(raw_usage.get("contextWindow"))
        max_output_tokens = _nonnegative_int(raw_usage.get("maxOutputTokens"))
        canonical_model = raw_usage.get("canonicalModel")
        provider = raw_usage.get("provider")
        if (
            tokens is None
            or web_search_requests is None
            or cost_usd is None
            or context_window is None
            or max_output_tokens is None
            or (canonical_model is not None and not isinstance(canonical_model, str))
            or (provider is not None and not isinstance(provider, str))
        ):
            continue
        models[name] = ModelUsage(
            tokens=tokens,
            web_search_requests=web_search_requests,
            cost_usd=cost_usd,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            canonical_model=canonical_model,
            provider=provider,
        )
    return models


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nonnegative_number(value: object) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    return float(value)


def format_usage(*, usage: TraceUsage) -> str:
    duration = usage.duration_seconds
    tokens = usage.tokens
    return (
        f"usage: {duration:.1f}s · {usage.turns} turns · "
        f"{usage.tool_calls} tool calls · tokens "
        f"{_format_token_count(tokens.input_tokens)} input / "
        f"{_format_token_count(tokens.cache_creation_input_tokens)} cache-write / "
        f"{_format_token_count(tokens.cache_read_input_tokens)} cache-read / "
        f"{_format_token_count(tokens.output_tokens)} output · ${usage.cost_usd:.4f}"
    )


def _format_token_count(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}m"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def aggregate_usage(*, usages: tuple[TraceUsage, ...]) -> TraceUsage | None:
    if not usages:
        return None
    model_names = {name for usage in usages for name in usage.models}
    models: dict[str, ModelUsage] = {}
    for name in sorted(model_names):
        model_usages = [usage.models[name] for usage in usages if name in usage.models]
        first = model_usages[0]
        models[name] = ModelUsage(
            tokens=TokenUsage.total([usage.tokens for usage in model_usages]),
            web_search_requests=sum(
                usage.web_search_requests for usage in model_usages
            ),
            cost_usd=sum(usage.cost_usd for usage in model_usages),
            context_window=first.context_window,
            max_output_tokens=first.max_output_tokens,
            canonical_model=first.canonical_model,
            provider=first.provider,
        )
    return TraceUsage(
        duration_seconds=sum(usage.duration_seconds for usage in usages),
        api_duration_seconds=sum(usage.api_duration_seconds for usage in usages),
        turns=sum(usage.turns for usage in usages),
        tool_calls=sum(usage.tool_calls for usage in usages),
        cost_usd=sum(usage.cost_usd for usage in usages),
        tokens=TokenUsage.total([usage.tokens for usage in usages]),
        models=models,
    )


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

    bash_tool_use_ids: set[str] = set()
    for block in _iter_message_blocks(events=assistant_events):
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
    return {
        tool_use_id
        for block in _iter_message_blocks(events=events)
        if block.get("type") == "tool_result"
        and isinstance((tool_use_id := block.get("tool_use_id")), str)
        and tool_use_id
    }
