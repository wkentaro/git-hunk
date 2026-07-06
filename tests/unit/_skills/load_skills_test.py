import os
import sys
from pathlib import Path

import pytest

from git_hunk._skills import load_skills

_VALID = b"---\nname: good\ndescription: ok\n---\nbody\n"


def _write_skill(root: Path, name: str, content: bytes) -> None:
    (root / name).mkdir()
    (root / name / "SKILL.md").write_bytes(content)


def test_non_utf8_skill_is_skipped_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_skill(tmp_path, "good", _VALID)
    _write_skill(tmp_path, "bad", b"---\nname: bad\xff\n---\n")
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))

    assert [s.name for s in load_skills()] == ["good"]
    assert "could not read skill" in capsys.readouterr().err


def test_unclosed_frontmatter_loads_with_directory_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No closing ---: the skill still loads, but with no metadata.
    _write_skill(tmp_path, "core", b"---\nname: real\ndescription: d\n\nbody\n")
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))

    (skill,) = load_skills()
    assert skill.name == "core"
    assert skill.description == ""


def test_missing_skills_root_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path / "does-not-exist"))

    assert load_skills() == []


def test_directory_without_skill_md_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_skill(tmp_path, "good", _VALID)
    (tmp_path / "not-a-skill").mkdir()
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))

    assert [s.name for s in load_skills()] == ["good"]


@pytest.mark.skipif(
    sys.platform == "win32", reason="permission bits are not enforced on Windows"
)
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root bypasses permissions"
)
def test_unreadable_skill_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_skill(tmp_path, "good", _VALID)
    _write_skill(tmp_path, "noperm", b"---\nname: noperm\n---\n")
    unreadable = tmp_path / "noperm" / "SKILL.md"
    os.chmod(unreadable, 0o000)
    monkeypatch.setenv("GIT_HUNK_SKILLS_DIR", str(tmp_path))

    try:
        assert [s.name for s in load_skills()] == ["good"]
    finally:
        os.chmod(unreadable, 0o644)
