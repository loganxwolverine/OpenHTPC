# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic tests of the production Media Foundation database."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'payload/openhtpc-media-db.py'
spec = importlib.util.spec_from_file_location('media_db', COMPONENT)
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'media/media.db'
    media.initialize(path)
    with closing(media.connect(path)) as connection:
        yield connection


def version(db, **values):
    values = {'created_at': 'now', 'updated_at': 'now', **values}
    return db.execute(f"INSERT INTO media_versions ({','.join(values)}) VALUES "
                      f"({','.join('?' for _ in values)})", tuple(values.values())).lastrowid


def resource(db, **values):
    values = {'media_version_id': version(db), 'resource_kind': 'FILE',
              'created_at': 'now', **values}
    return db.execute(f"INSERT INTO resources ({','.join(values)}) VALUES "
                      f"({','.join('?' for _ in values)})", tuple(values.values())).lastrowid


def work(db):
    return db.execute("INSERT INTO works(work_type,title,created_at,updated_at) "
                      "VALUES ('MOVIE','Title','now','now')").lastrowid


def test_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    fallback = tmp_path / '.local/share/openhtpc/media/media.db'
    for env in ({}, {'XDG_DATA_HOME': ''}, {'XDG_DATA_HOME': 'relative'}):
        assert media.database_path(environ=env) == fallback
    assert media.database_path(environ={'XDG_DATA_HOME': str(tmp_path / 'data')}) == (
        tmp_path / 'data/openhtpc/media/media.db')


def test_initialization_permissions_and_idempotence(tmp_path):
    path = tmp_path / 'media/media.db'
    assert media.initialize(path) == path
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    with closing(media.connect(path)) as db:
        history = db.execute('SELECT * FROM schema_info').fetchall()
        version(db)
        db.commit()
    media.initialize(path)
    with closing(media.connect(path)) as db:
        assert db.execute('SELECT * FROM schema_info').fetchall() == history
        assert media.get_schema_version(db) == 2
        assert media.stats(db)['media_versions'] == 1
        assert set(media.stats(db)) == {
            'schema_info', 'works', 'external_ids', 'media_versions', 'resources',
            'video_streams', 'audio_streams', 'subtitle_streams', 'match_candidates'}


def test_each_connection_policy(tmp_path):
    path = media.initialize(tmp_path / 'media/media.db')
    for _ in range(2):
        with closing(media.connect(path)) as db:
            for pragma, value in [('foreign_keys', 1), ('journal_mode', 'wal'),
                                  ('busy_timeout', 5000), ('synchronous', 1)]:
                assert db.execute(f'PRAGMA {pragma}').fetchone()[0] == value
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO external_ids(work_id,provider,external_id,created_at) "
                           "VALUES (999,'test','1','now')")


def test_unidentified_and_locked_match(db):
    vid = version(db)
    assert db.execute('SELECT work_id,identification_state,match_locked FROM media_versions '
                      'WHERE id=?', (vid,)).fetchone() == (None, 'UNMATCHED', 0)
    version(db, work_id=work(db), identification_state='USER_MATCHED', match_locked=1)
    db.commit()
    assert db.execute("SELECT match_locked FROM media_versions WHERE "
                      "identification_state='USER_MATCHED'").fetchone() == (1,)
    columns = {row[1] for row in db.execute('PRAGMA table_info(media_versions)')}
    assert not columns & {'resolution', 'hdr_format', 'codec', 'frame_rate_num', 'width', 'height'}


def test_work_delete_relationships(db):
    wid = work(db)
    vid = version(db, work_id=wid)
    db.execute("INSERT INTO external_ids(work_id,provider,external_id,created_at) "
               "VALUES (?,'test','1','now')", (wid,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO external_ids(work_id,provider,external_id,created_at) "
                   "VALUES (?,'test','1','now')", (wid,))
    db.execute('DELETE FROM works WHERE id=?', (wid,))
    assert db.execute('SELECT work_id FROM media_versions WHERE id=?', (vid,)).fetchone() == (None,)
    assert media.stats(db)['external_ids'] == 0


@pytest.mark.parametrize('table', ['video_streams', 'audio_streams', 'subtitle_streams'])
def test_stream_uniqueness_and_cascade(db, table):
    rid = resource(db)
    sql = f'INSERT INTO {table}(resource_id,stream_index) VALUES (?,0)'
    db.execute(sql, (rid,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, (rid,))
    db.execute('DELETE FROM resources WHERE id=?', (rid,))
    assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone() == (0,)


def test_version_cascades(db):
    vid = version(db)
    resource(db, media_version_id=vid)
    db.execute("INSERT INTO match_candidates(media_version_id,provider,external_id,"
               "candidate_title,score,created_at) VALUES (?,'test','1','Title',0.8,'now')", (vid,))
    db.execute('DELETE FROM media_versions WHERE id=?', (vid,))
    assert media.stats(db)['resources'] == media.stats(db)['match_candidates'] == 0


def test_file_identity_and_missing_persistence(db):
    rid = resource(db, source_id='source', relative_path='movie.mkv', canonical_path='/old/movie.mkv')
    with pytest.raises(sqlite3.IntegrityError):
        resource(db, source_id='source', relative_path='movie.mkv', canonical_path='/new/movie.mkv')
    resource(db, source_id='other', relative_path='movie.mkv', canonical_path='/old/movie.mkv')
    resource(db, source_id='source', relative_path='other.mkv')
    resource(db, resource_kind='ISO', source_id='source', relative_path='movie.mkv')
    resource(db)  # Unknown source/path does not invent a shared identity.
    resource(db)
    db.execute("UPDATE resources SET availability_status='MISSING',canonical_path='/new/movie.mkv' WHERE id=?", (rid,))
    db.commit()
    assert db.execute('SELECT source_id,relative_path,availability_status FROM resources '
                      'WHERE id=?', (rid,)).fetchone() == ('source', 'movie.mkv', 'MISSING')
    indexes = {row[1]: row for row in db.execute('PRAGMA index_list(resources)')}
    assert indexes['resources_file_identity'][2:] == (1, 'c', 1)
    assert 'resources_version' in indexes


@pytest.mark.parametrize('values', [{'identification_state': 'INVALID'}, {'match_locked': 2}])
def test_match_constraints(db, values):
    with pytest.raises(sqlite3.IntegrityError):
        version(db, **values)


@pytest.mark.parametrize('values', [{'resource_kind': 'INVALID'}, {'availability_status': 'INVALID'}])
def test_resource_constraints(db, values):
    with pytest.raises(sqlite3.IntegrityError):
        resource(db, **values)


def test_integrity(db):
    assert media.check_integrity(db) == {'ok': True, 'integrity_check': ['ok'], 'foreign_key_check': []}
    db.execute('PRAGMA foreign_keys=OFF')
    db.execute("INSERT INTO external_ids(work_id,provider,external_id,created_at) VALUES (999,'test','1','now')")
    db.commit()
    assert media.check_integrity(db)['ok'] is False


@pytest.mark.parametrize('damage', ['DROP INDEX resources_file_identity',
                                   'ALTER TABLE works ADD COLUMN unwanted TEXT',
                                   'UPDATE schema_info SET version=3'])
def test_reject_schema_damage(tmp_path, damage):
    path = media.initialize(tmp_path / 'media/media.db')
    with closing(media.connect(path)) as db:
        db.execute(damage)
        db.commit()
        with pytest.raises(sqlite3.DatabaseError):
            media.check_integrity(db)
    with pytest.raises(sqlite3.DatabaseError):
        media.initialize(path)


def test_partial_and_corrupt_database(tmp_path):
    path = tmp_path / 'media/media.db'
    with closing(media.connect(path, create=True)) as db:
        db.execute('CREATE TABLE unrelated (id INTEGER)')
    with pytest.raises(sqlite3.DatabaseError):
        media.initialize(path)
    path.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        media.initialize(path)


def test_cli_explicit_initialization(tmp_path):
    env = {**os.environ, 'HOME': str(tmp_path), 'XDG_DATA_HOME': str(tmp_path / 'data')}
    path = media.database_path(environ=env)
    for operation in ('status', 'verify'):
        result = subprocess.run([sys.executable, str(COMPONENT), operation], env=env, capture_output=True, text=True)
        assert result.returncode == 1
        assert not path.parent.exists()
    for operation in ('init', 'status', 'verify', 'init'):
        result = subprocess.run([sys.executable, str(COMPONENT), operation], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['schema_version'] == 2
    assert subprocess.run([sys.executable, str(COMPONENT), 'sql'], env=env, capture_output=True).returncode == 2


def test_deployment_consistency():
    name = COMPONENT.name
    manifest = (ROOT / 'payload/managed-files.txt').read_text().splitlines()
    installer = (ROOT / 'payload/install-openhtpc-fedora.sh').read_text()
    products = re.search(r'readonly PRODUCT_FILES=\(([^)]*)\)', installer).group(1).split()
    assert manifest.count(name) == products.count(name) == 1
    assert 'for name in "${PRODUCT_FILES[@]}"; do install -m 0755 "$SCRIPT_DIR/$name" "$INSTALL_DIR/$name"; done' in installer
    assert 'exec "$ROOT/install.sh" "$@"' in (ROOT / 'update.sh').read_text()
    assert 'exec "$ROOT/payload/install-openhtpc-fedora.sh" "$@"' in (ROOT / 'install.sh').read_text()


def test_verification_preserves_caller_transaction(db):
    version(db)
    assert media.check_integrity(db)['ok']
    db.rollback()
    assert media.stats(db)['media_versions'] == 0


def test_concurrent_initialization(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / 'media/media.db'
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: media.initialize(path), range(8))) == [path] * 8
    with closing(media.connect(path)) as db:
        assert media.stats(db)['schema_info'] == 1
        assert media.check_integrity(db)['ok']


def test_existing_permissions_repaired_before_wal(tmp_path):
    path = media.initialize(tmp_path / 'media/media.db')
    path.chmod(0o644)
    path.parent.chmod(0o755)
    with closing(media.connect(path)) as db:
        version(db)
        db.commit()
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        for suffix in ('-wal', '-shm'):
            assert Path(str(path) + suffix).stat().st_mode & 0o777 == 0o600


def test_symlink_endpoint_rejected(tmp_path):
    target = tmp_path / 'target'
    target.write_text('untouched')
    link = tmp_path / 'media.db'
    link.symlink_to(target)
    with pytest.raises(ValueError):
        media.initialize(link)
    assert target.read_text() == 'untouched'


def test_work_type_and_lookup_indexes(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO works(work_type,title,created_at,updated_at) VALUES ('INVALID','t','n','n')")
    for table, name, column in [('external_ids', 'external_ids_work', 'work_id'),
                                ('media_versions', 'media_versions_work', 'work_id'),
                                ('resources', 'resources_version', 'media_version_id'),
                                ('match_candidates', 'match_candidates_version', 'media_version_id')]:
        assert name in {row[1] for row in db.execute(f'PRAGMA index_list({table})')}
        assert [row[2] for row in db.execute(f'PRAGMA index_info({name})')] == [column]


V1_TEST_SCHEMA = """
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


def _create_v1_database(path: Path) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(V1_TEST_SCHEMA)
        db.execute("INSERT INTO schema_info VALUES (1, '2026-09-11T00:00:00+00:00', 'Media Foundation schema v1')")
        db.commit()
    return path


def test_v1_to_v2_migration_and_historical_rows(tmp_path):
    path = _create_v1_database(tmp_path / 'media/media.db')
    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 1
        # Insert historical data
        rid = resource(db)
        db.execute("INSERT INTO video_streams (resource_id, stream_index, codec, width, height, is_default) "
                   "VALUES (?, 0, 'mpeg2video', 720, 576, 1)", (rid,))
        db.execute("INSERT INTO audio_streams (resource_id, stream_index, codec, channels, is_default) "
                   "VALUES (?, 1, 'ac3', 6, 1)", (rid,))
        db.commit()

    # Migrate via initialize
    media.initialize(path)

    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 2
        assert media.check_integrity(db)['ok'] is True
        history = [r[0] for r in db.execute("SELECT version FROM schema_info ORDER BY version").fetchall()]
        assert history == [1, 2]

        # Historical video row must have NULL for all newly added columns, especially is_forced
        v_row = db.execute(
            "SELECT field_order, color_range, bitrate, language, avg_frame_rate, r_frame_rate, is_forced "
            "FROM video_streams WHERE resource_id=? AND stream_index=0", (rid,)
        ).fetchone()
        assert v_row == (None, None, None, None, None, None, None)

        # Historical audio row must have NULL for is_forced
        a_row = db.execute(
            "SELECT is_forced FROM audio_streams WHERE resource_id=? AND stream_index=1", (rid,)
        ).fetchone()
        assert a_row == (None,)

        # Inserting new row with V2 values succeeds
        rid2 = resource(db)
        db.execute(
            "INSERT INTO video_streams ("
            "  resource_id, stream_index, codec, width, height, is_default, "
            "  field_order, color_range, bitrate, language, avg_frame_rate, r_frame_rate, is_forced"
            ") VALUES (?, 0, 'mpeg2video', 720, 576, 1, 'tt', 'tv', 5000000, 'fre', '25/1', '25/1', 0)",
            (rid2,)
        )
        db.execute(
            "INSERT INTO audio_streams ("
            "  resource_id, stream_index, codec, channels, is_default, is_forced"
            ") VALUES (?, 1, 'ac3', 2, 0, 1)",
            (rid2,)
        )
        db.commit()
        assert media.check_integrity(db)['ok'] is True


def test_v1_to_v2_migration_idempotence(tmp_path):
    path = _create_v1_database(tmp_path / 'media/media.db')
    media.initialize(path)

    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 2
        # Explicit _migrate_v1_to_v2 on already migrated db is a no-op
        media._migrate_v1_to_v2(db)
        assert media.get_schema_version(db) == 2

    # Calling initialize again is idempotent
    media.initialize(path)
    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 2
        assert media.check_integrity(db)['ok'] is True


def test_v1_to_v2_migration_rollback_on_failure(tmp_path):
    path = _create_v1_database(tmp_path / 'media/media.db')
    with closing(media.connect(path)) as db:
        # Pre-create a conflicting column to force migration statement failure
        db.execute("ALTER TABLE video_streams ADD COLUMN field_order TEXT")
        db.commit()

    with closing(media.connect(path)) as db:
        with pytest.raises(sqlite3.OperationalError):
            media._migrate_v1_to_v2(db)

    # Verify rollback: schema version remains 1 and no schema_info version 2 was added
    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 1
        rows = db.execute("SELECT version FROM schema_info").fetchall()
        assert rows == [(1,)]


def test_v2_check_constraints(db):
    rid = resource(db)
    # Valid field_order values
    for fo in ('progressive', 'tt', 'bb', 'tb', 'bt', 'unknown', None):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, field_order) VALUES (?, ?, ?)",
                   (rid, 100 + (hash(fo) % 1000), fo))
    # Invalid field_order
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, field_order) VALUES (?, 99, 'invalid')", (rid,))

    # Valid color_range values
    for cr in ('tv', 'pc', 'unknown', None):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, color_range) VALUES (?, ?, ?)",
                   (rid, 200 + (hash(cr) % 1000), cr))
    # Invalid color_range
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, color_range) VALUES (?, 98, 'invalid')", (rid,))

    # Negative bitrate disallowed
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, bitrate) VALUES (?, 97, -1)", (rid,))

    # Invalid is_forced on video_streams (not in 0, 1)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO video_streams (resource_id, stream_index, is_forced) VALUES (?, 96, 2)", (rid,))

    # Invalid is_forced on audio_streams (not in 0, 1)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO audio_streams (resource_id, stream_index, is_forced) VALUES (?, 95, 2)", (rid,))
