import json
import subprocess
from pathlib import Path
from typing import Any
from typing import NoReturn

import pytest

from eval.config import CLAUDE_CODE_VERSION
from eval.config import MODEL
from eval.model import build_command
from eval.model import build_prompt
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


def test_model_pins_are_exact() -> None:
    assert CLAUDE_CODE_VERSION == "2.1.222"
    assert MODEL == "claude-opus-4-8"


def test_prompt_loads_both_bundled_skills() -> None:
    prompt = build_prompt(task_prompt="Keep unrelated work in place.")

    assert "git-hunk skills get core logical-commits" in prompt
    assert "follow both skills" in prompt
    assert "conventional" not in prompt.lower()


def test_command_pins_model_and_isolates_claude() -> None:
    command = build_command(prompt="Do the task")

    assert command[:3] == ["claude", "-p", "Do the task"]
    assert command[command.index("--model") + 1] == MODEL
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
    monkeypatch.setattr(repo, "run", raise_timeout)
    trace_path = tmp_path / "trace.jsonl"

    with pytest.raises(RuntimeError, match="timed out after 1800 seconds"):
        run_claude(repo=repo, prompt="Do the task", trace_path=trace_path)

    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert events[0]["type"] == "assistant"
    assert events[-1]["type"] == "eval_metadata"
    assert events[-1]["exit_code"] == 124
    assert events[-1]["incomplete_output"] == '{"type":"assistant"'
