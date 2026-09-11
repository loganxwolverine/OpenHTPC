#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Persistent media knowledge, schema v1. Initialization is explicit only.

Callers own returned connections and must close them. FILE identity is the
source-relative pair when both values are known; canonical_path is diagnostic.
No scanning, identification, configuration, or playback integration lives here.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

SCHEMA_VERSION = 1
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
CREATE INDEX external_ids_work ON external_ids(work_id);
CREATE INDEX media_versions_work ON media_versions(work_id);
CREATE INDEX resources_version ON resources(media_version_id);
CREATE INDEX match_candidates_version ON match_candidates(media_version_id);
"""
TABLES = ('schema_info', 'works', 'external_ids', 'media_versions', 'resources',
          'video_streams', 'audio_streams', 'subtitle_streams', 'match_candidates')


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
        if db.execute('PRAGMA journal_mode = WAL').fetchone()[0] != 'wal':
            raise sqlite3.DatabaseError('WAL unavailable')
        db.execute('PRAGMA synchronous = NORMAL')
        return db
    except Exception:
        db.close()
        raise


def get_schema_version(db) -> int | None:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone():
        return None
    rows = db.execute('SELECT version FROM schema_info ORDER BY version').fetchall()
    if rows != [(SCHEMA_VERSION,)]:
        raise sqlite3.DatabaseError('Unsupported schema history')
    return SCHEMA_VERSION


def _schema_objects(db):
    return db.execute("SELECT type, name, tbl_name, sql FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()


def _verify_schema(db):
    if get_schema_version(db) != SCHEMA_VERSION:
        raise sqlite3.DatabaseError('Schema v1 is not initialized')
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(SCHEMA)
        if _schema_objects(db) != _schema_objects(expected):
            raise sqlite3.DatabaseError('Schema v1 definition mismatch')


def initialize(path=None) -> Path:
    """Atomically install v1 once, or validate it without rewriting history.

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
                    'Media Foundation schema v1'))
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
    """Return bounded counts for the v1 tables."""
    _verify_schema(db)
    return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in TABLES}


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
