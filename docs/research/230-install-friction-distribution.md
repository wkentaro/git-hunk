# Install friction and distribution channels for git-hunk

## Question

What does it take today for an agent (or its human) to get git-hunk installed
in a fresh environment — pip/pipx/uv tool, Homebrew, prebuilt binaries,
sandboxed-agent constraints — and which additional channels would remove real
friction for the agent-default wedge? Produce the current state, the gaps, and
a recommended channel set with costs.

Each claim below is tagged: **[repo]** = observed in this repository,
**[external]** = verified against a first-party doc or registry (URL cited),
**[unverified]** = could not be confirmed from a primary source and is marked
as such rather than asserted.

## Test environment

Audited the repo at `main` commit
[`64861ae`](https://github.com/wkentaro/git-hunk/commit/64861ae) (merge of
PR #251) on 2026-08-09, macOS (Darwin 25.5.0). Registry facts checked the same
day: PyPI via the JSON API (`https://pypi.org/pypi/git-hunk/json`), Homebrew
via the formulae API (`https://formulae.brew.sh/api/formula/git-hunk.json`),
GitHub releases and issues #192/#193/#230 via `gh`. External behavior claims
were read from the owning projects' documentation (docs.astral.sh/uv,
pipx source docs in pypa/pipx, docs.brew.sh, pyinstaller.org,
docs.python.org, shiv.readthedocs.io, code.claude.com/docs, docs.github.com,
actions/runner-images, OpenAI Codex docs at learn.chatgpt.com /
openai/codex-universal, packaging.python.org). No file outside this document
was modified; nothing was committed or pushed.

## Summary table

| Channel                                                 | Status today                                                                    | Works for the agent wedge?                                                                                   | Gap                                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| PyPI (`pip install git-hunk`)                           | Published: 0.1.0, 0.2.0 (latest 2026-04-16) [repo/external]                     | Yes, but installs 0.2.0, which predates `git-hunk skills`, durable IDs, Repository paths, and JSON v2 [repo] | **Release staleness, not a missing channel.** README on `main` documents features the installable release does not have     |
| `uv tool install` / `uvx`                               | Works against the same PyPI release [external]                                  | Best path: uv provisions Python itself, no preinstalled interpreter needed [external]                        | None beyond release staleness                                                                                               |
| pipx                                                    | Works against the same PyPI release [external]                                  | Yes, where pipx (needs Python >= 3.10 + pip) is present [external]                                           | None beyond release staleness                                                                                               |
| GitHub release artifacts                                | Tags v0.1.0/v0.2.0 + GitHub Releases exist; no attached binaries [repo]         | n/a                                                                                                          | wheel/sdist live only on PyPI                                                                                               |
| Homebrew (core or tap)                                  | No formula anywhere (formulae API 404) [external]                               | macOS humans only; agents rarely need it                                                                     | No tap; core has real per-release maintenance costs                                                                         |
| Prebuilt single-file binary                             | None [repo]                                                                     | Low value: every audited sandbox already has Python                                                          | Per-OS CI builds; `_skills.py` uses `Path(__file__)`, so zipapp breaks and PyInstaller needs data-file work [repo/external] |
| Sandboxed agents (Claude Code, GH Actions, Codex cloud) | `pip install` from PyPI is possible in all three, with caveats below [external] | Yes                                                                                                          | Network allowlisting (Claude Code sandbox, Codex agent phase) must include PyPI; docs don't say so anywhere in this repo    |

## Part 1 — Repo-observed current state

### Packaging and metadata

- Build backend: hatchling with `hatch-vcs` (version from git tags) and
  `hatch-fancy-pypi-readme` (`pyproject.toml:1-3`, `pyproject.toml:49-50`)
  [repo]. Version scheme is VCS-derived: between tags the version is a dev
  version (e.g. `0.2.1.dev276` observed in the #228 audit) [repo].
- Console script: `git-hunk = "git_hunk._cli:cli"` (`pyproject.toml:34-35`)
  [repo].
- Python floor: `requires-python = ">=3.10"` (`pyproject.toml:27`) [repo].
- Runtime dependencies: `click>=8` and `rich>=13` (`pyproject.toml:21`) — the
  tool is **not** stdlib-only at runtime [repo]. Both are pure-Python from
  git-hunk's point of view (the wheel is `py3-none-any`).
- Runtime system dependency: Git >= 2.28, because git-hunk forces
  `git diff --no-relative` (`README.md:29-30`) [repo].
- Bundled skills: `git_hunk/skills/core/SKILL.md` and
  `git_hunk/skills/logical-commits/SKILL.md`, served by
  `git-hunk skills list|get|path` (`git_hunk/_cli.py:645`) [repo].
  `tests/package_content_test.py` pins the wheel contents to exactly
  `git ls-files git_hunk`, so the skills ship inside the wheel and stay
  version-matched with the CLI [repo].
- Skills are loaded from a real filesystem path:
  `skills_root()` returns `Path(__file__).parent / "skills"`
  (`git_hunk/_skills.py:23-26`), overridable via `GIT_HUNK_SKILLS_DIR` [repo].
  This constrains non-wheel packaging (see Part 3).

### What is actually installable today

- PyPI has `git-hunk` 0.1.0 and 0.2.0; the latest files are
  `git_hunk-0.2.0-py3-none-any.whl` and `git_hunk-0.2.0.tar.gz`, uploaded
  2026-04-16 (`https://pypi.org/pypi/git-hunk/json`) [external]. Authorship
  matches this repo: author "Kentaro Wada", `project_urls` all point to
  `https://github.com/wkentaro/git-hunk` [external]. The name is ours; it is
  not squatted.
- Git tags on this repo: `v0.1.0`, `v0.2.0` only (`git tag`) [repo]. GitHub
  Releases exist for both (`gh release list`), with no binary assets [repo].
- **The published 0.2.0 predates the agent-facing surface.** At tag `v0.2.0`
  (2026-04-16), `git_hunk/` contains no `skills/` directory and no `_skills.py`
  (`git ls-tree -r v0.2.0 git_hunk/`) [repo]. Everything in
  `CHANGELOG.md` `## [Unreleased]` — the `skills` subcommand, durable SHA-256
  Hunk IDs, Repository paths, the Git 2.28 floor, JSON schema v2,
  `--include-matching`/`--exclude-matching` on `commit`, the one-sided
  replacement guard — is unreleased (`CHANGELOG.md:9-215`) [repo].
- README on `main` tells agents to run `git-hunk skills get core`
  (`README.md:48-67`); a fresh `pip install git-hunk` today produces a CLI
  where that command does not exist [repo]. The v0.2.0 README instead pointed
  at `npx skills add wkentaro/git-hunk` and copying a repo-side `SKILL.md`
  (`git show v0.2.0:README.md`), a mechanism `main` has removed [repo].
- README install instructions today: `pip install git-hunk`,
  `uv tool install git-hunk`, verify with `git-hunk --version`
  (`README.md:27-46`) [repo]. pipx is not mentioned.

### Release pipeline: exists on main vs. planned

Exists on `main` (`.github/workflows/publish.yml`) \[repo\]:

- Trigger: push of a `v*` tag; runs the test workflow, then builds with
  `uv build` (reproducible via `SOURCE_DATE_EPOCH`), verifies the wheel
  version matches the tag, and publishes with
  `pypa/gh-action-pypi-publish` under `permissions: id-token: write` and
  `environment: pypi` — i.e. PyPI **trusted publishing** (OIDC), no long-lived
  token in the workflow. Only a wheel and sdist are built; no binaries.
- This pipeline is what shipped 0.2.0: the PyPI upload timestamps match the
  `v0.2.0` tag date [repo/external].

Planned, not yet demonstrated on `main` \[repo, from issue text\]:

- #192 (open, `ready-for-agent`) proves the v0.3.0 candidate: package-content,
  metadata, install, and eval checks on one exact SHA, then freeze.
- #193 (open, `ready-for-human`) publishes v0.3.0 through a "protected"
  flow: tag, wait for the six-job test matrix, confirm the publish job waits
  on the protected `pypi` environment, inspect artifacts, approve, verify on
  PyPI. #193 step 8 says to close #64 ("Add PyPI environment protection")
  "only after the real approval gate and publication succeed" — so whether
  the `pypi` GitHub environment currently has required reviewers is a GitHub
  settings question that cannot be read from the repo; treat the approval
  gate as **planned/unverified**, while the trusted-publishing workflow
  itself is real and proven.

## Part 2 — Channel-by-channel external facts

### pip / pipx / uv against PyPI

- `pip install git-hunk` needs a Python >= 3.10 with pip and network access to
  `pypi.org` + `files.pythonhosted.org`. One friction on modern distro/system
  Pythons: the `EXTERNALLY-MANAGED` marker makes pip "exit with an error
  message indicating that package installation into this Python interpreter's
  directory are disabled outside of a virtual environment"
  (packaging.python.org/en/latest/specifications/externally-managed-environments/)
  [external]. On such systems a bare `pip install` fails and the user needs a
  venv, `pipx`, or `uv tool`.
- pipx "creates a separate virtual environment for each application" and
  exposes the entry point on PATH (pipx.pypa.io/stable/) [external].
  Installing pipx itself "needs Python 3.10 or newer" plus pip
  (pypa/pipx `docs/how-to/install-pipx.rst`) [external]; pipx can also fetch a
  standalone interpreter via `--fetch-python`
  (`docs/how-to/standalone-python.rst`) [external].
- `uv tool install git-hunk` "creates a persistent isolated virtual
  environment", linking the console script onto PATH; `uvx git-hunk` runs it
  from a cached temporary environment with no persistent install
  (docs.astral.sh/uv/concepts/tools/) [external]. Crucially for fresh
  environments: "Python does not need to be explicitly installed to use uv.
  By default, uv will automatically download Python versions when they are
  required" (docs.astral.sh/uv/guides/install-python/) [external]. uv is the
  only channel here that works on a machine with no Python at all.

### Homebrew

- No `git-hunk` formula exists in homebrew-core (formulae API returns 404)
  [external], and no tap was found.
- homebrew-core requirements (docs.brew.sh/Acceptable-Formulae) \[external\]:
  "Upstream must identify the packaged version as stable and provide an
  immutable tag or release"; "Software without a stable release is difficult
  to reproduce, bottle and support and is not eligible for homebrew/core";
  sources must be versioned with SHA-256 verification. The current page
  carries **no numeric star/fork notability thresholds** (claims of "75
  stars" style rules are stale third-party lore). It does say alternative
  trade-offs "belong in a third-party tap".
- Python CLIs in core are virtualenv formulas: "Include
  `Language::Python::Virtualenv` and use `virtualenv_install_with_resources`";
  "All Python module dependencies and their recursive dependencies ... must be
  declared as `resource`s" (for git-hunk: click, rich, and rich's transitive
  deps), regenerable with `brew update-python-resources`; the formula must
  track core's "current versioned Python formula" as core moves minor versions
  (docs.brew.sh/Language-Specific-Formulae) [external].
- A self-hosted tap is cheap: a GitHub repo named `homebrew-<name>`; users run
  `brew install wkentaro/git-hunk/git-hunk` (auto-taps) or `brew tap` first;
  `brew tap-new` scaffolds the repo and "Assuming you leave the default
  `.github/workflows` files in place, 'bottles' (binary packages) will be
  built by GitHub Actions" (docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
  [external].

### Prebuilt single-file binaries

- PyInstaller bundles "the active Python interpreter" so users "do not need to
  have Python installed at all", but "The output of PyInstaller is specific to
  the active operating system and the active version of Python" — you must
  build on each OS; there is no cross-compilation
  (pyinstaller.org/en/stable/operating-mode.html) [external]. That means a
  3-OS CI matrix per release, plus PyInstaller data-file configuration for
  `git_hunk/skills/` and code that resolves the bundle path — the current
  `Path(__file__)`-based `skills_root()` is not automatically correct in a
  one-file bundle [repo].
- zipapp `.pyz` archives require "a suitable version of Python installed" on
  the target, and a dependency with a C extension "cannot be run from a zip
  file" (docs.python.org/3/library/zipapp.html) [external]. More concretely
  for git-hunk: code inside a zip has no real filesystem path, and
  `skills_root()` builds one from `__file__` (`git_hunk/_skills.py:23-26`), so
  `git-hunk skills` would break under plain zipapp [repo].
- shiv produces zipapps that unpack "into a uniquely named subdirectory of
  `~/.shiv`" precisely because "many libraries also expect a filesystem in
  order to do things like building paths via `__file__`"
  (shiv.readthedocs.io) [external] — so shiv would work where zipapp would
  not, but still requires Python on the target, which removes most of its
  point versus plain pip/uv.

### Sandboxed-agent environments

- **Claude Code Bash sandbox**: network egress goes through a proxy limited to
  allowed domains; "The first time a command needs a new network domain,
  Claude Code prompts for approval", and `strictAllowlist` /
  `allowManagedDomainsOnly` can deny instead of prompting
  (code.claude.com/docs/en/sandboxing) [external]. There is no documented
  default PyPI allowance, so `pip install git-hunk` inside the sandbox works
  only after `pypi.org` / `files.pythonhosted.org` are approved or
  allowlisted. Python availability is the host's — the sandbox wraps the host
  machine, not a fresh image.
- **Claude Code devcontainer**: Claude Code installs into any dev container
  via a Feature; the Feature "installs Node.js itself when the base image
  doesn't provide it" — it does not install Python, so Python comes from the
  chosen base image; the reference container's `init-firewall.sh` "blocks all
  outbound traffic except the domains Claude Code and your development tools
  need" (code.claude.com/docs/en/devcontainer) [external]. A repo can vendor
  git-hunk by adding a `pip install git-hunk` / uv step to its Dockerfile or
  devcontainer setup, which runs at image-build time; if the runtime firewall
  is enabled, PyPI domains must be added for in-session installs.
- **GitHub Actions hosted runners**: the ubuntu-24.04 image preinstalls
  Python 3.12.3, Pip 24.0, and Pipx 1.16.0
  (actions/runner-images `images/ubuntu/Ubuntu2404-Readme.md`) [external], and
  GitHub documents that "You can also install additional software on
  GitHub-hosted runners"
  (docs.github.com/en/actions/concepts/runners/github-hosted-runners)
  [external]. `pip install git-hunk` in a workflow step is the ordinary path.
- **OpenAI Codex cloud**: the default `universal` image preinstalls common
  toolchains with a pinnable Python (`CODEX_ENV_PYTHON_VERSION`, with pyenv,
  poetry, uv, etc.; openai/codex-universal README) [external]; "Setup scripts
  run with internet access" and can run `pip install ...`, while "Agent
  internet access is off by default, but you can enable limited or
  unrestricted access" (learn.chatgpt.com/docs/environments/cloud-environment)
  [external]. So git-hunk must be installed in the environment setup script;
  an agent-phase `pip install` cannot be relied on. The exact default domain
  allowlist for "limited" mode was not verified here [unverified].
- Other hosted agent sandboxes (e.g. Claude Code on the web) were not audited
  against first-party docs in this pass; their default network posture is
  [unverified] and should not be assumed.

### What bundled skills imply for distribution

`git-hunk skills` is the version-matched documentation channel: the README
sends agents to it (`README.md:48-67`), and the wheel-content test guarantees
docs and code travel together [repo]. Two consequences:

1. Every distribution channel must preserve `git_hunk/skills/**` on a real
   filesystem path next to the module (works automatically for wheels,
   virtualenv-based brew formulas, and shiv; needs explicit handling for
   PyInstaller; broken for plain zipapp) [repo/external].
2. Channel proliferation multiplies version-skew surface. A brew formula or
   binary that lags PyPI ships stale agent docs with old behavior — the exact
   problem `skills` exists to avoid. Fewer, fresher channels beat many laggy
   ones for the agent wedge.

## Part 3 — Gaps

1. **The installable release is stale, and the README lies to a fresh
   installer.** `pip install git-hunk` yields 0.2.0 without `git-hunk skills`,
   durable IDs, Repository paths, or JSON v2, while `main`'s README documents
   all of them [repo]. Until v0.3.0 ships (#192/#193), every channel
   faithfully distributes the wrong thing. This is the dominant friction; no
   new channel fixes it.
2. **No sandbox-facing install guidance.** Nothing in the repo tells an agent
   operator to allowlist PyPI domains for the Claude Code sandbox, to put
   `pip install git-hunk` in a Codex setup script, or that `uvx git-hunk`
   exists for one-shot use [repo].
3. **No Homebrew presence at all** (core or tap) [external]. Matters mostly to
   macOS humans installing by habit; agents in the audited sandboxes do not
   need it.
4. **No prebuilt binaries** — but also no audited environment that needs them:
   Claude Code wraps the host, GH Actions and Codex images preinstall Python,
   and uv self-provisions Python elsewhere [external].
5. **Release approval gate not yet proven.** Trusted publishing exists and
   worked for 0.2.0; the protected-environment approval step is planned in
   #193 and unverifiable from the repo [repo/unverified].

## Recommended channel set with costs

Ordered by friction-removed-per-cost. "Freeze" refers to the #192 rule that
CLI or bundled-skill changes restart the release freeze; docs-only changes do
not.

1. **Ship v0.3.0 to PyPI through the existing pipeline** (already planned:
   #192 → #193). Removes the largest real friction — the README/installed
   mismatch and the missing `skills` surface — for every downstream channel at
   once.
   Costs: no new infrastructure (publish.yml with trusted publishing already
   exists and has shipped 0.2.0); the release-candidate proof and eval run
   that #192 already budgets; per-release cost thereafter is tag + approve.

2. **Docs: sandbox and uv install guidance** (README section or a short
   `docs/` page). State the three verified recipes: (a) `uv tool install git-hunk` / `uvx git-hunk`, noting uv provisions Python itself, so this is
   the fresh-environment default; (b) Claude Code sandbox/devcontainer: allow
   `pypi.org` and `files.pythonhosted.org`, or bake the install into the
   image; (c) Codex cloud: `pip install git-hunk` in the environment setup
   script because agent-phase internet is off by default. Mention pipx for
   PEP 668 (externally-managed) system Pythons.
   Costs: one-time docs writing only; no freeze impact; no per-release
   maintenance (commands are version-agnostic).

3. **Self-hosted Homebrew tap** (`wkentaro/homebrew-git-hunk`), after v0.3.0.
   `brew install wkentaro/git-hunk/git-hunk` with a
   `Language::Python::Virtualenv` formula; optionally keep the `brew tap-new`
   default workflows so bottles build in GitHub Actions.
   Costs: one-time ~a repo + one formula (resources generated with
   `brew update-python-resources`); per-release a url/sha bump plus resource
   refresh (automatable in the publish workflow later); no freeze impact
   (out-of-repo). Risk to manage: a lagging formula ships stale bundled
   skills, so automate the bump or clearly label the tap as secondary to
   PyPI.

Explicitly NOT recommended now:

- **homebrew-core submission.** git-hunk is pre-1.0 with a breaking release in
  flight; core adds ongoing obligations (dependency resources kept current,
  moving to each new core `python@3.x`, review latency on every version bump)
  and core's own docs route alternative trade-offs to third-party taps. A tap
  delivers the same `brew install` UX today. Revisit at a stable 1.x with
  organic demand.
- **PyInstaller per-OS binaries.** Highest cost in the set — a 3-OS build
  matrix per release (no cross-compilation), data-file/spec work for the
  bundled skills, binary signing/notarization questions — while every audited
  agent environment already has Python or uv can fetch one. Near-zero
  friction removed for the wedge.
- **zipapp/shiv artifacts.** Still require Python on the target, so they
  remove no friction pip/uv doesn't already cover; plain zipapp additionally
  breaks `skills_root()`'s `Path(__file__)` loading. Not worth a channel.
- **Any new channel before v0.3.0 ships.** It would only distribute the stale
  0.2.0 surface more widely.
