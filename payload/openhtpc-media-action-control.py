#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""One local media action request and HOME-owned worker lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


MAX_TOKEN_CHARS = 256
MAX_LOG_BYTES = 256 * 1024
_TOKEN_PATTERN = re.compile(r"iact_[A-Za-z0-9_-]+", re.ASCII)


def request_path(home: Path) -> Path:
    return home / ".local/state/openhtpc/media-action.fifo"


def lock_path(home: Path) -> Path:
    return home / ".local/state/openhtpc/media/media-action.lock"


def status_path(home: Path) -> Path:
    return home / ".local/state/openhtpc/media/media-action-status.json"


def log_path(home: Path) -> Path:
    return home / ".local/state/openhtpc/media/media-action.log"


def valid_action_token(token: object) -> bool:
    return (
        type(token) is str
        and 5 < len(token) <= MAX_TOKEN_CHARS
        and token.isascii()
        and _TOKEN_PATTERN.fullmatch(token) is not None
    )


def action_running(home: Path) -> bool:
    """Return true only when the lifetime lock is definitely held."""
    target = lock_path(home)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError:
        return False
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def request_action(home: Path, token: str) -> bool:
    """Submit one atomic request without waiting for HOME or the worker."""
    if not valid_action_token(token) or action_running(home):
        return False
    encoded = token.encode("ascii") + b"\n"
    try:
        fd = os.open(request_path(home), os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            return os.write(fd, encoded) == len(encoded)
        finally:
            os.close(fd)
    except OSError:
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_status(home: Path, status: dict) -> None:
    target = status_path(home)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(status, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_status(home: Path) -> dict | None:
    try:
        value = json.loads(status_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if type(value) is not dict:
        return None
    return value


def process_group_has_live_members(pgid: int) -> bool:
    """Return false for a group containing only zombies awaiting exact reap."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                try:
                    fields = (Path(entry.path) / "stat").read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
                    if (int(fields[2]) == pgid and int(fields[3]) == pgid
                            and fields[0] not in ("Z", "X", "x")):
                        return True
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except (OSError, ValueError, IndexError):
                    return True
    except OSError:
        return True
    return False


class ActionController:
    def __init__(self, home: Path, install: Path):
        self.home = Path(home)
        self.install = Path(install)
        state_root = self.home / ".local/state/openhtpc"
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(state_root, 0o700)
        self.target = request_path(self.home)
        self.target.unlink(missing_ok=True)
        os.mkfifo(self.target, 0o600)
        os.chmod(self.target, 0o600)
        self.fd = os.open(self.target, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        self.pending = b""
        self.child: subprocess.Popen | None = None
        self.child_pgid: int | None = None
        self.lock_fd: int | None = None
        self.operation_id: str | None = None
        self.started_at: str | None = None
        self.log_fd: int | None = None
        self.log_read_fd: int | None = None
        self.log_bytes = 0
        self.redaction_token = b""
        self.redaction_pending = b""

    def _acquire_lifetime_lock(self) -> bool:
        target = lock_path(self.home)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self.lock_fd = fd
        return True

    def _release_lifetime_lock(self) -> None:
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def _write_log(self, data: bytes) -> None:
        if self.log_fd is None or not data or self.log_bytes >= MAX_LOG_BYTES:
            return
        view = memoryview(data[:MAX_LOG_BYTES - self.log_bytes])
        while view:
            written = os.write(self.log_fd, view)
            self.log_bytes += written
            view = view[written:]

    def _redact_and_write(self, data: bytes, *, final: bool = False) -> None:
        token = self.redaction_token
        if not token:
            self._write_log(data)
            return
        buffer = self.redaction_pending + data
        while True:
            index = buffer.find(token)
            if index >= 0:
                self._write_log(buffer[:index])
                self._write_log(b"<action-token>")
                buffer = buffer[index + len(token):]
                continue
            if final:
                self._write_log(buffer)
                self.redaction_pending = b""
                return
            safe = len(buffer) - len(token) + 1
            if safe > 0:
                self._write_log(buffer[:safe])
                buffer = buffer[safe:]
            self.redaction_pending = buffer
            return

    def _drain_log(self, *, final: bool = False) -> None:
        if self.log_read_fd is None:
            return
        reads = 0
        while final or reads < 16:
            try:
                chunk = os.read(self.log_read_fd, 65536)
            except BlockingIOError:
                break
            if not chunk:
                final = True
                break
            self._redact_and_write(chunk)
            reads += 1
        if final:
            self._redact_and_write(b"", final=True)
            os.close(self.log_read_fd)
            self.log_read_fd = None
            if self.log_fd is not None:
                os.fsync(self.log_fd)
                os.close(self.log_fd)
                self.log_fd = None

    def _base_status(self, pid: int | None) -> dict:
        return {
            "schema": 1,
            "state": "RUNNING",
            "started_at": self.started_at,
            "finished_at": None,
            "pid": pid,
            "exit_code": None,
            "origin": "UI",
            "operation_id": self.operation_id,
            "log_path": str(log_path(self.home)),
        }

    def _finish_status(self, returncode: int, reason: str | None = None,
                       group_stop_signal: int | None = None) -> None:
        current = _read_status(self.home)
        if (type(current) is not dict or current.get("state") != "RUNNING"
                or current.get("operation_id") != self.operation_id
                or type(current.get("pid")) is not int
                or self.child is None or current.get("pid") != self.child.pid):
            return
        current.update(
            state="SUCCESS" if returncode == 0 and reason is None else "FAILED",
            finished_at=_utc_now(),
            exit_code=returncode,
        )
        if reason is not None:
            current["reason"] = reason
        if returncode < 0:
            current["terminated_signal"] = -returncode
        if group_stop_signal is not None:
            current["group_stop_signal"] = group_stop_signal
        _atomic_status(self.home, current)

    def _launch(self, token: str) -> None:
        if self.child is not None or not valid_action_token(token) or not self._acquire_lifetime_lock():
            return
        self.started_at = _utc_now()
        self.redaction_token = token.encode("ascii")
        self.redaction_pending = b""
        target_log = log_path(self.home)
        read_fd = None
        write_fd = None
        try:
            target_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(target_log.parent, 0o700)
            self.log_fd = os.open(
                target_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC, 0o600
            )
            os.fchmod(self.log_fd, 0o600)
            self.log_bytes = 0
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            os.set_blocking(read_fd, False)
            self.log_read_fd = read_fd
        except OSError:
            for pipe_fd in (read_fd, write_fd):
                if pipe_fd is not None:
                    os.close(pipe_fd)
            if self.log_fd is not None:
                os.close(self.log_fd)
                self.log_fd = None
            self.operation_id = f"media-action-setup-{os.getpid()}-{time.monotonic_ns()}"
            failed = self._base_status(None)
            failed.update(state="FAILED", finished_at=_utc_now(), exit_code=127, reason="SETUP_FAILED")
            try:
                _atomic_status(self.home, failed)
            except OSError:
                pass
            self._release_lifetime_lock()
            return
        argv = [
            str(self.install / "openhtpc-media-enrich.py"),
            "--token", token,
            "--home", str(self.home),
            "--install", str(self.install),
        ]
        try:
            self.child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=write_fd,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                pass_fds=(self.lock_fd,),
            )
            self.child_pgid = self.child.pid
            self.operation_id = f"media-action-{self.child.pid}-{time.monotonic_ns()}"
        except OSError:
            self.operation_id = f"media-action-launch-{os.getpid()}-{time.monotonic_ns()}"
            self._write_log(b"ACTION_LAUNCH_FAILED\n")
            failed = self._base_status(None)
            failed.update(state="FAILED", finished_at=_utc_now(), exit_code=127, reason="LAUNCH_FAILED")
            _atomic_status(self.home, failed)
            self.child = None
            self.child_pgid = None
            self._release_lifetime_lock()
        finally:
            os.close(write_fd)
        if self.child is None:
            self._drain_log(final=True)
            return
        try:
            _atomic_status(self.home, self._base_status(self.child.pid))
        except OSError:
            try:
                os.killpg(self.child_pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.child.wait()
            self._drain_log(final=True)
            self.child = None
            self.child_pgid = None
            self._release_lifetime_lock()

    def _complete_child(self) -> None:
        if self.child is None or self.child.poll() is None:
            return
        self.child.wait()
        self._drain_log(final=True)
        self._finish_status(self.child.returncode)
        self.child = None
        self.child_pgid = None
        self._release_lifetime_lock()
        self.operation_id = None
        self.started_at = None
        self.redaction_token = b""

    def poll(self) -> None:
        if self.fd is None:
            return
        self._drain_log()
        ignore_requests = self.child is not None
        while True:
            try:
                message = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            if ignore_requests or self.child is not None:
                self.pending = b""
                continue
            self.pending += message
            if len(self.pending) > MAX_TOKEN_CHARS + 1 and b"\n" not in self.pending:
                self.pending = b""
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                try:
                    token = line.decode("ascii")
                except UnicodeDecodeError:
                    continue
                self._launch(token)
                if self.child is not None:
                    self.pending = b""
                    break
        self._drain_log()
        self._complete_child()

    def close(self) -> None:
        if self.fd is None:
            return
        try:
            if self.child is not None:
                child = self.child
                pgid = self.child_pgid
                if child.poll() is not None and not process_group_has_live_members(pgid):
                    child.wait()
                    self._drain_log(final=True)
                    self._finish_status(child.returncode)
                    self.child = None
                    self.child_pgid = None
                    self._release_lifetime_lock()
                    return
                reason = "SESSION_STOPPED"
                group_stop_signal = None
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 3
                while process_group_has_live_members(pgid) and time.monotonic() < deadline:
                    self._drain_log()
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                if process_group_has_live_members(pgid):
                    reason = "FORCED_STOP"
                    group_stop_signal = signal.SIGKILL
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    deadline = time.monotonic() + 1
                    while process_group_has_live_members(pgid) and time.monotonic() < deadline:
                        self._drain_log()
                        time.sleep(0.01)
                child.wait()
                self._drain_log(final=True)
                self._finish_status(child.returncode, reason, group_stop_signal)
                self.child = None
                self.child_pgid = None
                self._release_lifetime_lock()
        finally:
            if self.log_read_fd is not None or self.log_fd is not None:
                self._drain_log(final=True)
            self._release_lifetime_lock()
            os.close(self.fd)
            self.fd = None
            try:
                self.target.unlink()
            except FileNotFoundError:
                pass
