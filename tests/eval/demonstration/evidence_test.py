import dataclasses
import datetime
import json
import shutil
from pathlib import Path

import mdformat

from eval.config import CLAUDE_CODE_VERSION
from eval.demonstration import ConditionResult
from eval.demonstration import Scenario
from eval.demonstration import StartingState
from eval.demonstration import evaluate_condition
from eval.demonstration import make_evidence_readme
from eval.demonstration import make_osam_scenario
from eval.demonstration import write_evidence
from eval.environment import EvalEnvironment
from eval.repo import GitRepo
from tests.eval.demonstration.traces import write_trace


def _remove_debug_output(repo: GitRepo) -> None:
    source = (repo.path / "pricing.py").read_text(encoding="utf-8")
    source = source.replace('    print(f"DEBUG price={normalized_price}")\n', "")
    repo.write_file(name="pricing.py", content=source)


def test_evidence_is_complete_and_redacts_repository_paths(
    pricing_repo: tuple[GitRepo, StartingState],
    pricing_scenario: Scenario,
    tmp_path: Path,
) -> None:
    repo, starting_state = pricing_repo
    _remove_debug_output(repo)
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Finish pricing work")
    trace_path = repo.path / ".git" / "raw.jsonl"
    repository_command = f"git -C {repo.path} status"
    write_trace(trace_path=trace_path, commands=(repository_command,))
    bare_result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
        scenario=pricing_scenario,
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
        scenario=pricing_scenario,
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
    evidence_readme = (evidence_dir / "README.md").read_text(encoding="utf-8")
    assert "- Scenario: `pricing`" in evidence_readme
    assert "## Ground truth" not in evidence_readme
    assert (
        mdformat.text(evidence_readme, extensions={"gfm"}, options={"number": True})
        == evidence_readme
    )
    manifest = json.loads((evidence_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["scenario"] == "pricing"
    assert manifest["ground_truth"] == []
    assert manifest["environment"]["git_hunk_version"].startswith("git-hunk ")


def test_evidence_readme_lists_ground_truth_series() -> None:
    scenario = make_osam_scenario()
    environment = EvalEnvironment(
        checkout=Path("/nonexistent"),
        commit="a" * 40,
        git_hunk_executable=Path("git-hunk"),
        imported_package=Path("git_hunk"),
        skill_paths={},
        skill_sha256={},
        claude_code_version=f"{CLAUDE_CODE_VERSION} (Claude Code)",
    )
    readme = make_evidence_readme(
        environment=environment,
        scenario=scenario,
        run_id="test-run",
        started_at=datetime.datetime(2026, 8, 7, tzinfo=datetime.timezone.utc),
        results=(),
    )

    assert "- Scenario: `osam`" in readme
    assert "## Ground truth" in readme
    assert "1. Introduce ModelBlob class to manage model blobs" in readme
    assert "4. Remove unused dataclasses import" in readme
    assert "eval/scenarios/osam" in readme
