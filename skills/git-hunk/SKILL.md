---
name: git-hunk
description: |
  Split uncommitted changes into focused, logical commits using git-hunk.
  Use when asked to "split changes", "split commits", "organize commits",
  "commit by hunk", or "separate changes into commits".
license: MIT
metadata:
  author: wkentaro
  version: 0.1.0
allowed-tools:
  - Bash
---

# /git-hunk - split changes into focused commits

Requires: `uv tool install git-hunk` (or `pip install git-hunk`)

## Workflow

1. `git-hunk list` — see all hunks (file, id, +/- stats). No diffs.
1. `git-hunk show <id> [<id>...]` or `git-hunk show --all` when headers aren't clear enough.
1. Plan commits before staging. For each planned commit, list the hunk IDs (and `-l` line ranges for partial hunks). A single hunk may need to be split across commits. Ask the user if grouping is ambiguous.
1. Stage and commit each group:
   ```bash
   git-hunk stage <id1> <id2> ...
   git commit -m "<type>: <description>"
   ```
1. `git-hunk list` again to check nothing got left behind.

## Partial hunks

Line selection (`-l`) works with `stage`, `unstage`, and `discard` (requires single id):

- Include lines: `git-hunk stage <id> -l 3,5-7`
- Exclude lines: `git-hunk stage <id> -l ^3,^5-7`

## Fixing mistakes

- `git-hunk unstage <id1> <id2> ...` — move staged hunks back to working tree.
- `git-hunk unstage <id> -l 3,5-7` — partially unstage specific lines.
- `git-hunk discard <id1> <id2> ...` — permanently discard unstaged hunks (restore from HEAD).
- `git-hunk discard <id> -l 3,5-7` — partially discard specific lines.

## Example `git-hunk list` output

```
unstaged:
labelme/app.py
  c43213b  @@ -78,6 +78,7 @@ _AI_CREATE_MODES  +1
  4da0d77  @@ -1364,6 +1365,19 @@ class MainWindow  +13
labelme/translate/de_DE.qm
  7a3befc  Binary file
```

## Notes

- IDs are content-based hashes, stable across partial staging, and support prefix matching
- `git-hunk list [<file>...]` — filter hunks by file path
- `--staged` / `--unstaged` to filter `list` and `show` (both search staged+unstaged by default)
- `--json` exists but plain output is usually enough
- One logical change per commit, conventional commit messages
