# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- **Breaking:** `list --json` now wraps its output in a versioned envelope,
  `{"schema_version": 1, "hunks": [...]}`, instead of a bare array, so consumers
  can depend on a documented, versioned shape (#23).
- README image paths are rewritten to absolute URLs so they render on PyPI.

### Fixed

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
- Constrain the source distribution to the package, tests, and metadata so it
  no longer ships unrelated `tmp/` files (#16).
- Split the no-newline last line when partial line-staging (`-l`) gives it a
  trailing newline, so staging only the addition no longer merges it with the
  added line and corrupts the file (#54).
- Reject an empty `--include-matching` / `--exclude-matching` pattern, which
  previously matched every line and silently selected the whole hunk, so an
  accidentally-empty pattern now errors like an empty `-l` spec (#87).

[unreleased]: https://github.com/wkentaro/git-hunk/compare/v0.2.0...HEAD
