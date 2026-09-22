#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""One local MEDIA update request and HOME-owned child lifecycle."""

import os
import fcntl
import json
import signal
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import subprocess


def request_path(home: Path) -> Path:
    return home / ".local/state/openhtpc/media-update.fifo"


def request_update(home: Path) -> bool:
    """Write one atomic request without waiting for HOME or the updater."""
    try:
        fd = os.open(request_path(home), os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            os.write(fd, b"UPDATE\n")
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def update_running(home: Path) -> bool:
    """Advisory fast path; the updater remains the lock authority."""
    path = home / ".local/state/openhtpc/media/library-update.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def process_group_has_live_members(pgid: int) -> bool:
    """Ignore zombies, including the owned leader held for an exact reap."""
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
                    stat = (Path(entry.path) / "stat").read_text(encoding="utf-8")
                    fields = stat.rsplit(") ", 1)[1].split()
                    if (int(fields[2]) == pgid and int(fields[3]) == pgid
                            and fields[0] not in ("Z", "X", "x")):
                        return True
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except (OSError, ValueError, IndexError):
                    return True
    except OSError:
        return True  # A procfs failure must not declare the group gone.
    return False


def repair_stopped_status(home: Path, pid: int, returncode: int, reason: str) -> None:
    """Finalize only the reaped UI child, without delaying a newer updater."""
    state_dir = home / ".local/state/openhtpc/media"
    with (state_dir / "library-update.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        status_path = state_dir / "library-update-status.json"
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if (type(status) is not dict or type(status.get("state")) is not str
                or status["state"] != "RUNNING" or type(status.get("pid")) is not int
                or status["pid"] != pid):
            return
        status.update(state="FAILED", finished_at=datetime.now(timezone.utc).isoformat(),
                      exit_code=returncode if returncode != 0 else 1, reason=reason)
        if returncode < 0:
            status["terminated_signal"] = -returncode
        if reason == "FORCED_STOP":
            status["group_stop_signal"] = signal.SIGKILL
        fd, temporary = tempfile.mkstemp(prefix=status_path.name + ".", dir=state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(status, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, status_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class UpdateController:
    def __init__(self, home: Path, install: Path):
        self.home = home
        self.install = install
        self.child = None
        self.child_pgid = None
        target = request_path(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(target.parent, 0o700)
        target.unlink(missing_ok=True)
        os.mkfifo(target, 0o600)
        self.fd = os.open(target, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        self.pending = b""
        self.target = target

    def poll(self):
        while True:
            try:
                message = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            self.pending += message
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if line != b"UPDATE" or self.child is not None or update_running(self.home):
                    continue
                log_path = self.target.parent / "media/library-update.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("ab") as log:
                    os.chmod(log_path, 0o600)
                    try:
                        self.child = subprocess.Popen(
                            [str(self.install / "openhtpc-media-library-update"),
                             "--home", str(self.home), "--install", str(self.install),
                             "--origin", "UI"],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        self.child_pgid = self.child.pid
                    except OSError as exc:
                        log.write(f"UPDATER_LAUNCH_FAILED: {exc}\n".encode())
        if self.child is not None and self.child.poll() is not None:
            self.child.wait()  # exact owned child, already complete
            self.child = None
            self.child_pgid = None

    def close(self):
        if self.fd is None:
            return
        try:
            if self.child is not None:
                child = self.child
                pgid = self.child_pgid
                reason = "SESSION_STOPPED"
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 3
                while process_group_has_live_members(pgid) and time.monotonic() < deadline:
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                if process_group_has_live_members(pgid):
                    reason = "FORCED_STOP"
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    killed_deadline = time.monotonic() + 1
                    while process_group_has_live_members(pgid) and time.monotonic() < killed_deadline:
                        time.sleep(0.01)
                child.wait()  # retain the unreaped leader PID until group cleanup
                try:
                    repair_stopped_status(self.home, child.pid, child.returncode, reason)
                except OSError:
                    pass
                self.child = None
                self.child_pgid = None
        finally:
            os.close(self.fd)
            self.fd = None
            try:
                self.target.unlink()
            except FileNotFoundError:
                pass
