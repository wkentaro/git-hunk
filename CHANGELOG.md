# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Agent evals end with a Markdown summary table comparing git-hunk and bare Git
  per task, with outcome, turns, and cost per cell, a legend for the failure
  reasons that occurred, and the prompt-cache caveat that makes the cost column
  readable. The exit code now reports the subject under test (the git-hunk
  variant) and solver errors, so a graded bare-Git failure is evidence instead
  of a red run (#221).
- Agent eval summary tables, usage lines, and run manifests count the tool calls
  each task variant made, so the workflow comparison reports the metric it is
  about (#220).
- Agent evals run every task with git-hunk and bare Git from equivalent initial
  state for direct workflow and cost comparison, and `--help` lists the
  available tasks (#216).
- Agent evals stream composed prompts and Bash calls, report normalized token
  and cost usage, and write human-readable transcripts (#215).
- `skills` subcommand (`git-hunk skills list|get|path`) serving the bundled,
  version-matched core usage guide for AI agents.
- Examples section in `--help` for every subcommand.
- Accept a file path as shorthand for all hunks in a file, so
  `git-hunk stage src/foo.py` stages every hunk in that file (#21).
- `--dry-run` for `stage`, `unstage`, and `discard`, previewing what would
  change without touching the index or working tree (#25).
- `context_before` field in `list --json`, exposing the function/section heading
  git names after the `@@` header (#27).
- `--include-matching` / `--exclude-matching` for `stage`, `unstage`, and
  `discard`, selecting changed lines by content instead of by line number
  (literal substring by default, `--regex` for regular expressions; repeatable
  and OR'd), so an agent can drop a line by what it contains without a
  `show` round trip (#55).
- `--include-matching` / `--exclude-matching` and `--regex` for `commit`, so an
  agent can commit a content-selected part of one Hunk without a separate
  staging command (#214).
- `logical-commits` skill (`git-hunk skills get logical-commits`) covering how
  to group hunks into logical commits and order them so each is independently
  valid, kept separate from `core` so a project that already defines its own
  commit conventions can load `core` alone (#178).

### Changed

- Ask for a one-line-per-commit close in the core skill, so the agent's final
  report stops restating the diff it just committed (#220).
- Condense the core skill to the rules an agent acts on, trimming the text it
  loads before its first inspection call (#220).
- Let a partial-line or Conditional Hunk ID commit chain path-addressed cleanup
  and the closing `git-hunk list` into one call, and make that list the agent's
  final check, so dropping a debug line out of a hunk costs one Bash call
  instead of two (#220).
- Streamline the core skill around one inspection call and one execution call,
  reducing redundant agent tool use (#217).
- Condense the logical-commits skill around commit judgment and make core
  isolate and refresh partial-line and Conditional Hunk ID operations (#218).
- **Breaking:** Use durable Hunk identity from ADR 0003. JSON returns full
  SHA-256 IDs and `id_stability`; human output shows unique prefixes and marks
  Conditional IDs; commands accept unambiguous case-insensitive prefixes from
  the combined staged and unstaged inventory. Complete Hunk moves preserve
  stable IDs, while partial operations create new IDs (#201).
- **Breaking:** Use the Repository path coordinate system defined in ADR 0002
  for inventory, selection, and mutation, so
  `list`, `show`, `stage`, `unstage`, `discard`, and `commit` have the same
  behavior from the worktree root and every subdirectory. File operands are
  exact paths relative to the worktree root. Absolute and escaping paths are
  rejected. Directories, globs, and Git pathspec syntax are not expanded
  (#194).
- **Breaking:** Require Git 2.28 or later. Canonical diff paths need
  `git diff --no-relative`, which earlier versions of Git reject (#194).
- **Breaking:** Git pathspec magic such as `':(bogus)x'` is no longer forwarded
  to git, so it no longer produces the clean git-failure error added in #107. A
  file operand that matches no changed file now fails with
  `no changed file matches` in `stage`, `unstage`, `discard`, and `commit`, and
  yields an empty inventory in `list` (#194).
- **Breaking:** A file operand is rejected only when it is empty, absolute, or
  escapes the worktree. An all-whitespace operand is now a legal Repository
  path, so a file literally named `"   "` is addressable (#194).
- **Breaking:** `list --json` now wraps its output in a versioned envelope,
  `{"schema_version": 2, "hunks": [...]}`, instead of a bare array, so consumers
  can depend on a documented, versioned shape (#23).
- **Breaking:** `--json` output is now the typed v2 hunk schema defined in
  ADR 0001, so consumers read typed fields instead of regex-parsing free text:
  the file-level fields `change_kind`, `a_mode`, `b_mode`, and `binary` are
  stamped on every hunk; `file`, `context_before`, and each line's `content` are
  byte-safe `{"text": ...}` / `{"bytes": ...}` objects (`context_before` is
  `null` when the hunk has no section heading); `header` is the bare `@@` range
  and is `null` for a whole-file (binary, mode-only, or type change) hunk;
  `show --json`
  carries a structured per-line `lines[]` body (each `{n, op, content}`, with an
  optional `no_newline`) and the raw `diff` string is dropped (#67).
- README image paths are rewritten to absolute URLs so they render on PyPI.
- The `core` skill documents the tool only. Guidance on grouping and ordering
  commits moved to the new `logical-commits` skill, and the conventional-commits
  message-format opinion is dropped entirely, so a project's own conventions
  apply (#178).

### Fixed

- Reject detected renames, copies, and unmerged index entries before showing a
  partial inventory or applying a selection. These states now fail without
  changing the index or working tree (#199).
- Treat file mode changes and text edits as independent Hunks, and list empty
  tracked additions and deletions as whole-file Hunks. Each change can now be
  selected independently, and mixed selections validate before mutation
  (#199).
- Make partial line selection safe and bounded: reject ambiguous grouped
  replacements atomically; validate range endpoints before expansion; preserve
  no-newline state by patch side; and reject submodule pointer line selection
  cleanly (#195).
- Partial line selection on an added or deleted text file no longer leaks a raw
  `git apply` "depends on old contents" error; the patch header is rewritten to
  describe both sides (#195).
- Stop `stage`, `unstage`, and `discard` from silently doing nothing when run
  from a subdirectory on a text hunk whose file lives elsewhere in the
  repository. `git apply` drops patched paths outside its working directory
  without a word, so the command printed its success line and exited `0` while
  the index was never touched. Every git call is now anchored to the worktree
  root (#159).
- Accept a file operand from a subdirectory in `stage`, `unstage`, `discard`,
  and `commit`, which previously reported `no changed file matches` for a path
  that `list` and `show` accepted (#127).
- `commit --help` no longer advertises `--include-matching`,
  `--exclude-matching`, and `--regex`, which the command never accepted; the
  help now lists only the options `commit` actually supports (#105).
- Preserve `\ No newline at end of file` markers so staging the last line of a
  file without a trailing newline no longer fails or silently stages nothing
  (#9).
- Parse git's quoted and octal-escaped paths, so files with non-ASCII names or
  names containing ` b/` appear and stage correctly (#10).
- Decode git output with `surrogateescape`, so a diff containing non-UTF-8 bytes
  no longer crashes with `UnicodeDecodeError` (#11).
- Apply partial line selection (`-l`) correctly for `unstage` and `discard` on
  hunks with more than one change group (#12).
- Escape user-controlled text in Rich output, so a path like `src/[id].tsx`
  renders verbatim instead of being swallowed as markup (#14).
- Reject empty or whitespace-only hunk ids, and report malformed `-l` ranges
  with a readable error (#15).
- Constrain the source distribution to the package and metadata so it no longer
  ships unrelated `tmp/` files (#16).
- Split the no-newline last line when partial line-staging (`-l`) gives it a
  trailing newline, so staging only the addition no longer merges it with the
  added line and corrupts the file (#54).
- Reject an empty `--include-matching` / `--exclude-matching` pattern, which
  previously matched every line and silently selected the whole hunk, so an
  accidentally-empty pattern now errors like an empty `-l` spec (#87).
- Normalize a leading `./` and the platform's native path separator before
  exact file matching, so `git-hunk list ./foo.py` surfaces an untracked
  `foo.py` instead of silently dropping it (#95).
- Stop the global `-h`/`--help` and `-V`/`--version` flags from falling through
  into a trailing subcommand, so `git-hunk -h stage src/foo.py` prints help
  without staging and `git-hunk -V list` prints the version without listing
  (#145).
- Report a clean `error:` message instead of a raw `FileNotFoundError`
  traceback when the `git` executable is not found on `PATH` (#122).
- Show a `Usage:` hint on the `--staged`/`--unstaged` conflict error for `list`
  and `show`, matching every other conflicting-flags error (#117).
- Match hunk ids case-insensitively, so an uppercased id like `git-hunk show 713B7B9` resolves like git's own object-id lookup instead of failing with a
  misleading "not found" / "no changed file matches" error (#150).
- Correct the `discard` help, README, and skill docs, which described it as
  restoring "from HEAD" when it restores from the index: discarding an unstaged
  hunk reverts it to the staged content, leaving a staged sibling edit intact
  (#109).
- Correct the skill guide and README's claim that a partially staged hunk's
  leftover keeps the same id, so the guide now says to re-run `git-hunk list` to
  get the leftover's new id (#149).
- Correct the README JSON table and skill docs, which described every listed
  hunk as carrying a usable `id`: an `untracked` entry's `id` is empty, so no
  git-hunk command can address it, and plain `list` renders it as a bare path
  (#162).
- Document that an `untracked` inventory entry has `header: null` and
  `context_before: null` without classifying it as a whole-file hunk (#202).
- Report untracked files with Repository paths, matching tracked Hunks,
  so running `git-hunk` from a subdirectory no longer emits an untracked `file`
  on a different path basis than the staged/unstaged hunks beside it (#103).
- Report a git failure while checking for already-staged changes in `commit`
  (e.g. a corrupt index) as a clean `error:` message instead of crashing with a
  raw Python traceback (#124).
- Scope the "requires exactly one hunk" note in `--help` to all line-selection
  options, so `--include-matching` / `--exclude-matching` no longer read as
  working across multiple hunks when they share the same single-hunk
  constraint as `-l` (#155).

[unreleased]: https://github.com/wkentaro/git-hunk/compare/v0.2.0...HEAD
