# Agent demonstration

This is one side-by-side Agent demonstration. It is not a statistical
benchmark.

- Run: `20260807T062735Z-2e58044-b5b3e85e`
- Started: `2026-08-07T06:27:35.498124Z`
- Git commit: `2e5804412e17f568a7c3174a5a115821a89327ab`
- Claude Code: `2.1.222 (Claude Code)`
- Model: `claude-opus-4-8`
- Retry: no
- Foundation: [issue #191](https://github.com/wkentaro/git-hunk/issues/191) and [PR #203](https://github.com/wkentaro/git-hunk/pull/203)

## Objective results

| Condition | Repository state | Commits | Duration | Cost | Tool calls |
| --- | --- | ---: | ---: | ---: | ---: |
| bare-git | pass | 3 | 42.4s | $0.1447 | 6 |
| git-hunk | pass | 3 | 65.8s | $0.2503 | 15 |

The objective checks cover the exact final `HEAD`, debug-line removal,
a clean index and worktree, and basic commit validity.

## Human review

Review whether the first commit normalizes numeric-string prices and
whether the next commit applies the discount together with the report
label. Also review each patch and commit message. These judgments are
not part of the objective result.

### bare-git

- `171bd6b97527` Support numeric-string prices in normalize_price
- `86def257f0d3` Apply discount in calculate_total
- `e5f8b3884d25` Update report label to reflect discounted total

[Trace](bare-git.jsonl) | [Commit patches](bare-git.patch)

### git-hunk

- `c4f98e9fb246` Support numeric-string prices via float conversion
- `9e064e4d898f` Apply discount when calculating total
- `f363217dc345` Label report total as discounted

[Trace](git-hunk.jsonl) | [Commit patches](git-hunk.patch)
