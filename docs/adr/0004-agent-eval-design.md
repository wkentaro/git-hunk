# ADR 0004: grade agent judgment from exact Repository state

**Status:** Proposed\
**Date:** 2026-08-07

## Context

git-hunk gives an agent the mechanics to make logical commits. The `core` skill
defines the CLI workflow. The `logical-commits` skill defines how to group and
order changes. Unit and end-to-end tests cover the CLI, but they do not prove
that an agent can use both skills to make the correct commit series without
loss of work.

The evaluation target is the git-hunk toolchain from the current checkout,
Claude Code, and one model. Claude Code's version is recorded for reproducibility
but is not pinned because it auto-updates. The result must depend only on
observable Git repository state. A command trace is useful for diagnosis, but
it is not score input.

This ADR is 0004 because current main already uses ADR 0002 for Repository path
semantics and ADR 0003 for durable Hunk identity.

## Decision

### Keep the evaluation code in the repository

The evaluation code is in `eval/`. Its deterministic tests are in
`tests/eval/`. Each raw model run is in a unique system temporary directory.
Its name includes the UTC start time and Git commit. The evaluator prints the
path and leaves the directory available for diagnosis.

The installed package has no eval entry point or runtime dependency. A package
content test builds the wheel and source distribution. It requires both
archives to contain only the tracked `git_hunk` package files and required
distribution metadata.

### Test both bundled skills

Each model task starts with this instruction:

```text
Run `git-hunk skills get core logical-commits` and follow both skills.
```

The evaluator tests commit grouping and order. It does not require a
Conventional Commit prefix. Commit message format is a project convention, and
the synthetic task repositories define no such convention.

### Grade exact state in a fixed order

Each task declares two independent forms of ground truth:

1. Changed-line sets define the required commit partition and partial order.
2. A complete Repository state defines the expected committed files, tracked
   worktree files, and untracked files. Each file records its Repository path,
   exact bytes, and Git file mode.

The grader checks the first failed invariant in this order:

| Check              | Required state                                                   | Failure reason       |
| ------------------ | ---------------------------------------------------------------- | -------------------- |
| Partition          | Actual commits match the declared changed-line groups            | `partition`          |
| Order              | Required before and after constraints hold                       | `order`              |
| Final commit       | The complete `HEAD` tree matches the declared files              | `final-tree`         |
| Index              | Its tree and exact paths equal `HEAD`                            | `leftover-index`     |
| Tracked worktree   | Exact bytes and modes match the declared tracked state           | `leftover-worktree`  |
| Untracked worktree | Exact paths, bytes, and modes match the declared untracked state | `leftover-untracked` |

The complete snapshots make absence exact. They also detect duplicate lines,
binary bytes, empty files, executable files, symlinks, and deletions. Changed
line sets are only for partition and order. The evaluator does not derive a
final tree from them.

Each result contains the first failure reason and expected-versus-actual detail.

### Use one grader for deterministic and model phases

The four version 1 tasks are:

1. Split a refactor from a feature and put the refactor first.
2. Separate independent changes in one file.
3. Commit a behavior change and drop a debug line.
4. Commit one complete change and keep unrelated work in the worktree.

Every task has a deterministic golden solver. The adversarial matrix proves all
grader boundaries. It includes a duplicate added line, a staged leftover, an
incorrect tracked leftover, and a binary untracked leftover. These tests run in
the normal model-free test suite.

The model phase is an opt-in `python -m eval` command. It uses the same tasks and
grader.

### Pin the model and isolate the model phase

`eval/config.py` pins the model to `claude-sonnet-5`. The runner has no model
override and requires the reported stream model to match the model pin.

The runner accepts the installed Claude Code version so automatic updates do not
block an eval run. It records the version in the run manifest.

The runner resolves the git-hunk executable, imported package, and both skill
paths. All paths must be inside the clean current checkout. It records the Git
commit and SHA-256 for both skill files.

Claude runs with Bash as its only tool. The allowed Bash commands are
`git-hunk` and `git`. The permission mode is `dontAsk`. Safe mode, no session
persistence, no browser integration, and an empty strict MCP configuration are
required.

Each task writes a structured JSONL trace. The trace contains the Claude stream
events and one eval metadata event with UTC start time, duration, and exit code.
Validation requires assistant turns, Bash inputs, tool results, one successful
result event, and the pinned reported model. Usage and cost fields stay in the
trace when Claude reports them. The grader never reads the trace.

The runner exits nonzero for a failed task, solver error, environment mismatch,
missing or malformed trace, or incomplete task selection. A selected-task run
can help diagnosis, but it cannot qualify.

### Keep this ADR Proposed in the integration ticket

This integration adds the deterministic evaluation and the model-pinned runner. It
does not claim a model result. A later release qualification must run all four
tasks once, without retry, on one clean commit. That work must add redacted run
evidence under `docs/eval/runs/<run-id>/` and change this ADR to Accepted only
after all deterministic, lint, package, and pinned model gates pass.

## Consequences

- Normal tests stay deterministic and model-free.
- Raw model runs do not modify the checkout. Their temporary directories are
  diagnostic data, not durable evidence.
- Release artifacts cannot include evaluator code or run data.
- A line-set collision cannot hide an incorrect final tree.
- Staged, tracked, and untracked leftovers have separate diagnoses.
- A later change to the CLI, either skill, an eval task, the runner, or the
  Claude Code version makes an earlier model result stale.
