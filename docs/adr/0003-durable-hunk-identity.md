# ADR 0003: Durable Hunk identity with conditional duplicate handling

**Status:** Accepted

v0.3.0 treats a Hunk ID as a durable address for an Unchanged Hunk. Its lifetime is
not limited to the current inventory. A canonical ID is a full SHA-256 value. JSON
returns the canonical ID. Human output shows an unambiguous prefix of at least seven
characters. Commands accept an unambiguous prefix. All commands calculate IDs from
the combined staged and unstaged inventory.

Text identity uses the Repository path and patch body. It excludes range positions,
section headings, and staged state. Whole-file identity includes the actual binary,
mode, or type change. An Unchanged Hunk keeps its ID when complete Hunks move between
staged and unstaged state.

Partial-line operations create new Hunks with new IDs. Each member of a Duplicate
Hunk group receives a unique Conditional Hunk ID. A Conditional Hunk ID can change
when its group changes. Every JSON Hunk reports `id_stability` as `"stable"` or
`"conditional"`. Human output marks each Conditional Hunk ID. The bundled skills
must get a new inventory after a partial-line operation or an operation on a
Conditional Hunk ID.

## Relationship to ADR 0001

This ADR amends the Hunk ID part of the JSON v2 schema in ADR 0001. The `id` field
contains the full canonical ID, and the required `id_stability` field is new. JSON v2
has not shipped in a release, so `schema_version` remains `2`.

We rejected snapshot-only IDs because they remove the main value of git-hunk. We also
rejected persistent lineage because its state and lifecycle cost are not justified for
v0.3.0.
