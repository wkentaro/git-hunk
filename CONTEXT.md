# git-hunk — domain context

## Glossary

- **Repository path** — a file path relative to the worktree root. It uses `/`
  and has the same meaning from every invocation directory. File operands select
  one exact Repository path. They do not expand directories, globs, or Git
  pathspec syntax.

- **Hunk**: the atomic, addressable unit of git-hunk. A contiguous change a user can
  `stage` / `show` / `discard` by `id`. Usually one `@@` section of a unified diff. A
  binary, mode-only, type, or empty tracked file change is a synthetic **whole-file
  hunk** with no `@@` range. It is the top-level object in `--json` because the tool is
  hunk-centric, not file-centric.

- **Hunk ID**: The deterministic address of one Hunk in the combined staged and
  unstaged inventory.

- **Unchanged Hunk**: A Hunk with the same Repository path and patch content. Text
  patch content includes context and newline state, but not range positions, section
  headings, or staged state. Whole-file patch content includes the binary, mode, or
  type change.

- **Duplicate Hunk group**: Two or more Hunks that have the same Repository path and
  patch content.

- **Conditional Hunk ID**: A unique Hunk ID that distinguishes members of a Duplicate
  Hunk group. It can change when the group changes.

- **Change group**: a maximal run of changed `-` and `+` lines with no context line
  between them. Partial line selection is unrestricted for pure additions, pure
  deletions, and one-for-one replacements. A larger grouped replacement is selected
  as a whole or not selected.

- **Whole-file hunk**: a hunk with no `@@` text range: a binary change, a mode-only
  (chmod) change, a type change (e.g. file to symlink), or an empty tracked addition
  or deletion. Has `header: null` and, in `show --json`, `lines: []`.

- **change_kind**: the git status letter for the hunk's file: `A` added, `D` deleted,
  `M` modified, `T` typechange. Always present. `R` (rename) and `C` (copy) are
  reserved and currently rejected before inventory or mutation (see #53). Mirrors
  `git diff --name-status`.

- **a_mode / b_mode** — the file's git mode (6-digit octal *string*, e.g. `"100644"`) on
  the pre-image (`a`) and post-image (`b`) side; `null` when that side does not exist.
  A mode change is `a_mode != b_mode`.

- **header** — for a text hunk, the **bare** `@@ -a,b +c,d @@` range, with git's trailing
  section heading stripped. `null` for a whole-file hunk. Distinct from the internal
  patch text, which keeps git's full `@@` line verbatim.

- **context_before** — the function/section heading git appends after the `@@` range
  (e.g. `def foo():`). The single source of that heading (it is *not* duplicated into
  `header`). `null` when the hunk has no heading (absence is uniformly `null`, like
  `header`).

- **lines[]** (`show --json` only) — the structured per-line hunk body. Each entry is
  `{n, op, content, no_newline?}`. `list --json` carries no body (it is an inventory view).

  - **n** — 1-based position within the hunk body; the index `-l` line-selection uses.
  - **op** — `" "` context, `"+"` addition, `"-"` deletion.
  - **no_newline** — optional; `true` when the line has no trailing newline. Replaces the
    free-floating `\ No newline at end of file` body line.

- **byte-safe union (`{text | bytes}`)** — the representation for any field holding
  arbitrary git/source-derived bytes (`file`, `context_before`, `lines[].content`):
  `{"text": s}` when the bytes are valid UTF-8, else `{"bytes": base64}`. Always an object
  (even for valid UTF-8) so consumers have one code path. The ripgrep `--json` idiom.

## Key decisions

- **ADR 0001** — `--json` schema v2 (typed Hunk model). The authoritative spec for the
  `--json` shape, except for the Hunk ID amendment in ADR 0003; converges
  #28/#40/#44/#50/#56 under one `schema_version: 2` bump.
- **ADR 0002** — Repository path. The authoritative spec for what a path means: one
  root-relative coordinate system, root-anchored git calls, exact literal operands;
  converges #127/#159.
- **ADR 0003**: Hunk IDs are durable for unchanged Hunks, unique in the combined
  staged and unstaged inventory, and conditional for Duplicate Hunk groups.

## Invariants

- `Hunk.file`, plain output, success output, file operands, internal patches, and
  whole-file mutations all use Repository paths.
- The hunk is the unit of addressing; `--json` is flat (`hunks: []`), not file-grouped.
- Display labels are derived in the UI layer from typed fields, never parsed back out of
  free text.
- The internal patch text fed to `git apply` preserves git's bytes verbatim; only the
  *JSON projection* is normalized (bared header, byte-safe union).
- A mode change and text changes in one file are separate, independently selectable
  Hunks.
- Detected rename, copy, and unmerged states fail before inventory output or mutation.
- An Unchanged Hunk keeps its Hunk ID when other complete Hunks move between staged
  and unstaged state.
- Moving a complete Hunk between staged and unstaged state does not change its Hunk ID.
- A partial-line operation creates new Hunks with new Hunk IDs.
- A Conditional Hunk ID can change when its Duplicate Hunk group changes.
- Each Hunk ID in an inventory addresses exactly one Hunk.
