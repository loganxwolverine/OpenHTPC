# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Comprehensive tests for Media Foundation presentation schema and domain model (DEV6A1).

Tests cover:
  - Fresh schema v3 creation and integrity verification
  - Strictly additive migration from schema v2 to schema v3
  - Non-regression: existing works, external_ids, media_versions, resources, streams untouched
  - Provider snapshots CRUD, deduplication, conflict updates, and cascade delete
  - Work presentations CRUD, multi-locale separation, conflict updates, and cascade delete
  - Foreign key constraint and ON DELETE SET NULL on source_snapshot_id
  - Provenance consistency guard: rejection of presentation-snapshot work mismatches
  - Genre normalization and payload JSON canonicalization
  - Strict work independence: presentations never mutate works identity attributes
  - Artwork storage class and no-cache-path guard
"""
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3

import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
COMPONENT = ROOT / "payload/openhtpc-media-db.py"
spec = importlib.util.spec_from_file_location("media_db", COMPONENT)
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Provide a freshly initialized schema v3 database connection."""
    path = tmp_path / "media/media.db"
    media.initialize(path)
    with closing(media.connect(path)) as connection:
        yield connection


def insert_work(db: sqlite3.Connection, title: str = "Inception", original_title: str | None = "Inception", year: int = 2010) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO works (work_type, title, original_title, year, created_at, updated_at) "
        "VALUES ('MOVIE', ?, ?, ?, ?, ?)",
        (title, original_title, year, now, now),
    )
    db.commit()
    return cur.lastrowid


def insert_external_id(db: sqlite3.Connection, work_id: int, provider: str = "tmdb", external_id: str = "27205") -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO external_ids (work_id, provider, external_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (work_id, provider, external_id, now),
    )
    db.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 1. Fresh Schema v3 Creation & Integrity
# ---------------------------------------------------------------------------

def test_fresh_schema_v3_creation_and_integrity(tmp_path):
    """Fresh initialization produces schema v4 with all tables, indexes, and passes integrity checks."""
    path = tmp_path / "fresh/media.db"
    assert media.initialize(path) == path
    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 4
        chk = media.check_integrity(db)
        assert chk["ok"] is True
        assert chk["integrity_check"] == ["ok"]
        assert chk["foreign_key_check"] == []

        st = media.stats(db)
        assert "provider_snapshots" in st
        assert "work_presentations" in st
        assert "media_version_searches" in st
        assert st["provider_snapshots"] == 0
        assert st["work_presentations"] == 0
        assert st["media_version_searches"] == 0
        assert len(st) == 12


def test_schema_indexes_exist(db):
    """Schema v3 indexes are properly registered."""
    ps_indexes = {row[1] for row in db.execute("PRAGMA index_list(provider_snapshots)")}
    assert "provider_snapshots_external_id" in ps_indexes

    wp_indexes = {row[1] for row in db.execute("PRAGMA index_list(work_presentations)")}
    assert "work_presentations_work" in wp_indexes


# ---------------------------------------------------------------------------
# 2. Additive Migration v2 -> v3
# ---------------------------------------------------------------------------

def test_v2_to_v3_migration_preserves_all_v2_tables_and_rows(tmp_path):
    """Migration from schema v2 to v3 is strictly additive and leaves existing data intact."""
    from tests.test_media_db_foundation import _create_v2_database

    path = _create_v2_database(tmp_path / "migrated/media.db")
    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 2

        # Populate representative v2 data
        wid = insert_work(db, title="Historical Movie", original_title="Original Movie", year=1999)
        eid = insert_external_id(db, wid, "tmdb", "99999")

        cur = db.execute(
            "INSERT INTO media_versions (work_id, provisional_title, created_at, updated_at) "
            "VALUES (?, 'Historical Version', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')",
            (wid,),
        )
        vid = cur.lastrowid

        cur = db.execute(
            "INSERT INTO resources (media_version_id, resource_kind, source_id, relative_path, availability_status, created_at) "
            "VALUES (?, 'FILE', 'src1', 'movie.mkv', 'AVAILABLE', '2026-09-01T00:00:00+00:00')",
            (vid,),
        )
        rid = cur.lastrowid

        db.execute(
            "INSERT INTO video_streams (resource_id, stream_index, codec, width, height, field_order, color_range, bitrate, is_forced) "
            "VALUES (?, 0, 'h264', 1920, 1080, 'progressive', 'tv', 8000000, 0)",
            (rid,),
        )
        db.execute(
            "INSERT INTO audio_streams (resource_id, stream_index, codec, channels, is_default, is_forced) "
            "VALUES (?, 1, 'aac', 2, 1, 0)",
            (rid,),
        )
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, candidate_year, score, created_at) "
            "VALUES (?, 'tmdb', '99999', 'Historical Movie', 1999, 1.0, '2026-09-01T00:00:00+00:00')",
            (vid,),
        )
        db.commit()

    # Perform migration
    media.initialize(path)

    with closing(media.connect(path)) as db:
        assert media.get_schema_version(db) == 4
        chk = media.check_integrity(db)
        assert chk["ok"] is True

        # Verify historical data untouched
        w_row = db.execute("SELECT title, original_title, year FROM works WHERE id = ?", (wid,)).fetchone()
        assert w_row == ("Historical Movie", "Original Movie", 1999)

        e_row = db.execute("SELECT provider, external_id FROM external_ids WHERE id = ?", (eid,)).fetchone()
        assert e_row == ("tmdb", "99999")

        v_row = db.execute("SELECT field_order, color_range, bitrate FROM video_streams WHERE resource_id = ? AND stream_index = 0", (rid,)).fetchone()
        assert v_row == ("progressive", "tv", 8000000)

        a_row = db.execute("SELECT codec, channels, is_forced FROM audio_streams WHERE resource_id = ? AND stream_index = 1", (rid,)).fetchone()
        assert a_row == ("aac", 2, 0)

        c_row = db.execute("SELECT candidate_title, score FROM match_candidates WHERE media_version_id = ?", (vid,)).fetchone()
        assert c_row == ("Historical Movie", 1.0)

        # New tables exist and are empty
        assert media.stats(db)["provider_snapshots"] == 0
        assert media.stats(db)["work_presentations"] == 0


# ---------------------------------------------------------------------------
# 3. Provider Snapshots Domain Model
# ---------------------------------------------------------------------------

def test_upsert_provider_snapshot_insert_and_retrieve(db):
    """Inserting a new provider snapshot succeeds and can be retrieved."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")

    payload = {
        "title": "Inception",
        "original_title": "Inception",
        "release_date": "2010-07-16",
        "runtime": 148,
        "overview": "A thief who steals corporate secrets through the use of dream-sharing technology...",
        "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
    }

    res = media.upsert_provider_snapshot(
        db,
        external_id_id=eid,
        snapshot_kind="DETAILS",
        locale="en-US",
        payload_json=payload,
    )
    assert res["ok"] is True
    assert res["is_update"] is False
    snap_id = res["id"]

    # Retrieve snapshot
    record = media.get_provider_snapshot(db, snap_id)
    assert record["ok"] is True
    assert record["id"] == snap_id
    assert record["external_id_id"] == eid
    assert record["snapshot_kind"] == "DETAILS"
    assert record["locale"] == "en-US"
    assert record["payload"]["title"] == "Inception"
    assert record["payload"]["runtime"] == 148


def test_upsert_provider_snapshot_idempotent_refresh(db):
    """Upserting an existing snapshot updates payload and updated_at while keeping id stable."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")

    payload1 = {"title": "Inception (Draft)", "runtime": 140}
    res1 = media.upsert_provider_snapshot(db, eid, "DETAILS", "en-US", payload1)
    id1 = res1["id"]
    created_at1 = res1["created_at"]

    payload2 = {"title": "Inception (Final)", "runtime": 148}
    res2 = media.upsert_provider_snapshot(db, eid, "DETAILS", "en-US", payload2)
    id2 = res2["id"]
    assert id2 == id1
    assert res2["is_update"] is True
    assert res2["created_at"] == created_at1

    # Verify database state
    record = media.get_provider_snapshot(db, id1)
    assert record["payload"]["title"] == "Inception (Final)"
    assert record["payload"]["runtime"] == 148


def test_provider_snapshot_separation_by_locale_and_kind(db):
    """Different locales and kinds for the same external_id create distinct snapshots."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")

    res_en = media.upsert_provider_snapshot(db, eid, "DETAILS", "en-US", {"title": "Inception"})
    res_fr = media.upsert_provider_snapshot(db, eid, "DETAILS", "fr-FR", {"title": "Inception (FR)"})
    res_credits = media.upsert_provider_snapshot(db, eid, "CREDITS", "en-US", {"cast": []})

    assert len({res_en["id"], res_fr["id"], res_credits["id"]}) == 3
    assert media.stats(db)["provider_snapshots"] == 3


def test_provider_snapshot_invalid_external_id(db):
    """Upserting with non-existent external_id fails foreign key constraint or error."""
    res = media.upsert_provider_snapshot(
        db,
        external_id_id=999999,
        snapshot_kind="DETAILS",
        locale="en-US",
        payload_json={"title": "Test"},
    )
    assert res["ok"] is False
    assert res["error"] in ("EXTERNAL_ID_NOT_FOUND", "DB_ERROR")


def test_provider_snapshot_cascade_on_external_id_delete(db):
    """Deleting an external_ids row cascades and deletes associated provider snapshots."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")
    res = media.upsert_provider_snapshot(db, eid, "DETAILS", "en-US", {"title": "Inception"})
    snap_id = res["id"]

    db.execute("DELETE FROM external_ids WHERE id = ?", (eid,))
    db.commit()

    record = media.get_provider_snapshot(db, snap_id)
    assert record["ok"] is False
    assert record == "NOT_FOUND"


def test_provider_snapshot_malformed_json_rejection(db):
    """Malformed payload_json is rejected."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")

    res = media.upsert_provider_snapshot(
        db,
        external_id_id=eid,
        snapshot_kind="DETAILS",
        locale="en-US",
        payload_json="not valid json {",
    )
    assert res["ok"] is False
    assert res["error"] == "INVALID_PAYLOAD_JSON"


def test_provider_snapshot_unicode_support(db):
    """Provider snapshots properly store and retrieve Unicode text including CJK and accented characters."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "129")

    payload = {
        "title": "千と千尋の神隠し",
        "original_title": "千と千尋の神隠し",
        "overview": "10歳の少女・千尋は、両親と共に引越し先へと向かう途中で...",
    }
    res = media.upsert_provider_snapshot(db, eid, "DETAILS", "ja-JP", payload)
    assert res["ok"] is True

    record = media.get_provider_snapshot(db, res["id"])
    assert record["payload"]["title"] == "千と千尋の神隠し"
    assert "千尋" in record["payload"]["overview"]


# ---------------------------------------------------------------------------
# 4. Work Presentations Domain Model
# ---------------------------------------------------------------------------

def test_upsert_work_presentation_insert_and_retrieve(db):
    """Inserting a normalized work presentation succeeds and can be retrieved."""
    wid = insert_work(db, title="Inception", original_title="Inception")
    eid = insert_external_id(db, wid, "tmdb", "27205")
    snap_res = media.upsert_provider_snapshot(db, eid, "DETAILS", "fr-FR", {"title": "Inception"})
    snap_id = snap_res["id"]

    res = media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="fr-FR",
        source_snapshot_id=snap_id,
        display_title="Inception",
        display_original_title="Inception",
        release_date="2010-07-21",
        runtime_minutes=148,
        overview="Dom Cobb est un voleur expérimenté...",
        genres=["Action", "Science-Fiction", "Thriller"],
    )
    assert res["ok"] is True
    assert res["is_update"] is False
    pres_id = res["id"]

    record = media.get_work_presentation(db, wid, "fr-FR")
    assert record["ok"] is True
    assert record["id"] == pres_id
    assert record["work_id"] == wid
    assert record["locale"] == "fr-FR"
    assert record["source_snapshot_id"] == snap_id
    assert record["display_title"] == "Inception"
    assert record["display_original_title"] == "Inception"
    assert record["release_date"] == "2010-07-21"
    assert record["runtime_minutes"] == 148
    assert "Dom Cobb" in record["overview"]
    assert record["genres"] == ["Action", "Science-Fiction", "Thriller"]


def test_upsert_work_presentation_idempotent_refresh(db):
    """Upserting an existing presentation updates fields and updated_at while keeping id stable."""
    wid = insert_work(db)

    res1 = media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="en-US",
        display_title="Preliminary Title",
        runtime_minutes=140,
    )
    id1 = res1["id"]
    created_at1 = res1["created_at"]

    res2 = media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="en-US",
        display_title="Final Title",
        runtime_minutes=148,
    )
    assert res2["id"] == id1
    assert res2["is_update"] is True
    assert res2["created_at"] == created_at1

    record = media.get_work_presentation(db, wid, "en-US")
    assert record["display_title"] == "Final Title"
    assert record["runtime_minutes"] == 148


def test_work_presentation_multi_locale_separation(db):
    """Different locales for the same work store distinct presentation records."""
    wid = insert_work(db)

    res_en = media.upsert_work_presentation(db, wid, "en-US", display_title="Spirited Away")
    res_ja = media.upsert_work_presentation(db, wid, "ja-JP", display_title="千と千尋の神隠し")
    res_fr = media.upsert_work_presentation(db, wid, "fr-FR", display_title="Le Voyage de Chihiro")

    assert len({res_en["id"], res_ja["id"], res_fr["id"]}) == 3
    assert media.stats(db)["work_presentations"] == 3

    assert media.get_work_presentation(db, wid, "ja-JP")["display_title"] == "千と千尋の神隠し"
    assert media.get_work_presentation(db, wid, "fr-FR")["display_title"] == "Le Voyage de Chihiro"


def test_work_presentation_missing_work_rejection(db):
    """Upserting presentation for non-existent work fails."""
    res = media.upsert_work_presentation(
        db,
        work_id=888888,
        locale="en-US",
        display_title="Ghost",
    )
    assert res["ok"] is False
    assert res["error"] == "WORK_NOT_FOUND"


# ---------------------------------------------------------------------------
# 5. Provenance Consistency Guard (Section 15)
# ---------------------------------------------------------------------------

def test_provenance_consistency_guard_rejects_work_snapshot_mismatch(db):
    """Source snapshot belonging to Work A cannot be linked to Work B."""
    wid_a = insert_work(db, title="Work A")
    eid_a = insert_external_id(db, wid_a, "tmdb", "111")
    snap_a = media.upsert_provider_snapshot(db, eid_a, "DETAILS", "en-US", {"title": "Work A"})

    wid_b = insert_work(db, title="Work B")

    # Attempt to use snap_a as source for wid_b
    res = media.upsert_work_presentation(
        db,
        work_id=wid_b,
        locale="en-US",
        source_snapshot_id=snap_a["id"],
        display_title="Work B",
    )
    assert res["ok"] is False
    assert res["error"] == "PRESENTATION_SOURCE_WORK_MISMATCH"
    assert "belongs to work" in res["message"]


def test_work_presentation_missing_source_snapshot_rejection(db):
    """Non-existent source_snapshot_id is rejected."""
    wid = insert_work(db)
    res = media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="en-US",
        source_snapshot_id=777777,
        display_title="Work",
    )
    assert res["ok"] is False
    assert res["error"] == "SNAPSHOT_NOT_FOUND"


def test_work_presentation_source_snapshot_deletion_sets_null(db):
    """When a referenced provider snapshot is deleted, work_presentation.source_snapshot_id becomes NULL."""
    wid = insert_work(db)
    eid = insert_external_id(db, wid, "tmdb", "27205")
    snap = media.upsert_provider_snapshot(db, eid, "DETAILS", "en-US", {"title": "Inception"})
    snap_id = snap["id"]

    pres = media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="en-US",
        source_snapshot_id=snap_id,
        display_title="Inception",
    )
    assert pres["ok"] is True

    # Delete snapshot
    db.execute("DELETE FROM provider_snapshots WHERE id = ?", (snap_id,))
    db.commit()

    # Presentation survives with source_snapshot_id = None
    record = media.get_work_presentation(db, wid, "en-US")
    assert record["ok"] is True
    assert record["source_snapshot_id"] is None
    assert record["display_title"] == "Inception"


def test_work_presentation_work_cascade_deletion(db):
    """Deleting a work row cascades and deletes all associated work_presentations."""
    wid = insert_work(db)
    media.upsert_work_presentation(db, wid, "en-US", display_title="Title EN")
    media.upsert_work_presentation(db, wid, "fr-FR", display_title="Title FR")
    assert media.stats(db)["work_presentations"] == 2

    db.execute("DELETE FROM works WHERE id = ?", (wid,))
    db.commit()

    assert media.stats(db)["work_presentations"] == 0
    assert media.get_work_presentation(db, wid, "en-US") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 6. Strict Work Independence (Crucial Requirement)
# ---------------------------------------------------------------------------

def test_work_independence_presentation_never_mutates_works_table(db):
    """Presentation operations must NEVER modify works.title, works.original_title, or works.updated_at."""
    wid = insert_work(db, title="Canonical Work Title", original_title="Original Canonical Title", year=2000)
    w_before = db.execute("SELECT title, original_title, year, created_at, updated_at FROM works WHERE id = ?", (wid,)).fetchone()

    # Perform presentation insert
    media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="fr-FR",
        display_title="Titre Présentation Modifié",
        display_original_title="Autre Titre Original",
        overview="Un résumé différent...",
        genres=["Comédie"],
    )

    w_after_insert = db.execute("SELECT title, original_title, year, created_at, updated_at FROM works WHERE id = ?", (wid,)).fetchone()
    assert w_after_insert == w_before

    # Perform presentation update
    media.upsert_work_presentation(
        db,
        work_id=wid,
        locale="fr-FR",
        display_title="Deuxième Titre",
        genres=["Drame"],
    )

    w_after_update = db.execute("SELECT title, original_title, year, created_at, updated_at FROM works WHERE id = ?", (wid,)).fetchone()
    assert w_after_update == w_before


# ---------------------------------------------------------------------------
# 7. Artwork Storage Policy & No-Cache-Path Guard (Section 16 & 17)
# ---------------------------------------------------------------------------

def test_artwork_storage_class_constant():
    """ARTWORK_STORAGE_CLASS is defined as REPRODUCIBLE_CACHE."""
    assert hasattr(media, "ARTWORK_STORAGE_CLASS")
    assert media.ARTWORK_STORAGE_CLASS == "REPRODUCIBLE_CACHE"


def test_no_local_artwork_path_columns_in_presentation_tables(db):
    """Critical correction: Neither provider_snapshots nor work_presentations contain local artwork paths."""
    forbidden_substrings = ("poster_local", "backdrop_local", "cache_path", "local_path", "artwork_path")

    # Check work_presentations columns
    wp_cols = [row[1].lower() for row in db.execute("PRAGMA table_info(work_presentations)")]
    for col in wp_cols:
        for bad in forbidden_substrings:
            assert bad not in col, f"Forbidden column '{col}' in work_presentations!"

    # Check provider_snapshots columns
    ps_cols = [row[1].lower() for row in db.execute("PRAGMA table_info(provider_snapshots)")]
    for col in ps_cols:
        for bad in forbidden_substrings:
            assert bad not in col, f"Forbidden column '{col}' in provider_snapshots!"

    # Specifically assert absence of previously proposed candidate columns
    assert "poster_local_path" not in wp_cols
    assert "backdrop_local_path" not in wp_cols
    assert "artwork_cache_path" not in wp_cols
    assert "poster_local_path" not in ps_cols
    assert "backdrop_local_path" not in ps_cols
    assert "artwork_cache_path" not in ps_cols


# ---------------------------------------------------------------------------
# 8. Helper APIs (normalize_genres, canonicalize_payload_json, PresentationRecord)
# ---------------------------------------------------------------------------

def test_normalize_genres():
    """normalize_genres correctly strips, deduplicates, and preserves order."""
    assert media.normalize_genres(None) == "[]"
    assert media.normalize_genres([]) == "[]"
    assert media.normalize_genres("") == "[]"
    assert media.normalize_genres("   ") == "[]"

    # List input with duplicates and whitespace
    res = media.normalize_genres([" Action ", "Sci-Fi", "Action", "Drama  ", "Sci-Fi"])
    assert json.loads(res) == ["Action", "Sci-Fi", "Drama"]

    # Tuple input
    res_tup = media.normalize_genres(("Comedy", "Animation", "Comedy"))
    assert json.loads(res_tup) == ["Comedy", "Animation"]

    # JSON array string input
    res_str = media.normalize_genres('["Action", "Thriller", "Action"]')
    assert json.loads(res_str) == ["Action", "Thriller"]

    # Non-string element rejected
    with pytest.raises(ValueError):
        media.normalize_genres(["Action", 123])

    # Invalid type rejected
    with pytest.raises(ValueError):
        media.normalize_genres(12345)


def test_canonicalize_payload_json():
    """canonicalize_payload_json produces deterministic, compact, sorted-key JSON."""
    dict_payload = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
    canon = media.canonicalize_payload_json(dict_payload)
    assert canon == '{"a":1,"b":2,"nested":{"y":25,"z":26}}'

    # String input normalized to canonical form
    raw_json = '{\n  "b": 2,\n  "a": 1\n}'
    canon2 = media.canonicalize_payload_json(raw_json)
    assert canon2 == '{"a":1,"b":2}'

    # Invalid JSON string rejected
    with pytest.raises(ValueError):
        media.canonicalize_payload_json("invalid { json")


def test_presentation_record_transparent_equality(db):
    """PresentationRecord provides transparent equality and boolean semantics."""
    wid = insert_work(db)
    not_found = media.get_work_presentation(db, wid, "non-existent")
    assert not_found["ok"] is False
    assert not_found == "NOT_FOUND"
    assert not_found == None  # noqa: E711
    assert not bool(not_found)

    found = media.upsert_work_presentation(db, wid, "en-US", display_title="Found")
    assert bool(found)
    assert found != "NOT_FOUND"
    assert found != None  # noqa: E711
