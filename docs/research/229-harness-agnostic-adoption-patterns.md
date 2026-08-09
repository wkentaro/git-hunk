# Harness-agnostic adoption patterns for agent CLI tools

## Question

How do coding-agent stacks (Claude Code, Codex CLI, Cursor, OpenHands, aider,
MCP-based tools) discover and adopt third-party CLI tools without
harness-specific integration, and which patterns (AGENTS.md conventions,
bundled skills served by the CLI itself, MCP wrappers, plugin registries) have
actually driven adoption for comparable tools? Map each pattern to what
git-hunk already has and what it lacks. (Issue #229; input to the #235
decision "Decide the harness-agnostic integration pattern". This document maps
the option space; it does not make the decision.)

## Method

Surveyed 2026-08-09 against primary sources only: the official docs of each
harness, the specs they cite (agentskills.io, agents.md,
modelcontextprotocol.io), and the repos/docs of comparable agent-adopted CLI
tools (ripgrep, fd/bat/jq, gh, ast-grep, difftastic, jj, Graphite `gt`,
git-absorb, uv/ruff). git-hunk's own state audited on `main` at the #251
merge. Two doc hosts moved recently: OpenAI Codex docs 308-redirect from
`developers.openai.com/codex/*` to `learn.chatgpt.com`, and OpenHands docs
from `docs.all-hands.dev` to `docs.openhands.dev`; citations use the redirect
targets.

## Pattern summary table

| #   | Pattern                                                                                               | Adoption evidence strength                                                       | git-hunk today                                                                                                                                           |
| --- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Plain CLI + instruction-file conventions (AGENTS.md / CLAUDE.md / rules)                              | Strong for famous tools (gh, jq, git); weak for new tools                        | README "For AI agents" section; no prescribed AGENTS.md/CLAUDE.md snippet                                                                                |
| 2   | Harness bundling / special-casing                                                                     | Strongest driver (ripgrep, uv/ruff in codex-universal)                           | None; not actionable by a tool author                                                                                                                    |
| 3   | MCP wrapper                                                                                           | Weak unless bundled by a harness (github-mcp-server in Copilot is the exception) | None                                                                                                                                                     |
| 4   | Skills in the Agent Skills open standard (files on disk; optionally a Claude Code plugin/marketplace) | Emerging, real but modest traction (ast-grep, Astral)                            | Two spec-shaped SKILL.md files bundled in the package, but no documented path onto disk in `.agents/skills/` or `.claude/skills/`; no plugin/marketplace |
| 5   | Skill text served by the CLI itself (`git-hunk skills get`)                                           | No harness formalizes it; works today via shell in every harness                 | Fully built: `skills list/get/path`, `--json`, `--help` pointer                                                                                          |

## Part 1 — How each harness discovers third-party tools

Every harness below can run any CLI via its shell tool under a permission or
sandbox policy, so the baseline "pattern 0" (a good CLI with good `--help`)
works everywhere. The differentiating mechanisms are what gets a tool *known*
to the agent without the user pasting instructions.

### Claude Code

- Instruction files: `CLAUDE.md` at enterprise/user/project levels plus
  `.claude/rules/*.md`; loads walking up the directory tree. Claude Code does
  **not** read AGENTS.md natively — official guidance is an `@AGENTS.md`
  import or a symlink
  ([memory docs](https://code.claude.com/docs/en/memory)).
- Skills: `SKILL.md` folders in `~/.claude/skills/`, project
  `.claude/skills/`, or a plugin's `skills/`; both user-invocable and
  model-invoked via the frontmatter `description`. The docs state Claude Code
  skills follow the Agent Skills open standard
  ([skills docs](https://code.claude.com/docs/en/skills)).
- MCP: `claude mcp add`, project-scope `.mcp.json`
  ([MCP docs](https://code.claude.com/docs/en/mcp)).
- Plugins: bundle skills, hooks, MCP servers, and `bin/` executables;
  distributed via marketplaces, including Anthropic's curated
  `claude-plugins-official`
  ([plugins docs](https://code.claude.com/docs/en/plugins)).
- Plugin hints: a CLI that detects `CLAUDECODE=1` may print a one-line
  `<claude-code-hint type="plugin" …/>` to stderr and Claude Code offers a
  one-time install prompt — but only for plugins in the official Anthropic
  marketplace
  ([plugin hints docs](https://code.claude.com/docs/en/plugin-hints)).

### OpenAI Codex CLI

- AGENTS.md: global `~/.codex/AGENTS.md` plus files from the git root down to
  the cwd, closer files winning
  ([AGENTS.md docs](https://learn.chatgpt.com/docs/agent-configuration/agents-md)).
- Skills: Codex adopted the Agent Skills standard; skills load from repo
  `.agents/skills`, `$HOME/.agents/skills`, and `/etc/codex/skills`, invoked
  as `$skill-name` or implicitly
  ([skills docs](https://learn.chatgpt.com/docs/build-skills)).
- MCP: `codex mcp add` / `[mcp_servers]` in `config.toml`
  ([MCP docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)).

### Cursor

- Rules: `.cursor/rules/*.mdc`; plain AGENTS.md at root or nested is the
  documented "simpler alternative"
  ([rules docs](https://cursor.com/docs/context/rules)).
- Skills: supports the Agent Skills standard, discovering `.agents/skills/`
  and `.cursor/skills/` (project), `~/.agents/skills/` and `~/.cursor/skills/`
  (user), plus legacy `.claude/skills/` and `.codex/skills/` for
  compatibility ([skills docs](https://cursor.com/docs/context/skills)).
- MCP: `.cursor/mcp.json`, with one-click marketplace installs
  ([MCP docs](https://cursor.com/docs/context/mcp)).

### OpenHands

- Repo-root AGENTS.md is included in the initial system prompt; supports the
  Agent Skills spec from `<project>/.agents/skills/` and `~/.agents/skills/`;
  the legacy `.openhands/microagents/` mechanism is deprecated in favor of
  skills ([skills docs](https://docs.openhands.dev/overview/skills)).
- MCP via `~/.openhands/mcp.json` or settings
  ([MCP docs](https://docs.openhands.dev/openhands/usage/cli/mcp-servers)).
- Third-party CLIs otherwise enter through a custom sandbox image with the
  tool preinstalled
  ([custom sandbox guide](https://docs.openhands.dev/openhands/usage/advanced/custom-sandbox-guide)).

### aider

- Conventions files loaded read-only (`CONVENTIONS.md` via `--read`)
  ([conventions docs](https://aider.chat/docs/usage/conventions.html)); listed
  as an AGENTS.md supporter on [agents.md](https://agents.md/).
- No skills mechanism, no plugin registry, and no native MCP support anywhere
  in its docs or changelog through the latest release
  ([HISTORY](https://aider.chat/HISTORY.html)); the project is lightly
  maintained. Arbitrary CLIs run via `/run`, `--lint-cmd`, `--test-cmd`
  ([lint/test docs](https://aider.chat/docs/usage/lint-test.html)).

### The cross-cutting standards

- **AGENTS.md** ([agents.md](https://agents.md/)): a plain-Markdown "README
  for agents", now stewarded by the Agentic AI Foundation under the Linux
  Foundation. Supporters include Codex, Cursor, aider, OpenHands, Gemini CLI,
  Copilot, Zed, and many others. Claude Code is the notable non-native
  supporter (import/symlink workaround only).
- **Agent Skills** ([agentskills.io](https://agentskills.io/)): originally
  developed by Anthropic, released as an open standard; a skill is a folder
  with a `SKILL.md` (`name` + `description` frontmatter minimum) and optional
  scripts/references, loaded by progressive disclosure. The client showcase
  lists official adopter docs for roughly 45 products including Codex,
  Cursor, Gemini CLI, OpenCode, OpenHands, Copilot/VS Code, Goose, and Amp. A
  `.agents/skills/` + `~/.agents/skills/` directory convention has converged
  across the non-Anthropic harnesses (Codex, Cursor, OpenHands all read it).
- **MCP** ([modelcontextprotocol.io](https://modelcontextprotocol.io/)):
  servers expose tools/resources/prompts; the official registry at
  `registry.modelcontextprotocol.io` has been in preview since September 2025
  and is still pre-GA
  ([registry announcement](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)).
  Client-side discovery remains per-harness config/marketplace.

Key structural fact: **skills discovery is file-based in every harness**. No
harness discovers a skill by executing a CLI; the SKILL.md must exist on disk
in a scanned directory (or arrive via a plugin). A CLI that *serves* its skill
(pattern 5) relies on an instruction file or the user to trigger the fetch.

## Part 2 — What actually drove adoption for comparable tools

- **ripgrep** — harness bundling (pattern 2), preceded by fame. Claude Code
  vendors `rg` via `@vscode/ripgrep` (confirmed by Anthropic's own issue
  tracker, e.g.
  [anthropics/claude-code#42101](https://github.com/anthropics/claude-code/issues/42101));
  Codex's packaging pipeline hard-requires a bundled ripgrep
  ([openai/codex `scripts/codex_package`](https://github.com/openai/codex/tree/main/scripts/codex_package));
  Cursor inherits VS Code's bundling. BurntSushi shipped nothing
  agent-specific.
- **gh CLI** — harness-docs endorsement plus ubiquity. Claude Code's best
  practices say CLI tools are "the most context-efficient way to interact
  with external services" and name `gh` explicitly
  ([best practices](https://code.claude.com/docs/en/best-practices)).
  GitHub's official MCP wrapper
  ([github/github-mcp-server](https://github.com/github/github-mcp-server))
  gets its adoption from being enabled by default in GitHub's own Copilot
  agent
  ([Copilot docs](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent));
  outside Copilot, Anthropic's docs steer to `gh`.
- **jq / fd / bat** — pure ubiquity; jq gets a docs nudge (Claude Code's
  hooks docs tell users to install it,
  [hooks docs](https://code.claude.com/docs/en/hooks)). No author-shipped
  integrations.
- **ast-grep** — the closest analogue to git-hunk: a niche power-CLI whose
  authors ship every author-side pattern at once. Official docs page "Using
  ast-grep with AI Tools" covers a prompt snippet, `llms.txt`, an
  experimental MCP server, and a Claude Code skill
  ([prompting docs](https://astgrep.com/advanced/prompting.html)); the
  first-party skill/marketplace repo
  ([ast-grep/agent-skill](https://github.com/ast-grep/agent-skill), created
  Nov 2025, ~829 stars) has the traction, while the MCP server
  ([ast-grep/ast-grep-mcp](https://github.com/ast-grep/ast-grep-mcp)) is
  labeled experimental and de-emphasized by their own docs. The skill still
  requires the CLI preinstalled.
- **uv / ruff** — ubiquity and cloud-sandbox bundling first
  ([openai/codex-universal](https://github.com/openai/codex-universal)
  preinstalls both); Astral later shipped an official Claude Code plugin
  marketplace with uv/ruff/ty skills
  ([astral-sh/claude-code-plugins](https://github.com/astral-sh/claude-code-plugins),
  ~297 stars) whose README also recommends a CLAUDE.md pointer line. The
  skills are polish, not the adoption driver.
- **Graphite `gt`** — MCP embedded in the CLI itself (`gt mcp`, installed via
  `claude mcp add graphite gt mcp`), still beta with no independent adoption
  evidence beyond Graphite's own docs
  ([gt-mcp docs](https://graphite.com/docs/gt-mcp)).
- **jj (Jujutsu)** — counter-direction: the repo ships no AGENTS.md/CLAUDE.md
  or skill (verified against the repo root file listing); community members
  filled the gap with third-party skills (e.g.
  [RealAdarsh/jj-skill](https://github.com/RealAdarsh/jj-skill)). Demand-pull
  without first-party supply.
- **difftastic, git-absorb** — no agent story at all despite obvious fit;
  difftastic's docs are human-oriented (`GIT_EXTERNAL_DIFF`,
  [git usage](https://difftastic.wilfred.me.uk/git.html)) and its output is
  deliberately non-machine-readable. Existence proof that "a good CLI agents
  could use" does not adopt itself.
- **Marketplace composition signal** — Anthropic's own bundled plugin
  marketplace and the anthropics/skills repo contain only Anthropic-authored
  content; tool authors with traction (ast-grep, Astral) publish their own
  marketplaces
  ([anthropics/skills](https://github.com/anthropics/skills)).

Ranked by demonstrated adoption effect: (2) harness bundling, then (1)
ubiquity + harness-docs endorsement, then (4) author-shipped skills (real,
modest, growing), then (5) instruction-file snippets (always an adjunct),
then (3) standalone MCP wrappers (underperform their CLI siblings unless a
harness bundles them).

## Part 3 — What git-hunk has today

Audited on `main` (post-#251):

- **Bundled skills, spec-shaped.** `git_hunk/skills/core/SKILL.md` and
  `git_hunk/skills/logical-commits/SKILL.md` ship inside the wheel with
  Agent-Skills-compatible frontmatter (`name`, `description`, plus the
  Claude-specific `allowed-tools`). Content is versioned with the CLI, so it
  never goes stale — the property the README advertises.
- **The CLI serves its own skills (pattern 5, fully built).**
  `git-hunk skills` lists, `skills get <name>...` prints full skill text,
  `skills path [<name>]` prints the on-disk location, all with `--json`
  (`git_hunk/_cli.py:645-692`). `git-hunk --help` points agents here first.
- **README positioning.** The "Why?" section names AI agents as the first
  audience; the "For AI agents" section documents `git-hunk skills get core`
  (`README.md:48-66`).
- **No install path onto harness-scanned disk.** Nothing documents copying or
  symlinking `git-hunk skills path` output into `.agents/skills/`,
  `.claude/skills/`, or `~/.agents/skills/` — the only locations harnesses
  actually scan.
- **No AGENTS.md/CLAUDE.md contribution.** The README prescribes no
  one-line snippet for a project's AGENTS.md/CLAUDE.md, and the repo's own
  agent docs are internal conventions, not a template for consumers.
- **No MCP server, no plugin, no marketplace entry.** The only MCP references
  in the repo are the eval harness isolating itself with an empty MCP config
  (`eval/model.py:161-163`).
- **Eval-only Claude Code coupling.** `docs/adr/0004-agent-eval-design.md`
  runs evals through Claude Code, but that is test infrastructure, not an
  integration surface.

## Conclusion — pattern verdicts and ranked recommendation

### Pattern 1: instruction-file conventions (AGENTS.md / CLAUDE.md / rules)

- **What it is:** a one-line pointer ("this repo uses git-hunk; run
  `git-hunk skills get core` before committing") in the file every harness
  already reads.
- **Evidence:** universal reach — AGENTS.md is read natively by Codex,
  Cursor, OpenHands, aider, and ~20 others; Claude Code needs CLAUDE.md or an
  import. But snippets appear only as an adjunct in every surveyed tool-author
  integration (ast-grep, Astral); no evidence a snippet alone drives adoption.
- **git-hunk has:** nothing prescribed. **Missing:** a canonical copy-paste
  snippet in the README, worded to work in both AGENTS.md and CLAUDE.md.

### Pattern 2: harness bundling

- **What it is:** the harness vendors the binary (ripgrep) or preinstalls it
  in its cloud image (uv/ruff in codex-universal).
- **Evidence:** the strongest adoption driver observed, but it is granted by
  harness vendors, not shipped by tool authors.
- **git-hunk has:** nothing; **missing:** nothing actionable — at most a
  long-term aspiration once the tool is proven elsewhere.

### Pattern 3: MCP wrapper

- **What it is:** an MCP server exposing stage/unstage/commit as tools,
  possibly embedded in the CLI (`git-hunk mcp`, the Graphite shape).
- **Evidence:** weakest pattern for CLI-shaped tools — github-mcp-server
  succeeds only where bundled by GitHub's own harness; ast-grep's MCP is
  experimental and de-emphasized; GT MCP is beta with no independent
  adoption; aider cannot use MCP at all. Anthropic's own docs recommend CLIs
  over wrappers for context efficiency.
- **git-hunk has:** nothing. **Missing:** everything, but the evidence says
  building it now would be supply without demand.

### Pattern 4: skills on disk (Agent Skills standard; optionally a plugin)

- **What it is:** the SKILL.md folders land in a directory harnesses scan —
  project `.agents/skills/` (Codex/Cursor/OpenHands) and `.claude/skills/`
  (Claude Code, also read by Cursor) — via documented copy/symlink of
  `git-hunk skills path`, a future `git-hunk skills install` convenience, or
  a Claude Code plugin marketplace repo.
- **Evidence:** the emerging author-side pattern with real traction
  (ast-grep ~829 stars, Astral's marketplace), and the skills format is now a
  cross-harness open standard, so one artifact covers Claude Code, Codex,
  Cursor, OpenHands, Gemini CLI, and OpenCode.
- **git-hunk has:** the artifact itself — its bundled skills are already
  spec-shaped, and `skills path` already exposes the source directory.
  **Missing:** the delivery step and its docs; a decision on symlink (never
  stale) vs copy (spec-portable) vs plugin (Claude-only, adds hint-protocol
  eligibility); and versioned-staleness handling for copies.

### Pattern 5: CLI-served skill text (`git-hunk skills get`)

- **What it is:** the running CLI is the source of truth; the agent pulls the
  guide into context on demand.
- **Evidence:** no harness formalizes CLI-served skills — discovery is
  file-based everywhere — but the mechanism works through the shell in every
  harness and uniquely guarantees version match. It has no discovery story of
  its own: something (pattern 1 or 4) must tell the agent to run it.
- **git-hunk has:** the full mechanism. **Missing:** only the discovery
  trigger.

### Ranked recommendation (for #235 to decide, not decided here)

1. **Bridge pattern 5 to pattern 4**: document (and possibly automate) getting
   the already-spec-shaped bundled skills into `.agents/skills/` and
   `.claude/skills/`. Highest leverage per unit work: git-hunk already owns
   the hard part (the skill content), and the file-based discovery gap is the
   one thing keeping every harness from finding it.
2. **Add the pattern-1 snippet**: a canonical AGENTS.md/CLAUDE.md line in the
   README. Near-zero cost, universal reach, and the standard adjunct in every
   successful comparable.
3. **Defer a Claude Code plugin/marketplace** until the skills-on-disk story
   exists; it is a packaging of pattern 4 for one harness, and it is the only
   route to the plugin-hint auto-discovery protocol if that ever matters.
4. **Do not build an MCP server now**: weakest evidence, duplicated surface
   area, and the tool's value is exactly the context-efficient CLI shape the
   harness vendors themselves recommend.

The one assumption in the question worth correcting: "bundled skills served
by the CLI itself" and "skills" are not one pattern. The serving mechanism
(pattern 5) is finished and unique to git-hunk, but no harness will ever call
it spontaneously; adoption hinges on the file-based delivery (pattern 4) and
the instruction-file pointer (pattern 1) that this survey found to be the
live, evidence-backed author-side patterns.
