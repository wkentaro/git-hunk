# AGENTS.md

## Changelog

User-facing changes go in `CHANGELOG.md` under `## [Unreleased]`
([Keep a Changelog](https://keepachangelog.com/) format), with the PR number.
At release, that section is promoted to the new version.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical label strings (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
