import dataclasses
import datetime
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from eval.config import CLAUDE_CODE_VERSION
from eval.demonstration import CONDITIONS
from eval.demonstration import TASK_PROMPT
from eval.demonstration import ConditionResult
from eval.demonstration import StartingState
from eval.demonstration import build_demonstration_repository
from eval.demonstration import evaluate_condition
from eval.demonstration import require_condition_commands
from eval.demonstration import write_evidence
from eval.environment import EvalEnvironment
from eval.harness import list_hunks
from eval.harness import run_git_hunk
from eval.model import build_command
from eval.repo import GitRepo


@pytest.fixture
def demonstration_repo(eval_repo: GitRepo) -> tuple[GitRepo, StartingState]:
    starting_state = build_demonstration_repository(repo=eval_repo)
    return eval_repo, starting_state


def _write_trace(*, trace_path: Path, commands: tuple[str, ...]) -> None:
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


def _remove_debug_output(repo: GitRepo) -> None:
    source = (repo.path / "pricing.py").read_text(encoding="utf-8")
    source = source.replace('    print(f"DEBUG price={normalized_price}")\n', "")
    repo.write_file(name="pricing.py", content=source)


def _make_toolchain_commits(repo: GitRepo) -> None:
    (hunk,) = list_hunks(repo, "pricing.py")
    run_git_hunk(
        repo,
        "discard",
        str(hunk["id"]),
        "--include-matching",
        "DEBUG",
    )
    (hunk,) = list_hunks(repo, "pricing.py")
    run_git_hunk(
        repo,
        "stage",
        str(hunk["id"]),
        "--include-matching",
        "normalized_price",
    )
    repo.git("commit", "-m", "Normalize numeric-string prices")
    run_git_hunk(
        repo,
        "commit",
        "pricing.py",
        "-m",
        "Apply discounts and update the report label",
    )


def test_fixture_interleaves_changes_in_one_natural_hunk(
    demonstration_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, _ = demonstration_repo
    diff = repo.git("diff", "--unified=3")

    assert diff.count("\n@@ ") == 1
    assert "float(price)" in diff
    assert "DEBUG" in diff
    assert "(1 - discount)" in diff
    assert "Discounted total" in diff


def test_toolchain_solution_passes_all_objective_checks(
    demonstration_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, starting_state = demonstration_repo
    _make_toolchain_commits(repo)
    trace_path = repo.path / ".git" / "git-hunk.jsonl"
    _write_trace(
        trace_path=trace_path,
        commands=(
            "git-hunk skills get core logical-commits",
            "git-hunk list --json",
            "git-hunk commit pricing.py -m done",
        ),
    )

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="git-hunk",
        trace_path=trace_path,
    )

    assert result.passed
    assert [commit.subject for commit in result.commits] == [
        "Normalize numeric-string prices",
        "Apply discounts and update the report label",
    ]
    assert result.trace_summary.usage == {
        "input_tokens": 100,
        "output_tokens": 50,
    }


def test_objective_checks_leave_grouping_for_human_review(
    demonstration_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, starting_state = demonstration_repo
    _remove_debug_output(repo)
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "bare-git.jsonl"
    _write_trace(
        trace_path=trace_path,
        commands=("git add pricing.py", "git commit -m 'Finish pricing work'"),
    )

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
    )

    assert result.passed
    assert len(result.commits) == 1


def test_objective_checks_reject_debug_output(
    demonstration_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, starting_state = demonstration_repo
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "bare-git.jsonl"
    _write_trace(trace_path=trace_path, commands=("git commit -am done",))

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
    )

    assert not result.passed
    assert not result.checks.final_head
    assert not result.checks.debug_removed


def test_both_conditions_receive_the_same_task_prompt() -> None:
    commands = [
        build_command(
            prompt=TASK_PROMPT,
            allowed_tools=condition.allowed_tools,
            append_system_prompt=condition.system_prompt,
        )
        for condition in CONDITIONS
    ]

    assert [command[2] for command in commands] == [TASK_PROMPT, TASK_PROMPT]
    assert [command[command.index("--allowedTools") + 1] for command in commands] == [
        "Bash",
        "Bash",
    ]


def test_bare_git_condition_rejects_git_hunk_commands() -> None:
    with pytest.raises(RuntimeError, match="bare Git condition invoked"):
        require_condition_commands(
            condition="bare-git",
            commands=("git hunk list",),
        )


def test_bare_git_condition_allows_shell_commands() -> None:
    require_condition_commands(
        condition="bare-git",
        commands=("sed -i.bak '/DEBUG/d' pricing.py", "git commit -am done"),
    )


@pytest.mark.parametrize(
    "commands,error",
    [
        (("git-hunk list",), "did not load both bundled skills"),
        (
            ("git-hunk skills get core logical-commits", "git status"),
            "did not use git-hunk",
        ),
    ],
)
def test_git_hunk_condition_requires_skills_and_cli_use(
    commands: tuple[str, ...], error: str
) -> None:
    with pytest.raises(RuntimeError, match=error):
        require_condition_commands(condition="git-hunk", commands=commands)


def test_evidence_is_complete_and_redacts_repository_paths(
    demonstration_repo: tuple[GitRepo, StartingState], tmp_path: Path
) -> None:
    repo, starting_state = demonstration_repo
    _remove_debug_output(repo)
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "raw.jsonl"
    repository_command = f"git -C {repo.path} status"
    _write_trace(trace_path=trace_path, commands=(repository_command,))
    bare_result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
    )
    toolchain_result = dataclasses.replace(
        bare_result,
        condition="git-hunk",
        commands=(
            f"git-hunk -C {repo.path} skills get core logical-commits",
            f"git-hunk -C {repo.path} list",
        ),
    )
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git_hunk_executable_name = shutil.which("git-hunk")
    assert git_hunk_executable_name is not None
    environment = EvalEnvironment(
        checkout=checkout,
        commit="a" * 40,
        git_hunk_executable=Path(git_hunk_executable_name),
        imported_package=checkout / "git_hunk" / "__init__.py",
        skill_paths={},
        skill_sha256={"core": "b" * 64, "logical-commits": "c" * 64},
        claude_code_version=f"{CLAUDE_CODE_VERSION} (Claude Code)",
    )
    results: tuple[ConditionResult, ...] = (bare_result, toolchain_result)

    evidence_dir = write_evidence(
        environment=environment,
        run_id="test-run",
        started_at=datetime.datetime(2026, 8, 7, tzinfo=datetime.timezone.utc),
        duration_seconds=3.0,
        starting_state=starting_state,
        results=results,
        trace_paths={"bare-git": trace_path, "git-hunk": trace_path},
        repository_paths={"bare-git": repo.path, "git-hunk": repo.path},
    )

    assert {path.name for path in evidence_dir.iterdir()} == {
        "README.md",
        "bare-git.jsonl",
        "bare-git.patch",
        "git-hunk.jsonl",
        "git-hunk.patch",
        "prompt.txt",
        "run.json",
    }
    evidence_text = "".join(
        path.read_text(encoding="utf-8") for path in evidence_dir.iterdir()
    )
    assert str(repo.path) not in evidence_text
    assert "<REPOSITORY>" in evidence_text
    assert "one side-by-side Agent demonstration" in evidence_text
