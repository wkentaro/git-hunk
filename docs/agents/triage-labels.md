# Triage Labels

This repository uses separate label axes for issue type, issue triage, and pull-request verdicts.

## Issues

Every triaged issue must carry exactly one `type:` label and exactly one triage label. An issue without a triage label is fresh work for an agent to route; `needs-triage` is reserved for a maintainer decision.

| Type label | Meaning |
| --------------- | ------------------------------------------ |
| `type: bug` | Reporting a defect to fix |
| `type: feature` | Requesting a new capability or improvement |
| `type: task` | Other work: maintenance, refactor, or docs |

| Triage label | Meaning |
| ----------------- | -------------------------------------------- |
| `needs-triage` | Maintainer needs to evaluate this issue |
| `needs-info` | Waiting on the reporter for more information |
| `ready-for-agent` | Fully specified and ready for an AFK agent |
| `ready-for-human` | Requires human implementation |
| `wontfix` | Will not be actioned |

## Pull requests

A draft PR is still being built. A non-draft PR without a verdict is ready for an agent to finalize. `needs-info` is shared with issues when a PR is waiting on an outside human.

An agent that finishes finalizing a PR applies exactly one of these mutually exclusive verdicts:

| Agent verdict | Meaning |
| ------------------ | ---------------------------------------------------------------- |
| `recommend-merge` | Agent endorses the PR for maintainer review and merge |
| `recommend-close` | Agent recommends that the maintainer review and close the PR |
| `recommend-triage` | Code is sound, but the maintainer must make a product/scope call |

`maintainer-approved` records a maintainer's review of the current head while required checks or merging remain. Apply it only on explicit maintainer direction; never infer it from an agent verdict, green CI, or mergeability. It may coexist with an agent verdict because they record decisions by different authorities.

Verdicts record decisions; they do not merge or close a PR. A new commit makes agent and maintainer verdicts stale: remove the affected label and renew it only after the corresponding authority reviews the new head.
