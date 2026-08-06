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
