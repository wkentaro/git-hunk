import copy
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import NoReturn

import pytest

from eval.config import EFFORT
from eval.config import MODEL
from eval.model import VARIANTS
from eval.model import aggregate_usage
from eval.model import build_command
from eval.model import build_prompt
from eval.model import format_usage
from eval.model import read_trace_usage
from eval.model import run_claude
from eval.model import validate_trace
from eval.repo import GitRepo


@pytest.fixture
def trace_events() -> list[dict[str, Any]]:
    return [
        {
            "type": "assistant",
            "message": {
                "model": MODEL,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Bash",
                        "input": {"command": "git status"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "",
                    }
                ]
            },
        },
        {"type": "result", "subtype": "success", "total_cost_usd": 0.1},
        {
            "type": "eval_metadata",
            "started_at": "2026-08-07T00:00:00Z",
            "duration_seconds": 1.5,
            "exit_code": 0,
        },
    ]


def _write_trace(*, trace_path: Path, events: list[dict[str, Any]]) -> None:
    trace_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )


def test_variant_prompts_differ_only_by_tool_instruction() -> None:
    task_prompt = "Keep unrelated work in place."
    git_hunk_variant, bare_git_variant = VARIANTS
    git_hunk_prompt = build_prompt(
        task_prompt=task_prompt,
        variant=git_hunk_variant,
    )
    bare_git_prompt = build_prompt(
        task_prompt=task_prompt,
        variant=bare_git_variant,
    )

    git_hunk_instruction = (
        "Run `git-hunk skills get core logical-commits` and follow both skills."
    )
    bare_git_instruction = "Use only Git commands; do not use `git-hunk`."
    assert git_hunk_instruction in git_hunk_prompt
    assert bare_git_instruction in bare_git_prompt
    assert git_hunk_prompt.replace(
        git_hunk_instruction, "<tool instruction>"
    ) == bare_git_prompt.replace(bare_git_instruction, "<tool instruction>")
    assert git_hunk_prompt.endswith(task_prompt)
    assert bare_git_prompt.endswith(task_prompt)


def test_command_pins_model_and_isolates_claude() -> None:
    git_hunk_variant, bare_git_variant = VARIANTS
    command = build_command(prompt="Do the task", variant=git_hunk_variant)

    assert command[:3] == ["claude", "-p", "Do the task"]
    assert command[command.index("--model") + 1] == MODEL
    assert command[command.index("--effort") + 1] == EFFORT
    assert command[command.index("--tools") + 1] == "Bash"
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert command[command.index("--output-format") + 1] == "stream-json"
    assert command[command.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "--verbose" in command
    assert "--safe-mode" in command
    assert "--no-session-persistence" in command
    assert "--no-chrome" in command
    assert "--strict-mcp-config" in command
    allowed_index = command.index("--allowedTools")
    assert command[allowed_index + 1 : allowed_index + 3] == [
        "Bash(git-hunk:*)",
        "Bash(git:*)",
    ]

    bare_git_command = build_command(prompt="Do the task", variant=bare_git_variant)
    bare_allowed_index = bare_git_command.index("--allowedTools")
    assert bare_git_command[bare_allowed_index + 1 : bare_allowed_index + 2] == [
        "Bash(git:*)"
    ]
    assert "Bash(git-hunk:*)" not in bare_git_command


def test_validate_trace_accepts_complete_trace(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path=trace_path, events=trace_events)

    validate_trace(trace_path=trace_path)


@pytest.mark.parametrize(
    "events,error",
    [
        ([{"type": "not-json"}], "missing assistant"),
        (
            [
                {
                    "type": "assistant",
                    "message": {"model": "opus", "content": []},
                }
            ],
            "reported model",
        ),
    ],
)
def test_validate_trace_rejects_incomplete_or_wrong_model(
    tmp_path: Path, events: list[dict[str, Any]], error: str
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path=trace_path, events=events)

    with pytest.raises(RuntimeError, match=error):
        validate_trace(trace_path=trace_path)


def test_validate_trace_rejects_malformed_json(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed JSON"):
        validate_trace(trace_path=trace_path)


def test_validate_trace_rejects_empty_bash_command(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_events[0]["message"]["content"][0]["input"] = {"command": ""}
    _write_trace(trace_path=trace_path, events=trace_events)

    with pytest.raises(RuntimeError, match="nonempty command"):
        validate_trace(trace_path=trace_path)


def test_validate_trace_rejects_unmatched_tool_result(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_events[1]["message"]["content"][0]["tool_use_id"] = "other-tool"
    _write_trace(trace_path=trace_path, events=trace_events)

    with pytest.raises(RuntimeError, match="missing tool results"):
        validate_trace(trace_path=trace_path)


@pytest.mark.parametrize(
    ("result_events", "error"),
    [
        ([], "one result event"),
        (
            [
                {"type": "result", "subtype": "success"},
                {"type": "result", "subtype": "success"},
            ],
            "one result event",
        ),
        ([{"type": "result", "subtype": "error"}], "not successful"),
    ],
)
def test_validate_trace_rejects_invalid_result_events(
    tmp_path: Path,
    trace_events: list[dict[str, Any]],
    result_events: list[dict[str, Any]],
    error: str,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_events[2:3] = result_events
    _write_trace(trace_path=trace_path, events=trace_events)

    with pytest.raises(RuntimeError, match=error):
        validate_trace(trace_path=trace_path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("started_at", None, "UTC started_at"),
        ("started_at", "2026-08-07T00:00:00", "UTC started_at"),
        ("duration_seconds", -1, "finite nonnegative duration"),
        ("duration_seconds", float("nan"), "finite nonnegative duration"),
        ("exit_code", None, "integer exit code"),
        ("exit_code", 1, "nonzero exit code"),
    ],
)
def test_validate_trace_rejects_invalid_metadata(
    tmp_path: Path,
    trace_events: list[dict[str, Any]],
    field: str,
    value: object,
    error: str,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_events[-1][field] = value
    _write_trace(trace_path=trace_path, events=trace_events)

    with pytest.raises(RuntimeError, match=error):
        validate_trace(trace_path=trace_path)


def test_run_claude_writes_partial_trace_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial_trace = (
        '{"type":"assistant","message":{"model":"partial"}}\n{"type":"assistant"'
    )

    def raise_timeout(*args: str, **kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired(
            cmd="claude",
            timeout=1800,
            output=partial_trace,
        )

    repo = GitRepo(tmp_path)
    monkeypatch.setattr(repo, "run_stream", raise_timeout)
    trace_path = tmp_path / "trace.jsonl"
    transcript_path = tmp_path / "transcript.txt"

    with pytest.raises(RuntimeError, match="timed out after 1800 seconds"):
        run_claude(
            repo=repo,
            prompt="Do the task",
            variant=VARIANTS[0],
            trace_path=trace_path,
            transcript_path=transcript_path,
        )

    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert events[0]["type"] == "assistant"
    assert events[-1]["type"] == "eval_metadata"
    assert events[-1]["exit_code"] == 124
    assert events[-1]["incomplete_output"] == '{"type":"assistant"'


def test_run_claude_streams_tool_calls_without_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    trace_events: list[dict[str, Any]],
) -> None:
    trace_events[1]["message"]["content"][0].update(
        {"content": "command output stays in JSONL", "is_error": True}
    )
    trace_events[2:2] = [
        {
            "type": "assistant",
            "message": {
                "model": MODEL,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-2",
                        "name": "Bash",
                        "input": {"command": "git diff"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-2",
                        "content": " \n\n",
                    }
                ]
            },
        },
    ]
    raw_trace = "".join(f"{json.dumps(event)}\n" for event in trace_events[:-1])

    def run_stream(
        *args: str,
        timeout_seconds: float,
        on_stdout_line: Callable[[str], None],
    ) -> subprocess.CompletedProcess[str]:
        del timeout_seconds
        for line in raw_trace.splitlines(keepends=True):
            on_stdout_line(line)
        return subprocess.CompletedProcess(args, 0, raw_trace, "")

    repo = GitRepo(tmp_path)
    monkeypatch.setattr(repo, "run_stream", run_stream, raising=False)
    trace_path = tmp_path / "trace.jsonl"
    transcript_path = tmp_path / "transcript.txt"

    run_claude(
        repo=repo,
        prompt="First line.\n\nSecond line.",
        variant=VARIANTS[0],
        trace_path=trace_path,
        transcript_path=transcript_path,
    )

    expected = "\n".join(
        [
            "variant: git-hunk",
            "prompt:",
            "  First line.",
            "  ",
            "  Second line.",
            "tool calls:",
            "  - git status",
            "  - git diff",
        ]
    )
    assert capsys.readouterr().out.rstrip() == expected
    assert transcript_path.read_text(encoding="utf-8").rstrip() == expected


def test_trace_usage_has_stable_shape_and_compact_format(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_events[2].update(
        {
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
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 16,
                    "cacheCreationInputTokens": 8434,
                    "cacheReadInputTokens": 59782,
                    "outputTokens": 1327,
                    "webSearchRequests": 0,
                    "costUSD": 0.0891406,
                    "contextWindow": 1_000_000,
                    "maxOutputTokens": 64_000,
                    "canonicalModel": "claude-sonnet-5",
                    "provider": "firstParty",
                }
            },
        }
    )
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path=trace_path, events=trace_events)

    usage = read_trace_usage(trace_path=trace_path)

    assert usage is not None
    assert usage.to_dict() == {
        "duration_seconds": 22.67,
        "api_duration_seconds": 22.618,
        "turns": 8,
        "tool_calls": 1,
        "cost_usd": 0.0891406,
        "tokens": {
            "input": 16,
            "cache_creation_input": 8434,
            "cache_read_input": 59782,
            "output": 1327,
        },
        "models": {
            "claude-sonnet-5": {
                "tokens": {
                    "input": 16,
                    "cache_creation_input": 8434,
                    "cache_read_input": 59782,
                    "output": 1327,
                },
                "web_search_requests": 0,
                "cost_usd": 0.0891406,
                "context_window": 1_000_000,
                "max_output_tokens": 64_000,
                "canonical_model": "claude-sonnet-5",
                "provider": "firstParty",
            }
        },
    }
    assert format_usage(usage=usage) == (
        "usage: 22.7s · 8 turns · 1 tool calls · tokens 16 input / "
        "8.4k cache-write / 59.8k cache-read / 1.3k output · $0.0891"
    )

    total = aggregate_usage(usages=(usage, usage))

    assert total is not None
    assert total.to_dict()["tokens"] == {
        "input": 32,
        "cache_creation_input": 16868,
        "cache_read_input": 119564,
        "output": 2654,
    }
    assert total.models["claude-sonnet-5"].cost_usd == pytest.approx(0.1782812)
    assert format_usage(usage=total) == (
        "usage: 45.3s · 16 turns · 2 tool calls · tokens 32 input / "
        "16.9k cache-write / 119.6k cache-read / 2.7k output · $0.1783"
    )


def test_trace_usage_counts_each_tool_use_once(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_events[2].update(
        {
            "duration_ms": 1000,
            "duration_api_ms": 900,
            "num_turns": 2,
            "total_cost_usd": 0.01,
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": 2,
                "cache_read_input_tokens": 3,
                "output_tokens": 4,
            },
        }
    )

    restreamed = copy.deepcopy(trace_events[0])
    second_call = copy.deepcopy(trace_events[0])
    second_call["message"]["content"][0]["id"] = "tool-2"
    non_assistant = copy.deepcopy(trace_events[0])
    non_assistant["type"] = "user"
    non_assistant["message"]["content"][0]["id"] = "tool-3"
    trace_events[1:1] = [restreamed, second_call, non_assistant]
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path=trace_path, events=trace_events)

    usage = read_trace_usage(trace_path=trace_path)

    assert usage is not None
    assert usage.tool_calls == 2


def test_trace_usage_accepts_missing_optional_model_metadata(
    tmp_path: Path, trace_events: list[dict[str, Any]]
) -> None:
    trace_events[2].update(
        {
            "duration_ms": 1000,
            "duration_api_ms": 900,
            "num_turns": 1,
            "total_cost_usd": 0.01,
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": 2,
                "cache_read_input_tokens": 3,
                "output_tokens": 4,
            },
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 1,
                    "cacheCreationInputTokens": 2,
                    "cacheReadInputTokens": 3,
                    "outputTokens": 4,
                    "webSearchRequests": 0,
                    "costUSD": 0.01,
                    "contextWindow": 1_000_000,
                    "maxOutputTokens": 64_000,
                }
            },
        }
    )
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path=trace_path, events=trace_events)

    usage = read_trace_usage(trace_path=trace_path)

    assert usage is not None
    assert usage.models["claude-sonnet-5"].canonical_model is None
    assert usage.models["claude-sonnet-5"].provider is None
