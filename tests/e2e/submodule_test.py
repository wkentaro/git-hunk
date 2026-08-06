import pytest

from .conftest import GitHunkCLI


def _bump_submodule(cli: GitHunkCLI, content: str) -> None:
    cli.repo.write_file("sub/f", content)
    cli.repo.git("-C", "sub", "add", "f")
    cli.repo.git("-C", "sub", "commit", "-m", content)


@pytest.fixture
def bumped_submodule(cli: GitHunkCLI) -> GitHunkCLI:
    # An embedded repository, not a .gitmodules-registered submodule: git records
    # both as a mode 160000 gitlink and emits the same "Subproject commit" diff,
    # and git-hunk never reads .gitmodules, so this skips `git submodule add` and
    # the protocol.file.allow override a local-path submodule would need on CI.
    cli.repo.git("init", "sub")
    cli.repo.git("-C", "sub", "config", "user.email", "test@test.com")
    cli.repo.git("-C", "sub", "config", "user.name", "Test")
    _bump_submodule(cli, "one")
    cli.repo.git("add", "sub")
    cli.repo.git("commit", "-m", "init")
    _bump_submodule(cli, "two")
    return cli


def test_list_reports_a_gitlink_bump_as_a_text_hunk(
    bumped_submodule: GitHunkCLI,
) -> None:
    hunks = bumped_submodule.run_list_json("list", "--unstaged", "--json")
    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk["file"]["text"] == "sub"
    assert hunk["change_kind"] == "M"
    assert hunk["a_mode"] == "160000"
    assert hunk["b_mode"] == "160000"
    # A moved submodule pointer is a one-line "Subproject commit" diff, so it is
    # a patchable text hunk rather than a whole-file one despite the odd mode.
    assert hunk["binary"] is False
    assert hunk["header"] == "@@ -1 +1 @@"
    assert hunk["additions"] == 1
    assert hunk["deletions"] == 1


def test_list_plaintext_gives_a_gitlink_no_whole_file_label(
    bumped_submodule: GitHunkCLI,
) -> None:
    out = bumped_submodule.run_ok("list", "--unstaged")
    assert "@@ -1 +1 @@" in out
    # The whole-file labels are reserved for hunks with no @@ range; a gitlink
    # bump has one, so it renders like any other text hunk.
    assert "Mode " not in out
    assert "Type change" not in out
    assert "Binary file" not in out


def test_show_renders_the_subproject_commit_body(
    bumped_submodule: GitHunkCLI,
) -> None:
    hunks = bumped_submodule.run_list_json("list", "--unstaged", "--json")
    assert len(hunks) == 1
    out = bumped_submodule.run_ok("show", hunks[0]["id"])
    assert "-Subproject commit " in out
    assert "+Subproject commit " in out


def test_stage_then_unstage_round_trips_a_gitlink_bump(
    bumped_submodule: GitHunkCLI,
) -> None:
    cli = bumped_submodule
    unstaged = cli.run_list_json("list", "--unstaged", "--json")
    assert len(unstaged) == 1
    cli.run_ok("stage", unstaged[0]["id"])
    assert cli.repo.git("diff", "--cached", "--name-only").split() == ["sub"]
    staged = cli.run_list_json("list", "--staged", "--json")
    assert len(staged) == 1
    cli.run_ok("unstage", staged[0]["id"])
    assert cli.repo.git("diff", "--cached").strip() == ""


def _capture_gitlink_state(cli: GitHunkCLI) -> tuple[str, str, str, str]:
    return (
        cli.repo.git("rev-parse", "HEAD"),
        cli.repo.git("ls-files", "--stage", "sub"),
        cli.repo.git("diff", "HEAD"),
        cli.repo.git("-C", "sub", "rev-parse", "HEAD"),
    )


def _assert_submodule_line_error(returncode: int, stderr: str) -> None:
    assert returncode == 1
    assert "submodule" in stderr
    assert "select the hunk as a whole" in stderr
    assert "git apply" not in stderr
    assert "corrupt patch" not in stderr


@pytest.mark.parametrize(
    "selector",
    [
        ("-l", "1"),
        ("--include-matching", "Subproject"),
        ("--exclude-matching", "Subproject"),
    ],
)
def test_stage_rejects_gitlink_line_selection(
    bumped_submodule: GitHunkCLI, selector: tuple[str, ...]
) -> None:
    cli = bumped_submodule
    before = _capture_gitlink_state(cli)

    result = cli.run("stage", cli.only_hunk_id("--unstaged"), *selector)

    _assert_submodule_line_error(result.returncode, result.stderr)
    assert _capture_gitlink_state(cli) == before


def test_unstage_rejects_gitlink_line_selection(
    bumped_submodule: GitHunkCLI,
) -> None:
    cli = bumped_submodule
    cli.run_ok("stage", cli.only_hunk_id("--unstaged"))
    before = _capture_gitlink_state(cli)

    result = cli.run("unstage", cli.only_hunk_id("--staged"), "-l", "1")

    _assert_submodule_line_error(result.returncode, result.stderr)
    assert _capture_gitlink_state(cli) == before


def test_discard_rejects_gitlink_line_selection(
    bumped_submodule: GitHunkCLI,
) -> None:
    cli = bumped_submodule
    before = _capture_gitlink_state(cli)

    result = cli.run("discard", cli.only_hunk_id("--unstaged"), "-l", "1")

    _assert_submodule_line_error(result.returncode, result.stderr)
    assert _capture_gitlink_state(cli) == before


def test_commit_rejects_gitlink_line_selection(
    bumped_submodule: GitHunkCLI,
) -> None:
    cli = bumped_submodule
    before = _capture_gitlink_state(cli)

    result = cli.run(
        "commit",
        cli.only_hunk_id("--unstaged"),
        "-l",
        "1",
        "-m",
        "partial",
    )

    _assert_submodule_line_error(result.returncode, result.stderr)
    assert _capture_gitlink_state(cli) == before
