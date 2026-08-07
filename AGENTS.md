# AGENTS.md

## Changelog

User-facing changes go in `CHANGELOG.md` under `## [Unreleased]`
([Keep a Changelog](https://keepachangelog.com/) format), with the PR number.
At release, that section is promoted to the new version.

## Tests

The suite removes inherited `GIT_*` variables that can make Git use the outer
repository. You can run the suite from inside `git rebase --exec`, a hook,
`filter-branch`, or `bisect run`. The `_scrubbed_git_env` fixture in
`tests/conftest.py` removes these variables and explains why this is necessary.
Keep this behavior. `tests/git_env_test.py` verifies that the suite does not
change the outer repository.

Pass Git plumbing protocols through binary subprocess input. Text-mode stdin
converts LF to CRLF on Windows and can make commands such as
`git update-index --index-info` silently ignore records. Mark only filename
cases that Windows does not allow as skipped, not the full behavior test.

Temporary repositories that compare exact worktree bytes must set
`core.autocrlf=false`. Otherwise, Git can convert LF to CRLF on Windows and
make platform-independent expected bytes fail.

Keep generated model traces and run manifests byte-for-byte. Do not edit opaque
IDs or verbatim model and tool output to satisfy prose lint. These evidence
paths are excluded from `typos`.

Run `make lint` after new evidence files are tracked. Its Markdown check uses
`git ls-files`, so it does not check untracked evidence.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical label strings (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
