import re

from ..conftest import GitHunkCLI


def test_json_returns_canonical_stable_hunk_id(
    modified_text_hunk: GitHunkCLI,
) -> None:
    [hunk] = modified_text_hunk.run_list_json("list", "--json")

    assert re.fullmatch(r"[0-9a-f]{64}", hunk["id"])
    assert hunk["id_stability"] == "stable"
