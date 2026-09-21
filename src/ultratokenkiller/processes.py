"""Owned process trees and bounded, disk-free stdout capture."""
from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading


def run_owned(command, *, input: str, timeout: float, env=None, cwd=None):
    """Run an acceptance client with ownership of its complete process tree.

    Output is kept in memory only. On timeout the CLI launcher and descendants
    are terminated before returning, so a timed-out client cannot spend budget.
    """
    job = WindowsJob() if sys.platform == "win32" else None
    process = None
    terminated = False
    def terminate():
        nonlocal terminated
        if terminated:
            return
        terminated = True
        if job:
            job.terminate()
        elif process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   env=env, cwd=cwd, creationflags=0x00000004 if job else 0,
                                   start_new_session=job is None)
        if job:
            job.attach_and_resume(process)
        try:
            stdout, stderr = process.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate()
            stdout, stderr = process.communicate(timeout=5)
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from None
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if process is not None:
            terminate()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        if job:
            job.close()


class WindowsJob:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                        ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def attach_and_resume(self, process):
        from ctypes import wintypes
        if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        resume = self.ctypes.WinDLL("ntdll").NtResumeProcess
        resume.argtypes = [wintypes.HANDLE]
        resume.restype = self.ctypes.c_long
        if resume(wintypes.HANDLE(int(process._handle))) != 0:
            raise OSError("Could not resume owned command process")

    def terminate(self):
        self.kernel.TerminateJobObject(self.handle, 130)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def execute(command, *, capture: bool, write, memory_limit=8*1024*1024):
    """Return exit status, captured bytes (or None if streamed), and fallback reason."""
    if not capture:
        return subprocess.call(command), None, "passthrough"
    job = WindowsJob() if sys.platform == "win32" else None
    process = None
    reader = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE if capture else None,
                                   creationflags=0x00000004 if job else 0, start_new_session=job is None)
        if job:
            job.attach_and_resume(process)
        if not capture:
            return process.wait(), None, "passthrough"
        messages = queue.Queue(maxsize=4)
        stop = threading.Event()
        def enqueue(item):
            while not stop.is_set():
                try:
                    messages.put(item, timeout=.1)
                    return
                except queue.Full:
                    continue
        def read():
            try:
                while chunk := process.stdout.read1(65536):
                    enqueue(chunk)
            finally:
                enqueue(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        content = bytearray()
        streamed = False
        while True:
            try:
                part = messages.get(timeout=.1)
            except queue.Empty:
                continue
            if part is None:
                break
            if streamed:
                write(part)
            elif len(content)+len(part) > memory_limit:
                write(bytes(content))
                content.clear()
                write(part)
                streamed = True
            else:
                content.extend(part)
        code = process.wait()
        return code, None if streamed else bytes(content), "memory_limit_passthrough" if streamed else None
    except BaseException:
        if process is not None:
            if job:
                job.terminate()
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if not job:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
        raise
    finally:
        if reader:
            stop.set()
            reader.join(timeout=1)
        if process and process.stdout:
            process.stdout.close()
        if job:
            job.close()


def execute_channels(
    command,
    *,
    capture: bool,
    write_stdout,
    write_stderr,
    memory_limit=8 * 1024 * 1024,
):
    """Capture stdout/stderr independently while preserving exit and cancellation semantics.

    The memory limit applies to both channels together.  Once exceeded, buffered bytes are
    written back to their original channels and the remainder streams without compression.
    """
    if not capture:
        return subprocess.call(command), None, None, "passthrough"
    job = WindowsJob() if sys.platform == "win32" else None
    process = None
    readers = []
    stop = threading.Event()
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x00000004 if job else 0,
            start_new_session=job is None,
        )
        if job:
            job.attach_and_resume(process)
        messages = queue.Queue(maxsize=8)

        def enqueue(item):
            while not stop.is_set():
                try:
                    messages.put(item, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def read(channel, stream):
            try:
                while chunk := stream.read1(65536):
                    enqueue((channel, chunk))
            finally:
                enqueue((channel, None))

        for channel, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            reader = threading.Thread(target=read, args=(channel, stream), daemon=True)
            readers.append(reader)
            reader.start()

        content = {"stdout": bytearray(), "stderr": bytearray()}
        writers = {"stdout": write_stdout, "stderr": write_stderr}
        finished = set()
        streamed = False
        while len(finished) < 2:
            try:
                channel, part = messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if part is None:
                finished.add(channel)
                continue
            if streamed:
                writers[channel](part)
                continue
            total = len(content["stdout"]) + len(content["stderr"]) + len(part)
            if total > memory_limit:
                if content["stdout"]:
                    write_stdout(bytes(content["stdout"]))
                if content["stderr"]:
                    write_stderr(bytes(content["stderr"]))
                content["stdout"].clear()
                content["stderr"].clear()
                writers[channel](part)
                streamed = True
            else:
                content[channel].extend(part)
        code = process.wait()
        if streamed:
            return code, None, None, "memory_limit_passthrough"
        return code, bytes(content["stdout"]), bytes(content["stderr"]), None
    except BaseException:
        if process is not None:
            if job:
                job.terminate()
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if not job:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
        raise
    finally:
        stop.set()
        for reader in readers:
            reader.join(timeout=1)
        if process:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        if job:
            job.close()
