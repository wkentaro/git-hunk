# git-hunk

[![PyPI](https://img.shields.io/pypi/v/git_hunk.svg)](https://pypi.org/project/git-hunk/)
[![Python](https://img.shields.io/pypi/pyversions/git_hunk.svg)](https://pypi.org/project/git-hunk/)
[![Build](https://github.com/wkentaro/git-hunk/actions/workflows/test.yml/badge.svg)](https://github.com/wkentaro/git-hunk/actions/workflows/test.yml)
[![License](https://img.shields.io/pypi/l/git_hunk.svg)](https://pypi.org/project/git-hunk/)

Non-interactive, programmatic alternative to `git add -p`.

Every hunk gets a stable, content-based ID so you can inspect, filter, and
stage changes without interactive prompts.

<img src="assets/teaser.png" alt="git-hunk teaser" width="800">

## Why?

`git add -p` requires interactive input. That makes it unusable for:

- **AI agents** (Claude Code, Codex, etc.) that need to split changes into logical commits
- **Scripts & CI/CD** that automate commit organization
- **Editor integrations** that want hunk-level staging without shelling out to a TUI

`git-hunk` solves this by assigning each hunk a stable ID and exposing simple
stage/unstage/discard commands.

## Install

```bash
pip install git-hunk
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git-hunk
```

Verify it works:

```bash
git-hunk --version
```

### For AI agents

A usage guide ships inside the CLI, so agents (Claude Code, Codex, etc.) can
load it on demand. It always matches the installed version, so it never goes
stale:

```bash
git-hunk skills get core
```

`git-hunk --help` points here first.

## Quick start

```bash
# See all hunks across staged, unstaged, and untracked files
git-hunk list

# Show the diff for a specific hunk
git-hunk show d161935

# Stage specific hunks, then commit
git-hunk stage d161935 a3f82c1
git commit -m "feat: add validation for user input"

# Stage the remaining hunks
git-hunk stage e7b4012
git commit -m "fix: handle empty response in API client"
```

## Usage

### List hunks

```bash
git-hunk list                          # all hunks (unstaged + staged + untracked)
git-hunk list --unstaged               # unstaged hunks only
git-hunk list --staged                 # staged hunks only
git-hunk list src/foo.py src/bar.py    # specific files
git-hunk list --json                   # JSON output for scripting
```

### Show hunks

```bash
git-hunk show                          # show all hunks (staged + unstaged)
git-hunk show d161935                  # show a single hunk
git-hunk show d161935 a3f82c1          # show multiple hunks
git-hunk show --staged                 # show all staged hunks
git-hunk show --unstaged               # show all unstaged hunks
```

### Stage, unstage, discard

```bash
git-hunk stage d161935                 # stage a hunk
git-hunk stage d161935 a3f82c1         # stage multiple hunks
git-hunk stage d161935 -l 3,5-7        # stage specific lines only
git-hunk unstage d161935               # move back to working tree
git-hunk unstage d161935 -l 3,5-7      # unstage specific lines only
git-hunk discard d161935               # restore from HEAD
git-hunk discard d161935 -l ^3,^5-7    # discard excluding specific lines
```

### Commit

```bash
git-hunk commit d161935 -m "fix: ..."      # stage a hunk and commit it in one step
git-hunk commit d161935 -l 3,5-7 -m "..."  # stage specific lines and commit
```

`commit` aborts if anything is already staged, so the commit contains exactly
the selected hunks.

### JSON output

```bash
git-hunk list --json
```

`list --json` emits a versioned envelope so consumers can depend on a stable
shape:

```json
{
  "schema_version": 2,
  "hunks": [
    {
      "id": "d161935",
      "file": { "text": "src/main.py" },
      "status": "unstaged",
      "header": { "text": "@@ -10,3 +10,5 @@ def main():" },
      "context_before": { "text": "def main():" },
      "additions": 2,
      "deletions": 0,
      "diff": { "text": "..." }
    }
  ]
}
```

| Field            | Type   | Description                                                                                       |
| ---------------- | ------ | ------------------------------------------------------------------------------------------------- |
| `schema_version` | int    | Envelope version; bumped on any incompatible change to the shape below.                           |
| `hunks`          | array  | The hunks (empty array when there are no changes).                                                |
| `id`             | string | Stable, content-based hunk id (7-char SHA-256 prefix); accepts prefixes.                          |
| `file`           | object | Path of the changed file, as a byte-safe value (see below).                                       |
| `status`         | string | One of `staged`, `unstaged`, `untracked`.                                                         |
| `header`         | object | The hunk's `@@ ... @@` header, or a `Binary file (...)` / `Mode ...` label, as a byte-safe value. |
| `context_before` | object | The function/section git names after the `@@` header, as a byte-safe value; empty when none.      |
| `additions`      | int    | Number of added lines.                                                                            |
| `deletions`      | int    | Number of removed lines.                                                                          |
| `diff`           | object | The unified diff for the hunk, as a byte-safe value (empty for whole-file changes).               |

Fields carrying git-derived text (`file`, `header`, `context_before`, `diff`)
are byte-safe values: always an object with exactly one key, never a bare
string. UTF-8 content is `{"text": "<string>"}`; non-UTF-8 content (a path or
diff line with bytes that aren't valid UTF-8) is `{"bytes": "<base64>"}`, the
standard base64 of the raw bytes, so the original is recoverable losslessly and
the document stays valid for strict JSON parsers. (Plain string output would
emit lone surrogates that `jq` corrupts and Go/Rust parsers reject.)

Adding a new field is backward-compatible and does not change `schema_version`;
renaming, removing, or changing the type of an existing field bumps it. (Before
`schema_version` existed, `list --json` returned a bare array.)

## Comparison

|                  | Interactive | Programmatic | Hunk IDs | Line-level control | JSON output |
| ---------------- | ----------- | ------------ | -------- | ------------------ | ----------- |
| `git add -p`     | Yes         | No           | No       | Yes                | No          |
| `git add <file>` | No          | Yes          | No       | No                 | No          |
| **`git-hunk`**   | **No**      | **Yes**      | **Yes**  | **Yes**            | **Yes**     |

## How it works

1. Parses `git diff` output into individual hunks
2. Assigns each hunk a stable, content-based ID (SHA-256 prefix)
3. For staging: reconstructs a minimal patch and pipes it through `git apply --cached`
4. For discarding: reconstructs a reverse patch and applies it to the working tree

IDs are stable across partial staging -- they are derived from the changed lines,
not the `@@` line numbers that shift as you stage hunks.

## Contributing

Bug reports, feature requests, and pull requests are welcome on
[GitHub](https://github.com/wkentaro/git-hunk).

```bash
git clone https://github.com/wkentaro/git-hunk.git
cd git-hunk
make setup   # install dependencies
make test    # run tests
make lint    # run linters
```

## License

MIT ([LICENSE](https://github.com/wkentaro/git-hunk/blob/main/LICENSE))
