---
name: logical-commits
description: How to group hunks into commits, order them so each is independently valid, and write conventional commit messages. Use when the user asks how to split a pile of changes into commits and has no convention of their own.
---

# git-hunk logical commits

Judgment guidance for splitting changes into commits. The mechanics of
inspecting and staging hunks are in the `core` skill; this skill covers only
what belongs in which commit, in what order, and how its message reads.

## Grouping hunks into commits

Plan the commits *before* you stage anything. For each planned commit, write
down the hunk IDs it contains.

- **One logical change per commit.** A bug fix, a refactor, a feature, a
  formatting pass, a test: each is its own commit, even when they touch the
  same file.
- **Group by intent, not by file.** Two hunks in different files that serve one
  change belong together; two hunks in one file that serve different changes
  belong apart.
- **When grouping is ambiguous, ask the user.** Don't guess at intent you can't
  see in the diff.

## Ordering commits

Order so that **each commit is independently valid**: the build/tests would
pass at every commit, not just at the end.

- Refactors and groundwork that a feature depends on come **before** the feature.
- A rename or signature change comes before the code that uses the new form.
- Pure formatting goes in its own commit (first or last), never mixed into a
  logic commit where it hides the real change.

## Commit messages

One logical change per commit; conventional commit messages (`feat:`, `fix:`,
`refactor:`, `docs:`, `test:`, `chore:`).
