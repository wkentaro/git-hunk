# git-hunk

[![PyPI](https://img.shields.io/pypi/v/git-hunk.svg)](https://pypi.python.org/pypi/git-hunk)
[![License](https://img.shields.io/pypi/l/git-hunk.svg)](https://pypi.python.org/pypi/git-hunk)

Non-interactive git hunk staging for AI agents.

## Why?

`git add -p` is interactive, so AI agents can't (really) use it. `git-hunk` gives
every hunk a stable ID so agents can inspect, filter, and stage changes
programmatically.

## Highlights

- Non-interactive alternative to `git add -p` (no interactive prompts)
- Stage, unstage, and discard individual hunks by ID and lines (`-l 3,5-7` or `-l ^3,^5-7`)
- JSON output via `--json`

## Getting started

Install git-hunk with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git-hunk
```

(Or: `pip install git-hunk`)

List hunks, then stage one by ID:

```console
$ git-hunk list
src/foo.py
  d161935  @@ -47,7 +47,7 @@ def bar():  +1 -1
  a3f82c1  @@ -92,4 +92,8 @@ class Foo   +4 -0

$ git-hunk stage d161935
```

## Usage

### List hunks

```bash
git-hunk list                          # unstaged hunks
git-hunk list --staged                 # staged hunks
git-hunk list src/foo.py src/bar.py    # specific files
git-hunk list --json                   # JSON output
```

### Show a hunk

```bash
git-hunk show d161935
```

### Stage, unstage, discard

```bash
git-hunk stage d161935                 # stage a hunk
git-hunk stage d161935 a3f82c1         # stage multiple hunks
git-hunk stage d161935 -l 3,5-7        # stage specific lines only
git-hunk unstage d161935               # move back to working tree
git-hunk discard d161935               # restore from HEAD
```

## How it works

1. Parses `git diff` output into individual hunks
2. Assigns each hunk a stable, content-based ID (SHA-256 prefix)
3. For staging: reconstructs a minimal patch and pipes it through `git apply --cached`
4. For discarding: reconstructs a reverse patch and applies it to the working tree

## Contributing

Bug reports, feature requests, and pull requests are welcome on
[GitHub](https://github.com/wkentaro/git-hunk).

## License

git-hunk is licensed under the MIT license ([LICENSE](LICENSE) or
<https://opensource.org/licenses/MIT>).
