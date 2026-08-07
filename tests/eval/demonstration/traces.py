import json
from pathlib import Path
from typing import Any


def write_trace(*, trace_path: Path, commands: tuple[str, ...]) -> None:
    tool_uses = [
        {
            "type": "tool_use",
            "id": f"tool-{index}",
            "name": "Bash",
            "input": {"command": command},
        }
        for index, command in enumerate(commands, start=1)
    ]
    tool_results = [
        {
            "type": "tool_result",
            "tool_use_id": f"tool-{index}",
            "content": "",
        }
        for index in range(1, len(commands) + 1)
    ]
    events: list[dict[str, Any]] = [
        {
            "type": "assistant",
            "message": {"model": "claude-opus-4-8", "content": tool_uses},
        },
        {"type": "user", "message": {"content": tool_results}},
        {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.25,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
        {
            "type": "eval_metadata",
            "started_at": "2026-08-07T00:00:00Z",
            "duration_seconds": 1.5,
            "exit_code": 0,
        },
    ]
    trace_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )
