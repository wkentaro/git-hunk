import subprocess
import sys
import time
from pathlib import Path

import pytest

from eval.repo import GitRepo


def _assert_descendant_stopped(*, marker_path: Path, sentinel_path: Path) -> None:
    marker_path.write_text("check", encoding="utf-8")
    time.sleep(1)
    assert not sentinel_path.exists()


def test_run_stream_drains_stdout_and_stderr_without_deadlock(tmp_path: Path) -> None:
    stdout_lines: list[str] = []
    script = "\n".join(
        [
            "import sys",
            "print('first', flush=True)",
            "sys.stderr.write('e' * 1_000_000)",
            "sys.stderr.flush()",
            "print('second', flush=True)",
        ]
    )

    result = GitRepo(tmp_path).run_stream(
        sys.executable,
        "-c",
        script,
        timeout_seconds=5,
        on_stdout_line=stdout_lines.append,
    )

    assert result.returncode == 0
    assert result.stdout == "first\nsecond\n"
    assert len(result.stderr) == 1_000_000
    assert stdout_lines == ["first\n", "second\n"]


def test_run_stream_timeout_kills_descendants_holding_pipes(tmp_path: Path) -> None:
    stdout_lines: list[str] = []
    script = "\n".join(
        [
            "import subprocess",
            "import sys",
            "import time",
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
            "print('ready', flush=True)",
            "time.sleep(60)",
        ]
    )
    started_at = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        GitRepo(tmp_path).run_stream(
            sys.executable,
            "-c",
            script,
            timeout_seconds=1,
            on_stdout_line=stdout_lines.append,
        )

    assert time.monotonic() - started_at < 5
    assert caught.value.output == "ready\n"
    assert stdout_lines == ["ready\n"]


def test_run_stream_timeout_kills_descendant_holding_only_stderr(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "check-descendant"
    sentinel_path = tmp_path / "descendant-survived"
    descendant_script = "\n".join(
        [
            "import time",
            "from pathlib import Path",
            f"marker = Path({str(marker_path)!r})",
            "while not marker.exists():",
            "    time.sleep(0.01)",
            f"Path({str(sentinel_path)!r}).write_text('alive')",
        ]
    )
    script = "\n".join(
        [
            "import subprocess",
            "import sys",
            "subprocess.Popen(",
            f"    [sys.executable, '-c', {descendant_script!r}],",
            "    stdout=subprocess.DEVNULL,",
            ")",
        ]
    )
    started_at = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        GitRepo(tmp_path).run_stream(
            sys.executable,
            "-c",
            script,
            timeout_seconds=0.5,
            on_stdout_line=lambda line: None,
        )

    assert time.monotonic() - started_at < 5
    _assert_descendant_stopped(
        marker_path=marker_path,
        sentinel_path=sentinel_path,
    )


def test_run_stream_interrupt_kills_descendants(tmp_path: Path) -> None:
    marker_path = tmp_path / "check-descendant"
    sentinel_path = tmp_path / "descendant-survived"
    descendant_script = "\n".join(
        [
            "import time",
            "from pathlib import Path",
            f"marker = Path({str(marker_path)!r})",
            "while not marker.exists():",
            "    time.sleep(0.01)",
            f"Path({str(sentinel_path)!r}).write_text('alive')",
        ]
    )
    script = "\n".join(
        [
            "import subprocess",
            "import sys",
            "import time",
            f"subprocess.Popen([sys.executable, '-c', {descendant_script!r}])",
            "print('ready', flush=True)",
            "time.sleep(60)",
        ]
    )

    def interrupt(line: str) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        GitRepo(tmp_path).run_stream(
            sys.executable,
            "-c",
            script,
            timeout_seconds=5,
            on_stdout_line=interrupt,
        )

    _assert_descendant_stopped(
        marker_path=marker_path,
        sentinel_path=sentinel_path,
    )
