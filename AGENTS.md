# AGENTS.md

## Changelog

User-facing changes go in `CHANGELOG.md` under `## [Unreleased]`
([Keep a Changelog](https://keepachangelog.com/) format), with the PR number.
At release, that section is promoted to the new version.

## Tests

The suite scrubs the inherited `GIT_*` environment for the session, so it is
safe to run from inside `git rebase --exec`, a hook, `filter-branch`, or
`bisect run`. `_scrubbed_git_env` in `tests/conftest.py` explains why; keep the
suite hermetic, `tests/git_env_test.py` pins it.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical label strings (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
