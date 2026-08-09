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

### Compare git-hunk with bare Git

Every selected task runs twice, first with `git-hunk` and then with bare Git.
Both variants use the same initial Repository state, model, task-specific
prompt, and grader. The task is built once, then its complete repository is
copied back to the same temporary checkout path before each variant so Git
metadata and the model-visible path are identical. Their composed prompts
differ only in the tool instruction.
The git-hunk variant says:

```text
Run `git-hunk skills get core logical-commits` and follow both skills.
```

The bare-Git variant says:

```text
Use only Git commands; do not use `git-hunk`.
```

The fixed order makes repeated runs easy to compare, but raw cost is subject to
prompt-cache asymmetry: the first variant can create cache entries that the
second variant reads. The manifest retains cache-creation and cache-read token
counts separately, so cost comparisons must account for that warm-cache effect.
Because the run ends with a table that places both variants' costs side by side,
the runner prints that caveat directly under the table. A reader who copies the
table therefore copies the reason its cost column is not order-neutral.

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
paths. All paths must be inside the current checkout. It records the Git commit,
whether the checkout is dirty, and SHA-256 for both skill files.

Claude runs with Bash as its only tool. The git-hunk variant allows `git-hunk`
and `git`; the bare-Git variant allows only `git`. The permission mode is
`dontAsk`. Safe mode, no session persistence, no browser integration, and an
empty strict MCP configuration are required.

Each task variant writes a structured JSONL trace and transcript whose filenames
include the variant. The trace contains the Claude stream events and one eval
metadata event with UTC start time, duration, and exit code. The runner prints
the variant and exact composed prompt, then prints each Bash command as an
indented bullet under a `tool calls` section as events arrive, so a human or
agent can compare the prompt and tool-use sequence while the task is running.
It writes the same view to a human-readable task transcript; tool results stay
in the complete JSONL trace rather than cluttering the concise live view. The
grader outcome and usage summary appear together under a `result` section.

Validation requires assistant turns, Bash inputs, tool results, one successful
result event, and the pinned reported model. When Claude reports usage and cost,
the runner prints a compact per-task summary. Usage durations come from Claude's
task results; the run manifest separately records whole-run wall time.

The runner copies normalized metrics, including the per-model breakdown, into
the run manifest. Claude reports no tool-call count, so the runner derives one
by counting the distinct tool-use IDs in the trace's assistant events. That
count is a reported metric, not score input. The original fields remain in the
trace. The grader never reads the trace. The manifest field for the run-level
verdict is `gate_passed`,
not `passed`, because it reports the exit-code gate below rather than every
graded outcome.

The run ends with one Markdown table: a row per task, a column per variant, and
a cell holding that variant's outcome, turn count, and cost. A multi-task run
adds a total row whose per-variant count is how many of those distinct tasks
that variant got right. Because each cell is one sample, that count is a
demonstration tally and not a success rate over repeated trials. Grading is the
headline, so a failed cell names the grader's failure reason verbatim and a
legend below the table glosses only the reasons that occurred. That keeps one
vocabulary across grader, manifest, transcript, and table. The legend is a
Markdown list: consecutive bare lines collapse into one rendered paragraph,
which would make a pasted legend unreadable. A cell whose run reported no usage
shows the outcome with its metrics collapsed, and the total then states how many
runs reported, including when none did. Cost is rounded to the cent, and a
nonzero cost that would round to zero renders as `<$0.01` instead. The table
replaces a separate aggregate line, which would restate the total row with less
detail. Task rows are named by the task identifier that `--task` selects, not by
a prose title, so a reader can rerun any single row.

The exit code reports the subject under test, not the comparison. Each variant
declares whether it is the subject, so the gate reads that flag rather than
matching a variant name. The runner exits zero only when every subject variant
passes. A graded bare-Git outcome is evidence and never fails the run, because
the runs that best show what git-hunk adds are exactly the runs where bare Git
fails. The runner still exits nonzero for a solver error in either variant, an
environment mismatch, or a missing or malformed trace: those are broken
infrastructure rather than a graded result. Each selected task is an independent
paired comparison; passing it does not depend on running any other task in the
same invocation.

### Keep this ADR Proposed in the integration ticket

This integration adds the deterministic evaluation and the model-pinned runner.
It does not claim a model result. A later evaluation study can archive redacted
evidence for independently run tasks under `docs/eval/runs/<run-id>/` and change
this ADR to Accepted after its deterministic, lint, package, and pinned model
gates pass.

## Consequences

- Normal tests stay deterministic and model-free.
- Raw model runs do not modify the checkout. Their temporary directories are
  diagnostic data, not durable evidence.
- Release artifacts cannot include evaluator code or run data.
- A line-set collision cannot hide an incorrect final tree.
- Staged, tracked, and untracked leftovers have separate diagnoses.
- A bare-Git failure is a published result, not a red run.
- The table reports one sample per cell. It is an agent demonstration, not a
  statistical benchmark, so its totals count distinct tasks rather than repeated
  trials of one task.
- A later change to the CLI, either skill, an eval task, the runner, or the
  Claude Code version makes an earlier model result stale.
