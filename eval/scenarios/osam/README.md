# osam demonstration scenario

This directory is the fixture for the `osam` Agent demonstration scenario. It
is extracted from the real repository
[wkentaro/osam](https://github.com/wkentaro/osam), which was named `samuel` at
that point in its history. The source project is MIT licensed and has the same
author as git-hunk, so the excerpt can live here.

## Layout

- `base/` — the touched files as of the base commit
  `7c996090b05a24f96709027942e7dd982f2f0b04`.
- `dirty/` — the same files as of the end commit
  `0139c7e80a5c6592225df6b0fb36ebc6e428dce8`, plus the new `samuel/apis.py`.
- `ground-truth/` — the four real commit diffs between those commits, in
  order.

| Patch     | Real commit    | Subject                                                        |
| --------- | -------------- | -------------------------------------------------------------- |
| `1.patch` | `85e9255ef46f` | Introduce ModelBlob class to manage model blobs                |
| `2.patch` | `ae7a5cddca77` | Use unified api for both python and http                       |
| `3.patch` | `b4633375c9f8` | Ensure image embedding shape is (embedding_dim, height, width) |
| `4.patch` | `0139c7e80a5c` | Remove unused dataclasses import                               |

## Why this range

The squashed diff has 402 changed lines across 7 files. The per-commit
changed-line totals sum exactly to the squashed diff, so no line is edited
twice and the real series is a well-defined ground truth partition.
`samuel/_types.py` is touched by three of the four commits inside one natural
hunk, and `samuel/_models/_efficient_sam.py` mixes two commits inside one
hunk, so file-level staging cannot reproduce the partition. The commit that
follows this range in the real history is a 100% rename and is excluded
because rename support is tracked in
[#53](https://github.com/wkentaro/git-hunk/issues/53).

Only the files that the commit range touches are vendored. The rest of the
project is not needed, because the demonstration checks Repository state, not
program behavior.

The vendored files under `base/` and `dirty/` and the diffs under
`ground-truth/` keep their historical bytes. They are excluded from lint and
typo checks and must not be edited.
