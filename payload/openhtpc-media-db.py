#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Persistent media knowledge, schema v4. Initialization is explicit only.

Callers own returned connections and must close them. FILE identity is the
source-relative pair when both values are known; canonical_path is diagnostic.
No scanning, identification, configuration, or playback integration lives here.

Identity vs Presentation distinction:
  works.original_title
    = identity-time clue/value retained by current qualified identity contract.
  work_presentations.display_original_title
    = presentation value derived from selected provider snapshot.

Artwork storage policy:
  ARTWORK_STORAGE_CLASS = REPRODUCIBLE_CACHE
  Posters and backdrops are reproducible cache assets stored outside SQLite;
  canonical presentation records never contain local artwork paths.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any

SCHEMA_VERSION = 4
ARTWORK_STORAGE_CLASS = "REPRODUCIBLE_CACHE"
SCHEMA = """
CREATE TABLE schema_info (
 version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT
);
CREATE TABLE works (
 id INTEGER PRIMARY KEY,
 work_type TEXT NOT NULL CHECK(work_type IN ('MOVIE','TV_SERIES','TV_EPISODE','VIDEO')),
 title TEXT NOT NULL, original_title TEXT, normalized_title TEXT, year INTEGER,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE external_ids (
 id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
 provider TEXT NOT NULL, external_id TEXT NOT NULL, confidence TEXT,
 created_at TEXT NOT NULL, UNIQUE(provider, external_id)
);
CREATE TABLE media_versions (
 id INTEGER PRIMARY KEY, work_id INTEGER REFERENCES works(id) ON DELETE SET NULL,
 provisional_title TEXT, provisional_year INTEGER, edition_title TEXT,
 identification_state TEXT NOT NULL DEFAULT 'UNMATCHED'
 CHECK(identification_state IN ('UNMATCHED','AUTO_MATCHED','USER_MATCHED')),
 match_confidence REAL, match_method TEXT,
 match_locked INTEGER NOT NULL DEFAULT 0 CHECK(match_locked IN (0,1)),
 duration_seconds REAL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE resources (
 id INTEGER PRIMARY KEY,
 media_version_id INTEGER NOT NULL REFERENCES media_versions(id) ON DELETE CASCADE,
 resource_kind TEXT NOT NULL CHECK(resource_kind IN ('FILE','DISC','ISO','BDMV')),
 source_id TEXT, relative_path TEXT, canonical_path TEXT,
 file_size INTEGER, mtime_ns INTEGER, container_format TEXT,
 availability_status TEXT NOT NULL DEFAULT 'AVAILABLE'
 CHECK(availability_status IN ('AVAILABLE','MISSING','UNKNOWN')),
 scan_generation INTEGER NOT NULL DEFAULT 0,
 last_seen_at TEXT, last_scanned_at TEXT, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX resources_file_identity ON resources(source_id, relative_path)
 WHERE resource_kind = 'FILE';
CREATE TABLE video_streams (
 id INTEGER PRIMARY KEY,
 resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
 stream_index INTEGER NOT NULL, codec TEXT, profile TEXT, width INTEGER, height INTEGER,
 pixel_format TEXT, bit_depth INTEGER, frame_rate_num INTEGER, frame_rate_den INTEGER,
 sample_aspect_ratio TEXT, display_aspect_ratio TEXT, color_primaries TEXT,
 color_transfer TEXT, color_matrix TEXT, hdr_format TEXT, dolby_vision_profile INTEGER,
 duration_seconds REAL, is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
 field_order TEXT NULL CHECK(field_order IS NULL OR field_order IN ('progressive','tt','bb','tb','bt','unknown')),
 color_range TEXT NULL CHECK(color_range IS NULL OR color_range IN ('tv','pc','unknown')),
 bitrate INTEGER NULL CHECK(bitrate IS NULL OR bitrate >= 0),
 language TEXT NULL, avg_frame_rate TEXT NULL, r_frame_rate TEXT NULL,
 is_forced INTEGER NULL CHECK(is_forced IS NULL OR is_forced IN (0,1)),
 UNIQUE(resource_id, stream_index)
);
CREATE TABLE audio_streams (
 id INTEGER PRIMARY KEY,
 resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
 stream_index INTEGER NOT NULL, codec TEXT, profile TEXT, channels INTEGER,
 channel_layout TEXT, sample_rate INTEGER, bitrate INTEGER, language TEXT, title TEXT,
 atmos INTEGER NOT NULL DEFAULT 0 CHECK(atmos IN (0,1)),
 dtsx INTEGER NOT NULL DEFAULT 0 CHECK(dtsx IN (0,1)),
 is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
 is_forced INTEGER NULL CHECK(is_forced IS NULL OR is_forced IN (0,1)),
 UNIQUE(resource_id, stream_index)
);
CREATE TABLE subtitle_streams (
 id INTEGER PRIMARY KEY,
 resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
 stream_index INTEGER NOT NULL, codec TEXT, language TEXT, title TEXT,
 is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
 is_forced INTEGER NOT NULL DEFAULT 0 CHECK(is_forced IN (0,1)),
 UNIQUE(resource_id, stream_index)
);
CREATE TABLE match_candidates (
 id INTEGER PRIMARY KEY,
 media_version_id INTEGER NOT NULL REFERENCES media_versions(id) ON DELETE CASCADE,
 provider TEXT NOT NULL, external_id TEXT NOT NULL, candidate_title TEXT NOT NULL,
 candidate_year INTEGER, candidate_payload_json TEXT, score REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL
);
CREATE TABLE provider_snapshots (
 id INTEGER PRIMARY KEY,
 external_id_id INTEGER NOT NULL REFERENCES external_ids(id) ON DELETE CASCADE,
 snapshot_kind TEXT NOT NULL,
 locale TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 fetched_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(external_id_id, snapshot_kind, locale)
);
CREATE TABLE work_presentations (
 id INTEGER PRIMARY KEY,
 work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
 locale TEXT NOT NULL,
 source_snapshot_id INTEGER REFERENCES provider_snapshots(id) ON DELETE SET NULL,
 display_title TEXT NOT NULL,
 display_original_title TEXT,
 release_date TEXT,
 runtime_minutes INTEGER CHECK(runtime_minutes IS NULL OR runtime_minutes >= 0),
 overview TEXT,
 genres_json TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(work_id, locale)
);
CREATE TABLE media_version_searches (
 id INTEGER PRIMARY KEY,
 media_version_id INTEGER NOT NULL REFERENCES media_versions(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 query_title TEXT,
 query_year INTEGER,
 query_locale TEXT NOT NULL DEFAULT 'fr-FR',
 query_media_type TEXT NOT NULL DEFAULT 'movie',
 query_signature TEXT NOT NULL,
 search_status TEXT NOT NULL CHECK(search_status IN ('CANDIDATES','NO_RESULT','FAILED')),
 failure_reason TEXT,
 searched_at TEXT NOT NULL,
 UNIQUE(media_version_id, provider)
);
CREATE INDEX external_ids_work ON external_ids(work_id);
CREATE INDEX media_versions_work ON media_versions(work_id);
CREATE INDEX resources_version ON resources(media_version_id);
CREATE INDEX match_candidates_version ON match_candidates(media_version_id);
CREATE INDEX provider_snapshots_external_id ON provider_snapshots(external_id_id);
CREATE INDEX work_presentations_work ON work_presentations(work_id);
CREATE INDEX media_version_searches_version ON media_version_searches(media_version_id);
"""
TABLES = ('schema_info', 'works', 'external_ids', 'media_versions', 'resources',
          'video_streams', 'audio_streams', 'subtitle_streams', 'match_candidates',
          'provider_snapshots', 'work_presentations', 'media_version_searches')


def database_path(*, environ=None, home=None) -> Path:
    """Use absolute XDG_DATA_HOME, or the standard per-user fallback."""
    env = os.environ if environ is None else environ
    xdg = env.get('XDG_DATA_HOME', '')
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else (
        Path(home) if home is not None else Path.home()) / '.local/share'
    return base / 'openhtpc/media/media.db'


def connect(path=None, *, create=False) -> sqlite3.Connection:
    """Open with Core connection policy; only explicit create permits creation."""
    path = Path(path) if path is not None else database_path()
    if create:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Refuse symlink endpoints rather than changing their target permissions.
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Database directory/file must not be a symlink')
    if not create and not path.is_file():
        raise FileNotFoundError(path)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        db.execute('PRAGMA busy_timeout = 5000')
        db.execute('PRAGMA foreign_keys = ON')
        for attempt in range(10):
            try:
                if db.execute('PRAGMA journal_mode = WAL').fetchone()[0] != 'wal':
                    raise sqlite3.DatabaseError('WAL unavailable')
                break
            except sqlite3.OperationalError as exc:
                if 'locked' in str(exc) and attempt < 9:
                    time.sleep(0.05)
                    continue
                raise
        db.execute('PRAGMA synchronous = NORMAL')
        return db
    except Exception:
        db.close()
        raise


def get_schema_version(db) -> int | None:
    if not _schema_objects(db):
        return None
    rows = db.execute('SELECT version FROM schema_info ORDER BY version').fetchall()
    versions = [r[0] for r in rows]
    if versions == [1]:
        return 1
    if versions in ([2], [1, 2]):
        return 2
    if versions in ([3], [2, 3], [1, 3], [1, 2, 3]):
        return 3
    if versions in ([SCHEMA_VERSION],
                    [3, SCHEMA_VERSION], [2, SCHEMA_VERSION], [1, SCHEMA_VERSION],
                    [2, 3, SCHEMA_VERSION], [1, 3, SCHEMA_VERSION], [1, 2, SCHEMA_VERSION],
                    [1, 2, 3, SCHEMA_VERSION]):
        return SCHEMA_VERSION
    raise sqlite3.DatabaseError('Unsupported schema history')


def _migrate_v1_to_v2(db: sqlite3.Connection) -> None:
    """Migrate database from schema v1 to schema v2.

    Strictly additive: adds field_order, color_range, bitrate, language,
    avg_frame_rate, r_frame_rate, is_forced to video_streams, and
    is_forced to audio_streams.
    """
    if get_schema_version(db) in (2, 3, 4):
        return
    if get_schema_version(db) != 1:
        raise sqlite3.DatabaseError(f'Cannot migrate schema from version {get_schema_version(db)} to 2')
    in_tx = db.in_transaction
    if not in_tx:
        db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE video_streams ADD COLUMN field_order TEXT NULL CHECK(field_order IS NULL OR field_order IN ('progressive','tt','bb','tb','bt','unknown'))")
        db.execute("ALTER TABLE video_streams ADD COLUMN color_range TEXT NULL CHECK(color_range IS NULL OR color_range IN ('tv','pc','unknown'))")
        db.execute("ALTER TABLE video_streams ADD COLUMN bitrate INTEGER NULL CHECK(bitrate IS NULL OR bitrate >= 0)")
        db.execute("ALTER TABLE video_streams ADD COLUMN language TEXT NULL")
        db.execute("ALTER TABLE video_streams ADD COLUMN avg_frame_rate TEXT NULL")
        db.execute("ALTER TABLE video_streams ADD COLUMN r_frame_rate TEXT NULL")
        db.execute("ALTER TABLE video_streams ADD COLUMN is_forced INTEGER NULL CHECK(is_forced IS NULL OR is_forced IN (0,1))")
        db.execute("ALTER TABLE audio_streams ADD COLUMN is_forced INTEGER NULL CHECK(is_forced IS NULL OR is_forced IN (0,1))")
        db.execute("INSERT INTO schema_info (version, applied_at, description) VALUES (?, ?, ?)",
                   (2, datetime.now(timezone.utc).isoformat(), 'Media Foundation schema v2'))
        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise


def _migrate_v2_to_v3(db: sqlite3.Connection) -> None:
    """Migrate database from schema v2 to schema v3.

    Strictly additive: creates provider_snapshots and work_presentations tables
    and their associated indexes.
    """
    if get_schema_version(db) in (3, 4):
        return
    if get_schema_version(db) != 2:
        raise sqlite3.DatabaseError(f'Cannot migrate schema from version {get_schema_version(db)} to 3')
    in_tx = db.in_transaction
    if not in_tx:
        db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("""
        CREATE TABLE provider_snapshots (
         id INTEGER PRIMARY KEY,
         external_id_id INTEGER NOT NULL REFERENCES external_ids(id) ON DELETE CASCADE,
         snapshot_kind TEXT NOT NULL,
         locale TEXT NOT NULL,
         payload_json TEXT NOT NULL,
         fetched_at TEXT NOT NULL,
         created_at TEXT NOT NULL,
         updated_at TEXT NOT NULL,
         UNIQUE(external_id_id, snapshot_kind, locale)
        )
        """)
        db.execute("CREATE INDEX provider_snapshots_external_id ON provider_snapshots(external_id_id)")
        db.execute("""
        CREATE TABLE work_presentations (
         id INTEGER PRIMARY KEY,
         work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
         locale TEXT NOT NULL,
         source_snapshot_id INTEGER REFERENCES provider_snapshots(id) ON DELETE SET NULL,
         display_title TEXT NOT NULL,
         display_original_title TEXT,
         release_date TEXT,
         runtime_minutes INTEGER CHECK(runtime_minutes IS NULL OR runtime_minutes >= 0),
         overview TEXT,
         genres_json TEXT,
         created_at TEXT NOT NULL,
         updated_at TEXT NOT NULL,
         UNIQUE(work_id, locale)
        )
        """)
        db.execute("CREATE INDEX work_presentations_work ON work_presentations(work_id)")
        db.execute("INSERT INTO schema_info (version, applied_at, description) VALUES (?, ?, ?)",
                   (3, datetime.now(timezone.utc).isoformat(), 'Media Foundation schema v3'))
        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise


def _migrate_v3_to_v4(db: sqlite3.Connection) -> None:
    """Migrate database from schema v3 to schema v4.

    Strictly additive: creates media_version_searches table and its associated
    index.
    """
    if get_schema_version(db) == 4:
        return
    if get_schema_version(db) != 3:
        raise sqlite3.DatabaseError(f'Cannot migrate schema from version {get_schema_version(db)} to 4')
    in_tx = db.in_transaction
    if not in_tx:
        db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("""
        CREATE TABLE media_version_searches (
         id INTEGER PRIMARY KEY,
         media_version_id INTEGER NOT NULL REFERENCES media_versions(id) ON DELETE CASCADE,
         provider TEXT NOT NULL,
         query_title TEXT,
         query_year INTEGER,
         query_locale TEXT NOT NULL DEFAULT 'fr-FR',
         query_media_type TEXT NOT NULL DEFAULT 'movie',
         query_signature TEXT NOT NULL,
         search_status TEXT NOT NULL CHECK(search_status IN ('CANDIDATES','NO_RESULT','FAILED')),
         failure_reason TEXT,
         searched_at TEXT NOT NULL,
         UNIQUE(media_version_id, provider)
        )
        """)
        db.execute("CREATE INDEX media_version_searches_version ON media_version_searches(media_version_id)")
        db.execute("INSERT INTO schema_info (version, applied_at, description) VALUES (?, ?, ?)",
                   (4, datetime.now(timezone.utc).isoformat(), 'Media Foundation schema v4'))
        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise


def _schema_objects(db):
    return db.execute("SELECT type, name, tbl_name, sql FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()


def _structural_schema(db):
    result = {}
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    indexes = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    result['tables'] = tables
    result['indexes'] = indexes
    for t in tables:
        cols = [(r[1], r[2], r[3], r[4], r[5]) for r in db.execute(f'PRAGMA table_info({t})').fetchall()]
        fks = [(r[2], r[3], r[4], r[5], r[6]) for r in db.execute(f'PRAGMA foreign_key_list({t})').fetchall()]
        idxs = [(r[1], r[2], r[4]) for r in db.execute(f'PRAGMA index_list({t})').fetchall()]
        result[t] = {'columns': cols, 'foreign_keys': fks, 'indexes': idxs}
    return result


def _verify_schema(db):
    if get_schema_version(db) != SCHEMA_VERSION:
        raise sqlite3.DatabaseError(f'Schema v{SCHEMA_VERSION} is not initialized')
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(SCHEMA)
        if _structural_schema(db) != _structural_schema(expected):
            raise sqlite3.DatabaseError(f'Schema v{SCHEMA_VERSION} definition mismatch')


def initialize(path=None) -> Path:
    """Atomically install v4 once, migrate v1/v2/v3, or validate without rewriting history.

    Unknown/partial schemas are rejected; future migrations need explicit code.
    BEGIN IMMEDIATE serializes concurrent initializers before inspecting schema.
    """
    path = Path(path) if path is not None else database_path()
    with closing(connect(path, create=True)) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            if not _schema_objects(db):
                for statement in SCHEMA.split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute('INSERT INTO schema_info VALUES (?, ?, ?)', (
                    SCHEMA_VERSION, datetime.now(timezone.utc).isoformat(),
                    'Media Foundation schema v4'))
            else:
                ver = get_schema_version(db)
                if ver == 1:
                    _migrate_v1_to_v2(db)
                    _migrate_v2_to_v3(db)
                    _migrate_v3_to_v4(db)
                elif ver == 2:
                    _migrate_v2_to_v3(db)
                    _migrate_v3_to_v4(db)
                elif ver == 3:
                    _migrate_v3_to_v4(db)
            _verify_schema(db)
    return path


def check_integrity(db) -> dict:
    """Verify schema, SQLite structure and referential integrity in one snapshot."""
    db.execute('SAVEPOINT media_db_verify')
    try:
        _verify_schema(db)
        integrity = [row[0] for row in db.execute('PRAGMA integrity_check')]
        foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
        return {'ok': integrity == ['ok'] and not foreign_keys,
                'integrity_check': integrity, 'foreign_key_check': foreign_keys}
    finally:
        db.execute('RELEASE media_db_verify')


def stats(db) -> dict:
    """Return bounded counts for the v3 tables."""
    _verify_schema(db)
    return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in TABLES}


class PresentationRecord(dict):
    """Dictionary representing a presentation or snapshot record.

    Provides transparent equality checks:
      record == "NOT_FOUND"  -> True if record is a NOT_FOUND error
      record == None         -> True if record is a NOT_FOUND error
      bool(record)           -> False if record has "ok": False
    """

    def __eq__(self, other: Any) -> bool:
        if other is None and not self.get("ok", True):
            return True
        if other == "NOT_FOUND" and self.get("error") == "NOT_FOUND":
            return True
        return super().__eq__(other)

    def __bool__(self) -> bool:
        return bool(self.get("ok", True))


def normalize_genres(genres: list[Any] | tuple[Any, ...] | str | None) -> str:
    """Normalize presentation genres to a deterministic JSON array of strings.

    - Strings only
    - Strips whitespace
    - Discards empty strings
    - Preserves order
    - Deduplicates deterministically
    - Returns JSON array string
    """
    if genres is None:
        return "[]"
    if isinstance(genres, str):
        s = genres.strip()
        if not s:
            return "[]"
        try:
            parsed = json.loads(s)
            if not isinstance(parsed, list):
                raise ValueError("genres JSON must be an array")
            items = parsed
        except json.JSONDecodeError:
            raise ValueError(f"Invalid genres JSON: {genres}")
    elif isinstance(genres, (list, tuple)):
        items = list(genres)
    else:
        raise ValueError("genres must be a list, tuple, JSON array string, or None")

    seen: set[str] = set()
    cleaned: list[str] = []
    for g in items:
        if not isinstance(g, str):
            raise ValueError(f"Genre item must be a string, got {type(g).__name__}")
        trimmed = g.strip()
        if trimmed and trimmed not in seen:
            seen.add(trimmed)
            cleaned.append(trimmed)

    return json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'))


def canonicalize_payload_json(payload: str | dict | list) -> str:
    """Validate and canonically serialize provider snapshot payload JSON."""
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if isinstance(payload, str):
        parsed = json.loads(payload)
        return json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    raise ValueError(f"payload_json must be a JSON string, dict, or list, got {type(payload).__name__}")


def upsert_provider_snapshot(
    db: sqlite3.Connection,
    external_id_id: int,
    snapshot_kind: str,
    locale: str,
    payload_json: str | dict | list,
    fetched_at: str | datetime | None = None,
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Upsert a provider snapshot for an external ID, kind, and locale.

    Validates external_id exists, canonicalizes payload_json, and preserves row ID
    on update. Does NOT mutate works or external_ids.
    """
    if not isinstance(external_id_id, int) or isinstance(external_id_id, bool) or external_id_id <= 0:
        if raise_on_error:
            raise ValueError(f"Invalid external_id_id: {external_id_id}")
        return {"ok": False, "error": "INVALID_EXTERNAL_ID", "message": f"Invalid external_id_id: {external_id_id}"}

    ext = db.execute("SELECT id FROM external_ids WHERE id = ?", (external_id_id,)).fetchone()
    if ext is None:
        if raise_on_error:
            raise ValueError(f"external_id {external_id_id} not found")
        return {"ok": False, "error": "EXTERNAL_ID_NOT_FOUND", "message": f"external_id {external_id_id} not found"}

    kind_clean = str(snapshot_kind or "").strip()
    if not kind_clean:
        if raise_on_error:
            raise ValueError("snapshot_kind must not be empty")
        return {"ok": False, "error": "INVALID_SNAPSHOT_KIND", "message": "snapshot_kind must not be empty"}

    locale_clean = str(locale or "").strip()
    if not locale_clean:
        if raise_on_error:
            raise ValueError("locale must not be empty")
        return {"ok": False, "error": "INVALID_LOCALE", "message": "locale must not be empty"}

    try:
        canon_json = canonicalize_payload_json(payload_json)
    except Exception as exc:
        if raise_on_error:
            raise ValueError(f"Invalid payload JSON: {exc}") from exc
        return {"ok": False, "error": "INVALID_PAYLOAD_JSON", "message": f"Invalid payload JSON: {exc}"}

    if fetched_at is None:
        fetched_at_str = datetime.now(timezone.utc).isoformat()
    elif isinstance(fetched_at, datetime):
        fetched_at_str = fetched_at.astimezone(timezone.utc).isoformat()
    elif isinstance(fetched_at, str) and fetched_at.strip():
        fetched_at_str = fetched_at.strip()
    else:
        if raise_on_error:
            raise ValueError(f"Invalid fetched_at: {fetched_at}")
        return {"ok": False, "error": "INVALID_FETCHED_AT", "message": f"Invalid fetched_at: {fetched_at}"}

    now_iso = datetime.now(timezone.utc).isoformat()

    existing = db.execute(
        "SELECT id, created_at FROM provider_snapshots WHERE external_id_id = ? AND snapshot_kind = ? AND locale = ?",
        (external_id_id, kind_clean, locale_clean),
    ).fetchone()

    in_tx = db.in_transaction
    if not in_tx:
        db.execute("BEGIN IMMEDIATE")
    try:
        if existing is not None:
            snapshot_id, created_at = existing[0], existing[1]
            db.execute(
                """
                UPDATE provider_snapshots
                SET payload_json = ?, fetched_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (canon_json, fetched_at_str, now_iso, snapshot_id),
            )
            is_update = True
        else:
            cur = db.execute(
                """
                INSERT INTO provider_snapshots (
                    external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (external_id_id, kind_clean, locale_clean, canon_json, fetched_at_str, now_iso, now_iso),
            )
            snapshot_id = cur.lastrowid
            created_at = now_iso
            is_update = False

        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise

    return {
        "ok": True,
        "id": snapshot_id,
        "external_id_id": external_id_id,
        "snapshot_kind": kind_clean,
        "locale": locale_clean,
        "payload_json": canon_json,
        "fetched_at": fetched_at_str,
        "created_at": created_at,
        "updated_at": now_iso,
        "is_update": is_update,
    }


def get_provider_snapshot(
    db: sqlite3.Connection,
    snapshot_id_or_external_id_id: int,
    snapshot_kind: str | None = None,
    locale: str | None = None,
) -> PresentationRecord:
    """Retrieve provider snapshot record by snapshot ID or by (external_id_id, snapshot_kind, locale).

    Returns PresentationRecord with ok=True on success, or ok=False with error="NOT_FOUND".
    """
    if snapshot_kind is None and locale is None:
        row = db.execute(
            """
            SELECT id, external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at
            FROM provider_snapshots
            WHERE id = ?
            """,
            (snapshot_id_or_external_id_id,),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT id, external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at
            FROM provider_snapshots
            WHERE external_id_id = ? AND snapshot_kind = ? AND locale = ?
            """,
            (snapshot_id_or_external_id_id, str(snapshot_kind).strip(), str(locale).strip()),
        ).fetchone()

    if row is None:
        return PresentationRecord({
            "ok": False,
            "error": "NOT_FOUND",
            "message": "provider_snapshot not found",
        })

    payload_json = row[4]
    try:
        payload = json.loads(payload_json)
    except Exception:
        payload = {}

    return PresentationRecord({
        "ok": True,
        "id": row[0],
        "external_id_id": row[1],
        "snapshot_kind": row[2],
        "locale": row[3],
        "payload_json": payload_json,
        "payload": payload,
        "fetched_at": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    })


def upsert_work_presentation(
    db: sqlite3.Connection,
    work_id: int,
    locale: str,
    display_title: str,
    display_original_title: str | None = None,
    release_date: str | None = None,
    runtime_minutes: int | None = None,
    overview: str | None = None,
    genres: list[Any] | tuple[Any, ...] | str | None = None,
    source_snapshot_id: int | None = None,
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Upsert normalized presentation for a work and locale.

    Validates work exists, checks source_snapshot provenance if supplied,
    normalizes genres to deterministic JSON, and preserves row ID on update.
    Does NOT mutate works, external_ids, or media_versions.
    """
    if not isinstance(work_id, int) or isinstance(work_id, bool) or work_id <= 0:
        if raise_on_error:
            raise ValueError(f"Invalid work_id: {work_id}")
        return {"ok": False, "error": "INVALID_WORK_ID", "message": f"Invalid work_id: {work_id}"}

    w_chk = db.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
    if w_chk is None:
        if raise_on_error:
            raise ValueError(f"work {work_id} not found")
        return {"ok": False, "error": "WORK_NOT_FOUND", "message": f"work {work_id} not found"}

    locale_clean = str(locale or "").strip()
    if not locale_clean:
        if raise_on_error:
            raise ValueError("locale must not be empty")
        return {"ok": False, "error": "INVALID_LOCALE", "message": "locale must not be empty"}

    title_clean = str(display_title or "").strip()
    if not title_clean:
        if raise_on_error:
            raise ValueError("display_title must not be empty")
        return {"ok": False, "error": "INVALID_DISPLAY_TITLE", "message": "display_title must not be empty"}

    if runtime_minutes is not None:
        if not isinstance(runtime_minutes, int) or isinstance(runtime_minutes, bool) or runtime_minutes < 0:
            if raise_on_error:
                raise ValueError(f"Invalid runtime_minutes: {runtime_minutes}")
            return {"ok": False, "error": "INVALID_RUNTIME_MINUTES", "message": f"Invalid runtime_minutes: {runtime_minutes}"}

    # Provenance consistency validation (Section 15)
    if source_snapshot_id is not None:
        if not isinstance(source_snapshot_id, int) or isinstance(source_snapshot_id, bool) or source_snapshot_id <= 0:
            if raise_on_error:
                raise ValueError(f"Invalid source_snapshot_id: {source_snapshot_id}")
            return {"ok": False, "error": "INVALID_SOURCE_SNAPSHOT_ID", "message": f"Invalid source_snapshot_id: {source_snapshot_id}"}

        snap_row = db.execute(
            """
            SELECT ps.id, e.work_id
            FROM provider_snapshots ps
            JOIN external_ids e ON e.id = ps.external_id_id
            WHERE ps.id = ?
            """,
            (source_snapshot_id,),
        ).fetchone()

        if snap_row is None:
            if raise_on_error:
                raise ValueError(f"source_snapshot {source_snapshot_id} not found")
            return {"ok": False, "error": "SNAPSHOT_NOT_FOUND", "message": f"source_snapshot {source_snapshot_id} not found"}

        snap_work_id = snap_row[1]
        if snap_work_id != work_id:
            if raise_on_error:
                raise ValueError(f"PRESENTATION_SOURCE_WORK_MISMATCH: snapshot belongs to work {snap_work_id}, not {work_id}")
            return {
                "ok": False,
                "error": "PRESENTATION_SOURCE_WORK_MISMATCH",
                "message": f"Source snapshot {source_snapshot_id} belongs to work {snap_work_id}, not {work_id}",
                "work_id": work_id,
                "snapshot_work_id": snap_work_id,
            }

    try:
        genres_json = normalize_genres(genres)
    except Exception as exc:
        if raise_on_error:
            raise ValueError(f"Invalid genres: {exc}") from exc
        return {"ok": False, "error": "INVALID_GENRES", "message": f"Invalid genres: {exc}"}

    orig_clean = str(display_original_title).strip() if display_original_title else None
    rel_clean = str(release_date).strip() if release_date else None
    over_clean = str(overview).strip() if overview else None

    now_iso = datetime.now(timezone.utc).isoformat()

    existing = db.execute(
        "SELECT id, created_at FROM work_presentations WHERE work_id = ? AND locale = ?",
        (work_id, locale_clean),
    ).fetchone()

    in_tx = db.in_transaction
    if not in_tx:
        db.execute("BEGIN IMMEDIATE")
    try:
        if existing is not None:
            pres_id, created_at = existing[0], existing[1]
            db.execute(
                """
                UPDATE work_presentations
                SET source_snapshot_id = ?,
                    display_title = ?,
                    display_original_title = ?,
                    release_date = ?,
                    runtime_minutes = ?,
                    overview = ?,
                    genres_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_snapshot_id,
                    title_clean,
                    orig_clean,
                    rel_clean,
                    runtime_minutes,
                    over_clean,
                    genres_json,
                    now_iso,
                    pres_id,
                ),
            )
            is_update = True
        else:
            cur = db.execute(
                """
                INSERT INTO work_presentations (
                    work_id, locale, source_snapshot_id, display_title, display_original_title,
                    release_date, runtime_minutes, overview, genres_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    locale_clean,
                    source_snapshot_id,
                    title_clean,
                    orig_clean,
                    rel_clean,
                    runtime_minutes,
                    over_clean,
                    genres_json,
                    now_iso,
                    now_iso,
                ),
            )
            pres_id = cur.lastrowid
            created_at = now_iso
            is_update = False

        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise

    return {
        "ok": True,
        "id": pres_id,
        "work_id": work_id,
        "locale": locale_clean,
        "source_snapshot_id": source_snapshot_id,
        "display_title": title_clean,
        "display_original_title": orig_clean,
        "release_date": rel_clean,
        "runtime_minutes": runtime_minutes,
        "overview": over_clean,
        "genres_json": genres_json,
        "genres": json.loads(genres_json),
        "created_at": created_at,
        "updated_at": now_iso,
        "is_update": is_update,
    }


def get_work_presentation(
    db: sqlite3.Connection,
    work_id: int,
    locale: str,
) -> PresentationRecord:
    """Retrieve normalized presentation record for a work and locale.

    Returns PresentationRecord with ok=True on success, or ok=False with error="NOT_FOUND".
    """
    row = db.execute(
        """
        SELECT id, work_id, locale, source_snapshot_id, display_title, display_original_title,
               release_date, runtime_minutes, overview, genres_json, created_at, updated_at
        FROM work_presentations
        WHERE work_id = ? AND locale = ?
        """,
        (work_id, str(locale).strip()),
    ).fetchone()

    if row is None:
        return PresentationRecord({
            "ok": False,
            "error": "NOT_FOUND",
            "message": f"work_presentation not found for work_id={work_id}, locale={locale}",
        })

    g_json = row[9] or "[]"
    try:
        genres = json.loads(g_json)
    except Exception:
        genres = []

    return PresentationRecord({
        "ok": True,
        "id": row[0],
        "work_id": row[1],
        "locale": row[2],
        "source_snapshot_id": row[3],
        "display_title": row[4],
        "display_original_title": row[5],
        "release_date": row[6],
        "runtime_minutes": row[7],
        "overview": row[8],
        "genres_json": g_json,
        "genres": genres,
        "created_at": row[10],
        "updated_at": row[11],
    })


VALID_SEARCH_STATUSES = frozenset({'CANDIDATES', 'NO_RESULT', 'FAILED'})


def normalize_title(text: str | None) -> str:
    """Comparison normalization for titles.

    Lowercases, strips punctuation, and collapses whitespace.
    """
    if not text:
        return ""
    s = str(text).casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def compute_query_signature(
    provider: str,
    media_type: str = "movie",
    locale: str = "fr-FR",
    title: str | None = None,
    year: int | None = None,
) -> str:
    """Compute deterministic SHA-256 signature for provider search query.

    Accounts for:
      - provider (lowercased, stripped)
      - media_type (lowercased, stripped)
      - locale (stripped)
      - normalized search title
      - extracted year (int or None)
    """
    norm_provider = str(provider or "").strip().lower()
    norm_media_type = str(media_type or "movie").strip().lower()
    norm_locale = str(locale or "fr-FR").strip()
    norm_title = normalize_title(title)
    norm_year = int(year) if year is not None else None

    canonical_payload = {
        "locale": norm_locale,
        "media_type": norm_media_type,
        "normalized_title": norm_title,
        "provider": norm_provider,
        "year": norm_year,
    }
    canonical_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()


def upsert_media_version_search(
    db: sqlite3.Connection,
    media_version_id: int,
    provider: str,
    query_signature: str,
    search_status: str,
    failure_reason: str | None = None,
    searched_at: str | datetime | None = None,
    query_title: str | None = None,
    query_year: int | None = None,
    query_locale: str = "fr-FR",
    query_media_type: str = "movie",
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Upsert durable search state for a media_version and provider.

    Guarantees provider-scoping, deterministic query signature binding,
    and transaction atomicity.
    """
    if not isinstance(media_version_id, int) or isinstance(media_version_id, bool) or media_version_id <= 0:
        raise ValueError(f"Invalid media_version_id: {media_version_id}")

    mv = db.execute("SELECT id FROM media_versions WHERE id = ?", (media_version_id,)).fetchone()
    if mv is None:
        raise ValueError(f"media_version {media_version_id} not found")

    provider_clean = str(provider or "").strip().lower()
    if not provider_clean:
        raise ValueError("provider must not be empty")

    sig_clean = str(query_signature or "").strip().lower()
    if not sig_clean:
        raise ValueError("query_signature must not be empty")

    status_clean = str(search_status or "").strip().upper()
    if status_clean not in VALID_SEARCH_STATUSES:
        raise ValueError(f"Invalid search_status: {search_status}")

    if searched_at is None:
        searched_at_str = datetime.now(timezone.utc).isoformat()
    elif isinstance(searched_at, datetime):
        searched_at_str = searched_at.astimezone(timezone.utc).isoformat()
    elif isinstance(searched_at, str) and searched_at.strip():
        searched_at_str = searched_at.strip()
    else:
        raise ValueError(f"Invalid searched_at: {searched_at}")

    failure_clean = str(failure_reason).strip()[:500] if failure_reason is not None else None
    title_clean = str(query_title).strip() if query_title is not None else None
    year_int = int(query_year) if query_year is not None else None
    locale_clean = str(query_locale or "fr-FR").strip()
    media_type_clean = str(query_media_type or "movie").strip().lower()

    existing = db.execute(
        "SELECT id FROM media_version_searches WHERE media_version_id = ? AND provider = ?",
        (media_version_id, provider_clean),
    ).fetchone()

    in_tx = db.in_transaction
    if not in_tx:
        db.execute("BEGIN IMMEDIATE")
    try:
        if existing is not None:
            row_id = existing[0]
            db.execute(
                """
                UPDATE media_version_searches
                SET query_title = ?,
                    query_year = ?,
                    query_locale = ?,
                    query_media_type = ?,
                    query_signature = ?,
                    search_status = ?,
                    failure_reason = ?,
                    searched_at = ?
                WHERE id = ?
                """,
                (title_clean, year_int, locale_clean, media_type_clean, sig_clean, status_clean, failure_clean, searched_at_str, row_id),
            )
            is_update = True
        else:
            cur = db.execute(
                """
                INSERT INTO media_version_searches (
                    media_version_id, provider, query_title, query_year,
                    query_locale, query_media_type, query_signature,
                    search_status, failure_reason, searched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (media_version_id, provider_clean, title_clean, year_int, locale_clean, media_type_clean, sig_clean, status_clean, failure_clean, searched_at_str),
            )
            row_id = cur.lastrowid
            is_update = False

        if not in_tx:
            db.commit()
    except Exception:
        if not in_tx:
            db.rollback()
        raise

    return {
        "ok": True,
        "id": row_id,
        "media_version_id": media_version_id,
        "provider": provider_clean,
        "query_title": title_clean,
        "query_year": year_int,
        "query_locale": locale_clean,
        "query_media_type": media_type_clean,
        "query_signature": sig_clean,
        "search_status": status_clean,
        "failure_reason": failure_clean,
        "searched_at": searched_at_str,
        "is_update": is_update,
    }


def get_media_version_search(
    db: sqlite3.Connection,
    media_version_id: int,
    provider: str,
) -> dict[str, Any] | None:
    """Retrieve search state record for a media_version and provider.

    Returns dict on success, or None if no search state exists.
    """
    row = db.execute(
        """
        SELECT id, media_version_id, provider, query_title, query_year,
               query_locale, query_media_type, query_signature, search_status,
               failure_reason, searched_at
        FROM media_version_searches
        WHERE media_version_id = ? AND provider = ?
        """,
        (media_version_id, str(provider).strip().lower()),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "media_version_id": row[1],
        "provider": row[2],
        "query_title": row[3],
        "query_year": row[4],
        "query_locale": row[5],
        "query_media_type": row[6],
        "query_signature": row[7],
        "search_status": row[8],
        "failure_reason": row[9],
        "searched_at": row[10],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('init', 'status', 'verify'))
    args = parser.parse_args(argv)
    path = database_path()
    try:
        if args.operation == 'init':
            initialize(path)
        with closing(connect(path)) as db:
            result = {'path': str(path), 'schema_version': get_schema_version(db)}
            if args.operation == 'verify':
                result.update(check_integrity(db))
            else:
                result['stats'] = stats(db)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('ok', True) else 1
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'path': str(path), 'error': str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
