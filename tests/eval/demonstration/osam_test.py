import json
from pathlib import Path

import pytest

import eval.demonstration
from eval.demonstration import Scenario
from eval.demonstration import StartingState
from eval.demonstration import evaluate_condition
from eval.grader import read_head
from eval.harness import list_hunks
from eval.harness import run_git_hunk
from eval.repo import GitRepo
from eval.repo import init_repo
from eval.task import FileState
from eval.task import make_file
from tests.eval.demonstration.traces import write_trace

GROUND_TRUTH_DIR = (
    Path(eval.demonstration.__file__).parent / "scenarios" / "osam" / "ground-truth"
)


@pytest.fixture
def ground_truth_states(
    tmp_path_factory: pytest.TempPathFactory, osam_scenario: Scenario
) -> list[frozenset[FileState]]:
    repo = init_repo(path=tmp_path_factory.mktemp("ground-truth"))
    for file in sorted(osam_scenario.base_files, key=lambda file: file.path):
        repo.write_file(name=file.path, content=file.content)
    states: list[frozenset[FileState]] = []
    for patch in sorted(GROUND_TRUTH_DIR.glob("*.patch")):
        result = repo.run_bytes("git", "apply", str(patch))
        assert result.returncode == 0, result.stderr.decode()
        states.append(_read_worktree(repo=repo))
    return states


def _read_worktree(*, repo: GitRepo) -> frozenset[FileState]:
    return frozenset(
        make_file(
            path=path.relative_to(repo.path).as_posix(),
            content=path.read_bytes(),
        )
        for path in repo.path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )


def _find_hunk(repo: GitRepo, path: str, contains: str) -> str:
    matches = []
    for hunk in list_hunks(repo, path):
        if hunk["status"] != "unstaged":
            continue
        envelope = json.loads(run_git_hunk(repo, "show", str(hunk["id"]), "--json"))
        text = "\n".join(
            line["content"].get("text", "") for line in envelope["hunks"][0]["lines"]
        )
        if contains in text:
            matches.append(str(hunk["id"]))
    assert len(matches) == 1, f"{path} contains {contains!r} in {len(matches)} hunks"
    return matches[0]


def _unstaged_ids(repo: GitRepo, path: str) -> list[str]:
    return [
        str(hunk["id"])
        for hunk in list_hunks(repo, path)
        if hunk["status"] == "unstaged"
    ]


def test_ground_truth_patches_reconstruct_dirty_state(
    ground_truth_states: list[frozenset[FileState]],
    osam_scenario: Scenario,
) -> None:
    assert len(ground_truth_states) == len(osam_scenario.ground_truth)
    assert ground_truth_states[-1] == osam_scenario.dirty_files


def test_fixture_interleaves_ground_truth_commits_in_shared_hunks(
    osam_repo: tuple[GitRepo, StartingState],
) -> None:
    repo, _ = osam_repo
    hunks = list_hunks(repo)

    assert sum(hunk["status"] == "unstaged" for hunk in hunks) == 19
    untracked = [hunk for hunk in hunks if hunk["status"] == "untracked"]
    assert [hunk["file"]["text"] for hunk in untracked] == ["samuel/apis.py"]

    top = _find_hunk(repo, "samuel/_types.py", "from samuel import _json")
    envelope = json.loads(run_git_hunk(repo, "show", top, "--json"))
    body = "\n".join(
        f"{line['op']}{line['content'].get('text', '')}"
        for line in envelope["hunks"][0]["lines"]
    )
    assert "-import dataclasses" in body
    assert "+from samuel import _json" in body
    assert "+    def validate_embedding(cls, embedding):" in body


def test_toolchain_reproduces_ground_truth_series(
    osam_repo: tuple[GitRepo, StartingState],
    osam_scenario: Scenario,
    ground_truth_states: list[frozenset[FileState]],
) -> None:
    repo, starting_state = osam_repo

    run_git_hunk(repo, "stage", "samuel/_models/_base.py")
    for needle in (
        "from samuel._models._base import ModelBlob",
        'encoder_session=self._inference_sessions["encoder"]',
        'decoder_session=self._inference_sessions["decoder"]',
        '"encoder": ModelBlob(',
    ):
        run_git_hunk(repo, "stage", _find_hunk(repo, "samuel/_models/_sam.py", needle))
    for needle in (
        "from samuel._models._base import ModelBlob",
        'masks, _, _ = self._inference_sessions["decoder"]',
        '"encoder": ModelBlob(',
    ):
        run_git_hunk(
            repo,
            "stage",
            _find_hunk(repo, "samuel/_models/_efficient_sam.py", needle),
        )
    # The remaining hunk mixes two ground truth commits; lines 4-5 are the
    # session rename and lines 8-9 are the embedding-shape fix.
    mixed = _find_hunk(
        repo,
        "samuel/_models/_efficient_sam.py",
        '_inference_sessions["encoder"].run',
    )
    run_git_hunk(repo, "stage", mixed, "-l", "4,5")
    repo.git("commit", "-m", osam_scenario.ground_truth[0])
    assert read_head(repo=repo) == ground_truth_states[0]

    run_git_hunk(repo, "stage", "samuel/__main__.py", "samuel/_server.py")
    repo.git("add", "samuel/apis.py")
    # The top _types.py hunk mixes three ground truth commits; the selection
    # takes the unified-api lines and leaves the embedding validator and the
    # dataclasses-import removal for the later commits.
    top = _find_hunk(repo, "samuel/_types.py", "from samuel import _json")
    run_git_hunk(repo, "stage", top, "-l", "3-4,8,10-14,16-17,34-45")
    run_git_hunk(
        repo, "stage", _find_hunk(repo, "samuel/_types.py", "def serialize_points")
    )
    run_git_hunk(
        repo,
        "stage",
        _find_hunk(repo, "samuel/_types.py", "class GenerateMaskRequest"),
    )
    repo.git("commit", "-m", osam_scenario.ground_truth[1])
    assert read_head(repo=repo) == ground_truth_states[1]

    for hunk_id in _unstaged_ids(repo, "samuel/_models/_efficient_sam.py"):
        run_git_hunk(repo, "stage", hunk_id)
    run_git_hunk(
        repo, "stage", _find_hunk(repo, "samuel/_models/_sam.py", "output[0][0]")
    )
    run_git_hunk(
        repo,
        "stage",
        _find_hunk(repo, "samuel/_models/_sam.py", "image_embedding.embedding[None"),
    )
    run_git_hunk(
        repo, "stage", _find_hunk(repo, "samuel/_types.py", "def validate_embedding")
    )
    repo.git("commit", "-m", osam_scenario.ground_truth[2])
    assert read_head(repo=repo) == ground_truth_states[2]

    run_git_hunk(repo, "stage", "samuel/_types.py")
    repo.git("commit", "-m", osam_scenario.ground_truth[3])
    assert read_head(repo=repo) == ground_truth_states[3]

    trace_path = repo.path / ".git" / "git-hunk.jsonl"
    write_trace(
        trace_path=trace_path,
        commands=(
            "git-hunk skills get core logical-commits",
            "git-hunk list --json",
            "git-hunk stage samuel/_types.py",
        ),
    )
    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="git-hunk",
        trace_path=trace_path,
        scenario=osam_scenario,
    )

    assert result.passed
    assert [commit.subject for commit in result.commits] == list(
        osam_scenario.ground_truth
    )


def test_single_commit_passes_objective_checks_but_shows_in_evidence(
    osam_repo: tuple[GitRepo, StartingState],
    osam_scenario: Scenario,
) -> None:
    repo, starting_state = osam_repo
    repo.git("add", "--all")
    repo.git("commit", "-m", "Finish all work")
    trace_path = repo.path / ".git" / "bare-git.jsonl"
    write_trace(trace_path=trace_path, commands=("git commit -am done",))

    result = evaluate_condition(
        repo=repo,
        base=starting_state.base_commit,
        condition="bare-git",
        trace_path=trace_path,
        scenario=osam_scenario,
    )

    assert result.passed
    assert len(result.commits) == 1


def test_build_uses_scenario_base_and_dirty_states(
    osam_repo: tuple[GitRepo, StartingState],
    osam_scenario: Scenario,
) -> None:
    repo, _ = osam_repo

    assert read_head(repo=repo) == osam_scenario.base_files
    assert _read_worktree(repo=repo) == osam_scenario.dirty_files
    assert osam_scenario.expected_head == osam_scenario.dirty_files
