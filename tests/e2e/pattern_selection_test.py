from pathlib import Path

import pytest

from .conftest import GitHunkCLI

# HEAD "keep" -> working "keep / DEBUG line / FEATURE line": one hunk, two added
# lines. Body line numbers: 1=" keep" 2="+DEBUG line" 3="+FEATURE line".


@pytest.fixture
def added_lines(cli: GitHunkCLI) -> GitHunkCLI:
    cli.repo.write_file("f.txt", "keep\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "keep\nDEBUG line\nFEATURE line\n")
    return cli


def _only_id(cli: GitHunkCLI, *flags: str) -> str:
    hunks = cli.run_list_json("list", *flags, "--json")
    assert len(hunks) == 1
    return hunks[0]["id"]


def _working(cli: GitHunkCLI) -> str:
    return (Path(cli.repo.path) / "f.txt").read_text()


def test_stage_exclude_matching(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "stage", _only_id(added_lines, "--unstaged"), "--exclude-matching", "DEBUG"
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nFEATURE line\n"


def test_stage_include_matching(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "stage", _only_id(added_lines, "--unstaged"), "--include-matching", "DEBUG"
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nDEBUG line\n"


def test_unstage_include_matching(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok("stage", _only_id(added_lines, "--unstaged"))
    added_lines.run_ok(
        "unstage", _only_id(added_lines, "--staged"), "--include-matching", "DEBUG"
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nFEATURE line\n"


def test_discard_include_matching(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "discard", _only_id(added_lines, "--unstaged"), "--include-matching", "DEBUG"
    )
    assert _working(added_lines) == "keep\nFEATURE line\n"


def test_discard_exclude_matching(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "discard", _only_id(added_lines, "--unstaged"), "--exclude-matching", "DEBUG"
    )
    assert _working(added_lines) == "keep\nDEBUG line\n"


def test_unstage_regex(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok("stage", _only_id(added_lines, "--unstaged"))
    added_lines.run_ok(
        "unstage",
        _only_id(added_lines, "--staged"),
        "--include-matching",
        "D.BUG",
        "--regex",
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nFEATURE line\n"


def test_repeated_flag_is_ored(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "stage",
        _only_id(added_lines, "--unstaged"),
        "--include-matching",
        "DEBUG",
        "--include-matching",
        "FEATURE",
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nDEBUG line\nFEATURE line\n"


def test_matching_is_case_sensitive(added_lines: GitHunkCLI) -> None:
    r = added_lines.run(
        "stage", _only_id(added_lines, "--unstaged"), "--include-matching", "debug"
    )
    assert r.returncode != 0
    assert "no changed line matches" in r.stderr
    assert added_lines.repo.git("show", ":f.txt") == "keep\n"


def test_literal_metacharacters_match_literally(added_lines: GitHunkCLI) -> None:
    # 'D.BUG' is not a substring of any line; as a literal it matches nothing.
    r = added_lines.run(
        "stage", _only_id(added_lines, "--unstaged"), "--include-matching", "D.BUG"
    )
    assert r.returncode != 0
    assert "no changed line matches" in r.stderr


def test_regex_opt_in(added_lines: GitHunkCLI) -> None:
    added_lines.run_ok(
        "stage",
        _only_id(added_lines, "--unstaged"),
        "--include-matching",
        "D.BUG",
        "--regex",
    )
    assert added_lines.repo.git("show", ":f.txt") == "keep\nDEBUG line\n"


def test_zero_matches_stages_nothing(added_lines: GitHunkCLI) -> None:
    r = added_lines.run(
        "stage", _only_id(added_lines, "--unstaged"), "--exclude-matching", "nope"
    )
    assert r.returncode != 0
    assert "no changed line matches" in r.stderr
    assert added_lines.repo.git("show", ":f.txt") == "keep\n"


def test_line_spec_and_matching_are_mutually_exclusive(added_lines: GitHunkCLI) -> None:
    r = added_lines.run(
        "stage",
        _only_id(added_lines, "--unstaged"),
        "-l",
        "2",
        "--include-matching",
        "DEBUG",
    )
    assert r.returncode != 0
    assert "choose one of" in r.stderr


def test_both_matching_flags_are_mutually_exclusive(added_lines: GitHunkCLI) -> None:
    r = added_lines.run(
        "stage",
        _only_id(added_lines, "--unstaged"),
        "--include-matching",
        "DEBUG",
        "--exclude-matching",
        "FEATURE",
    )
    assert r.returncode != 0
    assert "choose one of" in r.stderr


def test_regex_without_matching_flag_is_rejected(added_lines: GitHunkCLI) -> None:
    # --regex alone has no effect; reject it rather than silently staging the hunk.
    r = added_lines.run("stage", _only_id(added_lines, "--unstaged"), "--regex")
    assert r.returncode != 0
    assert "--regex requires" in r.stderr
    assert added_lines.repo.git("show", ":f.txt") == "keep\n"


def test_empty_include_matching_is_rejected(added_lines: GitHunkCLI) -> None:
    # An empty pattern would match every line; reject it rather than silently
    # staging the whole hunk.
    r = added_lines.run(
        "stage", _only_id(added_lines, "--unstaged"), "--include-matching", ""
    )
    assert r.returncode != 0
    assert "empty match pattern" in r.stderr
    assert added_lines.repo.git("show", ":f.txt") == "keep\n"
