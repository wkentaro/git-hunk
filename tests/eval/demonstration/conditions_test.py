import pytest

from eval.demonstration import CONDITIONS
from eval.demonstration import Scenario
from eval.demonstration import require_condition_commands
from eval.model import build_command


def test_both_conditions_receive_the_same_task_prompt(
    pricing_scenario: Scenario,
) -> None:
    commands = [
        build_command(
            prompt=pricing_scenario.task_prompt,
            allowed_tools=condition.allowed_tools,
            append_system_prompt=condition.system_prompt,
        )
        for condition in CONDITIONS
    ]

    assert [command[2] for command in commands] == [
        pricing_scenario.task_prompt,
        pricing_scenario.task_prompt,
    ]
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
