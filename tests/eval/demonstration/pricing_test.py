from eval.demonstration import Scenario
from eval.demonstration import StartingState
from eval.demonstration import evaluate_condition
from eval.harness import list_hunks
from eval.harness import run_git_hunk
from eval.repo import GitRepo
from tests.eval.demonstration.traces import write_trace


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
    pricing_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, _ = pricing_repo
    diff = repo.git("diff", "--unified=3")

    assert diff.count("\n@@ ") == 1
    assert "float(price)" in diff
    assert "DEBUG" in diff
    assert "(1 - discount)" in diff
    assert "Discounted total" in diff


def test_toolchain_solution_passes_all_objective_checks(
    pricing_repo: tuple[GitRepo, StartingState],
    pricing_scenario: Scenario,
) -> None:
    repo, starting_state = pricing_repo
    _make_toolchain_commits(repo)
    trace_path = repo.path / ".git" / "git-hunk.jsonl"
    write_trace(
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
        scenario=pricing_scenario,
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
    pricing_repo: tuple[GitRepo, StartingState],
    pricing_scenario: Scenario,
) -> None:
    repo, starting_state = pricing_repo
    _remove_debug_output(repo)
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "bare-git.jsonl"
    write_trace(
        trace_path=trace_path,
        commands=("git add pricing.py", "git commit -m 'Finish pricing work'"),
    )

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
        scenario=pricing_scenario,
    )

    assert result.passed
    assert len(result.commits) == 1


def test_objective_checks_reject_debug_output(
    pricing_repo: tuple[GitRepo, StartingState],
    pricing_scenario: Scenario,
) -> None:
    repo, starting_state = pricing_repo
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "bare-git.jsonl"
    write_trace(trace_path=trace_path, commands=("git commit -am done",))

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
        scenario=pricing_scenario,
    )

    assert not result.passed
    assert not result.checks.final_head
    assert not result.checks.forbidden_content_absent
