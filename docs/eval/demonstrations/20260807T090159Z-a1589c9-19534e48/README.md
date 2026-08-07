# Agent demonstration

This is one side-by-side Agent demonstration. It is not a statistical
benchmark.

- Run: `20260807T090159Z-a1589c9-19534e48`
- Scenario: `osam`
- Started: `2026-08-07T09:01:59.441277Z`
- Git commit: `a1589c9c3670cf598c2b2592c98c33b5720814ad`
- Claude Code: `2.1.222 (Claude Code)`
- Model: `claude-opus-4-8`
- Retry: no
- Foundation: [issue #210](https://github.com/wkentaro/git-hunk/issues/210)

## Objective results

| Condition | Repository state | Commits | Duration |    Cost | Tool calls |
| --------- | ---------------- | ------: | -------: | ------: | ---------: |
| bare-git  | fail             |       4 |   391.5s | $1.7693 |         17 |
| git-hunk  | pass             |       4 |   271.3s | $1.3132 |         21 |

The objective checks cover the exact final `HEAD`, absence of
forbidden content, a clean index and worktree, and basic commit
validity.

## Ground truth

The dirty worktree squashes this real commit series
(see [`eval/scenarios/osam`](../../../../eval/scenarios/osam/README.md)):

1. Introduce ModelBlob class to manage model blobs
2. Use unified api for both python and http
3. Ensure image embedding shape is (embedding_dim, height, width)
4. Remove unused dataclasses import

## Human review

Review whether each commit matches one piece of the ground truth
series, whether hunks from different concerns stay separated, and
whether the commit order is dependency-safe. Also review each patch
and commit message. These judgments are not part of the objective
result.

### bare-git

- `259175970b14` Introduce ModelBlob to encapsulate model blob url, hash, and path
- `012810554e32` Keep image embeddings in (embedding_dim, height, width) shape
- `8e3af1285c04` Remove unused dataclasses import
- `5bb7073fa593` Unify request and response API for Python API and HTTP server

[Trace](bare-git.jsonl) | [Commit patches](bare-git.patch)

### git-hunk

- `b453ce5123b8` Keep image embeddings in shape (embedding_dim, height, width)
- `c1247b2f6d6a` Introduce ModelBlob to replace per-model URL, MD5, and path attributes
- `3816259c7278` Add unified generate_mask request/response API for Python and HTTP
- `bffba812db08` Remove now-unused \_json import from __main__

[Trace](git-hunk.jsonl) | [Commit patches](git-hunk.patch)
