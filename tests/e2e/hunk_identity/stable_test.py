from ..conftest import GitHunkCLI


def test_complete_hunk_keeps_id_across_stage_and_unstage(
    modified_text_hunk: GitHunkCLI,
) -> None:
    cli = modified_text_hunk
    [unstaged] = cli.run_list_json("list", "--json")

    cli.run_ok("stage", unstaged["id"])
    [staged] = cli.run_list_json("list", "--json")
    cli.run_ok("unstage", unstaged["id"])

    assert staged["id"] == unstaged["id"]
    assert staged["id_stability"] == "stable"


def test_unchanged_hunk_keeps_id_when_its_range_shifts(cli: GitHunkCLI) -> None:
    original = [f"line {number}" for number in range(1, 41)]
    cli.repo.write_file("f.txt", "\n".join(original) + "\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    changed = original[:]
    changed.insert(1, "inserted")
    changed[35] = "changed late"
    cli.repo.write_file("f.txt", "\n".join(changed) + "\n")
    early, late = cli.run_list_json("list", "--unstaged", "--json")

    cli.run_ok("stage", early["id"])
    [shifted_late] = cli.run_list_json("list", "--unstaged", "--json")

    assert shifted_late["header"] != late["header"]
    assert shifted_late["id"] == late["id"]
    cli.run_ok("stage", late["id"])
    assert cli.repo.git("diff") == ""
