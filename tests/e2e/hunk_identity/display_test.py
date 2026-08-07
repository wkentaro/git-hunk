from ..conftest import GitHunkCLI


def test_plain_list_shows_human_hunk_id_prefix(
    modified_text_hunk: GitHunkCLI,
) -> None:
    [hunk] = modified_text_hunk.run_list_json("list", "--json")

    output = modified_text_hunk.run_ok("list")

    assert hunk["id"][:7] in output
    assert hunk["id"] not in output
