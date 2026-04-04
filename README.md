# git-hunk

[![PyPI](https://img.shields.io/pypi/v/git-hunk.svg)](https://pypi.python.org/pypi/git-hunk)
[![Python](https://img.shields.io/pypi/pyversions/git-hunk.svg)](https://pypi.python.org/pypi/git-hunk)
[![Build](https://github.com/wkentaro/git-hunk/actions/workflows/test.yml/badge.svg)](https://github.com/wkentaro/git-hunk/actions/workflows/test.yml)
[![License](https://img.shields.io/pypi/l/git-hunk.svg)](https://pypi.python.org/pypi/git-hunk)

Non-interactive, programmatic alternative to `git add -p`.

Every hunk gets a stable, content-based ID so you can inspect, filter, and
stage changes without interactive prompts.

<img src="https://github.com/wkentaro/git-hunk/blob/main/assets/teaser.png?raw=true" alt="git-hunk teaser" width="800">

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

### Agent skill (optional)

For Claude Code, Codex, and other AI agents, add the skill via
[skills](https://github.com/vercel-labs/skills):

```bash
npx skills add wkentaro/git-hunk
```

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
git-hunk show d161935                  # show a single hunk
git-hunk show d161935 a3f82c1          # show multiple hunks
git-hunk show --all                    # show all hunks (staged + unstaged)
git-hunk show --all --staged           # show all staged hunks
git-hunk show --all --unstaged         # show all unstaged hunks
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

### JSON output

```bash
git-hunk list --json
```

```json
[
  {
    "id": "d161935",
    "file": "src/main.py",
    "status": "unstaged",
    "header": "@@ -10,3 +10,5 @@",
    "additions": 2,
    "deletions": 0,
    "diff": "..."
  }
]
```

## Comparison

| | Interactive | Programmatic | Hunk IDs | Line-level control | JSON output |
|---|---|---|---|---|---|
| `git add -p` | Yes | No | No | Yes | No |
| `git add <file>` | No | Yes | No | No | No |
| **`git-hunk`** | **No** | **Yes** | **Yes** | **Yes** | **Yes** |

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
