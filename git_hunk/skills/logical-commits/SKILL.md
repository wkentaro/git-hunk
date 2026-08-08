---
name: logical-commits
description: Decides how to group, order, and describe working-tree changes as focused commits. Use when splitting mixed changes in a project with no commit conventions of its own.
allowed-tools: Bash(git-hunk:*), Bash(git:*)
---

# git-hunk logical commits

Plan the entire commit series from the core skill's diff output before changing
the repository, and follow that skill's command workflow.

## Grouping

- Put one intent in each commit: one feature, fix, refactor, test, or formatting
  change.
- Group by intent, not file. Related hunks across files belong together;
  unrelated hunks in one file stay apart.
- Preserve incomplete or unrelated work when the user asks. If intent remains
  genuinely ambiguous after reading the diff, ask instead of guessing.

## Ordering

Each commit must stand alone: the build and tests would pass at every commit,
not only the last. Put prerequisites first: a refactor, rename, or signature
change precedes behavior that depends on it. Keep pure formatting separate.

## Messages

Follow any clear repository convention. Otherwise use a concise message
describing only that commit's change.
