#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Explicit-resource Media Descriptor Ingestion.

Connects DEV2 Media Probe technical descriptors to DEV1 persistent SQLite storage.
Ingests ONE explicitly supplied file within an explicit source root.
Does NOT scan directories, discover sources from configuration, infer works/titles,
or integrate with runtime/playback.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any


def compute_source_id(source_root: Path | str) -> str:
    """Compute canonical OPENHTPC source_id from source root directory."""
    path = Path(source_root).resolve()
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


def resolve_source_relative(media_file: Path | str, source_root: Path | str) -> tuple[Path, Path, str, str]:
    """Validate media file is within source root and derive logical identity.

    Returns (file_resolved, root_resolved, source_id, relative_path_posix).
    Raises ValueError or FileNotFoundError if invalid.
    """
    root_path = Path(source_root)
    file_path = Path(media_file)

    if not root_path.exists():
        raise ValueError(f"Source root does not exist: {root_path}")
    if not root_path.is_dir():
        raise ValueError(f"Source root is not a directory: {root_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"Media file does not exist: {file_path}")

    root_resolved = root_path.resolve()
    file_resolved = file_path.resolve()

    if not file_resolved.is_file():
        raise ValueError(f"Media path is not a regular file: {file_path}")

    try:
        relative = file_resolved.relative_to(root_resolved)
    except ValueError:
        raise ValueError(f"Media file '{file_path}' is outside source root '{root_path}'")

    rel_posix = relative.as_posix()
    if rel_posix in ("", "."):
        raise ValueError("Media file cannot be the source root itself")
    if rel_posix.startswith("../") or "/../" in rel_posix:
        raise ValueError(f"Path escape detected in relative path: {rel_posix}")

    sid = compute_source_id(root_resolved)
    return file_resolved, root_resolved, sid, rel_posix


_MEDIA_PROBE = None
_MEDIA_DB = None


def set_media_probe_module(mod: Any) -> None:
    global _MEDIA_PROBE
    _MEDIA_PROBE = mod


def set_media_db_module(mod: Any) -> None:
    global _MEDIA_DB
    _MEDIA_DB = mod


def _load_media_probe():
    global _MEDIA_PROBE
    if _MEDIA_PROBE is not None:
        return _MEDIA_PROBE
    for name in ("media_probe", "openhtpc_media_probe"):
        if name in sys.modules:
            _MEDIA_PROBE = sys.modules[name]
            return _MEDIA_PROBE
    try:
        import openhtpc_media_probe as media_probe  # type: ignore
        _MEDIA_PROBE = media_probe
        return media_probe
    except ImportError:
        pass
    import importlib.util
    probe_path = Path(__file__).resolve().parent / "openhtpc-media-probe.py"
    if not probe_path.is_file():
        raise RuntimeError(f"Media probe component not found at {probe_path}")
    spec = importlib.util.spec_from_file_location("openhtpc_media_probe", probe_path)
    if not spec or not spec.loader:
        raise RuntimeError("Failed to load openhtpc-media-probe spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MEDIA_PROBE = mod
    return mod


def _load_media_db():
    global _MEDIA_DB
    if _MEDIA_DB is not None:
        return _MEDIA_DB
    for name in ("media_db", "openhtpc_media_db"):
        if name in sys.modules:
            _MEDIA_DB = sys.modules[name]
            return _MEDIA_DB
    try:
        import openhtpc_media_db as media_db  # type: ignore
        _MEDIA_DB = media_db
        return media_db
    except ImportError:
        pass
    import importlib.util
    db_path = Path(__file__).resolve().parent / "openhtpc-media-db.py"
    if not db_path.is_file():
        raise RuntimeError(f"Media DB component not found at {db_path}")
    spec = importlib.util.spec_from_file_location("openhtpc_media_db", db_path)
    if not spec or not spec.loader:
        raise RuntimeError("Failed to load openhtpc-media-db spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MEDIA_DB = mod
    return mod


def validate_descriptor(descriptor: dict[str, Any]) -> None:
    """Ensure descriptor conforms to DEV2 contract before attempting DB operations."""
    if not isinstance(descriptor, dict):
        raise ValueError("Descriptor must be a dictionary")
    if not descriptor.get("ok"):
        raise ValueError(f"Descriptor indicates failure: {descriptor.get('error')}")
    resource_info = descriptor.get("resource")
    if not isinstance(resource_info, dict):
        raise ValueError("Descriptor missing valid 'resource' object")
    if not isinstance(descriptor.get("video_streams"), list):
        raise ValueError("Descriptor missing 'video_streams' list")
    if not isinstance(descriptor.get("audio_streams"), list):
        raise ValueError("Descriptor missing 'audio_streams' list")
    if not isinstance(descriptor.get("subtitle_streams"), list):
        raise ValueError("Descriptor missing 'subtitle_streams' list")


def ingest_descriptor(
    db: sqlite3.Connection,
    descriptor: dict[str, Any],
    source_id: str,
    relative_path: str,
) -> dict[str, Any]:
    """Persist normalized descriptor into media.db using caller's transaction.

    Maintains single logical resource idempotence:
    - Re-ingestion updates existing resource and streams
    - work_id remains NULL (no identity inference)
    - Stale stream rows are cleanly replaced
    """
    validate_descriptor(descriptor)

    resource_info = descriptor["resource"]
    video_streams = descriptor["video_streams"]
    audio_streams = descriptor["audio_streams"]
    subtitle_streams = descriptor["subtitle_streams"]

    now_iso = datetime.now(timezone.utc).isoformat()
    canonical_path = resource_info.get("canonical_path")
    file_size = resource_info.get("file_size")
    mtime_ns = resource_info.get("mtime_ns")
    container_format = resource_info.get("container_format")
    duration_seconds = resource_info.get("duration_seconds")

    # Check for existing resource by logical FILE identity (source_id, relative_path)
    cur = db.execute(
        "SELECT id, media_version_id FROM resources WHERE resource_kind = 'FILE' AND source_id = ? AND relative_path = ?",
        (source_id, relative_path),
    )
    row = cur.fetchone()

    if row is None:
        # First ingest: create new media_version without work_id
        cur = db.execute(
            """
            INSERT INTO media_versions (
                work_id, provisional_title, provisional_year, edition_title,
                identification_state, match_confidence, match_method, match_locked,
                duration_seconds, created_at, updated_at
            ) VALUES (
                NULL, NULL, NULL, NULL,
                'UNMATCHED', NULL, NULL, 0,
                ?, ?, ?
            )
            """,
            (duration_seconds, now_iso, now_iso),
        )
        media_version_id = cur.lastrowid

        cur = db.execute(
            """
            INSERT INTO resources (
                media_version_id, resource_kind, source_id, relative_path,
                canonical_path, file_size, mtime_ns, container_format,
                availability_status, scan_generation, last_seen_at, last_scanned_at,
                created_at
            ) VALUES (
                ?, 'FILE', ?, ?,
                ?, ?, ?, ?,
                'AVAILABLE', 0, ?, ?,
                ?
            )
            """,
            (
                media_version_id,
                source_id,
                relative_path,
                canonical_path,
                file_size,
                mtime_ns,
                container_format,
                now_iso,
                now_iso,
                now_iso,
            ),
        )
        resource_id = cur.lastrowid
        action = "inserted"
    else:
        resource_id, media_version_id = row
        # Update existing media_version duration and timestamp
        db.execute(
            """
            UPDATE media_versions
            SET duration_seconds = ?, updated_at = ?
            WHERE id = ?
            """,
            (duration_seconds, now_iso, media_version_id),
        )

        # Update existing resource mutable facts
        db.execute(
            """
            UPDATE resources
            SET canonical_path = ?, file_size = ?, mtime_ns = ?, container_format = ?,
                availability_status = 'AVAILABLE', last_seen_at = ?, last_scanned_at = ?
            WHERE id = ?
            """,
            (canonical_path, file_size, mtime_ns, container_format, now_iso, now_iso, resource_id),
        )

        # Clear existing streams to prevent stale accumulation
        db.execute("DELETE FROM video_streams WHERE resource_id = ?", (resource_id,))
        db.execute("DELETE FROM audio_streams WHERE resource_id = ?", (resource_id,))
        db.execute("DELETE FROM subtitle_streams WHERE resource_id = ?", (resource_id,))
        action = "updated"

    # Insert video streams
    video_count = 0
    for v in video_streams:
        if not isinstance(v, dict):
            continue
        db.execute(
            """
            INSERT INTO video_streams (
                resource_id, stream_index, codec, profile, width, height,
                pixel_format, bit_depth, frame_rate_num, frame_rate_den,
                sample_aspect_ratio, display_aspect_ratio, color_primaries,
                color_transfer, color_matrix, hdr_format, dolby_vision_profile,
                duration_seconds, is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_id,
                v.get("stream_index"),
                v.get("codec"),
                v.get("profile"),
                v.get("width"),
                v.get("height"),
                v.get("pixel_format"),
                v.get("bit_depth"),
                v.get("frame_rate_num"),
                v.get("frame_rate_den"),
                v.get("sample_aspect_ratio"),
                v.get("display_aspect_ratio"),
                v.get("color_primaries"),
                v.get("color_transfer"),
                v.get("color_matrix"),
                v.get("hdr_format"),
                v.get("dolby_vision_profile"),
                v.get("duration_seconds"),
                1 if v.get("is_default") else 0,
            ),
        )
        video_count += 1

    # Insert audio streams
    audio_count = 0
    for a in audio_streams:
        if not isinstance(a, dict):
            continue
        db.execute(
            """
            INSERT INTO audio_streams (
                resource_id, stream_index, codec, profile, channels,
                channel_layout, sample_rate, bitrate, language, title,
                atmos, dtsx, is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_id,
                a.get("stream_index"),
                a.get("codec"),
                a.get("profile"),
                a.get("channels"),
                a.get("channel_layout"),
                a.get("sample_rate"),
                a.get("bitrate"),
                a.get("language"),
                a.get("title"),
                0,
                0,
                1 if a.get("is_default") else 0,
            ),
        )
        audio_count += 1

    # Insert subtitle streams
    subtitle_count = 0
    for s in subtitle_streams:
        if not isinstance(s, dict):
            continue
        db.execute(
            """
            INSERT INTO subtitle_streams (
                resource_id, stream_index, codec, language, title,
                is_default, is_forced
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_id,
                s.get("stream_index"),
                s.get("codec"),
                s.get("language"),
                s.get("title"),
                1 if s.get("is_default") else 0,
                1 if s.get("is_forced") else 0,
            ),
        )
        subtitle_count += 1

    return {
        "ok": True,
        "action": action,
        "media_version_id": media_version_id,
        "resource_id": resource_id,
        "source_id": source_id,
        "relative_path": relative_path,
        "canonical_path": canonical_path,
        "streams": {
            "video": video_count,
            "audio": audio_count,
            "subtitle": subtitle_count,
        },
    }


def ingest_file(
    file_path: str | Path,
    source_root: str | Path,
    db_path: str | Path | None = None,
    ffprobe_bin: str | None = None,
    timeout: float = 15.0,
    probe_func: Any = None,
) -> dict[str, Any]:
    """Execute complete ingestion pipeline: validate -> probe -> transactional DB persist."""
    # 1. Resolve and validate paths
    try:
        file_resolved, root_resolved, sid, rel_posix = resolve_source_relative(file_path, source_root)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "ok": False,
            "error": "PATH_VALIDATION_FAILED",
            "message": str(exc),
        }

    # 2. Probe using DEV2
    if probe_func is not None:
        probe_result = probe_func(file_resolved, ffprobe_bin=ffprobe_bin, timeout=timeout)
    else:
        try:
            media_probe = _load_media_probe()
        except Exception as exc:
            return {
                "ok": False,
                "error": "PROBE_LOAD_FAILED",
                "message": f"Cannot load media probe: {exc}",
            }
        probe_result = media_probe.probe(file_resolved, ffprobe_bin=ffprobe_bin, timeout=timeout)

    if not probe_result.get("ok"):
        return {
            "ok": False,
            "error": "PROBE_FAILED",
            "message": probe_result.get("message", "Media probe failed"),
            "probe_error": probe_result.get("error"),
        }

    # 3. Validate descriptor
    try:
        validate_descriptor(probe_result)
    except ValueError as exc:
        return {
            "ok": False,
            "error": "DESCRIPTOR_INVALID",
            "message": str(exc),
        }

    # 4. Open DB and persist transactionally
    try:
        media_db = _load_media_db()
        target_db_path = Path(db_path) if db_path is not None else media_db.database_path()
        with closing(media_db.connect(target_db_path, create=False)) as db:
            with db:
                return ingest_descriptor(db, probe_result, sid, rel_posix)
    except Exception as exc:
        return {
            "ok": False,
            "error": "DB_PERSISTENCE_FAILED",
            "message": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="Path to media file")
    parser.add_argument("--source-root", required=True, help="Explicit source root directory")
    parser.add_argument("--db", default=None, help="Path to custom media.db")
    parser.add_argument("--ffprobe", default=None, help="Path to custom ffprobe binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout for probe in seconds")

    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "ingest":
        raw_args.pop(0)

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if not args.file:
        parser.print_help(sys.stderr)
        return 2

    res = ingest_file(
        file_path=args.file,
        source_root=args.source_root,
        db_path=args.db,
        ffprobe_bin=args.ffprobe,
        timeout=args.timeout,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
