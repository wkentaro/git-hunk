import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import eval.repo as eval_repo
from eval.repo import GitRepo


def _assert_descendant_stopped(*, marker_path: Path, sentinel_path: Path) -> None:
    marker_path.write_text("check", encoding="utf-8")
    time.sleep(1)
    assert not sentinel_path.exists()


def test_run_stream_drains_stdout_and_stderr_without_deadlock(
    *, tmp_path: Path
) -> None:
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


def test_run_stream_timeout_kills_descendants_holding_pipes(*, tmp_path: Path) -> None:
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
    *,
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
            on_stdout_line=lambda _line: None,
        )

    assert time.monotonic() - started_at < 5
    _assert_descendant_stopped(
        marker_path=marker_path,
        sentinel_path=sentinel_path,
    )


def test_run_stream_interrupt_kills_descendants(*, tmp_path: Path) -> None:
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

    def interrupt(_line: str, /) -> None:
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


@pytest.mark.parametrize(
    "close_stdout",
    [False, True],
    ids=["while-streaming", "after-stdout-closes"],
)
def test_cancel_streams_stops_a_stream_on_another_thread(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close_stdout: bool
) -> None:
    # A fresh flag keeps the cancellation from leaking into other tests.
    monkeypatch.setattr(eval_repo, "_cancelled", threading.Event())
    marker_path = tmp_path / "marker"
    sentinel_path = tmp_path / "sentinel"
    closed_path = tmp_path / "closed"
    script = "\n".join(
        [
            "import os",
            "import time",
            "from pathlib import Path",
            "print('ready', flush=True)",
            *(
                ["os.close(1)", f"Path({str(closed_path)!r}).touch()"]
                if close_stdout
                else []
            ),
            f"marker = Path({str(marker_path)!r})",
            "while not marker.exists():",
            "    time.sleep(0.01)",
            f"Path({str(sentinel_path)!r}).write_text('alive')",
        ]
    )
    ready = threading.Event()
    errors: list[BaseException] = []

    def stream() -> None:
        try:
            GitRepo(tmp_path).run_stream(
                sys.executable,
                "-c",
                script,
                timeout_seconds=60,
                on_stdout_line=lambda _line: ready.set(),
            )
        except BaseException as error:  # noqa: BLE001 -- recorded for the assert
            errors.append(error)

    thread = threading.Thread(target=stream)
    thread.start()
    assert ready.wait(timeout=10)
    if close_stdout:
        # Cancel only once the stream has seen EOF and moved on to waiting
        # for the process, which is the wait that must still notice it.
        while not closed_path.exists():
            time.sleep(0.01)
        time.sleep(0.5)
    eval_repo.cancel_streams()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(errors) == 1
    assert "cancelled" in str(errors[0])
    _assert_descendant_stopped(marker_path=marker_path, sentinel_path=sentinel_path)
