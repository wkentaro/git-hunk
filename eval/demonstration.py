import argparse
import dataclasses
import datetime
import hashlib
import json
import platform
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from typing import Final
from typing import Literal
from typing import cast

from eval.config import MODEL
from eval.environment import EvalEnvironment
from eval.environment import resolve_environment
from eval.grader import read_head
from eval.model import read_trace_events
from eval.model import run_claude
from eval.repo import GitRepo
from eval.repo import init_repo
from eval.task import make_file

ConditionName = Literal["bare-git", "git-hunk"]

TASK_PROMPT: Final = (
    "The working tree contains numeric-string price support, discount behavior, "
    "a matching report-label change, and temporary debug output. Remove the debug "
    "output. Organize the finished work into focused commits in a dependency-safe "
    "order, and leave the repository clean."
)
_BARE_GIT_SYSTEM_PROMPT: Final = (
    "Use normal shell commands to inspect and edit repository files. Use Git, not "
    "git-hunk, for version-control operations. Do not invoke git-hunk or load its "
    "bundled skills."
)
_GIT_HUNK_SYSTEM_PROMPT: Final = (
    "Use normal shell commands to inspect and edit repository files. Use the "
    "git-hunk toolchain for version-control operations. First run `git-hunk skills "
    "get core logical-commits`, follow both skills, and use git-hunk to organize "
    "the commits."
)
_BASE_PRICING: Final = (
    "def normalize_price(price):\n"
    "    normalized_price = price\n"
    "\n"
    "    return normalized_price\n"
    "\n"
    "\n"
    "def calculate_total(price, discount):\n"
    "    return normalize_price(price)\n"
    "\n"
    "\n"
    "def format_report(total):\n"
    '    return f"Total: {total:.2f}"\n'
)
_DIRTY_PRICING: Final = (
    "def normalize_price(price):\n"
    "    normalized_price = float(price)\n"
    "\n"
    '    print(f"DEBUG price={normalized_price}")\n'
    "    return normalized_price\n"
    "\n"
    "\n"
    "def calculate_total(price, discount):\n"
    "    return normalize_price(price) * (1 - discount)\n"
    "\n"
    "\n"
    "def format_report(total):\n"
    '    return f"Discounted total: {total:.2f}"\n'
)
_FINAL_PRICING: Final = _DIRTY_PRICING.replace(
    '    print(f"DEBUG price={normalized_price}")\n',
    "",
)
_EXPECTED_HEAD: Final = frozenset(
    {make_file(path="pricing.py", content=_FINAL_PRICING)}
)


@dataclasses.dataclass(frozen=True)
class Condition:
    name: ConditionName
    allowed_tools: tuple[str, ...]
    system_prompt: str


@dataclasses.dataclass(frozen=True)
class CommitEvidence:
    sha: str
    subject: str
    valid: bool
    problems: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ObjectiveChecks:
    final_head: bool
    debug_removed: bool
    clean_repository: bool
    valid_commits: bool

    @property
    def passed(self) -> bool:
        return all(dataclasses.astuple(self))


@dataclasses.dataclass(frozen=True)
class TraceSummary:
    duration_seconds: float
    cost_usd: float | None
    usage: dict[str, Any]
    tool_calls: int


@dataclasses.dataclass(frozen=True)
class ConditionResult:
    condition: ConditionName
    checks: ObjectiveChecks
    commits: tuple[CommitEvidence, ...]
    commands: tuple[str, ...]
    trace_summary: TraceSummary
    patch: str

    @property
    def passed(self) -> bool:
        return self.checks.passed


@dataclasses.dataclass(frozen=True)
class StartingState:
    base_commit: str
    head_tree: str
    dirty_diff_sha256: str


CONDITIONS: Final = (
    Condition(
        name="bare-git",
        allowed_tools=("Bash",),
        system_prompt=_BARE_GIT_SYSTEM_PROMPT,
    ),
    Condition(
        name="git-hunk",
        allowed_tools=("Bash",),
        system_prompt=_GIT_HUNK_SYSTEM_PROMPT,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.demonstration")
    parser.parse_args(argv)

    try:
        environment = resolve_environment()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        evidence_dir = run_demonstration(environment=environment)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"evidence: {evidence_dir}")
    return 0


def run_demonstration(*, environment: EvalEnvironment) -> Path:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_clock = time.monotonic()
    run_id = _make_run_id(started_at=started_at, commit=environment.commit)
    raw_dir = environment.checkout / "log" / "agent-demonstration" / run_id
    raw_dir.mkdir(parents=True)
    results: list[ConditionResult] = []
    trace_paths: dict[ConditionName, Path] = {}
    repository_paths: dict[ConditionName, Path] = {}

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        template_path = temp_path / "template"
        template_path.mkdir()
        template_repo = init_repo(path=template_path)
        starting_state = build_demonstration_repository(repo=template_repo)

        for index, condition in enumerate(CONDITIONS, start=1):
            print(
                f"running {index}/{len(CONDITIONS)}: {condition.name}",
                flush=True,
            )
            repo_path = temp_path / condition.name
            shutil.copytree(template_repo.path, repo_path)
            repo = GitRepo(repo_path)
            _require_starting_state(repo=repo, expected=starting_state)
            trace_path = raw_dir / f"{condition.name}.jsonl"
            try:
                run_claude(
                    repo=repo,
                    prompt=TASK_PROMPT,
                    trace_path=trace_path,
                    allowed_tools=condition.allowed_tools,
                    append_system_prompt=condition.system_prompt,
                )
                result = evaluate_condition(
                    repo=repo,
                    base=starting_state.base_commit,
                    condition=condition.name,
                    trace_path=trace_path,
                )
            except RuntimeError as error:
                raise RuntimeError(
                    f"{condition.name} failed; the complete demonstration is invalid: "
                    f"{error}"
                ) from error
            results.append(result)
            trace_paths[condition.name] = trace_path
            repository_paths[condition.name] = repo.path
            mark = "PASS" if result.passed else "FAIL"
            print(f"{mark} {condition.name}: objective repository state", flush=True)

        evidence_dir = write_evidence(
            environment=environment,
            run_id=run_id,
            started_at=started_at,
            duration_seconds=time.monotonic() - started_clock,
            starting_state=starting_state,
            results=tuple(results),
            trace_paths=trace_paths,
            repository_paths=repository_paths,
        )
    return evidence_dir


def build_demonstration_repository(*, repo: GitRepo) -> StartingState:
    repo.write_file(name="pricing.py", content=_BASE_PRICING)
    repo.git("add", "pricing.py")
    repo.git("commit", "-m", "Initial pricing behavior")
    base_commit = repo.git("rev-parse", "HEAD").strip()
    head_tree = repo.git("rev-parse", "HEAD^{tree}").strip()
    repo.write_file(name="pricing.py", content=_DIRTY_PRICING)
    dirty_diff = repo.git_bytes("diff", "--binary", "--no-ext-diff")
    return StartingState(
        base_commit=base_commit,
        head_tree=head_tree,
        dirty_diff_sha256=hashlib.sha256(dirty_diff).hexdigest(),
    )


def evaluate_condition(
    *,
    repo: GitRepo,
    base: str,
    condition: ConditionName,
    trace_path: Path,
) -> ConditionResult:
    events = read_trace_events(trace_path=trace_path)
    commands = read_bash_commands(events=events)
    require_condition_commands(condition=condition, commands=commands)
    commits = read_commit_evidence(repo=repo, base=base)
    actual_head = read_head(repo=repo)
    status = repo.git("status", "--porcelain=v1", "--untracked-files=all")
    debug_removed = all(b"DEBUG" not in file.content for file in actual_head)
    checks = ObjectiveChecks(
        final_head=actual_head == _EXPECTED_HEAD,
        debug_removed=debug_removed,
        clean_repository=not status,
        valid_commits=bool(commits) and all(commit.valid for commit in commits),
    )
    patch = repo.git(
        "log",
        "--reverse",
        "--format=commit %H%nAuthor: %an <%ae>%nDate:   %aI%n%n    %s%n",
        "--stat",
        "--patch",
        f"{base}..HEAD",
    )
    return ConditionResult(
        condition=condition,
        checks=checks,
        commits=commits,
        commands=commands,
        trace_summary=summarize_trace(events=events),
        patch=patch,
    )


def read_commit_evidence(*, repo: GitRepo, base: str) -> tuple[CommitEvidence, ...]:
    records = repo.git("rev-list", "--reverse", "--parents", f"{base}..HEAD")
    commits: list[CommitEvidence] = []
    expected_parent = base
    for record in records.splitlines():
        parts = record.split()
        sha = parts[0]
        problems: list[str] = []
        if len(parts) != 2:
            problems.append("commit is not part of a linear history")
            parent = parts[1] if len(parts) > 1 else expected_parent
        else:
            parent = parts[1]
        if parent != expected_parent:
            problems.append("commit parent does not match the prior commit")
        parent_tree = repo.git("rev-parse", f"{parent}^{{tree}}").strip()
        commit_tree = repo.git("rev-parse", f"{sha}^{{tree}}").strip()
        if parent_tree == commit_tree:
            problems.append("commit is empty")
        if repo.run("git", "diff", "--check", parent, sha).returncode != 0:
            problems.append("commit has whitespace errors")
        try:
            source = repo.git("show", f"{sha}:pricing.py")
            compile(source, "pricing.py", "exec")
        except (RuntimeError, SyntaxError):
            problems.append("pricing.py does not compile")
        subject = repo.git("show", "-s", "--format=%s", sha).strip()
        if not subject:
            problems.append("commit subject is empty")
        commits.append(
            CommitEvidence(
                sha=sha,
                subject=subject,
                valid=not problems,
                problems=tuple(problems),
            )
        )
        expected_parent = sha
    return tuple(commits)


def read_bash_commands(*, events: list[dict[str, Any]]) -> tuple[str, ...]:
    commands: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name") != "Bash":
                continue
            tool_input = block.get("input")
            command = (
                tool_input.get("command") if isinstance(tool_input, dict) else None
            )
            if isinstance(command, str):
                commands.append(command)
    return tuple(commands)


def require_condition_commands(
    *, condition: ConditionName, commands: tuple[str, ...]
) -> None:
    git_hunk_pattern = re.compile(r"\bgit(?:-|\s+)hunk\b")
    git_hunk_commands = [
        command for command in commands if git_hunk_pattern.search(command)
    ]
    if condition == "bare-git":
        if git_hunk_commands:
            raise RuntimeError("the bare Git condition invoked git-hunk")
        return

    skill_commands = [
        command
        for command in git_hunk_commands
        if re.search(r"\bgit-hunk\s+skills\s+get\b", command)
    ]
    loaded_core = any(re.search(r"\bcore\b", command) for command in skill_commands)
    loaded_logical = any(
        re.search(r"\blogical-commits\b", command) for command in skill_commands
    )
    if not loaded_core or not loaded_logical:
        raise RuntimeError("the git-hunk condition did not load both bundled skills")
    used_git_hunk = any(
        re.search(r"\bgit-hunk\s+(stage|unstage|discard|commit)\b", command)
        for command in git_hunk_commands
    )
    if not used_git_hunk:
        raise RuntimeError("the git-hunk condition did not use git-hunk")


def summarize_trace(*, events: list[dict[str, Any]]) -> TraceSummary:
    metadata = next(event for event in events if event.get("type") == "eval_metadata")
    result = next(event for event in events if event.get("type") == "result")
    duration_seconds = cast("float", metadata["duration_seconds"])
    raw_cost = result.get("total_cost_usd")
    cost_usd = float(raw_cost) if isinstance(raw_cost, (int, float)) else None
    raw_usage = result.get("usage")
    usage = cast("dict[str, Any]", raw_usage) if isinstance(raw_usage, dict) else {}
    return TraceSummary(
        duration_seconds=duration_seconds,
        cost_usd=cost_usd,
        usage=usage,
        tool_calls=len(read_bash_commands(events=events)),
    )


def write_evidence(
    *,
    environment: EvalEnvironment,
    run_id: str,
    started_at: datetime.datetime,
    duration_seconds: float,
    starting_state: StartingState,
    results: tuple[ConditionResult, ...],
    trace_paths: dict[ConditionName, Path],
    repository_paths: dict[ConditionName, Path],
) -> Path:
    staging_dir = environment.checkout / "log" / "agent-demonstration-evidence" / run_id
    staging_dir.mkdir(parents=True)
    artifact_hashes: dict[str, str] = {}
    replacements = {
        **{str(path): "<REPOSITORY>" for path in repository_paths.values()},
        str(environment.checkout): "<CHECKOUT>",
        str(Path.home()): "<HOME>",
    }
    for result in results:
        condition = result.condition
        trace_name = f"{condition}.jsonl"
        redacted_events = redact_value(
            value=read_trace_events(trace_path=trace_paths[condition]),
            replacements=replacements,
        )
        trace_text = "".join(
            f"{json.dumps(event, sort_keys=True)}\n"
            for event in cast("list[dict[str, Any]]", redacted_events)
        )
        trace_file = staging_dir / trace_name
        trace_file.write_text(trace_text, encoding="utf-8")
        artifact_hashes[trace_name] = hashlib.sha256(trace_text.encode()).hexdigest()

        patch_name = f"{condition}.patch"
        patch_text = redact_text(
            text=result.patch,
            replacements=replacements,
        )
        patch_file = staging_dir / patch_name
        patch_file.write_text(patch_text, encoding="utf-8")
        artifact_hashes[patch_name] = hashlib.sha256(patch_text.encode()).hexdigest()

    prompt_text = make_prompt_evidence()
    (staging_dir / "prompt.txt").write_text(prompt_text, encoding="utf-8")
    artifact_hashes["prompt.txt"] = hashlib.sha256(prompt_text.encode()).hexdigest()

    readme_text = make_evidence_readme(
        environment=environment,
        run_id=run_id,
        started_at=started_at,
        results=results,
    )
    (staging_dir / "README.md").write_text(readme_text, encoding="utf-8")
    artifact_hashes["README.md"] = hashlib.sha256(readme_text.encode()).hexdigest()

    manifest = make_manifest(
        environment=environment,
        run_id=run_id,
        started_at=started_at,
        duration_seconds=duration_seconds,
        starting_state=starting_state,
        results=results,
        artifact_hashes=artifact_hashes,
        replacements=replacements,
    )
    (staging_dir / "run.json").write_text(
        f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    evidence_dir = environment.checkout / "docs" / "eval" / "demonstrations" / run_id
    evidence_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir.rename(evidence_dir)
    return evidence_dir


def make_manifest(
    *,
    environment: EvalEnvironment,
    run_id: str,
    started_at: datetime.datetime,
    duration_seconds: float,
    starting_state: StartingState,
    results: tuple[ConditionResult, ...],
    artifact_hashes: dict[str, str],
    replacements: dict[str, str],
) -> dict[str, Any]:
    condition_by_name = {condition.name: condition for condition in CONDITIONS}
    return {
        "run_id": run_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": duration_seconds,
        "commit": environment.commit,
        "clean_worktree_at_start": True,
        "claude_code_version": environment.claude_code_version,
        "model": MODEL,
        "environment": {
            "operating_system": platform.platform(),
            "python_version": platform.python_version(),
            "git_version": GitRepo(environment.checkout).git("--version").strip(),
            "git_hunk_version": _read_git_hunk_version(environment=environment),
        },
        "task_prompt": TASK_PROMPT,
        "condition_order": [condition.name for condition in CONDITIONS],
        "retried": False,
        "starting_state": dataclasses.asdict(starting_state),
        "skill_sha256": environment.skill_sha256,
        "artifacts": artifact_hashes,
        "conditions": [
            {
                "name": result.condition,
                "system_prompt": condition_by_name[result.condition].system_prompt,
                "allowed_tools": list(
                    condition_by_name[result.condition].allowed_tools
                ),
                "objective_passed": result.passed,
                "checks": dataclasses.asdict(result.checks),
                "commits": [dataclasses.asdict(commit) for commit in result.commits],
                "commands": [
                    redact_text(text=command, replacements=replacements)
                    for command in result.commands
                ],
                "trace_summary": dataclasses.asdict(result.trace_summary),
                "trace": f"{result.condition}.jsonl",
                "patch": f"{result.condition}.patch",
            }
            for result in results
        ],
    }


def make_prompt_evidence() -> str:
    sections = [f"Task prompt\n\n{TASK_PROMPT}\n"]
    for condition in CONDITIONS:
        sections.append(
            f"{condition.name} system prompt\n\n{condition.system_prompt}\n"
        )
    return "\n".join(sections)


def make_evidence_readme(
    *,
    environment: EvalEnvironment,
    run_id: str,
    started_at: datetime.datetime,
    results: tuple[ConditionResult, ...],
) -> str:
    lines = [
        "# Agent demonstration",
        "",
        "This is one side-by-side Agent demonstration. It is not a statistical",
        "benchmark.",
        "",
        f"- Run: `{run_id}`",
        f"- Started: `{started_at.isoformat().replace('+00:00', 'Z')}`",
        f"- Git commit: `{environment.commit}`",
        f"- Claude Code: `{environment.claude_code_version}`",
        f"- Model: `{MODEL}`",
        "- Retry: no",
        "- Foundation: [issue #191](https://github.com/wkentaro/git-hunk/issues/191) "
        "and [PR #203](https://github.com/wkentaro/git-hunk/pull/203)",
        "",
        "## Objective results",
        "",
        "| Condition | Repository state | Commits | Duration | Cost | Tool calls |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        outcome = "pass" if result.passed else "fail"
        cost = (
            f"${result.trace_summary.cost_usd:.4f}"
            if result.trace_summary.cost_usd is not None
            else "not reported"
        )
        lines.append(
            f"| {result.condition} | {outcome} | {len(result.commits)} | "
            f"{result.trace_summary.duration_seconds:.1f}s | {cost} | "
            f"{result.trace_summary.tool_calls} |"
        )
    lines.extend(
        [
            "",
            "The objective checks cover the exact final `HEAD`, debug-line removal,",
            "a clean index and worktree, and basic commit validity.",
            "",
            "## Human review",
            "",
            "Review whether the first commit normalizes numeric-string prices and",
            "whether the next commit applies the discount together with the report",
            "label. Also review each patch and commit message. These judgments are",
            "not part of the objective result.",
        ]
    )
    for result in results:
        lines.extend(["", f"### {result.condition}", ""])
        for commit in result.commits:
            lines.append(f"- `{commit.sha[:12]}` {commit.subject}")
        lines.extend(
            [
                "",
                f"[Trace]({result.condition}.jsonl) | "
                f"[Commit patches]({result.condition}.patch)",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def redact_value(*, value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, str):
        return redact_text(text=value, replacements=replacements)
    if isinstance(value, list):
        return [redact_value(value=item, replacements=replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: redact_value(value=item, replacements=replacements)
            for key, item in value.items()
        }
    return value


def redact_text(*, text: str, replacements: dict[str, str]) -> str:
    redacted = text
    for source, replacement in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        redacted = redacted.replace(source, replacement)
    return redacted


def _require_starting_state(*, repo: GitRepo, expected: StartingState) -> None:
    actual = StartingState(
        base_commit=repo.git("rev-parse", "HEAD").strip(),
        head_tree=repo.git("rev-parse", "HEAD^{tree}").strip(),
        dirty_diff_sha256=hashlib.sha256(
            repo.git_bytes("diff", "--binary", "--no-ext-diff")
        ).hexdigest(),
    )
    if actual != expected:
        raise RuntimeError("condition did not start from the shared Repository state")


def _read_git_hunk_version(*, environment: EvalEnvironment) -> str:
    result = GitRepo(environment.checkout).run(
        str(environment.git_hunk_executable),
        "--version",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git-hunk --version failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _make_run_id(*, started_at: datetime.datetime, commit: str) -> str:
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}-{commit[:7]}-{suffix}"


if __name__ == "__main__":
    raise SystemExit(main())
