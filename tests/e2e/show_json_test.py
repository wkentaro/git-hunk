import base64
from pathlib import Path

from git_hunk._cli import JSON_SCHEMA_VERSION

from .conftest import GitHunkCLI


def _two_group(cli: GitHunkCLI) -> str:
    cli.repo.write_file("f.txt", "a\nb\nc\nd\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nB\nc\nD\n")
    return cli.run_list_json("list", "--unstaged", "--json")[0]["id"]


def test_show_json_envelope_and_structured_body(cli: GitHunkCLI) -> None:
    hid = _two_group(cli)

    envelope = cli.run_list_envelope("show", hid, "--unstaged", "--json")
    assert envelope["schema_version"] == JSON_SCHEMA_VERSION
    body = envelope["hunks"][0]

    assert "diff" not in body  # the raw blob is gone from JSON
    ops = [line["op"] for line in body["lines"]]
    assert ops == [" ", "-", "+", " ", "-", "+"]
    # n is the 1-based body position; every line is counted, context included.
    assert [line["n"] for line in body["lines"]] == [1, 2, 3, 4, 5, 6]
    assert body["lines"][2]["content"] == {"text": "B"}


def test_show_json_n_round_trips_with_line_selection(cli: GitHunkCLI) -> None:
    hid = _two_group(cli)
    lines = cli.run_list_json("show", hid, "--unstaged", "--json")[0]["lines"]

    # Select exactly the first change group (the b -> B pair) by its n indices.
    ns = [line["n"] for line in lines if line["content"]["text"] in ("b", "B")]
    cli.run_ok("stage", hid, "-l", ",".join(str(n) for n in ns))

    assert cli.repo.git("show", ":f.txt") == "a\nB\nc\nd\n"


def test_show_json_non_utf8_content_round_trips_as_bytes(cli: GitHunkCLI) -> None:
    path = Path(cli.repo.path) / "f.txt"
    path.write_bytes(b"line\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    path.write_bytes(b"l\xe9ne\n")  # 0xe9 is invalid standalone UTF-8

    hid = cli.run_list_json("list", "--unstaged", "--json")[0]["id"]
    body = cli.run_list_json("show", hid, "--unstaged", "--json")[0]

    byte_contents = [
        line["content"] for line in body["lines"] if "bytes" in line["content"]
    ]
    assert byte_contents
    assert base64.b64decode(byte_contents[0]["bytes"]) == b"l\xe9ne"
