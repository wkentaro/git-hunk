# ADR 0005: one publication bar for eval numbers

**Status:** Accepted\
**Proposed:** 2026-08-09\
**Accepted:** 2026-08-09

## Context

ADR 0004 defines the paired git-hunk versus bare-Git eval and frames its
result as an agent demonstration, not a statistical benchmark. The README's
`## Eval` section publishes the qualifying run's table, and the package readme
is assembled from `README.md` by `hatch-fancy-pypi-readme`, so each release's
PyPI page freezes whatever table the README carries at upload. GitHub's README
stays editable; a released PyPI page does not.

[#231](https://github.com/wkentaro/git-hunk/issues/231) asked what the eval
must satisfy before its numbers publish as adoption proof: repeat count and
spread reporting, cost accounting, model coverage, and where results live. The
v0.3.0 release forced the question, because shipping the README as it stood
would have answered it permanently by default.

## Decision

One bar governs every publicly visible eval number. There is no lighter tier
for a release record versus an adoption claim: the README table, the frozen
PyPI page it becomes, and any announcement or post cite the same numbers held
to the same bar.

### Three repeats per task variant

A published table reports `--repeat 3` output in ADR 0004's repeated-run
format: median with the observed range in brackets, a pass column counting
passing repeats, and qualification only when the subject variant passes every
repeat. Three repeats show run-to-run stability without claiming statistical
power; ADR 0004's demonstration framing is unchanged, and no success rate is
claimed at any repeat count.

### Cost is order-neutral or absent

The runner's cost column is not order-neutral
([#224](https://github.com/wkentaro/git-hunk/issues/224)): bare Git runs
second and partly reads the prompt cache the git-hunk run warmed. Until cost
is computed order-neutrally — the manifest already retains cache-creation and
cache-read token counts separately — published tables omit the cost column and
lead with tool calls and turns. Qualifying-run records on the release pull
request and ticket keep the full runner table; its caveat travels with it, per
ADR 0004.

### One pinned model suffices

`claude-sonnet-5` at the pinned reasoning effort meets the bar when the
published table names the model, effort, and harness version prominently. The
claim is scoped to that agent, not to agents generally. A model matrix is a
possible later extension, not a requirement of the bar.

### The README is the home

The `## Eval` section carries the current qualifying table, dated and
commit-pinned. Raw manifests, traces, and transcripts stay outside git, with
summaries on the release pull request and release ticket, as ADR 0004 already
requires.

## Consequences

- v0.3.0 ships the `## Eval` section rewritten from an N=3 re-qualification;
  the single-sample table it replaces did not meet the bar.
- A qualifying run costs three times a single-sample run, and its gate is
  strictly harder: the subject variant must pass every repeat.
- The cost column returns to published tables only when
  [#224](https://github.com/wkentaro/git-hunk/issues/224) lands.
- Announcements and positioning
  ([#233](https://github.com/wkentaro/git-hunk/issues/233)) cite the published
  table and no stronger claim.
- The bar was decided in
  [#231](https://github.com/wkentaro/git-hunk/issues/231); the grilling record
  and the explicit v0.3.0 ship decision live on that issue.
