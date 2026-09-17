# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for DEV6C1: Batch Enrichment Orchestrator.

Strict Test Contracts:
  - 100% hermetic offline execution with ZERO real network calls.
  - Fail-closed network guard enforcing REAL_PROVIDER_NETWORK_CALLS = 0.
  - Read-only plan mode contract (mode=ro, 0 DB writes, 0 network, 0 cache writes).
  - Mandatory source scoping (--source-id, --source-root, mismatch rejection, cross-source rejection).
  - Strict conservative auto-matching policy (Title+Year exact, score >= 80, margin >= 20).
  - USER_MATCHED & locked identity immutability.
  - Work reuse by external_id and new Work creation through qualified primitive.
  - Presentation refresh (fr-FR) and reproducible poster cache (w500 JPEG).
  - Idempotent repeated execution and transaction-per-item resumability.
  - Bounded execution controls (--limit N, explicit --media-version-id).
  - Item-local provider failure containment (timeout, 429, no results, HTTP error, malformed).
  - Immutability of resources, video/audio/subtitle streams, and schema_info.
  - ISO resources out-of-scope boundary (DEV6C_ISO_BEHAVIOR = IGNORE_OUT_OF_SCOPE).
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
from typing import Any
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"

# ─── Load Payload Modules ───────────────────────────────────────────────────

def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


media_db = _load_module(PAYLOAD / "openhtpc-media-db.py", "media_db_enrich")
tmdb_provider = _load_module(PAYLOAD / "openhtpc-media-provider-tmdb.py", "tmdb_provider_enrich")
media_match = _load_module(PAYLOAD / "openhtpc-media-match.py", "media_match_enrich")
media_pres = _load_module(PAYLOAD / "openhtpc-media-presentation.py", "media_pres_enrich")
media_art = _load_module(PAYLOAD / "openhtpc-media-artwork.py", "media_art_enrich")
media_enrich = _load_module(PAYLOAD / "openhtpc-media-enrich.py", "media_enrich_prod")

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


# ─── Test Environment Fixture ────────────────────────────────────────────────

class EnrichTestEnv:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.source_root = tmp_path / "media_root"
        self.source_root.mkdir()
        self.source_id = media_enrich.compute_source_id(self.source_root)
        self.db_path = tmp_path / "media.db"

        # Initialize schema 3 database
        media_db.initialize(self.db_path)

        # Write fake TMDb credential so load_credential finds it
        sec_dir = self.home / ".config/openhtpc/secrets"
        sec_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tok_file = sec_dir / "tmdb-token"
        tok_file.write_text("ey_mock_token_dev6c1\n", encoding="utf-8")
        tok_file.chmod(0o600)

    def connect(self, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        return media_db.connect(self.db_path)

    def add_media(
        self,
        relative_path: str,
        *,
        source_id: str | None = None,
        identification_state: str = "UNMATCHED",
        work_id: int | None = None,
        match_locked: int = 0,
        match_confidence: float | None = None,
        match_method: str | None = None,
        resource_kind: str = "FILE",
        availability_status: str = "AVAILABLE",
        duration_seconds: float = 7200.0,
    ) -> int:
        sid = source_id or self.source_id
        now_iso = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO media_versions (
                    work_id, provisional_title, provisional_year, edition_title,
                    identification_state, match_confidence, match_method, match_locked,
                    duration_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    None,
                    None,
                    None,
                    identification_state,
                    match_confidence,
                    match_method,
                    match_locked,
                    duration_seconds,
                    now_iso,
                    now_iso,
                ),
            )
            mv_id = cur.lastrowid
            cur = conn.execute(
                """
                INSERT INTO resources (
                    media_version_id, resource_kind, source_id, relative_path,
                    canonical_path, file_size, mtime_ns, container_format,
                    availability_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mv_id,
                    resource_kind,
                    sid,
                    relative_path,
                    f"/media/{relative_path}",
                    1024000,
                    1700000000,
                    "matroska",
                    availability_status,
                    now_iso,
                ),
            )
            res_id = cur.lastrowid

            # Add sample stream facts
            conn.execute(
                """
                INSERT INTO video_streams (
                    resource_id, stream_index, codec, width, height, duration_seconds
                ) VALUES (?, 0, 'h264', 1920, 1080, ?)
                """,
                (res_id, duration_seconds),
            )
            conn.execute(
                """
                INSERT INTO audio_streams (
                    resource_id, stream_index, codec, channels, language
                ) VALUES (?, 1, 'aac', 6, 'fre')
                """,
                (res_id,),
            )
            conn.commit()
            return mv_id

    def add_work(self, title: str, year: int, tmdb_id: int) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO works (
                    work_type, title, original_title, normalized_title, year, created_at, updated_at
                ) VALUES ('MOVIE', ?, ?, ?, ?, ?, ?)
                """,
                (title, title, title.lower(), year, now_iso, now_iso),
            )
            wid = cur.lastrowid
            conn.execute(
                """
                INSERT INTO external_ids (
                    work_id, provider, external_id, confidence, created_at
                ) VALUES (?, 'tmdb_movie', ?, '100.0', ?)
                """,
                (wid, str(tmdb_id), now_iso),
            )
            conn.commit()
            return wid


@pytest.fixture
def env(tmp_path: Path) -> EnrichTestEnv:
    return EnrichTestEnv(tmp_path)


def _default_search_handler(tmdb_id: int = 550, title: str = "Inception", year: int = 2010):
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", title).lower() or "poster"
    return {
        "results": [
            {
                "id": tmdb_id,
                "title": title,
                "original_title": title,
                "release_date": f"{year}-07-16",
                "overview": f"Overview for {title}",
                "poster_path": f"/{clean}_poster.jpg",
                "backdrop_path": f"/{clean}_backdrop.jpg",
            }
        ]
    }


def _default_details_handler(tmdb_id: int = 550, title: str = "Inception", year: int = 2010):
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", title).lower() or "poster"
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "release_date": f"{year}-07-16",
        "runtime": 148,
        "overview": f"Overview for {title}",
        "poster_path": f"/{clean}_poster.jpg",
        "backdrop_path": f"/{clean}_backdrop.jpg",
        "genres": [{"id": 28, "name": "Action"}],
    }


# ─── TEST GROUPS 1–4: PLAN MODE CONTRACT ─────────────────────────────────────

def test_01_plan_opens_db_read_only(env: EnrichTestEnv):
    """Plan opens DB in read-only mode (mode=ro); writes must fail."""
    env.add_media("Inception (2010).mkv")
    with closing(media_enrich.connect_db(env.db_path, read_only=True)) as ro_conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            ro_conn.execute("INSERT INTO works (work_type, title, created_at, updated_at) VALUES ('MOVIE', 'X', 'now', 'now')")


def test_02_plan_performs_zero_db_write(env: EnrichTestEnv):
    """Plan mode performs exactly 0 database writes."""
    env.add_media("Inception (2010).mkv")
    before_hash = hashlib.sha256(env.db_path.read_bytes()).hexdigest()

    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        plan=True,
        db_path=env.db_path,
        home=env.home,
    )
    assert res["ok"] is True
    assert res["outcome"] == "PLAN_READY"

    after_hash = hashlib.sha256(env.db_path.read_bytes()).hexdigest()
    assert before_hash == after_hash


def test_03_plan_performs_zero_provider_network(env: EnrichTestEnv):
    """Plan mode executes exactly 0 provider network calls."""
    env.add_media("Inception (2010).mkv")
    opener = MockOpener()

    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        plan=True,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert len(opener.requests) == 0


def test_04_plan_performs_zero_artwork_write_or_download(env: EnrichTestEnv):
    """Plan mode makes zero artwork downloads or cache writes."""
    env.add_media("Inception (2010).mkv")
    cache_dir = env.home / ".cache/openhtpc/media/artwork"
    opener = MockOpener()

    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        plan=True,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert not cache_dir.exists() or len(list(cache_dir.rglob("*.*"))) == 0


# ─── TEST GROUPS 5–8: SOURCE SCOPING ─────────────────────────────────────────

def test_05_source_id_scope(env: EnrichTestEnv):
    """Running for source A processes ONLY source A; source B items remain untouched."""
    other_source_id = "1122334455667788"
    mv1 = env.add_media("Inception (2010).mkv", source_id=env.source_id)
    mv2 = env.add_media("Avatar (2009).mkv", source_id=other_source_id)

    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })

    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "AUTO_MATCHED"
        assert s2 == "UNMATCHED"


def test_06_source_root_scope(env: EnrichTestEnv):
    """Specifying --source-root correctly derives canonical source_id."""
    env.add_media("Inception (2010).mkv")
    res = media_enrich.run_batch_enrichment(
        source_root=env.source_root,
        plan=True,
        db_path=env.db_path,
        home=env.home,
    )
    assert res["ok"] is True
    assert res["source_id"] == env.source_id


def test_07_source_id_root_mismatch_rejects(env: EnrichTestEnv):
    """If --source-id and --source-root disagree, fail closed."""
    res = media_enrich.run_batch_enrichment(
        source_id="mismatched_source_id",
        source_root=env.source_root,
        plan=True,
        db_path=env.db_path,
        home=env.home,
    )
    assert res["ok"] is False
    assert res["outcome"] == "REJECTED"
    assert res["error"] == "SOURCE_ID_ROOT_MISMATCH"


def test_08_cross_source_media_version_id_rejects(env: EnrichTestEnv):
    """Requesting an explicit media_version_id belonging to another source must reject."""
    mv_other = env.add_media("Avatar (2009).mkv", source_id="other_source_1234")
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        media_version_ids=[mv_other],
        plan=True,
        db_path=env.db_path,
        home=env.home,
    )
    assert res["ok"] is False
    assert res["outcome"] == "REJECTED"
    assert res["error"] == "CROSS_SOURCE_MEDIA_VERSION_ID"


# ─── TEST GROUPS 9–14: AUTO-MATCHING POLICY ──────────────────────────────────

def test_09_title_and_year_exact_safe_match_auto_accepts(env: EnrichTestEnv):
    """Title+Year exact match with score >= 80 and margin >= 20 auto-accepts."""
    mv_id = env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        row = conn.execute(
            "SELECT identification_state, match_method, match_locked, work_id FROM media_versions WHERE id = ?",
            (mv_id,),
        ).fetchone()
        assert row[0] == "AUTO_MATCHED"
        assert row[1] == "AUTO_TITLE_YEAR_EXACT"
        assert row[2] == 0
        assert row[3] is not None


def test_10_title_only_never_auto_accepts(env: EnrichTestEnv):
    """Section 7: Yearless items — AUTO_ACCEPT is strictly forbidden."""
    mv_id = env.add_media("Inception.mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 0
    assert res["unresolved"] == 1

    with closing(env.connect()) as conn:
        row = conn.execute(
            "SELECT identification_state, work_id FROM media_versions WHERE id = ?",
            (mv_id,),
        ).fetchone()
        assert row[0] == "UNMATCHED"
        assert row[1] is None

        # Candidate suggestions should still be persisted with PENDING status
        cands = conn.execute("SELECT status, candidate_title FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert len(cands) == 1
        assert cands[0][0] == "PENDING"
        assert cands[0][1] == "Inception"


def test_11_score_below_80_remains_unresolved(env: EnrichTestEnv):
    """Candidate with score below 80 remains UNMATCHED."""
    mv_id = env.add_media("Alien (1979).mkv")
    # Low similarity candidate
    opener = MockOpener({
        "search/movie": {
            "results": [
                {
                    "id": 999,
                    "title": "Alien Warfare",
                    "original_title": "Alien Warfare",
                    "release_date": "1979-01-01",
                    "overview": "",
                }
            ]
        }
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 0
    assert res["unresolved"] == 1

    with closing(env.connect()) as conn:
        state = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert state == "UNMATCHED"


def test_12_margin_below_20_remains_unresolved(env: EnrichTestEnv):
    """When top two candidates have margin < 20, auto-match is rejected."""
    mv_id = env.add_media("The Matrix (1999).mkv")
    opener = MockOpener({
        "search/movie": {
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "original_title": "The Matrix",
                    "release_date": "1999-03-30",
                },
                {
                    "id": 604,
                    "title": "The Matrix Revisited",
                    "original_title": "The Matrix Revisited",
                    "release_date": "1999-11-19",
                },
            ]
        }
    })
    # If the scoring logic yields margin < 20, check_auto_match_eligibility rejects
    # Let's test with exact same candidate title and year to ensure margin is 0
    opener.routes["search/movie"] = {
        "results": [
            {"id": 603, "title": "The Matrix", "release_date": "1999-03-30"},
            {"id": 604, "title": "The Matrix", "release_date": "1999-03-30"},
        ]
    }
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 0

    with closing(env.connect()) as conn:
        state = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert state == "UNMATCHED"


def test_13_normalized_title_mismatch_remains_unresolved(env: EnrichTestEnv):
    """Candidate title not exactly matching clue title remains UNMATCHED."""
    mv_id = env.add_media("Inception 2 (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 0

    with closing(env.connect()) as conn:
        state = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert state == "UNMATCHED"


def test_14_year_mismatch_remains_unresolved(env: EnrichTestEnv):
    """Candidate year not matching clue year remains UNMATCHED."""
    mv_id = env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2011),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["auto_matched"] == 0

    with closing(env.connect()) as conn:
        state = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert state == "UNMATCHED"


# ─── TEST GROUPS 15–18: USER_MATCHED & LOCKED SAFETY ─────────────────────────

def test_15_locked_identity_never_changed(env: EnrichTestEnv):
    """match_locked = 1 item is never searched or rematched."""
    wid = env.add_work("Gladiator", 2000, 98)
    mv_id = env.add_media(
        "Gladiator (2000).mkv",
        identification_state="USER_MATCHED",
        work_id=wid,
        match_locked=1,
        match_method="USER_CONFIRMATION",
    )
    opener = MockOpener()
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["searched"] == 0

    with closing(env.connect()) as conn:
        row = conn.execute("SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert row[0] == "USER_MATCHED"
        assert row[1] == 1
        assert row[2] == wid


def test_16_user_matched_never_rematched(env: EnrichTestEnv):
    """USER_MATCHED items are never searched or rematched."""
    wid = env.add_work("Alerte", 1995, 299)
    mv_id = env.add_media(
        "Alerte (1995).mkv",
        identification_state="USER_MATCHED",
        work_id=wid,
        match_locked=0,
        match_method="USER_MANUAL_SEARCH",
    )
    opener = MockOpener()
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["searched"] == 0

    with closing(env.connect()) as conn:
        row = conn.execute("SELECT identification_state, match_method, work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert row[0] == "USER_MATCHED"
        assert row[1] == "USER_MANUAL_SEARCH"
        assert row[2] == wid


def test_17_user_matched_receives_missing_presentation(env: EnrichTestEnv):
    """USER_MATCHED item missing fr-FR presentation receives explicit refresh."""
    wid = env.add_work("Alerte", 1995, 299)
    env.add_media("Alerte (1995).mkv", identification_state="USER_MATCHED", work_id=wid)

    opener = MockOpener({
        "movie/299": _default_details_handler(299, "Alerte !", 1995),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["presentation_refreshed"] == 1

    with closing(env.connect()) as conn:
        pres = conn.execute("SELECT display_title, locale FROM work_presentations WHERE work_id = ?", (wid,)).fetchone()
        assert pres is not None
        assert pres[0] == "Alerte !"
        assert pres[1] == "fr-FR"


def test_18_user_matched_receives_missing_poster(env: EnrichTestEnv):
    """USER_MATCHED item missing local poster receives poster download."""
    wid = env.add_work("Alerte", 1995, 299)
    env.add_media("Alerte (1995).mkv", identification_state="USER_MATCHED", work_id=wid)

    opener = MockOpener({
        "movie/299": _default_details_handler(299, "Alerte !", 1995),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["ok"] is True
    assert res["posters_cached"] == 1

    # Verify cached file exists on disk
    cache_dir = env.home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500"
    files = list(cache_dir.glob("*.jpg"))
    assert len(files) == 1
    assert files[0].read_bytes() == SYNTHETIC_JPEG


# ─── TEST GROUPS 19–22: CANDIDATE PERSISTENCE & WORK REUSE ───────────────────

def test_19_candidate_suggestions_persisted_for_unresolved_item(env: EnrichTestEnv):
    """Candidate suggestions are persisted with status='PENDING' for unresolved item."""
    mv_id = env.add_media("Inception.mkv")  # yearless -> unresolved
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
    })
    media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    with closing(env.connect()) as conn:
        cands = conn.execute("SELECT status, candidate_title FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert len(cands) == 1
        assert cands[0][0] == "PENDING"
        assert cands[0][1] == "Inception"


def test_20_repeat_unresolved_lookup_does_not_create_bad_duplicates(env: EnrichTestEnv):
    """Re-enriching an unresolved item clears previous PENDING candidates and replaces them."""
    mv_id = env.add_media("Inception.mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
    })
    media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)

    with closing(env.connect()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchone()[0]
        assert count == 1  # Exactly 1, no duplicate accumulation


def test_21_work_reuse_by_existing_external_id(env: EnrichTestEnv):
    """When candidate external_id already exists in external_ids, Work row is reused."""
    wid_existing = env.add_work("Inception", 2010, 550)
    mv_id = env.add_media("Inception (2010).mkv")

    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        work_count = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        assert work_count == 1  # No second work created
        assigned_wid = conn.execute("SELECT work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert assigned_wid == wid_existing


def test_22_new_work_creation_through_existing_primitive(env: EnrichTestEnv):
    """When external_id is new, exactly one Work row is created with work_type='MOVIE'."""
    mv_id = env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        works = conn.execute("SELECT id, work_type, title, year FROM works").fetchall()
        assert len(works) == 1
        assert works[0][1] == "MOVIE"
        assert works[0][2] == "Inception"
        assert works[0][3] == 2010


# ─── TEST GROUPS 23–26: PRESENTATION & ARTWORK ───────────────────────────────

def test_23_presentation_fr_fr(env: EnrichTestEnv):
    """Presentation records are persisted with locale='fr-FR'."""
    env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["presentation_refreshed"] == 1

    with closing(env.connect()) as conn:
        locales = [row[0] for row in conn.execute("SELECT locale FROM work_presentations").fetchall()]
        assert locales == ["fr-FR"]


def test_24_presentation_failure_item_local(env: EnrichTestEnv):
    """Presentation failure on movie A does not fail movie B; movie A identity remains intact."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie?query=Inception": _default_search_handler(550, "Inception", 2010),
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/550": urllib.error.HTTPError("url", 500, "Server Error", {}, None),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["outcome"] == "PARTIAL"
    assert res["auto_matched"] == 2
    assert res["presentation_refreshed"] == 1
    assert res["presentation_failed"] == 1

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "AUTO_MATCHED"
        assert s2 == "AUTO_MATCHED"


def test_25_poster_cache_hit_zero_download(env: EnrichTestEnv):
    """When poster is already in cache, zero network request is made for poster."""
    wid = env.add_work("Inception", 2010, 550)
    env.add_media("Inception (2010).mkv", identification_state="USER_MATCHED", work_id=wid)

    # Pre-cache presentation snapshot and poster file
    c_path = media_art.cache_path("/inception_poster.jpg", home=env.home)
    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_bytes(SYNTHETIC_JPEG)

    opener = MockOpener({
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    # First ensure presentation exists
    media_pres.refresh_work_presentation(env.connect(), wid, locale="fr-FR", home=env.home, opener=opener)
    image_reqs_before = [r for r in opener.requests if "image.tmdb.org" in r]
    assert len(image_reqs_before) == 0

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["ok"] is True
    assert res["posters_cache_hit"] == 1
    assert res["posters_cached"] == 0
    image_reqs_after = [r for r in opener.requests if "image.tmdb.org" in r]
    assert len(image_reqs_after) == 0


def test_26_poster_failure_item_local(env: EnrichTestEnv):
    """Poster download failure on movie A is item-local; movie B poster still succeeds."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    def _poster_fail(req):
        if "inception_poster.jpg" in req.full_url:
            raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        return MockHTTPResponse(SYNTHETIC_JPEG)

    opener = MockOpener({
        "search/movie?query=Inception": _default_search_handler(550, "Inception", 2010),
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/550": _default_details_handler(550, "Inception", 2010),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
        "image.tmdb.org": _poster_fail,
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["outcome"] == "PARTIAL"
    assert res["poster_failed"] == 1
    assert res["posters_cached"] == 1

    # Identity and presentations remain valid
    with closing(env.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_presentations").fetchone()[0] == 2


# ─── TEST GROUPS 27–28: IDEMPOTENCE & RESUMABILITY ───────────────────────────

def test_27_idempotent_second_run(env: EnrichTestEnv):
    """Second run makes 0 new works, 0 new presentations, 0 poster downloads."""
    env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res1 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res1["auto_matched"] == 1
    assert res1["presentation_refreshed"] == 1
    assert res1["posters_cached"] == 1

    # Second run
    res2 = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res2["auto_matched"] == 0
    assert res2["presentation_refreshed"] == 0
    assert res2["posters_cached"] == 0
    assert res2["posters_cache_hit"] == 1
    assert res2["already_complete"] == 1

    with closing(env.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM external_ids").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM work_presentations").fetchone()[0] == 1


def test_28_interrupt_and_resume(env: EnrichTestEnv):
    """Simulate interrupt after item 1; second run resumes cleanly without duplicating."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie?query=Inception": _default_search_handler(550, "Inception", 2010),
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/550": _default_details_handler(550, "Inception", 2010),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })

    # Run item 1 explicitly (simulating partial completion before interrupt)
    res1 = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        media_version_ids=[mv1],
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res1["auto_matched"] == 1

    # Second full run resumes
    res2 = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res2["auto_matched"] == 1  # only mv2 was newly auto-matched
    assert res2["already_complete"] == 1  # mv1 was already complete

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "AUTO_MATCHED"
        assert s2 == "AUTO_MATCHED"


# ─── TEST GROUPS 29–30: BOUNDED EXECUTION SEMANTICS ──────────────────────────

def test_29_limit_deterministic(env: EnrichTestEnv):
    """--limit N strictly limits processed media_version items ordered by id ASC."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        limit=1,
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["considered"] == 1
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "AUTO_MATCHED"
        assert s2 == "UNMATCHED"


def test_30_explicit_media_version_id_deterministic(env: EnrichTestEnv):
    """--media-version-id ID processes only specified ID."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie": _default_search_handler(19995, "Avatar", 2009),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })
    res = media_enrich.run_batch_enrichment(
        source_id=env.source_id,
        media_version_ids=[mv2],
        db_path=env.db_path,
        home=env.home,
        opener=opener,
    )
    assert res["considered"] == 1
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "UNMATCHED"
        assert s2 == "AUTO_MATCHED"


# ─── TEST GROUPS 31–34: PROVIDER FAILURES ARE ITEM-LOCAL ─────────────────────

def test_31_provider_timeout_item_local(env: EnrichTestEnv):
    """Provider timeout on item 1 does not prevent item 2 from completing."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie?query=Inception": TimeoutError("Connection timed out"),
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["outcome"] == "PARTIAL"
    assert res["provider_failed"] == 1
    assert res["auto_matched"] == 1

    with closing(env.connect()) as conn:
        s1 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv1,)).fetchone()[0]
        s2 = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv2,)).fetchone()[0]
        assert s1 == "UNMATCHED"
        assert s2 == "AUTO_MATCHED"


def test_32_provider_no_result_item_local(env: EnrichTestEnv):
    """Empty search results on item 1 increments no_result; item 2 succeeds."""
    mv1 = env.add_media("UnknownFilm (2020).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie?query=UnknownFilm": {"results": []},
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["no_result"] == 1
    assert res["auto_matched"] == 1


def test_33_provider_malformed_response_item_local(env: EnrichTestEnv):
    """Malformed provider JSON does not crash orchestrator."""
    mv1 = env.add_media("Inception (2010).mkv")
    mv2 = env.add_media("Avatar (2009).mkv")

    opener = MockOpener({
        "search/movie?query=Inception": b"NOT_JSON{broken",
        "search/movie?query=Avatar": _default_search_handler(19995, "Avatar", 2009),
        "movie/19995": _default_details_handler(19995, "Avatar", 2009),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["outcome"] == "PARTIAL"
    assert res["provider_failed"] == 1
    assert res["auto_matched"] == 1


def test_34_provider_429_behavior_bounded(env: EnrichTestEnv):
    """HTTP 429 rate limiting is handled boundedly without infinite retry."""
    env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": urllib.error.HTTPError("url", 429, "Rate Limited", {}, None),
    })

    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["outcome"] == "PARTIAL"
    assert res["provider_failed"] == 1
    assert len(opener.requests) == 1  # strictly 1 call, zero infinite retry


# ─── TEST GROUPS 35–37: IMMUTABLE TABLES & ISO BOUNDARY ──────────────────────

def test_35_zero_modification_to_resources_and_streams(env: EnrichTestEnv):
    """Enrichment never mutates resources, video_streams, audio_streams, subtitle_streams."""
    env.add_media("Inception (2010).mkv")

    def _table_dump(conn: sqlite3.Connection, table: str) -> list[tuple]:
        return conn.execute(f"SELECT * FROM {table} ORDER BY id ASC").fetchall()

    with closing(env.connect()) as conn:
        res_before = _table_dump(conn, "resources")
        v_before = _table_dump(conn, "video_streams")
        a_before = _table_dump(conn, "audio_streams")
        s_before = _table_dump(conn, "subtitle_streams")

    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["ok"] is True

    with closing(env.connect()) as conn:
        assert _table_dump(conn, "resources") == res_before
        assert _table_dump(conn, "video_streams") == v_before
        assert _table_dump(conn, "audio_streams") == a_before
        assert _table_dump(conn, "subtitle_streams") == s_before


def test_36_iso_remains_out_of_scope(env: EnrichTestEnv):
    """Section 22: ISO resources (resource_kind='ISO') are completely ignored."""
    mv_iso = env.add_media("Disc.iso", resource_kind="ISO")
    mv_file = env.add_media("Inception (2010).mkv", resource_kind="FILE")

    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    res = media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)
    assert res["considered"] == 1
    assert res["items"][0]["media_version_id"] == mv_file

    with closing(env.connect()) as conn:
        iso_state = conn.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_iso,)).fetchone()[0]
        assert iso_state == "UNMATCHED"


def test_37_schema_remains_3(env: EnrichTestEnv):
    """Schema version in schema_info remains strictly 3."""
    env.add_media("Inception (2010).mkv")
    opener = MockOpener({
        "search/movie": _default_search_handler(550, "Inception", 2010),
        "movie/550": _default_details_handler(550, "Inception", 2010),
    })
    media_enrich.run_batch_enrichment(source_id=env.source_id, db_path=env.db_path, home=env.home, opener=opener)

    with closing(env.connect()) as conn:
        ver = conn.execute("SELECT version FROM schema_info").fetchone()[0]
        assert ver == 3


# ─── TEST GROUP 38: CLI ENTRYPOINT ───────────────────────────────────────────

def test_38_cli_main_plan_and_execute(env: EnrichTestEnv, capsys):
    """CLI entrypoint works with --plan and normal execution."""
    env.add_media("Inception (2010).mkv")

    # 1. Plan CLI
    rc_plan = media_enrich.main([
        "--source-id", env.source_id,
        "--plan",
        "--db", str(env.db_path),
        "--home", str(env.home),
    ])
    out_plan = capsys.readouterr().out
    assert rc_plan == 0
    plan_json = json.loads(out_plan)
    assert plan_json["outcome"] == "PLAN_READY"
    assert plan_json["total_media"] == 1
    assert plan_json["title_and_year"] == 1

    # 2. Missing source CLI
    rc_err = media_enrich.main([
        "--plan",
        "--db", str(env.db_path),
        "--home", str(env.home),
    ])
    assert rc_err == 1
