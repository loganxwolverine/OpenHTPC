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
        assert media.get_schema_version(db) == 1
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
                                   'UPDATE schema_info SET version=2'])
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
        assert json.loads(result.stdout)['schema_version'] == 1
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
