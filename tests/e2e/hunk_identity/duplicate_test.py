from pathlib import Path

import pytest

from git_hunk._hunk import parse_hunk_range

from ..conftest import GitHunkCLI


def _commit_prefixed_duplicate_blocks(cli: GitHunkCLI) -> list[str]:
    # Room ahead of the first block, which the shared duplicate-group fixture
    # does not leave: its file starts at the block, so a change at the top falls
    # inside the first member's context and merges into it, dissolving the
    # group. Callers make their own edit on top of the returned lines.
    prefix = [f"prefix {number}" for number in range(10)]
    block = ["A", "B", "C", "target", "D", "E", "F"]
    separator = [f"separator {number}" for number in range(30)]
    original = prefix + block + separator + block
    cli.repo.write_file("f.txt", "\n".join(original) + "\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    return original


def test_duplicate_hunks_have_unique_conditional_ids(
    duplicate_hunks: GitHunkCLI,
) -> None:
    hunks = duplicate_hunks.run_list_json("list", "--json")

    assert len(hunks) == 2
    assert len({hunk["id"] for hunk in hunks}) == 2
    assert {hunk["id_stability"] for hunk in hunks} == {"conditional"}


def test_plain_output_marks_conditional_hunk_ids(
    duplicate_hunks: GitHunkCLI,
) -> None:
    output = duplicate_hunks.run_ok("list")

    assert output.count("conditional") == 2


def test_duplicate_ids_share_one_address_space_across_statuses(
    duplicate_hunks: GitHunkCLI,
) -> None:
    before = duplicate_hunks.run_list_json("list", "--json")
    before_ids = {hunk["id"] for hunk in before}

    duplicate_hunks.run_ok("stage", before[0]["id"])

    combined = duplicate_hunks.run_list_json("list", "--json")
    staged = duplicate_hunks.run_list_json("list", "--staged", "--json")
    unstaged = duplicate_hunks.run_list_json("list", "--unstaged", "--json")
    assert {hunk["id"] for hunk in combined} == before_ids
    assert {hunk["id"] for hunk in staged + unstaged} == before_ids
    assert {hunk["id_stability"] for hunk in combined} == {"conditional"}
    for hunk_id in before_ids:
        duplicate_hunks.run_ok("show", hunk_id)

    remaining_id = next(hunk_id for hunk_id in before_ids if hunk_id != before[0]["id"])
    duplicate_hunks.run_ok("stage", remaining_id)
    assert duplicate_hunks.repo.git("diff") == ""


def test_duplicate_group_keeps_ids_when_a_non_member_is_committed(
    duplicate_hunks: GitHunkCLI,
) -> None:
    # A Conditional Hunk ID survives a commit of a Hunk outside its group, so a
    # plan may queue complete-hunk operations ahead of an operation on one.
    for name in ("a.txt", "z.txt"):
        duplicate_hunks.repo.write_file(name, "old\n")
        duplicate_hunks.repo.git("add", name)
        duplicate_hunks.repo.git("commit", "-m", f"add {name}")
        duplicate_hunks.repo.write_file(name, "new\n")
    group_file = Path(duplicate_hunks.repo.path) / "f.txt"
    # The insertion goes in the middle of the duplicate_hunks fixture's
    # separator block, far enough from both members to stay its own hunk.
    # Adding a line rather than editing one also moves the second member's
    # pre-image coordinates once the non-member is committed.
    duplicate_hunks.repo.write_file(
        "f.txt",
        group_file.read_text().replace("separator 15\n", "separator 15\ninserted\n"),
    )
    before = duplicate_hunks.run_list_json("list", "--json")
    # The non-members sit in an earlier file, a later file, and between the two
    # members, so an ordinal counting hunks outside the group would move the
    # recorded IDs.
    assert [hunk["id_stability"] for hunk in before] == [
        "stable",
        "conditional",
        "stable",
        "conditional",
        "stable",
    ]
    # --json reports canonical IDs, so no prefix length can hide a renumbering.
    group_ids = [hunk["id"] for hunk in before if hunk["id_stability"] == "conditional"]
    non_member_ids = [hunk["id"] for hunk in before if hunk["id_stability"] == "stable"]

    duplicate_hunks.run_ok("commit", *non_member_ids, "-m", "unrelated")

    assert duplicate_hunks.repo.git("show", "HEAD:a.txt") == "new\n"
    assert duplicate_hunks.repo.git("show", "HEAD:z.txt") == "new\n"
    after = duplicate_hunks.run_list_json("list", "--json")
    # A list, not a set: the two members swapping IDs is a renumbering too.
    assert [hunk["id"] for hunk in after] == group_ids
    assert {hunk["id_stability"] for hunk in after} == {"conditional"}


def test_staged_duplicate_member_ignores_unstaged_hunks_in_other_files(
    duplicate_hunks: GitHunkCLI,
) -> None:
    # Ordering a Duplicate Hunk group's members adds the net line delta of the
    # unstaged Hunks that start before a staged member, and only Hunks with the
    # same Repository path can contribute one. Counting another path's would
    # move a staged member against its twin and renumber the group.
    members = duplicate_hunks.run_list_json("list", "--json")
    assert [hunk["id_stability"] for hunk in members] == ["conditional", "conditional"]
    first_start, second_start = (
        parse_hunk_range(hunk["header"]).new_start for hunk in members
    )
    assert first_start < second_start
    # Size the unrelated files from the fixture's own geometry. A miscount only
    # renumbers the group when it drags the staged member past its twin, so a
    # literal tuned to today's separation would leave the test passing and
    # detecting nothing the moment that separation grew.
    other_file_lines = second_start - first_start + 5
    # One unrelated path sorts before f.txt and one after. The guard compares
    # Repository paths rather than their order, so a half-guard that leaked only
    # one direction would survive a single unrelated path.
    for name in ("a.txt", "z.txt"):
        duplicate_hunks.repo.write_file(
            name, "".join(f"old {n}\n" for n in range(other_file_lines))
        )
        duplicate_hunks.repo.git("add", name)
        duplicate_hunks.repo.git("commit", "-m", f"add {name}")

    # Stage the later member: only a member whose position is adjusted at all
    # can be moved by a miscounted peer, and only the staged branch adjusts.
    duplicate_hunks.run_ok("stage", members[1]["id"])

    staged = duplicate_hunks.run_list_json("list", "--staged", "--json")
    assert len(staged) == 1
    # second_start was read before the member was staged, so pin that staging
    # did not move it. Given that, collapsing either unrelated path to one line
    # deletes four more lines than separate the pair, which is what makes a
    # miscount reorder them.
    assert parse_hunk_range(staged[0]["header"]).new_start == second_start
    # --json reports canonical IDs, so no prefix length can hide a renumbering.
    staged_id = staged[0]["id"]
    unstaged_id = duplicate_hunks.get_only_hunk_id("--unstaged")
    for name in ("a.txt", "z.txt"):
        duplicate_hunks.repo.write_file(name, "new\n")

    after_staged = duplicate_hunks.run_list_json("list", "--staged", "--json")
    after_unstaged = duplicate_hunks.run_list_json("list", "--unstaged", "--json")
    # Filtering on stability also fails if the group collapses to stable IDs.
    assert [
        hunk["id"]
        for hunk in after_staged + after_unstaged
        if hunk["id_stability"] == "conditional"
    ] == [staged_id, unstaged_id]


@pytest.mark.parametrize("ordinal", [0, 1])
def test_duplicate_member_keeps_id_across_different_diff_coordinates(
    cli: GitHunkCLI, ordinal: int
) -> None:
    original = _commit_prefixed_duplicate_blocks(cli)
    insertion = [f"inserted {number}" for number in range(100)]
    changed = insertion + [line.replace("target", "TARGET") for line in original]
    cli.repo.write_file("f.txt", "\n".join(changed) + "\n")
    duplicates = [
        hunk
        for hunk in cli.run_list_json("list", "--json")
        if hunk["id_stability"] == "conditional"
    ]

    cli.run_ok("stage", duplicates[ordinal]["id"])

    staged = cli.run_list_json("list", "--staged", "--json")
    remaining_duplicates = [
        hunk
        for hunk in cli.run_list_json("list", "--unstaged", "--json")
        if hunk["id_stability"] == "conditional"
    ]
    other_ordinal = 1 - ordinal
    assert [hunk["id"] for hunk in staged] == [duplicates[ordinal]["id"]]
    assert [hunk["id"] for hunk in remaining_duplicates] == [
        duplicates[other_ordinal]["id"]
    ]
    expected_index = original[:]
    target_index = expected_index.index("target")
    if ordinal == 1:
        target_index = expected_index.index("target", target_index + 1)
    expected_index[target_index] = "TARGET"
    assert cli.repo.git("show", ":f.txt") == "\n".join(expected_index) + "\n"
