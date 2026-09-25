#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Publish one small live MEDIA activity state for the running Flex UI."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Callable


MAX_STATUS_BYTES = 64 * 1024
MAX_MESSAGE_BYTES = 160
VALID_STATES = {"IDLE", "RUNNING", "SUCCESS", "FAILED"}

_LIBRARY = "library"
_ACTION = "action"
_SEARCH = "search"

_MESSAGES = {
    (_LIBRARY, "RUNNING"): "Médiathèque · mise à jour en cours…",
    (_LIBRARY, "SUCCESS"): "Médiathèque · mise à jour terminée",
    (_LIBRARY, "FAILED"): "Médiathèque · échec de la mise à jour",
    (_ACTION, "RUNNING"): "Fiche du film · mise à jour en cours…",
    (_ACTION, "SUCCESS"): "Fiche du film · mise à jour terminée",
    (_ACTION, "FAILED"): "Fiche du film · échec de la mise à jour",
    (_SEARCH, "RUNNING"): "Recherche TMDb · en cours…",
    (_SEARCH, "SUCCESS"): "Recherche TMDb · terminée",
    (_SEARCH, "FAILED"): "Recherche TMDb · échec de la recherche",
}


def _final_message(kind: str, state: str, status: dict | None = None) -> str:
    """Return a couch-friendly final message without exposing paths or provider details."""
    if kind == _LIBRARY and state == "SUCCESS" and type(status) is dict:
        summary = status.get("summary")
        if type(summary) is dict:
            found = summary.get("files_discovered")
            review = summary.get("still_unmatched")
            if (
                type(found) is int and type(review) is int
                and found >= 0 and 0 <= review <= found
            ):
                identified = found - review
                return (
                    f"Médiathèque · {found} médias trouvés · "
                    f"{identified} identifiés · {review} à vérifier"
                )
    return _MESSAGES[(kind, state)]


def state_path(home: Path) -> Path:
    return Path(home) / ".local/state/openhtpc/media/activity-state"


def _status_path(home: Path, kind: str) -> Path:
    names = {
        _LIBRARY: "library-update-status.json",
        _ACTION: "media-action-status.json",
        _SEARCH: "media-search-status.json",
    }
    return Path(home) / ".local/state/openhtpc/media" / names[kind]


def _lock_path(home: Path, kind: str) -> Path:
    names = {
        _LIBRARY: "library-update.lock",
        _ACTION: "media-action.lock",
        _SEARCH: "media-search.lock",
    }
    return Path(home) / ".local/state/openhtpc/media" / names[kind]


def _read_status(path: Path) -> dict | None:
    try:
        st = path.stat()
        if st.st_size < 2 or st.st_size > MAX_STATUS_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > MAX_STATUS_BYTES:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if type(value) is not dict:
        return None
    state = value.get("state")
    if state not in {"RUNNING", "SUCCESS", "FAILED"}:
        return None
    started_at = value.get("started_at")
    if started_at is not None and (type(started_at) is not str or len(started_at) > 128):
        return None
    finished_at = value.get("finished_at")
    if finished_at is not None and (type(finished_at) is not str or len(finished_at) > 128):
        return None
    pid = value.get("pid")
    if pid is not None and (type(pid) is not int or pid <= 0):
        return None
    operation_id = value.get("operation_id")
    if operation_id is not None and (type(operation_id) is not str or len(operation_id) > 128):
        return None
    return value


def _fingerprint(kind: str, status: dict | None) -> tuple | None:
    if status is None:
        return None
    operation = status.get("operation_id") if kind in {_ACTION, _SEARCH} else None
    if not operation:
        operation = f"{status.get('pid') or ''}:{status.get('started_at') or ''}"
    return (
        kind,
        operation,
        status.get("state"),
        status.get("started_at"),
        status.get("finished_at"),
        status.get("exit_code"),
    )


def _lock_held(path: Path) -> bool:
    try:
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _sanitize_message(message: str) -> str:
    clean = " ".join(str(message).replace("\r", " ").replace("\n", " ").split())
    encoded = clean.encode("utf-8")
    if len(encoded) <= MAX_MESSAGE_BYTES:
        return clean
    encoded = encoded[:MAX_MESSAGE_BYTES]
    while encoded:
        try:
            return encoded.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return ""


def _atomic_state(path: Path, state: str, message: str, serial: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    body = f"{state}\n{message}\n{serial}\n"
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ActivityPublisher:
    """Merge P1B/P3A status into one tiny, non-sensitive live UI state."""

    def __init__(
        self,
        home: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        success_ttl: float = 3.0,
        failure_ttl: float = 6.0,
    ):
        self.home = Path(home)
        self.clock = clock
        self.success_ttl = float(success_ttl)
        self.failure_ttl = float(failure_ttl)
        self.serial = 0
        self.visible: tuple[str, str] | None = None
        self.toast: tuple[str, str, float] | None = None
        self.seen: dict[str, tuple | None] = {}
        for kind in (_LIBRARY, _ACTION, _SEARCH):
            self.seen[kind] = _fingerprint(kind, _read_status(_status_path(self.home, kind)))
        self._publish("IDLE", "")

    def _publish(self, state: str, message: str) -> bool:
        if state not in VALID_STATES:
            state, message = "IDLE", ""
        message = "" if state == "IDLE" else _sanitize_message(message)
        if state != "IDLE" and not message:
            state, message = "IDLE", ""
        visible = (state, message)
        if visible == self.visible:
            return False
        self.serial += 1
        _atomic_state(state_path(self.home), state, message, self.serial)
        self.visible = visible
        return True

    def _statuses(self) -> dict[str, dict | None]:
        return {kind: _read_status(_status_path(self.home, kind)) for kind in (_LIBRARY, _ACTION, _SEARCH)}

    def poll(self) -> None:
        now = float(self.clock())
        statuses = self._statuses()

        finals: list[tuple[str, str, str, dict]] = []
        for kind, status in statuses.items():
            fingerprint = _fingerprint(kind, status)
            if fingerprint != self.seen.get(kind):
                if status is not None and status.get("state") in {"SUCCESS", "FAILED"}:
                    finals.append((
                        str(status.get("finished_at") or status.get("started_at") or ""),
                        kind,
                        str(status["state"]),
                        status,
                    ))
                self.seen[kind] = fingerprint

        if finals:
            _stamp, kind, final_state, final_status = max(finals, key=lambda item: item[0])
            ttl = self.success_ttl if final_state == "SUCCESS" else self.failure_ttl
            self.toast = (final_state, _final_message(kind, final_state, final_status), now + ttl)

        running: list[tuple[str, str]] = []
        for kind, status in statuses.items():
            if (
                status is not None
                and status.get("state") == "RUNNING"
                and _lock_held(_lock_path(self.home, kind))
            ):
                running.append((str(status.get("started_at") or ""), kind))

        if running:
            _stamp, kind = max(running, key=lambda item: item[0])
            self._publish("RUNNING", _MESSAGES[(kind, "RUNNING")])
            return

        if self.toast is not None:
            state, message, deadline = self.toast
            if now < deadline:
                self._publish(state, message)
                return
            self.toast = None

        self._publish("IDLE", "")

    def close(self) -> None:
        self.toast = None
        self._publish("IDLE", "")


__all__ = ["ActivityPublisher", "state_path"]
