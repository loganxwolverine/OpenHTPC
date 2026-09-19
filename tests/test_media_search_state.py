# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Focused hermetic tests for durable provider search state and Schema 4 (DEV6C1D)."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys
from typing import Any
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


media_db = _load_module(PAYLOAD / "openhtpc-media-db.py", "media_db_search_state")
tmdb_provider = _load_module(PAYLOAD / "openhtpc-media-provider-tmdb.py", "tmdb_provider_search_state")
media_match = _load_module(PAYLOAD / "openhtpc-media-match.py", "media_match_search_state")
media_pres = _load_module(PAYLOAD / "openhtpc-media-presentation.py", "media_pres_search_state")
media_art = _load_module(PAYLOAD / "openhtpc-media-artwork.py", "media_art_search_state")
media_enrich = _load_module(PAYLOAD / "openhtpc-media-enrich.py", "media_enrich_search_state")

# Wire dependency injection
media_match.set_media_db_module(media_db)
media_match.set_tmdb_provider_module(tmdb_provider)

media_pres.set_media_db_module(media_db)
media_pres.set_tmdb_provider_module(tmdb_provider)

media_enrich.set_media_db_module(media_db)
media_enrich.set_tmdb_provider_module(tmdb_provider)
media_enrich.set_media_match_module(media_match)
media_enrich.set_presentation_module(media_pres)
media_enrich.set_artwork_module(media_art)

SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


# ─── Network Guard ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fail_closed_network_guard(monkeypatch):
    """Enforce REAL_PROVIDER_NETWORK_CALLS = 0."""
    def no_socket(*args, **kwargs):
        raise RuntimeError("REAL_PROVIDER_NETWORK_CALLS: Real network socket connection strictly forbidden in hermetic tests")
    monkeypatch.setattr(socket, "socket", no_socket)


# ─── Mock HTTP Infrastructure ────────────────────────────────────────────────

class MockHTTPResponse(io.BytesIO):
    def __init__(self, data: bytes | str, status: int = 200) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        super().__init__(raw)
        self.status = status
        self.code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class MockOpener:
    def __init__(self, routes: dict[str, Any] | None = None, default_jpeg: bytes = SYNTHETIC_JPEG) -> None:
        self.routes = routes or {}
        self.default_jpeg = default_jpeg
        self.requests: list[str] = []

    def __call__(self, request: Any, timeout: float | None = None) -> Any:
        url = request.full_url if hasattr(request, "full_url") else str(request)
        self.requests.append(url)
        for pattern, handler in self.routes.items():
            if pattern in url:
                if isinstance(handler, Exception):
                    raise handler
                elif callable(handler):
                    return handler(request)
                elif isinstance(handler, (dict, list)):
                    return MockHTTPResponse(json.dumps(handler))
                elif isinstance(handler, bytes):
                    return MockHTTPResponse(handler)
        if "image.tmdb.org" in url:
            return MockHTTPResponse(self.default_jpeg)
        return MockHTTPResponse(json.dumps({"results": []}))


def _default_search_handler(item_id: int, title: str, year: int | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "original_title": title,
        "overview": f"Overview of {title}",
        "poster_path": f"/poster_{item_id}.jpg",
        "backdrop_path": f"/backdrop_{item_id}.jpg",
    }
    if year is not None:
        res["release_date"] = f"{year}-06-15"
    return {"results": [res]}


def _default_details_handler(item_id: int, title: str, year: int | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "original_title": title,
        "overview": f"Overview of {title}",
        "poster_path": f"/poster_{item_id}.jpg",
        "backdrop_path": f"/backdrop_{item_id}.jpg",
        "genres": [{"id": 28, "name": "Action"}],
    }
    if year is not None:
        res["release_date"] = f"{year}-06-15"
    return res


# ─── Schema 3 Reference DDL for Migration Testing ────────────────────────────

V3_SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

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
CREATE INDEX external_ids_work ON external_ids(work_id);
CREATE INDEX media_versions_work ON media_versions(work_id);
CREATE INDEX resources_version ON resources(media_version_id);
CREATE INDEX match_candidates_version ON match_candidates(media_version_id);
CREATE INDEX provider_snapshots_external_id ON provider_snapshots(external_id_id);
CREATE INDEX work_presentations_work ON work_presentations(work_id);
"""


# ─── Environment Fixture ─────────────────────────────────────────────────────

class SearchStateTestEnv:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.source_root = tmp_path / "media_root"
        self.source_root.mkdir()
        self.source_id = media_enrich.compute_source_id(self.source_root)
        self.db_path = tmp_path / "media.db"
        media_db.initialize(self.db_path)

        # Write fake TMDb credential so load_credential finds it
        sec_dir = self.home / ".config/openhtpc/secrets"
        sec_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tok_file = sec_dir / "tmdb-token"
        tok_file.write_text("ey_mock_token_dev6c1\n", encoding="utf-8")
        tok_file.chmod(0o600)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def add_media(
        self,
        rel_path: str,
        *,
        source_id: str | None = None,
        identification_state: str = "UNMATCHED",
        work_id: int | None = None,
        match_locked: int = 0,
        availability_status: str = "AVAILABLE",
        resource_kind: str = "FILE",
    ) -> int:
        sid = source_id or self.source_id
        canon = str(self.source_root / rel_path)
        now_iso = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO media_versions (
                    work_id, provisional_title, provisional_year, edition_title,
                    identification_state, match_confidence, match_method, match_locked,
                    duration_seconds, created_at, updated_at
                ) VALUES (?, NULL, NULL, NULL, ?, NULL, NULL, ?, 7200.0, ?, ?)
                """,
                (work_id, identification_state, match_locked, now_iso, now_iso),
            )
            mv_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO resources (
                    media_version_id, source_id, relative_path, canonical_path,
                    availability_status, resource_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (mv_id, sid, rel_path, canon, availability_status, resource_kind, now_iso),
            )
            conn.commit()
            return mv_id

    def add_work(self, title: str, year: int, external_id: int) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            cur = conn.execute(
                "INSERT INTO works (work_type, title, original_title, year, created_at, updated_at) VALUES ('MOVIE', ?, ?, ?, ?, ?)",
                (title, title, year, now_iso, now_iso),
            )
            wid = cur.lastrowid
            conn.execute(
                "INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', ?, ?)",
                (wid, str(external_id), now_iso),
            )
            conn.commit()
            return wid

    def add_search_state(
        self,
        mv_id: int,
        query_title: str,
        query_year: int | None = None,
        search_status: str = "CANDIDATES",
        failure_reason: str | None = None,
        provider: str = "tmdb_movie",
        locale: str = "fr-FR",
        media_type: str = "movie",
    ) -> None:
        sig = media_db.compute_query_signature(
            provider=provider,
            media_type=media_type,
            locale=locale,
            title=query_title,
            year=query_year,
        )
        with closing(self.connect()) as conn:
            media_db.upsert_media_version_search(
                conn,
                media_version_id=mv_id,
                provider=provider,
                query_title=query_title,
                query_year=query_year,
                query_locale=locale,
                query_media_type=media_type,
                query_signature=sig,
                search_status=search_status,
                failure_reason=failure_reason,
            )
            conn.commit()


@pytest.fixture
def env(tmp_path: Path) -> SearchStateTestEnv:
    return SearchStateTestEnv(tmp_path)


# ─── SECTION 1: FRESH SCHEMA 4 DATABASE ──────────────────────────────────────

def test_fresh_database_is_schema_4(tmp_path: Path):
    """Fresh initialized database must report schema version 4 and have 12 tables."""
    db_path = tmp_path / "fresh.db"
    media_db.initialize(db_path)

    with closing(media_db.connect(db_path)) as conn:
        assert media_db.get_schema_version(conn) == 4
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        assert "media_version_searches" in tables
        assert len(tables) == 12

        # Verify media_version_searches columns
        cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(media_version_searches)").fetchall()}
        expected_cols = {
            "id": "INTEGER",
            "media_version_id": "INTEGER",
            "provider": "TEXT",
            "query_title": "TEXT",
            "query_year": "INTEGER",
            "query_locale": "TEXT",
            "query_media_type": "TEXT",
            "query_signature": "TEXT",
            "search_status": "TEXT",
            "failure_reason": "TEXT",
            "searched_at": "TEXT",
        }
        for col, col_type in expected_cols.items():
            assert col in cols, f"Missing column {col}"
            assert cols[col].upper() == col_type, f"Column {col} type mismatch: {cols[col]} vs {col_type}"

        # Verify indexes
        idx_rows = conn.execute("PRAGMA index_list(media_version_searches)").fetchall()
        idx_names = [r[1] for r in idx_rows]
        assert "media_version_searches_version" in idx_names

        # Verify unique index on (media_version_id, provider)
        unique_indexes = [r for r in idx_rows if r[2] == 1]
        assert len(unique_indexes) >= 1
        unique_cols = set()
        for u_idx in unique_indexes:
            u_info = conn.execute(f"PRAGMA index_info({u_idx[1]})").fetchall()
            for col_entry in u_info:
                unique_cols.add(col_entry[2])
        assert "media_version_id" in unique_cols
        assert "provider" in unique_cols


# ─── SECTION 2: V3 TO V4 MIGRATION WITH RICH FIXTURE ─────────────────────────

def test_v3_to_v4_migration_with_rich_fixture(tmp_path: Path):
    """Migration preserves all existing Schema 3 data, passes integrity checks, and creates empty search state table."""
    db_path = tmp_path / "v3_rich.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(V3_SCHEMA_DDL)
    conn.execute("INSERT INTO schema_info VALUES (3, '2026-09-15T00:00:00+00:00', 'Media Foundation schema v3')")

    # Populate rich v3 fixture
    now_iso = "2026-01-01T12:00:00+00:00"
    # 1. Works & External IDs
    cur = conn.execute("INSERT INTO works (work_type, title, original_title, year, created_at, updated_at) VALUES ('MOVIE', 'Inception', 'Inception', 2010, ?, ?)", (now_iso, now_iso))
    wid1 = cur.lastrowid
    cur = conn.execute("INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', '550', ?)", (wid1, now_iso))
    eid1 = cur.lastrowid

    # 2. Media versions: AUTO_MATCHED, USER_MATCHED, UNMATCHED
    cur = conn.execute("INSERT INTO media_versions (work_id, identification_state, match_confidence, match_method, match_locked, created_at, updated_at) VALUES (?, 'AUTO_MATCHED', 95.0, 'tmdb_direct', 0, ?, ?)", (wid1, now_iso, now_iso))
    mv1 = cur.lastrowid
    cur = conn.execute("INSERT INTO media_versions (work_id, identification_state, match_confidence, match_method, match_locked, created_at, updated_at) VALUES (?, 'USER_MATCHED', 100.0, 'user_override', 1, ?, ?)", (wid1, now_iso, now_iso))
    mv2 = cur.lastrowid
    cur = conn.execute("INSERT INTO media_versions (work_id, identification_state, match_confidence, match_method, match_locked, created_at, updated_at) VALUES (NULL, 'UNMATCHED', NULL, NULL, 0, ?, ?)", (now_iso, now_iso))
    mv3 = cur.lastrowid

    # 3. Resources & Streams
    cur = conn.execute("INSERT INTO resources (media_version_id, source_id, relative_path, canonical_path, availability_status, resource_kind, created_at) VALUES (?, 'src1', 'Inception (2010).mkv', '/media/Inception (2010).mkv', 'AVAILABLE', 'FILE', ?)", (mv1, now_iso))
    r1 = cur.lastrowid
    conn.execute("INSERT INTO video_streams (resource_id, stream_index, codec, width, height, is_default, field_order) VALUES (?, 0, 'h264', 1920, 1080, 1, 'progressive')", (r1,))
    conn.execute("INSERT INTO audio_streams (resource_id, stream_index, codec, channels, is_default, is_forced) VALUES (?, 1, 'dts', 6, 1, 0)", (r1,))
    conn.execute("INSERT INTO subtitle_streams (resource_id, stream_index, codec, language, is_default, is_forced) VALUES (?, 2, 'subrip', 'en', 0, 0)", (r1,))

    # 4. Match candidates
    cur = conn.execute("INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, candidate_year, candidate_payload_json, score, status, created_at) VALUES (?, 'tmdb_movie', '550', 'Inception', 2010, '{\"id\": 550}', 95.0, 'SELECTED', ?)", (mv1, now_iso))
    mc1 = cur.lastrowid
    cur = conn.execute("INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, candidate_year, candidate_payload_json, score, status, created_at) VALUES (?, 'tmdb_movie', '999', 'Other Movie', 2010, '{}', 70.0, 'PENDING', ?)", (mv3, now_iso))
    mc2 = cur.lastrowid

    # 5. Provider snapshots & Presentations
    cur = conn.execute("INSERT INTO provider_snapshots (external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at) VALUES (?, 'movie_details', 'fr-FR', '{\"id\": 550}', ?, ?, ?)", (eid1, now_iso, now_iso, now_iso))
    ps1 = cur.lastrowid
    cur = conn.execute("INSERT INTO work_presentations (work_id, locale, source_snapshot_id, display_title, display_original_title, created_at, updated_at) VALUES (?, 'fr-FR', ?, 'Inception', 'Inception', ?, ?)", (wid1, ps1, now_iso, now_iso))
    wp1 = cur.lastrowid

    conn.commit()
    conn.close()

    # Perform migration
    media_db.initialize(db_path)

    with closing(media_db.connect(db_path)) as conn:
        assert media_db.get_schema_version(conn) == 4
        # Verify schema_info history
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_info ORDER BY version").fetchall()]
        assert versions == [3, 4]

        # Integrity check & foreign key check
        integrity = conn.execute("PRAGMA integrity_check").fetchall()
        assert integrity == [("ok",)]
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_errors) == 0

        # Verify historical rows remain intact
        assert conn.execute("SELECT title FROM works WHERE id=?", (wid1,)).fetchone()[0] == "Inception"
        assert conn.execute("SELECT external_id FROM external_ids WHERE id=?", (eid1,)).fetchone()[0] == "550"
        assert conn.execute("SELECT identification_state FROM media_versions WHERE id=?", (mv1,)).fetchone()[0] == "AUTO_MATCHED"
        assert conn.execute("SELECT identification_state FROM media_versions WHERE id=?", (mv2,)).fetchone()[0] == "USER_MATCHED"
        assert conn.execute("SELECT identification_state FROM media_versions WHERE id=?", (mv3,)).fetchone()[0] == "UNMATCHED"
        assert conn.execute("SELECT codec FROM video_streams WHERE resource_id=?", (r1,)).fetchone()[0] == "h264"
        assert conn.execute("SELECT candidate_title FROM match_candidates WHERE id=?", (mc1,)).fetchone()[0] == "Inception"
        assert conn.execute("SELECT candidate_title FROM match_candidates WHERE id=?", (mc2,)).fetchone()[0] == "Other Movie"
        assert conn.execute("SELECT display_title FROM work_presentations WHERE id=?", (wp1,)).fetchone()[0] == "Inception"

        # LEGACY_QUERY_SIGNATURE_BACKFILL = NOT_PROVABLE: table is created empty
        search_count = conn.execute("SELECT COUNT(*) FROM media_version_searches").fetchone()[0]
        assert search_count == 0


# ─── SECTION 3: DETERMINISTIC QUERY SIGNATURES ───────────────────────────────

def test_query_signature_determinism():
    """Query signature is deterministic and normalizes whitespace and casing."""
    sig1 = media_db.compute_query_signature(
        provider="tmdb_movie",
        media_type="movie",
        locale="fr-FR",
        title="The Matrix",
        year=1999,
    )
    sig2 = media_db.compute_query_signature(
        provider="tmdb_movie",
        media_type="movie",
        locale="fr-FR",
        title="  the   matrix  ",
        year=1999,
    )
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA-256 64-hex chars


def test_query_signature_variance():
    """Signature changes when title, year, locale, provider, or media_type changes."""
    base = media_db.compute_query_signature("tmdb_movie", "movie", "fr-FR", "Inception", 2010)

    # Year variation
    assert base != media_db.compute_query_signature("tmdb_movie", "movie", "fr-FR", "Inception", 2011)
    assert base != media_db.compute_query_signature("tmdb_movie", "movie", "fr-FR", "Inception", None)

    # Locale variation
    assert base != media_db.compute_query_signature("tmdb_movie", "movie", "en-US", "Inception", 2010)

    # Provider variation
    assert base != media_db.compute_query_signature("other_provider", "movie", "fr-FR", "Inception", 2010)

    # Media type variation
    assert base != media_db.compute_query_signature("tmdb_movie", "tv", "fr-FR", "Inception", 2010)

    # Title variation
    assert base != media_db.compute_query_signature("tmdb_movie", "movie", "fr-FR", "Avatar", 2010)


# ─── SECTION 4: FOREIGN KEY CASCADE ──────────────────────────────────────────

def test_foreign_key_cascade_on_media_version_delete(env: SearchStateTestEnv):
    """Deleting a media_version row cascades to delete its media_version_searches rows."""
    mv_id = env.add_media("Inception (2010).mkv")
    env.add_search_state(mv_id, query_title="Inception", query_year=2010, search_status="CANDIDATES")

    with closing(env.connect()) as conn:
        state = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert state is not None
        assert state["search_status"] == "CANDIDATES"

        # Delete the media_version row
        conn.execute("DELETE FROM media_versions WHERE id = ?", (mv_id,))
        conn.commit()

        # Cascade check
        state_after = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert state_after is None
        count = conn.execute("SELECT COUNT(*) FROM media_version_searches WHERE media_version_id = ?", (mv_id,)).fetchone()[0]
        assert count == 0


# ─── SECTION 5: UNIQUE CONSTRAINT AND UPSERT ─────────────────────────────────

def test_upsert_media_version_search(env: SearchStateTestEnv):
    """Upsert updates existing (media_version_id, provider) row without creating duplicate."""
    mv_id = env.add_media("Inception (2010).mkv")

    # First insert: FAILED
    env.add_search_state(
        mv_id,
        query_title="Inception",
        query_year=2010,
        search_status="FAILED",
        failure_reason="PROVIDER_TIMEOUT",
    )

    with closing(env.connect()) as conn:
        state = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert state is not None
        assert state["search_status"] == "FAILED"
        assert state["failure_reason"] == "PROVIDER_TIMEOUT"
        count = conn.execute("SELECT COUNT(*) FROM media_version_searches WHERE media_version_id = ?", (mv_id,)).fetchone()[0]
        assert count == 1

    # Second upsert: transitioned to CANDIDATES
    env.add_search_state(
        mv_id,
        query_title="Inception",
        query_year=2010,
        search_status="CANDIDATES",
        failure_reason=None,
    )

    with closing(env.connect()) as conn:
        state = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert state is not None
        assert state["search_status"] == "CANDIDATES"
        assert state["failure_reason"] is None
        count = conn.execute("SELECT COUNT(*) FROM media_version_searches WHERE media_version_id = ?", (mv_id,)).fetchone()[0]
        assert count == 1


# ─── SECTION 6: SEARCH STATUS VALIDATION ─────────────────────────────────────

def test_search_status_validation(env: SearchStateTestEnv):
    """Invalid search_status values raise ValueError."""
    mv_id = env.add_media("Inception (2010).mkv")
    sig = media_db.compute_query_signature("tmdb_movie", "movie", "fr-FR", "Inception", 2010)

    with closing(env.connect()) as conn:
        # Permitted statuses work
        for valid_status in ("CANDIDATES", "NO_RESULT", "FAILED"):
            media_db.upsert_media_version_search(
                conn,
                media_version_id=mv_id,
                provider="tmdb_movie",
                query_title="Inception",
                query_year=2010,
                query_locale="fr-FR",
                query_media_type="movie",
                query_signature=sig,
                search_status=valid_status,
            )
            conn.commit()
            row = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
            assert row["search_status"] == valid_status

        # Invalid statuses fail
        for invalid_status in ("PENDING", "SUCCESS", "ERROR", "UNKNOWN", "", None):
            with pytest.raises(ValueError):
                media_db.upsert_media_version_search(
                    conn,
                    media_version_id=mv_id,
                    provider="tmdb_movie",
                    query_title="Inception",
                    query_year=2010,
                    query_locale="fr-FR",
                    query_media_type="movie",
                    query_signature=sig,
                    search_status=invalid_status,  # type: ignore
                )


# ─── SECTION 7: QUERY CHANGE INVALIDATION ────────────────────────────────────

def test_query_change_invalidates_durable_search_state(env: SearchStateTestEnv):
    """When query clues change (e.g. year added), signature changes and search re-executes."""
    # Run 1: Item without year clue -> NO_RESULT
    mv_id = env.add_media("Dark Knight.mkv")
    opener1 = MockOpener({
        "search/movie?query=Dark+Knight": {"results": []},
    })
    res1 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener1)
    assert res1["searched"] == 1
    assert res1["no_result"] == 1

    with closing(env.connect()) as conn:
        st1 = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st1["search_status"] == "NO_RESULT"
        assert st1["query_year"] is None
        old_sig = st1["query_signature"]

    # In between runs, the file is renamed or updated with year 2008
    with closing(env.connect()) as conn:
        conn.execute("UPDATE resources SET relative_path = 'Dark Knight (2008).mkv' WHERE media_version_id = ?", (mv_id,))
        conn.commit()

    # Plan mode reports QUERY_CHANGED
    plan_res = media_enrich.run_batch_enrichment(source_id=env.source_id, plan=True, db_path=env.db_path, home=env.home)
    assert plan_res["items"][0]["search_eligibility"] == "QUERY_CHANGED"

    # Run 2: Enrichment detects query change and searches again
    opener2 = MockOpener({
        "search/movie?query=Dark+Knight": _default_search_handler(155, "Dark Knight", 2008),
        "movie/155": _default_details_handler(155, "Dark Knight", 2008),
    })
    res2 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener2)
    assert res2["searched"] == 1
    assert res2["auto_matched"] == 1

    with closing(env.connect()) as conn:
        st2 = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st2["search_status"] == "CANDIDATES"
        assert st2["query_year"] == 2008
        assert st2["query_signature"] != old_sig


# ─── SECTION 8: PROVIDER FAILURE RECORDING AND RETRY ─────────────────────────

def test_failure_recording_and_retry(env: SearchStateTestEnv):
    """Transient provider failures record FAILED and are automatically retried on next enrich."""
    mv_id = env.add_media("Inception (2010).mkv")

    # Run 1: Provider returns HTTP 500
    opener1 = MockOpener({
        "search/movie": urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None),
    })
    res1 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener1)
    assert res1["provider_failed"] == 1

    with closing(env.connect()) as conn:
        st1 = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st1 is not None
        assert st1["search_status"] == "FAILED"
        assert st1["failure_reason"] == "PROVIDER_HTTP_ERROR"

    # Plan mode indicates FAILED_RETRY
    plan = media_enrich.run_batch_enrichment(source_id=env.source_id, plan=True, db_path=env.db_path, home=env.home)
    assert plan["items"][0]["search_eligibility"] == "FAILED_RETRY"

    # Run 2: Provider is back up -> search succeeds and transitions
    opener2 = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res2 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener2)
    assert res2["searched"] == 1
    assert res2["auto_matched"] == 1

    with closing(env.connect()) as conn:
        st2 = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st2["search_status"] == "CANDIDATES"
        assert st2["failure_reason"] is None


# ─── SECTION 9: REFRESH CANDIDATES FAILURE PRESERVES EXISTING CANDIDATES ─────

def test_refresh_failure_preserves_candidates(env: SearchStateTestEnv):
    """When explicit refresh fails, existing match_candidates are preserved and status becomes FAILED."""
    mv_id = env.add_media("Inception.mkv")
    now_iso = datetime.now(timezone.utc).isoformat()
    with closing(env.connect()) as conn:
        conn.execute(
            """
            INSERT INTO match_candidates (
                media_version_id, provider, external_id, candidate_title,
                candidate_year, score, status, created_at
            ) VALUES (?, 'tmdb_movie', '550', 'Inception', 2010, 75.0, 'PENDING', ?)
            """,
            (mv_id, now_iso),
        )
        conn.commit()
    env.add_search_state(mv_id, query_title="Inception", search_status="CANDIDATES")

    # Run refresh with failing provider
    opener = MockOpener({
        "search/movie": urllib.error.HTTPError("url", 429, "Rate Limit", {}, None),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        refresh_candidates=True,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["provider_failed"] == 1

    with closing(env.connect()) as conn:
        # Existing candidate was NOT deleted
        cands = conn.execute("SELECT candidate_title, status FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert len(cands) == 1
        assert cands[0][0] == "Inception"
        assert cands[0][1] == "PENDING"

        # Search status is updated to FAILED
        st = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st["search_status"] == "FAILED"
        assert st["failure_reason"] == "PROVIDER_RATE_LIMITED"


# ─── SECTION 10: REFRESH NO_RESULT REMOVES STALE CANDIDATES ──────────────────

def test_refresh_no_result_deletes_pending_candidates(env: SearchStateTestEnv):
    """When refresh returns NO_RESULT, stale PENDING candidates are deleted and status is NO_RESULT."""
    mv_id = env.add_media("Inception.mkv")
    now_iso = datetime.now(timezone.utc).isoformat()
    with closing(env.connect()) as conn:
        conn.execute(
            """
            INSERT INTO match_candidates (
                media_version_id, provider, external_id, candidate_title,
                candidate_year, score, status, created_at
            ) VALUES (?, 'tmdb_movie', '550', 'Inception', 2010, 75.0, 'PENDING', ?)
            """,
            (mv_id, now_iso),
        )
        conn.commit()
    env.add_search_state(mv_id, query_title="Inception", search_status="CANDIDATES")

    # Run refresh where provider returns empty results
    opener = MockOpener({
        "search/movie": {"results": []},
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        refresh_candidates=True,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["no_result"] == 1

    with closing(env.connect()) as conn:
        # Stale PENDING candidate was deleted
        cands = conn.execute("SELECT * FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert len(cands) == 0

        # Search status is now NO_RESULT
        st = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st["search_status"] == "NO_RESULT"


# ─── SECTION 11: FULL NETWORK IDEMPOTENCE SCENARIO ───────────────────────────

def test_full_library_network_idempotence_scenario(env: SearchStateTestEnv):
    """Library with 500 matched, 15 candidates, 10 no-result, 2 failed, 1 never-searched.

    First run executes exactly 3 searches.
    Repeat run executes exactly 0 searches, 0 details, 0 artwork requests.
    """
    opener_map: dict[str, Any] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. 500 AUTO_MATCHED items
    with closing(env.connect()) as conn:
        for i in range(500):
            cur = conn.execute(
                "INSERT INTO works (work_type, title, original_title, year, created_at, updated_at) VALUES ('MOVIE', ?, ?, 2000, ?, ?)",
                (f"Matched Film {i}", f"Matched Film {i}", now_iso, now_iso),
            )
            wid = cur.lastrowid
            conn.execute(
                "INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', ?, ?)",
                (wid, str(10000 + i), now_iso),
            )
            cur = conn.execute(
                """
                INSERT INTO media_versions (
                    work_id, provisional_title, provisional_year, edition_title,
                    identification_state, match_confidence, match_method, match_locked,
                    duration_seconds, created_at, updated_at
                ) VALUES (?, NULL, NULL, NULL, 'AUTO_MATCHED', 95.0, 'tmdb_direct', 0, 7200.0, ?, ?)
                """,
                (wid, now_iso, now_iso),
            )
            mv_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO resources (
                    media_version_id, source_id, relative_path, canonical_path,
                    availability_status, resource_kind, created_at
                ) VALUES (?, ?, ?, ?, 'AVAILABLE', 'FILE', ?)
                """,
                (mv_id, env.source_id, f"Matched Film {i} (2000).mkv", f"/media/Matched Film {i} (2000).mkv", now_iso),
            )
            conn.execute(
                "INSERT INTO work_presentations (work_id, locale, display_title, created_at, updated_at) VALUES (?, 'fr-FR', ?, ?, ?)",
                (wid, f"Matched Film {i}", now_iso, now_iso),
            )
        conn.commit()

    # 2. 15 UNMATCHED with CANDIDATES
    for i in range(15):
        mv_c = env.add_media(f"Candidates Movie {i}.mkv")
        with closing(env.connect()) as conn:
            conn.execute(
                "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) VALUES (?, 'tmdb_movie', ?, ?, 70.0, 'PENDING', ?)",
                (mv_c, str(20000 + i), f"Candidates Movie {i}", now_iso),
            )
            conn.commit()
        env.add_search_state(mv_c, query_title=f"Candidates Movie {i}", search_status="CANDIDATES")

    # 3. 10 UNMATCHED with NO_RESULT
    for i in range(10):
        mv_nr = env.add_media(f"NoResult Movie {i}.mkv")
        env.add_search_state(mv_nr, query_title=f"NoResult Movie {i}", search_status="NO_RESULT")

    # 4. 2 UNMATCHED with FAILED (to be retried)
    mv_f1 = env.add_media("Failed Movie 1 (2018).mkv")
    env.add_search_state(mv_f1, query_title="Failed Movie 1", query_year=2018, search_status="FAILED", failure_reason="TIMEOUT")
    opener_map["search/movie?query=Failed+Movie+1"] = _default_search_handler(30001, "Failed Movie 1", 2018)
    opener_map["movie/30001"] = _default_details_handler(30001, "Failed Movie 1", 2018)

    mv_f2 = env.add_media("Failed Movie 2 (2019).mkv")
    env.add_search_state(mv_f2, query_title="Failed Movie 2", query_year=2019, search_status="FAILED", failure_reason="HTTP_503")
    opener_map["search/movie?query=Failed+Movie+2"] = _default_search_handler(30002, "Failed Movie 2", 2019)
    opener_map["movie/30002"] = _default_details_handler(30002, "Failed Movie 2", 2019)

    # 5. 1 NEVER_SEARCHED UNMATCHED
    mv_new = env.add_media("NeverSearched Movie (2022).mkv")
    opener_map["search/movie?query=NeverSearched+Movie"] = _default_search_handler(40001, "NeverSearched Movie", 2022)
    opener_map["movie/40001"] = _default_details_handler(40001, "NeverSearched Movie", 2022)

    opener = MockOpener(opener_map)

    # RUN 1
    res1 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res1["ok"] is True
    # Exactly 3 searched: 2 FAILED retried + 1 NEVER_SEARCHED
    assert res1["searched"] == 3
    assert res1["candidates_preserved"] == 15
    assert res1["no_results_preserved"] == 10
    search_requests_run1 = [r for r in opener.requests if "search/movie" in r]
    assert len(search_requests_run1) == 3

    # RUN 2 (repeat immediately)
    opener.requests.clear()
    res2 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res2["ok"] is True
    assert res2["searched"] == 0
    assert len(opener.requests) == 0


# ─── SECTION 12: PROVIDER SCOPING ────────────────────────────────────────────

def test_provider_scoping_independence(env: SearchStateTestEnv):
    """Search state is scoped by provider; status on tmdb_movie does not affect a different provider."""
    mv_id = env.add_media("Inception (2010).mkv")
    env.add_search_state(mv_id, query_title="Inception", query_year=2010, search_status="NO_RESULT", provider="tmdb_movie")

    with closing(env.connect()) as conn:
        tmdb_st = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert tmdb_st is not None
        assert tmdb_st["search_status"] == "NO_RESULT"

        other_st = media_db.get_media_version_search(conn, mv_id, "other_provider")
        assert other_st is None


# ─── SECTION 13: MISSING RESOURCE GATING ─────────────────────────────────────

def test_missing_resource_no_search_or_mutation(env: SearchStateTestEnv):
    """Resource with availability_status='MISSING' is never searched and does not mutate search state."""
    mv_id = env.add_media("Missing (2020).mkv", availability_status="MISSING")
    opener = MockOpener({
        "search/movie": _default_search_handler(999, "Missing", 2020),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["searched"] == 0
    assert res["missing_skipped"] == 1
    assert len(opener.requests) == 0

    with closing(env.connect()) as conn:
        st = media_db.get_media_version_search(conn, mv_id, "tmdb_movie")
        assert st is None
