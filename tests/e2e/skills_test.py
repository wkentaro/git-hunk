from pathlib import Path

import pytest

from .conftest import GitHunkCLI


def test_help_mentions_skills(cli: GitHunkCLI) -> None:
    out = cli.run_ok("--help")
    assert "Start here (for AI agents)" in out
    assert "git-hunk skills get core" in out
    assert "skills" in out


def test_list_is_default(cli: GitHunkCLI) -> None:
    assert cli.run_ok("skills") == cli.run_ok("skills", "list")


def test_list_shows_skill_name(cli: GitHunkCLI) -> None:
    assert "core" in cli.run_ok("skills", "list")


def test_list_json(cli: GitHunkCLI) -> None:
    skills = cli.run_json("skills", "list", "--json")
    names = [skill["name"] for skill in skills]
    assert "core" in names
    core = next(s for s in skills if s["name"] == "core")
    assert "git-hunk" in core["description"].lower()


def test_get_outputs_full_content(cli: GitHunkCLI) -> None:
    out = cli.run_ok("skills", "get", "core")
    assert "name: core" in out
    assert "## The core loop" in out


def test_get_json(cli: GitHunkCLI) -> None:
    skills = cli.run_json("skills", "get", "core", "--json")
    assert skills[0]["name"] == "core"
    assert "## The core loop" in skills[0]["content"]


@pytest.fixture
def two_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("alpha", "beta"):
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name.capitalize()} skill\n---\n\n"
            f"{name.capitalize()} body line\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))


def test_get_multiple_joins_bodies(cli: GitHunkCLI, two_skills: None) -> None:
    out = cli.run_ok("skills", "get", "alpha", "beta")
    assert "Alpha body line\n---\nname: beta" in out


def test_get_multiple_json(cli: GitHunkCLI, two_skills: None) -> None:
    skills = cli.run_json("skills", "get", "alpha", "beta", "--json")
    assert [s["name"] for s in skills] == ["alpha", "beta"]
    assert "Beta body line" in skills[1]["content"]


def test_get_unknown_skill_errors(cli: GitHunkCLI) -> None:
    result = cli.run("skills", "get", "nope")
    assert result.returncode == 1
    assert "not found" in result.stderr
    assert "core" in result.stderr


def test_get_requires_name(cli: GitHunkCLI) -> None:
    result = cli.run("skills", "get")
    assert result.returncode == 2
    assert "requires a skill name" in result.stderr


def test_path_prints_root(cli: GitHunkCLI) -> None:
    out = cli.run_ok("skills", "path").strip()
    assert out.endswith("skills")


def test_path_of_named_skill(cli: GitHunkCLI) -> None:
    out = cli.run_ok("skills", "path", "core").strip()
    assert Path(out).parts[-2:] == ("skills", "core")


def test_path_rejects_multiple_names(cli: GitHunkCLI) -> None:
    result = cli.run("skills", "path", "core", "extra")
    assert result.returncode == 2
    assert "at most one" in result.stderr


def test_list_rejects_arguments(cli: GitHunkCLI) -> None:
    result = cli.run("skills", "list", "extra")
    assert result.returncode == 2
    assert "takes no arguments" in result.stderr


def test_list_empty_skills_dir_exits_zero(
    cli: GitHunkCLI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))
    assert cli.run("skills", "list").returncode == 0
    assert cli.run_json("skills", "list", "--json") == []


def test_unknown_subcommand_errors(cli: GitHunkCLI) -> None:
    result = cli.run("skills", "frob")
    assert result.returncode == 2
    assert "unrecognized skills subcommand 'frob'" in result.stderr
