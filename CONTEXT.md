# git-hunk — domain context

## Glossary

- **Hunk** — the atomic, addressable unit of git-hunk. A contiguous change a user can
  `stage` / `show` / `discard` by `id`. Usually one `@@` section of a unified diff; for
  binary, mode-only, or type changes it is a synthetic **whole-file hunk** (no `@@` range).
  The top-level object in `--json` (the tool is hunk-centric, not file-centric).

- **Whole-file hunk** — a hunk with no `@@` text range: a binary change, a mode-only
  (chmod) change, or a type change (e.g. file ↔ symlink). Has `header: null` and (in
  `show --json`) `lines: []`.

- **change_kind** — the git status letter for the hunk's file: `A` added, `D` deleted,
  `M` modified, `T` typechange. Always present. `R` (rename) / `C` (copy) are reserved,
  not yet produced (see #53). Mirrors `git diff --name-status`.

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
  `--json` shape; converges #28/#40/#44/#50/#56 under one `schema_version: 2` bump.

## Invariants

- The hunk is the unit of addressing; `--json` is flat (`hunks: []`), not file-grouped.
- Display labels are derived in the UI layer from typed fields, never parsed back out of
  free text.
- The internal patch text fed to `git apply` preserves git's bytes verbatim; only the
  *JSON projection* is normalized (bared header, byte-safe union).
