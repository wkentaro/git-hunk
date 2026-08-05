# ADR 0001: `--json` schema v2 — typed Hunk model

**Status:** Accepted
**Date:** 2026-06-24
**Converges:** #28, #40, #44, #50, #56 (and bumps `schema_version` 1 → 2 once for all of them)

This ADR bundles several field-level decisions rather than splitting them across one
ADR each: they form a single `schema_version: 2` contract, must be consumed together,
and reviewing them apart would hide the cross-coupling this pass exists to resolve.

## Context

The v1 `--json` output (`{"schema_version": 1, "hunks": [...]}`) conflates display and
data in free-text strings. Five issues independently proposed changes to the same
`Hunk` / `to_dict` / `parse_diff` surface:

- **#44** — non-UTF-8 bytes leak as lone surrogates; strict parsers reject the document.
- **#50** — the function/section heading is rendered twice (in `header` and `context_before`).
- **#40** — change-kind and file mode are encoded in the free-text `header`; consumers must regex-parse it.
- **#56** — `show` has no structured per-line body, so an agent cannot reliably map a line number to its content for `-l` staging.
- **#28** — the `\ No newline at end of file` marker is a free-floating body line, not structured.

Implemented piecemeal, these would produce conflicting "v2" schemas. This ADR defines
one v2 model they all implement against.

## Decision

### 1. Document shape — flat hunks (not file-grouped)

v2 keeps v1's top-level skeleton: `{"schema_version": 2, "hunks": [...]}`. No `files: [...]`
grouping level. The hunk stays the top-level addressable object, matching the CLI's
`stage <id>` / `show <id>` / `discard <id>` verbs.

File-level fields (`change_kind`, `a_mode`, `b_mode`, `binary`) are stamped on **each**
hunk and repeat across a file's hunks. This is a deliberate, documented denormalization:
every mature structured-diff model (libgit2 delta, GitPython `Diff`, GitHub/GitLab APIs)
puts these at the file level, but those tools are file-centric; git-hunk is hunk-centric,
and self-contained hunks suit its agent consumers (filter, don't back-reference). The
values derive from one source and cannot diverge.

### 2. `change_kind` — git status letters

`change_kind`: one of `"A"` (added), `"D"` (deleted), `"M"` (modified), `"T"` (typechange).
**Always present, non-null.** `"R"` (rename) and `"C"` (copy) are **reserved** for when
renames land (#53). Single letters match `git diff --name-status` and are consistent with
the per-line `op` field's git-native single chars (see §6).

### 3. `a_mode` / `b_mode` — octal strings, always present

`a_mode` / `b_mode`: the file's git mode on each side as a 6-digit octal **string**
(`"100644"`, `"100755"`, `"120000"`, …), not a decimal int. **Always present**, `null`
when that side does not exist:

| case                        | a_mode     | b_mode     |
| --------------------------- | ---------- | ---------- |
| modify                      | `"100644"` | `"100644"` |
| chmod                       | `"100644"` | `"100755"` |
| added                       | `null`     | `"100644"` |
| deleted                     | `"100644"` | `null`     |
| typechange (file → symlink) | `"100644"` | `"120000"` |

A mode change is simply `a_mode != b_mode`; the UI derives the "Mode 100644 → 100755"
label from that. This deletes `_mode_change_header` from the data layer.

### 4. `binary` — explicit flag

`binary`: boolean, **always present** (`false` for text). Mirrors libgit2's
`GIT_DIFF_FLAG_BINARY`. Required so the UI can derive the "Binary file (modified)" label
from typed data (#40) and so a consumer can tell a binary whole-file change from a
mode-only one (both have empty bodies). Do not infer binary-ness from an empty body.

### 5. `header` — bare hunk range, or null

`header`: for a text hunk, the **bare** `@@ -a,b +c,d @@` range with git's trailing
section heading stripped (#50). The section heading lives only in `context_before`.
For a whole-file hunk (binary, mode-only, or type change — no `@@` range), `header` is `null`.

The internal `Hunk.diff` attribute used to build patches for `git apply` keeps git's
original `@@` line **verbatim** (including the section heading); only the JSON `header`
field is bared. These intentionally differ.

### 6. Body — lean `list`, structured `lines[]` in `show`

`list --json` is an **inventory** view and carries **no** body (mirrors `git diff --name-status` / `--numstat`, which omit the patch). `show --json` carries the body as a
structured `lines` array (mirrors libgit2 `git_diff_line`). The v1 raw `diff` string blob
is **removed** from JSON entirely — a monolithic blob would base64 wholesale under §7 on
a single non-UTF-8 byte; per-line structure localizes that.

A `lines[]` entry:

```json
{ "n": 7, "op": "+", "content": {"text": "..."}, "no_newline": true }
```

- `n` — 1-based position within the hunk body, the index `-l` staging uses. **Invariant:**
  `n` must match `-l`'s existing numbering exactly — every body line is counted, context
  lines included (`tests/e2e/line_selection_test.py` is the authority: `1=" a" 2="-b" 3="+B" 4=" c" 5="-d" 6="+D"`). Deliberately a single index, not libgit2's old+new lineno
  pair; `-l` needs one positional map.
- `op` — one of `" "` (context), `"+"` (addition), `"-"` (deletion).
- `content` — the line text **without** the leading `op` character, byte-safe-wrapped per
  §7. (The raw diff line `+foo` becomes `{"op": "+", "content": {"text": "foo"}}`.)
- `no_newline` — **optional**, present and `true` only when this line has no trailing
  newline (#28). The `\ No newline at end of file` marker is **not** a separate `lines[]`
  entry and does **not** consume an `n` index (matching `_print_hunk_diff`, which already
  excludes the marker from line numbering).

`show <id1> <id2> …` accepts multiple ids, so an agent triages cheaply with `list` then
batch-fetches bodies for the hunks it will act on.

### 7. Byte-safe encoding — `{text | bytes}` discriminated union (always-union)

Every field carrying **arbitrary git/source-derived bytes** is a discriminated union
(ripgrep `--json`'s shipped idiom), used **consistently** (always an object, even for
valid UTF-8, so consumers write one code path):

- valid UTF-8 → `{"text": "<string>"}`
- not valid UTF-8 → `{"bytes": "<standard base64 of the raw bytes>"}`

The raw bytes are recovered as `s.encode(errors="surrogateescape")`; if that is valid
UTF-8 it is `text`, else `bytes`.

**Union-wrapped fields:** `file`, `context_before`, and `lines[].content`. `context_before`
is `null` when the hunk has no section heading (parallel to `header: null` — absence is
encoded uniformly as `null`, never as `{"text": ""}`), so its type is `{text | bytes} | null`.
**Plain (never non-UTF-8):** `id` (hex), `status`, `change_kind`, `a_mode`, `b_mode`,
`binary`, `header` (ASCII range or null), `additions`, `deletions`, `n`, `op`,
`no_newline`.

## Resulting shapes

`list --json` hunk (inventory; no body):

```json
{
  "id": "abc1234",
  "file": {"text": "app.py"},
  "status": "unstaged",
  "change_kind": "M",
  "a_mode": "100644",
  "b_mode": "100644",
  "binary": false,
  "header": "@@ -11,7 +11,7 @@",
  "context_before": {"text": "def foo():"},
  "additions": 1,
  "deletions": 1
}
```

`show --json` hunk = the same fields **plus** `lines`:

```json
{
  "id": "abc1234",
  "file": {"text": "app.py"},
  "status": "unstaged",
  "change_kind": "M",
  "a_mode": "100644",
  "b_mode": "100644",
  "binary": false,
  "header": "@@ -11,7 +11,7 @@",
  "context_before": {"text": "def foo():"},
  "additions": 1,
  "deletions": 1,
  "lines": [
    {"n": 1, "op": " ", "content": {"text": "    x10 = 10"}},
    {"n": 2, "op": "-", "content": {"text": "    x12 = 12"}},
    {"n": 3, "op": "+", "content": {"bytes": "ICAgIHgxMiA9IDk5OQ=="}}
  ]
}
```

Binary modify (whole-file hunk):

```json
{
  "id": "...", "file": {"text": "logo.png"}, "status": "unstaged",
  "change_kind": "M", "a_mode": "100644", "b_mode": "100644",
  "binary": true, "header": null, "context_before": null,
  "additions": 0, "deletions": 0
}
```

## Consequences

- One `schema_version` 1 → 2 bump covers all five issues. The `schema_version` constant
  moves to `2`; whichever issue lands first performs the bump, the rest do not re-bump.
- Breaking changes for v1 consumers: `file`/`context_before` become objects; `header` is
  bared and may be `null`; the raw `diff` field is gone (use `show --json` `lines[]`);
  new fields `change_kind`/`a_mode`/`b_mode`/`binary`.
- The UI layer derives all human labels (`@@` heading, "Binary file (…)", "Mode X → Y")
  from typed fields; `_binary_file_header` and `_mode_change_header` leave the data layer.
- `id` semantics are unchanged here (whole-file entries' id behavior is governed by
  #13/#22, out of scope for this ADR).

## Out of scope

- Renames/copies (#53) — `R`/`C` are reserved in `change_kind` but not produced.
- Hunk-id stability and untracked/new-file staging (#13, #22).
- The schema-doc/versioning *process* (#23); this ADR is the schema, not the doc tooling.
