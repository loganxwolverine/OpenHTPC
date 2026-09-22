#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
"""HOME-owned asynchronous manual TMDb search lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


MAX_REQUEST_BYTES = 4095
MAX_TITLE_CHARS = 255
MAX_LOG_BYTES = 256 * 1024


def request_path(home: Path) -> Path:
    return Path(home) / ".local/state/openhtpc/media-search.fifo"


def lock_path(home: Path) -> Path:
    return Path(home) / ".local/state/openhtpc/media/media-search.lock"


def status_path(home: Path) -> Path:
    return Path(home) / ".local/state/openhtpc/media/media-search-status.json"


def log_path(home: Path) -> Path:
    return Path(home) / ".local/state/openhtpc/media/media-search.log"


def normalize_request(media_version_id: object, title: object, year: object) -> dict | None:
    if type(media_version_id) is not int or media_version_id <= 0:
        return None
    if type(title) is not str:
        return None
    title = title.strip()
    if not title or len(title) > MAX_TITLE_CHARS:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in title):
        return None
    if year is not None and (type(year) is not int or year < 1870 or year > 2100):
        return None
    return {"media_version_id": media_version_id, "title": title, "year": year}


def valid_request(value: object) -> bool:
    return type(value) is dict and normalize_request(
        value.get("media_version_id"), value.get("title"), value.get("year")
    ) == value


def search_running(home: Path) -> bool:
    path = lock_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
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


def request_search(home: Path, media_version_id: int, title: str, year: int | None) -> bool:
    request = normalize_request(media_version_id, title, year)
    if request is None or search_running(home):
        return False
    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        return False
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


def _atomic_status(home: Path, value: dict) -> None:
    target = status_path(home)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_status(home: Path) -> dict | None:
    try:
        value = json.loads(status_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if type(value) is dict else None


def process_group_has_live_members(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                fields = (Path(entry.path) / "stat").read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
                if int(fields[2]) == pgid and int(fields[3]) == pgid and fields[0] not in ("Z", "X", "x"):
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, ValueError, IndexError):
                return True
    except OSError:
        return True
    return False


class SearchController:
    def __init__(self, home: Path, install: Path):
        self.home = Path(home)
        self.install = Path(install)
        root = self.home / ".local/state/openhtpc"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
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

    def _acquire_lock(self) -> bool:
        path = lock_path(self.home)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self.lock_fd = fd
        return True

    def _release_lock(self) -> None:
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def _drain_log(self, final: bool = False) -> None:
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
            if self.log_fd is not None and self.log_bytes < MAX_LOG_BYTES:
                data = chunk[:MAX_LOG_BYTES - self.log_bytes]
                if data:
                    os.write(self.log_fd, data)
                    self.log_bytes += len(data)
            reads += 1
        if final:
            os.close(self.log_read_fd)
            self.log_read_fd = None
            if self.log_fd is not None:
                os.fsync(self.log_fd)
                os.close(self.log_fd)
                self.log_fd = None

    def _base_status(self, pid: int | None) -> dict:
        return {
            "schema": 1, "state": "RUNNING", "started_at": self.started_at,
            "finished_at": None, "pid": pid, "exit_code": None, "origin": "UI",
            "operation_id": self.operation_id, "log_path": str(log_path(self.home)),
        }

    def _finish_status(self, returncode: int, reason: str | None = None,
                       group_stop_signal: int | None = None) -> None:
        current = _read_status(self.home)
        if (type(current) is not dict or current.get("state") != "RUNNING"
                or current.get("operation_id") != self.operation_id
                or self.child is None or current.get("pid") != self.child.pid):
            return
        current.update(
            state="SUCCESS" if returncode == 0 and reason is None else "FAILED",
            finished_at=_utc_now(), exit_code=returncode,
        )
        if reason is not None:
            current["reason"] = reason
        if returncode < 0:
            current["terminated_signal"] = -returncode
        if group_stop_signal is not None:
            current["group_stop_signal"] = group_stop_signal
        _atomic_status(self.home, current)

    def _launch(self, request: dict) -> None:
        normalized = normalize_request(
            request.get("media_version_id"), request.get("title"), request.get("year")
        )
        if self.child is not None or normalized is None or not self._acquire_lock():
            return
        self.started_at = _utc_now()
        target_log = log_path(self.home)
        target_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target_log.parent, 0o700)
        read_fd = write_fd = None
        try:
            self.log_fd = os.open(
                target_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC, 0o600
            )
            os.fchmod(self.log_fd, 0o600)
            self.log_bytes = 0
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            os.set_blocking(read_fd, False)
            self.log_read_fd = read_fd
            argv = [
                str(self.install / "openhtpc-media-manual-search-ui"),
                "--worker-search", "--media-version-id", str(normalized["media_version_id"]),
                "--title", normalized["title"],
            ]
            if normalized["year"] is not None:
                argv.extend(["--year", str(normalized["year"])])
            argv.extend(["--home", str(self.home), "--install-dir", str(self.install)])
            self.child = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=write_fd, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(self.lock_fd,),
            )
            self.child_pgid = self.child.pid
            self.operation_id = f"media-search-{self.child.pid}-{time.monotonic_ns()}"
            _atomic_status(self.home, self._base_status(self.child.pid))
        except (OSError, ValueError):
            self.operation_id = f"media-search-launch-{os.getpid()}-{time.monotonic_ns()}"
            failed = self._base_status(None)
            failed.update(state="FAILED", finished_at=_utc_now(), exit_code=127, reason="LAUNCH_FAILED")
            try:
                _atomic_status(self.home, failed)
            except OSError:
                pass
            if self.child is not None:
                try:
                    os.killpg(self.child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.child.wait()
            self.child = None
            self.child_pgid = None
            self._release_lock()
        finally:
            if write_fd is not None:
                os.close(write_fd)
            if self.child is None:
                if read_fd is not None and self.log_read_fd is None:
                    os.close(read_fd)
                self._drain_log(final=True)

    def _complete_child(self) -> None:
        if self.child is None or self.child.poll() is None:
            return
        self.child.wait()
        self._drain_log(final=True)
        self._finish_status(self.child.returncode)
        self.child = None
        self.child_pgid = None
        self._release_lock()
        self.operation_id = None
        self.started_at = None

    def poll(self) -> None:
        if self.fd is None:
            return
        self._drain_log()
        ignore = self.child is not None
        while True:
            try:
                chunk = os.read(self.fd, MAX_REQUEST_BYTES + 1)
            except BlockingIOError:
                break
            if ignore or self.child is not None:
                self.pending = b""
                continue
            self.pending += chunk
            if len(self.pending) > MAX_REQUEST_BYTES and b"\n" not in self.pending:
                self.pending = b""
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if len(line) > MAX_REQUEST_BYTES:
                    continue
                try:
                    request = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if type(request) is not dict:
                    continue
                self._launch(request)
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
                child, pgid = self.child, self.child_pgid
                if child.poll() is not None and not process_group_has_live_members(pgid):
                    child.wait(); self._drain_log(final=True); self._finish_status(child.returncode)
                    self.child = None; self.child_pgid = None; self._release_lock()
                else:
                    reason, group_signal = "SESSION_STOPPED", None
                    try:
                        os.killpg(pgid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    deadline = time.monotonic() + 3
                    while process_group_has_live_members(pgid) and time.monotonic() < deadline:
                        self._drain_log(); time.sleep(0.05)
                    if process_group_has_live_members(pgid):
                        reason, group_signal = "FORCED_STOP", signal.SIGKILL
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    child.wait()
                    self._drain_log(final=True)
                    self._finish_status(child.returncode, reason, group_signal)
                    self.child = None; self.child_pgid = None; self._release_lock()
        finally:
            if self.log_read_fd is not None or self.log_fd is not None:
                self._drain_log(final=True)
            self._release_lock()
            os.close(self.fd)
            self.fd = None
            try:
                self.target.unlink()
            except FileNotFoundError:
                pass
