import ctypes
import os
import queue
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast


class GitRepo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def run(
        self,
        *args: str,
        timeout_seconds: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            capture_output=True,
            cwd=self.path,
            env=make_subprocess_env(),
            text=True,
            timeout=timeout_seconds,
        )

    def run_bytes(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            list(args),
            capture_output=True,
            cwd=self.path,
            env=make_subprocess_env(),
        )

    def run_stream(
        self,
        *args: str,
        timeout_seconds: float,
        on_stdout_line: Callable[[str], None],
    ) -> subprocess.CompletedProcess[str]:
        command = list(args)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        process = subprocess.Popen(
            command,
            cwd=self.path,
            env=make_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
        stdout = process.stdout
        stderr = process.stderr
        if stdout is None or stderr is None:
            raise RuntimeError("streaming subprocess pipes are unavailable")
        try:
            windows_job = (
                _WindowsJob.create_for_suspended_process(process=process)
                if os.name == "nt"
                else None
            )
        except BaseException:
            process.kill()
            process.wait()
            raise

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stdout_queue: queue.Queue[str | None] = queue.Queue()

        def read_stdout() -> None:
            try:
                for line in stdout:
                    stdout_queue.put(line)
            finally:
                stdout_queue.put(None)

        def read_stderr() -> None:
            stderr_lines.extend(stderr)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        deadline = time.monotonic() + timeout_seconds

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                line = stdout_queue.get(timeout=remaining)
                if line is None:
                    break
                stdout_lines.append(line)
                on_stdout_line(line)
            process.wait(timeout=max(0, deadline - time.monotonic()))
            for reader_thread in (stdout_thread, stderr_thread):
                reader_thread.join(timeout=max(0, deadline - time.monotonic()))
                if reader_thread.is_alive():
                    raise subprocess.TimeoutExpired(command, timeout_seconds)
        except (queue.Empty, subprocess.TimeoutExpired) as error:
            _stop_process_tree(
                process=process,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
                windows_job=windows_job,
            )
            while not stdout_queue.empty():
                line = stdout_queue.get_nowait()
                if line is not None:
                    stdout_lines.append(line)
                    on_stdout_line(line)
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=timeout_seconds,
                output="".join(stdout_lines),
                stderr="".join(stderr_lines),
            ) from error
        except BaseException:
            _stop_process_tree(
                process=process,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
                windows_job=windows_job,
            )
            raise

        if windows_job is not None:
            windows_job.close()
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )

    def git(self, *args: str) -> str:
        result = self.run("git", *args)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def git_bytes(self, *args: str) -> bytes:
        result = self.run_bytes("git", *args)
        if result.returncode != 0:
            detail = result.stderr.decode(errors="surrogateescape")
            raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
        return result.stdout

    def write_file(
        self, name: str, content: str | bytes, *, executable: bool = False
    ) -> None:
        file_path = self.path / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        file_path.write_bytes(data)
        if executable:
            file_path.chmod(file_path.stat().st_mode | stat.S_IXUSR)


class _WindowsJob:
    def __init__(self, *, kernel32: ctypes.CDLL, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @classmethod
    def create_for_suspended_process(
        cls, *, process: subprocess.Popen[str]
    ) -> "_WindowsJob | None":
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("read_operation_count", ctypes.c_ulonglong),
                ("write_operation_count", ctypes.c_ulonglong),
                ("other_operation_count", ctypes.c_ulonglong),
                ("read_transfer_count", ctypes.c_ulonglong),
                ("write_transfer_count", ctypes.c_ulonglong),
                ("other_transfer_count", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time_limit", ctypes.c_longlong),
                ("per_job_user_time_limit", ctypes.c_longlong),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set_size", ctypes.c_size_t),
                ("maximum_working_set_size", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("basic_limit_information", BasicLimitInformation),
                ("io_info", IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        class ThreadEntry32(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("usage_count", wintypes.DWORD),
                ("thread_id", wintypes.DWORD),
                ("owner_process_id", wintypes.DWORD),
                ("base_priority", wintypes.LONG),
                ("priority_delta", wintypes.LONG),
                ("flags", wintypes.DWORD),
            ]

        kernel32 = cast(
            ctypes.CDLL,
            getattr(ctypes, "WinDLL")("kernel32", use_last_error=True),
        )
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Thread32First.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ThreadEntry32),
        ]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ThreadEntry32),
        ]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenThread.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        job: _WindowsJob | None = None
        handle = kernel32.CreateJobObjectW(None, None)
        if handle:
            information = ExtendedLimitInformation()
            information.basic_limit_information.limit_flags = 0x00002000
            configured = kernel32.SetInformationJobObject(
                handle,
                9,
                ctypes.byref(information),
                ctypes.sizeof(information),
            )
            process_handle = kernel32.OpenProcess(
                0x00000101,
                False,
                process.pid,
            )
            assigned = bool(
                process_handle
                and kernel32.AssignProcessToJobObject(handle, process_handle)
            )
            if process_handle:
                kernel32.CloseHandle(process_handle)
            if configured and assigned:
                job = cls(kernel32=kernel32, handle=handle)
            else:
                kernel32.CloseHandle(handle)

        if not cls._resume_process(
            kernel32=kernel32,
            process_id=process.pid,
            thread_entry_type=ThreadEntry32,
        ):
            if job is not None:
                job.close()
            raise RuntimeError("failed to resume the streaming subprocess")
        return job

    @staticmethod
    def _resume_process(
        *, kernel32: ctypes.CDLL, process_id: int, thread_entry_type: type
    ) -> bool:
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return False
        try:
            entry = thread_entry_type()
            entry.size = ctypes.sizeof(entry)
            has_entry = bool(kernel32.Thread32First(snapshot, ctypes.byref(entry)))
            while has_entry:
                if entry.owner_process_id == process_id:
                    thread_handle = kernel32.OpenThread(0x0002, False, entry.thread_id)
                    if not thread_handle:
                        return False
                    try:
                        return kernel32.ResumeThread(thread_handle) != 0xFFFFFFFF
                    finally:
                        kernel32.CloseHandle(thread_handle)
                has_entry = bool(kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
            return False
        finally:
            kernel32.CloseHandle(snapshot)

    def terminate(self) -> bool:
        return bool(self._kernel32.TerminateJobObject(self._handle, 1))

    def close(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _stop_process_tree(
    *,
    process: subprocess.Popen[str],
    stdout_thread: threading.Thread,
    stderr_thread: threading.Thread,
    windows_job: _WindowsJob | None,
) -> None:
    _kill_process_tree(process=process, windows_job=windows_job)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if windows_job is not None:
        windows_job.close()


def _kill_process_tree(
    *, process: subprocess.Popen[str], windows_job: _WindowsJob | None
) -> None:
    if os.name == "nt":
        if windows_job is not None and windows_job.terminate():
            return
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def init_repo(path: str | Path) -> GitRepo:
    repo = GitRepo(path)
    repo.git("init", "--quiet")
    repo.git("config", "user.email", "test@test.com")
    repo.git("config", "user.name", "Test")
    repo.git("config", "core.autocrlf", "false")
    repo.git("config", "core.quotePath", "false")
    return repo


def make_subprocess_env() -> dict[str, str]:
    """Build a reproducible environment for eval subprocesses."""
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("GIT_"):
            del env[name]
    # Keep eval output stable when the invoking shell forces or disables color.
    for name in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        env.pop(name, None)
    env["NO_COLOR"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env
