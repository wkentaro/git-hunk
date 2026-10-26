import pytest

from git_hunk._hunk import NO_NEWLINE_MARKER

from .conftest import GitHunkCLI


def test_show_hunk_by_full_id(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id)
    assert r.returncode == 0
    assert "-old" in r.stdout
    assert "+new" in r.stdout


def test_show_hunk_by_uppercase_id(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id.upper())
    assert r.returncode == 0
    assert "-old" in r.stdout
    assert "+new" in r.stdout


def test_show_hunk_by_prefix(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    hunks = cli.run_list_json("list", "--json")
    prefix = hunks[0]["id"][:4]

    r = cli.run("show", prefix)
    assert r.returncode == 0
    assert "@@" in r.stdout


def test_show_staged_hunk(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    hunks = cli.run_list_json("list", "--staged", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id, "--staged")
    assert r.returncode == 0
    assert "+new" in r.stdout


def test_show_finds_staged_hunk_without_flag(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    cli.repo.git("add", "f.py")

    hunks = cli.run_list_json("list", "--staged", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id)
    assert r.returncode == 0
    assert "+new" in r.stdout


def test_show_no_args_shows_all(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "old\n")
    cli.repo.write_file("b.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("a.py", "staged\n")
    cli.repo.git("add", "a.py")
    cli.repo.write_file("b.py", "unstaged\n")

    r = cli.run("show")
    assert r.returncode == 0
    assert "+staged" in r.stdout
    assert "+unstaged" in r.stdout


@pytest.mark.parametrize(
    ("flags", "statuses"),
    [
        ([], ["staged", "unstaged"]),
        (["--staged"], ["staged"]),
        (["--unstaged"], ["unstaged"]),
    ],
)
def test_show_path_selects_every_visible_hunk_in_that_file(
    *, cli: GitHunkCLI, flags: list[str], statuses: list[str]
) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.write_file("other.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "staged\n")
    cli.repo.git("add", "f.py")
    cli.repo.write_file("f.py", "unstaged\n")
    cli.repo.write_file("other.py", "other\n")

    hunks = cli.run_list_json("show", "f.py", *flags, "--json")

    assert [h["status"] for h in hunks] == statuses
    assert all(h["file"]["text"] == "f.py" and h["lines"] for h in hunks)
    assert "other.py" not in cli.run_ok("show", "f.py", *flags)


def test_show_mixes_paths_and_ids_without_duplicates(*, cli: GitHunkCLI) -> None:
    for path in ("a.py", "b.py"):
        cli.repo.write_file(path, "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    for path in ("a.py", "b.py"):
        cli.repo.write_file(path, "new\n")
    a, b = cli.run_list_json("list", "--json")

    hunks = cli.run_list_json("show", "a.py", b["id"][:7], a["id"], "--json")

    assert [h["id"] for h in hunks] == [a["id"], b["id"]]


def test_show_hex_filename_takes_precedence_over_id_lookup(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("abcdef0", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("abcdef0", "new\n")

    assert "+new" in cli.run_ok("show", "abcdef0")


def test_show_rejects_id_outside_status_before_json_output(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")
    hunk_id = cli.get_only_hunk_id()

    result = cli.run("show", hunk_id, "--staged", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "not eligible" in result.stderr


def test_show_excludes_untracked_files_that_list_includes(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("tracked.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("tracked.py", "new\n")
    cli.repo.write_file("fresh.py", "fresh\n")

    listed = cli.run_list_json("list", "--json")
    untracked = [h for h in listed if h["status"] == "untracked"]
    assert [h["file"]["text"] for h in untracked] == ["fresh.py"]

    r = cli.run("show")
    assert r.returncode == 0
    assert "tracked.py" in r.stdout
    assert "fresh.py" not in r.stdout


def test_show_staged_and_unstaged_together_errors(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "new\n")

    r = cli.run("show", "--staged", "--unstaged")
    assert r.returncode != 0
    assert "cannot use --staged and --unstaged together" in r.stderr
    assert "Usage: git-hunk show" in r.stderr


def test_show_renders_no_newline_marker_unnumbered(*, cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nb\ncX")

    hunks = cli.run_list_json("list", "--json")
    hunk_id = hunks[0]["id"]

    r = cli.run("show", hunk_id)
    assert r.returncode == 0

    marker_line = next(
        line for line in r.stdout.splitlines() if NO_NEWLINE_MARKER in line
    )
    assert marker_line.strip() == NO_NEWLINE_MARKER

    assert "+cX" in r.stdout


def test_show_puts_exactly_one_rule_between_consecutive_hunks(
    *,
    cli: GitHunkCLI,
) -> None:
    # The rule divides hunks, so it appears between them and never leads the
    # output: N hunks render N-1 rules. Three files rather than two, so that a
    # rule firing once and never again stays distinguishable from the contract.
    paths = ["a.py", "b.py", "c.py"]
    for path in paths:
        cli.repo.write_file(path, "old\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    for path in paths:
        cli.repo.write_file(path, "new\n")

    lines = cli.run_ok("show").splitlines()
    rules = [i for i, line in enumerate(lines) if set(line.strip()) == {"─"}]
    headers = [i for i, line in enumerate(lines) if line.split(" ")[0] in paths]
    assert len(rules) == len(paths) - 1
    assert headers[0] < rules[0] < headers[1] < rules[1] < headers[2]
