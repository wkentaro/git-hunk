# git-hunk

Non-interactive git hunk tool for AI coding agents.

`git add -p` is interactive and human-only. `git-hunk` exposes hunk-level staging and discarding as simple, scriptable CLI commands with JSON output — designed for AI coding agents (Claude Code, Codex, etc.) and shell scripts.

## Install

```bash
uv pip install git-hunk
```

Or install from source:

```bash
uv pip install -e .
```

## Usage

### List hunks

```bash
# List unstaged hunks as JSON
git-hunk list

# List staged hunks
git-hunk list --staged

# List hunks for specific files
git-hunk list src/foo.py src/bar.py
```

Output:

```json
[
  {
    "id": "abc1234",
    "file": "src/foo.py",
    "index": 0,
    "header": "@@ -10,7 +10,9 @@ def bar():",
    "additions": 3,
    "deletions": 1,
    "context_before": "def bar():",
    "diff": "@@ -10,7 +10,9 @@ def bar():\n ..."
  }
]
```

### Show a hunk

```bash
git-hunk show abc1234
```

### Stage specific hunks

```bash
# Stage one or more hunks by ID
git-hunk stage abc1234
git-hunk stage abc1234 def5678
```

### Discard specific hunks

```bash
# Discard unstaged changes for specific hunks (restore from HEAD)
git-hunk discard abc1234
```

## How it works

1. Parses `git diff` output into individual hunks
2. Assigns each hunk a stable, content-based ID (SHA-256 prefix)
3. For staging: reconstructs a minimal patch with just the selected hunks and pipes it through `git apply --cached`
4. For discarding: reconstructs a reverse patch and applies it to the working tree

## Requirements

- Python 3.8+
- Git
