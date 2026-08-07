# ADR 0005: extract demonstration scenarios from real commit series

**Status:** Proposed\
**Date:** 2026-08-07

## Context

ADR 0004 defines one Agent demonstration: a small synthetic pricing task in
one file. The published run passed under both conditions, and bare Git used
less time, cost, and tool calls. The trace shows why. The bare Git agent never
needed `git add -p`. It discarded the dirty file with `git checkout --` and
re-created each logical change from scratch. On a 12-line diff, that
restore-and-rebuild workaround is cheap and safe.

That workaround does not scale. Its output cost grows with the content the
agent must re-type, and every re-typed byte must land exactly, or the final
tree drifts. git-hunk cost grows with the number of Hunks instead. A
demonstration of that difference needs a dirty worktree that is large, real,
and interleaved, with a known correct commit series.

## Decision

### Make the demonstration scenario a first-class object

`python -m eval.demonstration <scenario>` takes a scenario name. A Scenario
declares the task prompt, the base and dirty file states, the expected final
`HEAD`, forbidden content markers, the human-review guidance, and an optional
ground truth commit series. The pricing scenario from ADR 0004 stays available
unchanged as `pricing`. This amends the fixed-scenario wording of ADR 0004;
the objective grading order and the evidence rules of ADR 0004 stay in force.

The debug-line objective check of ADR 0004 generalizes to a
forbidden-content check driven by scenario markers. The commit compile check
generalizes from one hardcoded file to every `.py` file in each commit tree.

### Extract hard scenarios from a real commit series

A hard scenario vendors the touched files of a range of consecutive real
commits: the base state before the range, the dirty state at the end of the
range, and the per-commit diffs as the ground truth series. The demonstration
commits the base state, overwrites the worktree with the dirty state, and
asks the agent to reconstruct focused commits. Vendored fixtures keep the
build deterministic and offline.

A usable range must satisfy:

1. The per-commit changed-line totals sum exactly to the squashed diff, so no
   line is edited twice and the ground truth partition is well defined.
2. At least one file mixes two or more commits inside one natural hunk, so
   file-level staging cannot reproduce the partition.
3. No rename, copy, binary, or unmerged state, which git-hunk rejects or the
   grader cannot byte-compare (#53).
4. The source is licensed so this repository can vendor the bytes.

The first such scenario is `osam`: four consecutive commits from
wkentaro/osam with 402 changed lines across 7 files. Its fixture and
provenance live in `eval/scenarios/osam/`. A deterministic test proves the
git-hunk toolchain can reproduce the real series byte-exact at every
intermediate tree, so the scenario is feasible, not rigged.

### Keep ground truth out of the objective score

The objective checks stay state-based: exact final `HEAD`, forbidden content,
clean index and worktree, and basic commit validity. The ground truth series
is recorded in the evidence README and `run.json` as the reference for human
review of grouping and order. Several defensible partitions can exist; the
demonstration does not pretend one number can grade that judgment.

### Keep vendored fixture bytes verbatim

Files under a scenario's `base/`, `dirty/`, and `ground-truth/` directories
keep their historical bytes. They are excluded from lint and typo checks and
must not be edited. The scenario README records source commits and license.

## Consequences

- One runner and evidence format covers both the easy and the hard case, so
  the README can show both honestly.
- New hard scenarios reduce to extracting a commit range that satisfies the
  four range rules.
- The vendored fixture freezes the scenario; upstream history changes cannot
  invalidate published evidence.
- A scenario with a rename in its range stays impossible until #53 lands.
