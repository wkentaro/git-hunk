# ADR 0002: Repository path with one path coordinate system

**Status:** Accepted
**Date:** 2026-08-06
**Converges:** #127, #159 (implemented in #194)

## Context

Paths entered git-hunk on three different bases, and nothing reconciled them.

- `git diff` emits paths relative to the worktree root, so `Hunk.file`, plain output,
  and the internal patch text were all root-relative.
- `list` / `show` forwarded a file operand straight into `git diff -- <path>`, so **git**
  resolved it relative to the invocation directory.
- `stage` / `unstage` / `discard` / `commit` matched an operand in-process against the
  root-relative `Hunk.file`, so the same operand that `list` accepted was rejected
  from a subdirectory (#127).
- `run_git` ran every subprocess in the invocation directory. `git apply` silently
  ignores patched paths outside its working directory, so a textual `stage` of a hunk
  in a sibling directory printed success, exited 0, and never touched the index (#159).
  The whole-file path (`git add` / `git restore`) failed loudly on the same input.

The two failure modes share one cause: no single answer to "what does this path mean".
Fixing either alone leaves the other basis in place, so they are decided together here.

## Decision

### 1. One coordinate system: the Repository path

A **Repository path** is relative to the worktree root, uses `/`, and has the same
meaning from every invocation directory. It is the only path basis in git-hunk:
`Hunk.file`, plain output, success output, internal patch text, whole-file mutations,
and every user file operand.

There is no second, invocation-relative meaning. From `sub/`, `same.txt` selects the
file at the worktree root; `sub/same.txt` selects the one inside `sub/`.

### 2. Root-anchor every Git call

Bootstrap once with `git rev-parse --show-toplevel`, then pass that root as `cwd` to
every later Git query and mutation. This is a no-op at the root, so it cannot regress
the from-root case, and it removes `git apply`'s silent path-dropping entirely.

`rev-parse --show-toplevel` usually fails because there is no worktree to anchor to (no
repository, or a bare one), but it also refuses on dubious ownership or a bad config
value, and those messages carry the fix. git-hunk does not read git's English stderr to
classify the failure: it always reports "not a git repository" and passes git's own
message through as the tip, so the actionable half survives.

### 3. Force canonical diff paths

`git diff --no-relative --src-prefix=a/ --dst-prefix=b/` pins the diff output basis, so
a repository that sets `diff.relative`, `diff.noprefix`, or `diff.mnemonicPrefix` still
yields Repository paths and stable Hunk IDs.

Git 2.41's `--default-prefix` is the direct spelling of the prefix half, but it would
make 2.41 git-hunk's minimum, excluding Ubuntu 22.04 LTS (Git 2.34) and Debian 12
(Git 2.39). The explicit `--src-prefix` / `--dst-prefix` pair produces byte-identical
output and predates it, so the floor stays at `--no-relative`'s Git 2.28.

### 4. File operands are exact literal paths

An operand names one exact changed Repository path. Directories, globs, and Git
pathspec magic are not expanded. A leading `./` and internal `..` components are
normalized; absolute paths and paths that escape the worktree are rejected.

`git add` and `git restore` are the only calls that hand Git a path as a pathspec, so
they alone pass `--literal-pathspecs`. The path they receive is `Hunk.file`, taken from
Git's own diff output rather than from the operand, so this guards any filename
containing pathspec punctuation however the Hunk was selected. The flag is deliberately
not set globally: Git implements it by exporting `GIT_LITERAL_PATHSPECS=1`, which every
child process inherits, so a global setting would silently change how a commit hook's
own pathspecs behave.

Because operands are never forwarded to Git as pathspecs, an unmatched operand is
git-hunk's own concern, not a Git error. The mutation commands reject one: naming a
file they cannot act on is a mistake worth stopping for. `list` instead returns an
empty inventory, matching `git diff -- <path>`, so a consumer can ask "does this file
have hunks" without handling a failure.

The cost of that split is that `git-hunk list sub` reports no hunks even when `sub/`
contains changes, because a directory is an operand that matches no file rather than
an error. `git-hunk stage sub` does say so.

`commit` keeps its "stage the selected hunks, then run plain `git commit`" shape and
does not forward its operand as a commit pathspec.

### 5. Validate the repository before the operand

A Repository path only has meaning inside a worktree. The repository root is resolved
before any operand is normalized, so an invocation outside a repository reports "not a
git repository" rather than complaining about the shape of a path.

### 6. `show` stays ID-only

A Hunk ID already has the same meaning from every invocation directory, so `show` needs
no path operand.

## Consequences

- Running from a subdirectory is fully supported. Every command behaves identically
  from the worktree root and from any directory below it.
- **Breaking:** an operand is now root-relative everywhere. A user who ran
  `git-hunk list nested.py` from `sub/` must now write `sub/nested.py`.
- **Breaking:** the minimum supported Git version is 2.28.
- **Breaking:** a pathspec-shaped operand such as `':(bogus)x'` no longer reaches Git,
  so it no longer produces the clean git-failure error of #107. It simply matches no
  changed file.
- A file whose exact name contains glob or pathspec punctuation is now addressable,
  because nothing expands it.

## Out of scope

- Mid-mutation atomicity. A selection is validated completely before the first
  mutation, but a failure between the textual `git apply` leg and the whole-file leg
  can still leave the first applied. That is decided with the other file-level
  edge cases, not here.
- Rename and copy states, which remain rejected (#53).
