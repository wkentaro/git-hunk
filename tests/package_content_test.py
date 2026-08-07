import subprocess
import tarfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Final


def test_wheel_and_source_distribution_contain_only_package_files(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path)],
        capture_output=True,
        cwd=repository_root,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    tracked_package_files = {
        PurePosixPath(name)
        for name in subprocess.run(
            ["git", "ls-files", "git_hunk"],
            capture_output=True,
            check=True,
            cwd=repository_root,
            text=True,
        ).stdout.splitlines()
    }

    (wheel_path,) = tmp_path.glob("*.whl")
    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_members = [PurePosixPath(name) for name in wheel.namelist()]
    assert wheel_members
    assert all(_is_allowed_wheel_member(member) for member in wheel_members)
    assert {
        member for member in wheel_members if member.parts[0] == "git_hunk"
    } == tracked_package_files

    (source_path,) = tmp_path.glob("*.tar.gz")
    with tarfile.open(source_path, mode="r:gz") as source:
        source_members = [PurePosixPath(name) for name in source.getnames()]
    assert source_members
    assert all(_is_allowed_source_member(member) for member in source_members)
    source_package_files = {
        PurePosixPath(*member.parts[1:])
        for member in source_members
        if len(member.parts) > 1 and member.parts[1] == "git_hunk"
    }
    assert source_package_files == tracked_package_files


def _is_allowed_wheel_member(member: PurePosixPath) -> bool:
    return member.parts[0] == "git_hunk" or member.parts[0].endswith(".dist-info")


def _is_allowed_source_member(member: PurePosixPath) -> bool:
    ALLOWED_ROOT_FILES: Final = {
        ".gitignore",
        "LICENSE",
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
    }
    if len(member.parts) < 2:
        return True
    relative_parts = member.parts[1:]
    return relative_parts[0] == "git_hunk" or (
        len(relative_parts) == 1 and relative_parts[0] in ALLOWED_ROOT_FILES
    )
