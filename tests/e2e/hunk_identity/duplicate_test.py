from pathlib import Path

import pytest

from ..conftest import GitHunkCLI


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


@pytest.mark.parametrize("ordinal", [0, 1])
def test_duplicate_member_keeps_id_across_different_diff_coordinates(
    cli: GitHunkCLI, ordinal: int
) -> None:
    prefix = [f"prefix {number}" for number in range(10)]
    block = ["A", "B", "C", "target", "D", "E", "F"]
    separator = [f"separator {number}" for number in range(30)]
    original = prefix + block + separator + block
    cli.repo.write_file("f.txt", "\n".join(original) + "\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
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
