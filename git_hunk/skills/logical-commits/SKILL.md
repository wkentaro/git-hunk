---
name: logical-commits
description: Decides how to group, order, and describe working-tree changes as focused commits. Use when splitting mixed changes in a project with no commit conventions of its own.
allowed-tools: Bash(git-hunk:*), Bash(git:*)
---

# git-hunk logical commits

Plan the whole series from the core skill's output before changing anything.

- One intent per commit, grouped by intent, not file.
- When the user marks work as unrelated or in progress, commit only what they
  asked for and leave the rest, even if it looks finished. Ask if intent is
  genuinely ambiguous.
- Each commit must build and pass tests alone: prerequisites (refactors,
  renames) first, formatting separate.
- Follow the repository's message convention, else a concise message for that
  commit's change.
