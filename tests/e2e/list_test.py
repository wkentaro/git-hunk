from typing import Any
from typing import cast

from git_hunk._cli import JSON_SCHEMA_VERSION

from .conftest import GitHunkCLI

_REQUIRED_HUNK_KEYS = {
    "id",
    "file",
    "status",
    "change_kind",
    "a_mode",
    "b_mode",
    "binary",
    "header",
    "context_before",
    "additions",
    "deletions",
}
_STATUSES = {"staged", "unstaged", "untracked"}


def test_json_envelope_contract(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    envelope = cli.run_list_envelope("list", "--json")
    assert envelope["schema_version"] == JSON_SCHEMA_VERSION
    hunks = cast("list[dict[str, Any]]", envelope["hunks"])
    assert hunks
    for hunk in hunks:
        assert _REQUIRED_HUNK_KEYS <= hunk.keys()
        assert hunk["status"] in _STATUSES
        assert "diff" not in hunk
        assert "lines" not in hunk


def test_json_envelope_present_when_empty(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    envelope = cli.run_list_envelope("list", "--json")
    assert envelope["schema_version"] == JSON_SCHEMA_VERSION
    assert envelope["hunks"] == []


def test_no_changes_returns_empty_list(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "hello\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    hunks = cli.run_list_json("list", "--json")
    assert hunks == []


def test_single_file_single_hunk(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "line1\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "LINE1\nline2\nline3\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"]["text"] == "f.py"
    assert hunks[0]["additions"] == 1
    assert hunks[0]["deletions"] == 1
    assert "id" in hunks[0]


def test_single_file_multiple_hunks(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2
    assert all(h["file"]["text"] == "f.py" for h in hunks)


def test_multi_file_changes(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 2
    files = {h["file"]["text"] for h in hunks}
    assert files == {"a.py", "b.py"}


def test_list_staged(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    hunks = cli.run_list_json("list", "--staged", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"]["text"] == "f.py"


def test_list_file_filter(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_list_json("list", "--json", "a.py")
    assert len(hunks) == 1
    assert hunks[0]["file"]["text"] == "a.py"


def test_list_file_filter_untracked_normalizes_path(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("untracked.py", "new\n")
    cli.repo.write_file("sub/nested.py", "new\n")

    hunks = cli.run_list_json("list", "--json", "./untracked.py")
    assert [h["file"]["text"] for h in hunks] == ["untracked.py"]
    assert hunks[0]["status"] == "untracked"

    hunks = cli.run_list_json("list", "--json", "sub/nested.py")
    assert [h["file"]["text"] for h in hunks] == ["sub/nested.py"]


def test_list_new_file(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("new.py", "brand new\n")
    cli.repo.git("add", "new.py")

    hunks = cli.run_list_json("list", "--staged", "--json")
    assert len(hunks) == 1
    assert hunks[0]["file"]["text"] == "new.py"
    assert int(hunks[0]["additions"]) >= 1
    assert hunks[0]["deletions"] == 0


def test_list_default_shows_staged_and_unstaged(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "staged\n")
    cli.repo.git("add", "f.py")
    cli.repo.write_file("f.py", "unstaged\n")

    hunks = cli.run_list_json("list", "--json")
    statuses = {h["status"] for h in hunks}
    assert statuses == {"staged", "unstaged"}


def test_list_default_shows_untracked(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "init\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("untracked.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    untracked = [h for h in hunks if h["status"] == "untracked"]
    assert len(untracked) == 1
    assert untracked[0]["file"]["text"] == "untracked.py"
    # change_kind "A" must carry a b_mode (the would-be added side), per the ADR.
    assert untracked[0]["change_kind"] == "A"
    assert untracked[0]["a_mode"] is None
    assert untracked[0]["b_mode"] == "100644"


def test_empty_new_file_is_not_a_bogus_mode_hunk(cli: GitHunkCLI) -> None:
    # A staged empty new file has no @@ body and no mode change; it must not
    # surface as a whole-file hunk (which would render "Mode None -> ...").
    cli.repo.write_file("keep.txt", "x\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("empty.txt", "")
    cli.repo.git("add", "empty.txt")

    assert cli.run_list_json("list", "--staged", "--json") == []
    assert "Mode None" not in cli.run_ok("list", "--staged")


def test_list_unstaged_filter(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "staged\n")
    cli.repo.git("add", "f.py")
    cli.repo.write_file("f.py", "unstaged\n")

    hunks = cli.run_list_json("list", "--unstaged", "--json")
    assert all(h["status"] == "unstaged" for h in hunks)
    assert len(hunks) == 1


def test_list_staged_and_unstaged_mutual_exclusion(cli: GitHunkCLI) -> None:
    r = cli.run("list", "--staged", "--unstaged")
    assert r.returncode != 0
    assert "cannot use --staged and --unstaged together" in r.stderr
    assert "Usage: git-hunk list" in r.stderr


def test_list_status_field_in_json(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    assert all("status" in h for h in hunks)
    assert hunks[0]["status"] == "unstaged"


def test_list_plaintext_blank_lines_separate_sections_and_file_groups(
    cli: GitHunkCLI,
) -> None:
    cli.repo.write_file("s.py", "s\n")
    cli.repo.write_file("a.py", "a\n")
    cli.repo.write_file("b.py", "b\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("s.py", "S\n")
    cli.repo.git("add", "s.py")
    cli.repo.write_file("a.py", "A\n")
    cli.repo.write_file("b.py", "B\n")

    blocks = cli.run_ok("list").strip("\n").split("\n\n")
    assert len(blocks) == 3
    assert blocks[0].startswith("staged:")
    assert "s.py" in blocks[0]
    assert blocks[1].startswith("unstaged:")
    assert "a.py" in blocks[1]
    assert "b.py" in blocks[2]


def test_list_context_before_field_in_json_matches_display(cli: GitHunkCLI) -> None:
    body = ["def foo():"] + [f"    x{i} = {i}" for i in range(8)]
    cli.repo.write_file("f.py", "\n".join(body) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    body[4] = "    x3 = 99"
    cli.repo.write_file("f.py", "\n".join(body) + "\n")

    hunks = cli.run_list_json("list", "--json")
    assert len(hunks) == 1
    assert hunks[0]["context_before"] == {"text": "def foo():"}
    # Parity: the field equals the function context shown in the human display.
    assert "def foo():" in cli.run_ok("list")
