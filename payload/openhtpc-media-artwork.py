# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Explicit, reproducible movie-poster cache from persisted presentation provenance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
import urllib.error
import urllib.request
from typing import Any

PROVIDER = "tmdb_movie"
KIND = "poster"
SIZE = "w500"
TIMEOUT_SECONDS = 8
MAX_IMAGE_BYTES = 5_000_000
IMAGE_ROOT = "https://image.tmdb.org/t/p/w500"
POSTER_TOKEN = re.compile(r"^/[A-Za-z0-9_-]+\.jpg$")
MAX_POSTER_TOKEN_CHARS = 128


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _result(status: str, **fields: Any) -> dict[str, Any]:
    return {"status": status, **fields}


def cache_path(poster_path: str, *, home: Path | None = None) -> Path:
    """Return the canonical path for a validated provider poster token."""
    if not isinstance(poster_path, str) or len(poster_path) > MAX_POSTER_TOKEN_CHARS or not POSTER_TOKEN.fullmatch(poster_path):
        raise ValueError("INVALID_POSTER_PATH")
    material = f"{PROVIDER}|{KIND}|{SIZE}|{poster_path}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    base = Path(home) if home is not None else Path.home()
    return base / ".cache/openhtpc/media/artwork" / PROVIDER / KIND / SIZE / f"{digest}.jpg"


def resolve_work_poster(db: sqlite3.Connection, work_id: int, *, locale: str = "fr-FR", home: Path | None = None) -> dict[str, Any]:
    """Resolve existing snapshot metadata without filesystem writes or network."""
    if type(work_id) is not int or work_id <= 0 or not isinstance(locale, str) or not locale.strip():
        return _result("INVALID_INPUT")
    rows = db.execute(
        "SELECT source_snapshot_id FROM work_presentations WHERE work_id = ? AND locale = ?",
        (work_id, locale),
    ).fetchall()
    if len(rows) != 1:
        return _result("NO_PRESENTATION" if not rows else "AMBIGUOUS_PRESENTATION")
    snapshot_id = rows[0][0]
    if type(snapshot_id) is not int or snapshot_id <= 0:
        return _result("NO_SOURCE_SNAPSHOT")
    rows = db.execute(
        """SELECT ps.snapshot_kind, ps.locale, ps.payload_json,
                  e.provider, e.external_id, e.work_id
           FROM provider_snapshots ps
           JOIN external_ids e ON e.id = ps.external_id_id
           WHERE ps.id = ?""",
        (snapshot_id,),
    ).fetchall()
    if len(rows) != 1:
        return _result("NO_SOURCE_SNAPSHOT")
    kind, snap_locale, raw_payload, provider, external_id, source_work_id = rows[0]
    if kind != "MOVIE_DETAILS" or snap_locale != locale or provider != PROVIDER or source_work_id != work_id:
        return _result("WRONG_PROVIDER_PROVENANCE")
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        return _result("INVALID_SNAPSHOT_JSON")
    if not isinstance(payload, dict) or type(payload.get("id")) is not int or str(payload["id"]) != external_id:
        return _result("WRONG_PROVIDER_PROVENANCE")
    token = payload.get("poster_path")
    if token is None or token == "":
        return _result("NO_POSTER")
    try:
        target = cache_path(token, home=home)
    except ValueError:
        return _result("INVALID_POSTER_PATH")
    return _result("POSTER_RESOLVED", poster_path=token, cache_path=target)


def _valid_jpeg(data: bytes) -> bool:
    return len(data) >= 4 and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")


def _safe_parent(target: Path) -> None:
    # A cache directory may be deleted and recreated, but symlinked components
    # must never redirect the atomic replacement outside the user's cache.
    # target: ~/.cache/openhtpc/media/artwork/tmdb_movie/poster/w500/key.jpg
    for part in reversed(target.parents[:7]):
        if part.is_symlink():
            raise OSError("SYMLINKED_CACHE_DIRECTORY")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink():
        raise OSError("SYMLINKED_CACHE_DIRECTORY")


def ensure_work_poster(
    db: sqlite3.Connection,
    work_id: int,
    locale: str = "fr-FR",
    home: Path | None = None,
    opener: Any = None,
) -> dict[str, Any]:
    """Explicitly ensure one w500 JPEG poster; never mutate the database."""
    resolved = resolve_work_poster(db, work_id, locale=locale, home=home)
    if resolved["status"] != "POSTER_RESOLVED":
        return resolved
    target: Path = resolved["cache_path"]
    token: str = resolved["poster_path"]
    try:
        for part in reversed(target.parents[:7]):
            if part.is_symlink():
                return _result("CACHE_WRITE_FAILED")
        if target.is_symlink():
            return _result("CACHE_WRITE_FAILED")
        if target.is_file():
            with target.open("rb") as cached:
                data = cached.read(MAX_IMAGE_BYTES + 1)
            if len(data) <= MAX_IMAGE_BYTES and _valid_jpeg(data):
                return _result("OK_CACHE_HIT", cache_path=target)
            return _result("INVALID_IMAGE")
        _safe_parent(target)
    except OSError:
        return _result("CACHE_WRITE_FAILED")

    request = urllib.request.Request(IMAGE_ROOT + token, headers={"Accept": "image/jpeg"})
    fetch = opener if opener is not None else urllib.request.build_opener(_NoRedirect()).open
    try:
        with fetch(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return _result("HTTP_ERROR", http_status=exc.code)
    except (TimeoutError, socket.timeout):
        return _result("TIMEOUT")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return _result("TIMEOUT")
        return _result("OFFLINE")
    except OSError:
        return _result("OFFLINE")
    except Exception:
        return _result("OFFLINE")
    if len(data) > MAX_IMAGE_BYTES or not _valid_jpeg(data):
        return _result("INVALID_IMAGE")

    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".poster-", delete=False) as tmp:
            temporary = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(temporary, 0o600)
        if target.is_symlink():
            raise OSError("SYMLINKED_CACHE_FILE")
        os.replace(temporary, target)
        temporary = None
        return _result("OK_DOWNLOADED", cache_path=target)
    except OSError:
        return _result("CACHE_WRITE_FAILED")
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
