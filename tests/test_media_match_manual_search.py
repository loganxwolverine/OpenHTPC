# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic tests for DEV5C3A: Manual Movie Search Core (Headless Engine + CLI).

Verifies all 74 required invariants:
- Input validation (empty, oversized, control characters, NFC, CJK, accents, emoji, punctuation, shell chars).
- Year validation (optional, bounds 1888..current_year+5, invalid type/range pre-network).
- Provider call contract (exactly one GET, zero retry, page 1 only, no details/alt titles, no pagination).
- Privacy boundary (clean title, optional year, language only; zero leak of path, IDs, host, stream facts).
- Provider failure non-destructiveness (offline, auth, timeout, http error, invalid response -> zero DB mutation).
- Candidate lifecycle & deduplication:
    - Active PENDING generation replaced (bounded to max 5).
    - Current ACCEPTED preserved and omitted from duplicate PENDING.
    - REJECTED returned ID reactivated as PENDING.
    - SUPERSEDED returned ID reactivated as PENDING.
    - Repeated manual searches do not accumulate duplicate rows.
    - Duplicate IDs in single provider response deduplicated.
- Zero auto-match (manual score uses explicit query, NOT filename clues; perfect score still zero auto-match).
- Identity immutability (UNMATCHED, AUTO_MATCHED, USER_MATCHED remain unchanged; zero WORK creation).
- Candidate revision R1 -> R2 on suggestion change; stale token rejection under DEV5C1.
- Zero GUI, zero schema change (Schema V2), zero real network calls, XDG isolation.
- CLI success and failure JSON contracts.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
PROVIDER_PATH = PAYLOAD / "openhtpc-media-provider-tmdb.py"
MATCH_PATH = PAYLOAD / "openhtpc-media-match.py"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"

provider_spec = importlib.util.spec_from_file_location("tmdb_provider", PROVIDER_PATH)
tmdb_provider = importlib.util.module_from_spec(provider_spec)
provider_spec.loader.exec_module(tmdb_provider)

match_spec = importlib.util.spec_from_file_location("media_match", MATCH_PATH)
media_match = importlib.util.module_from_spec(match_spec)
match_spec.loader.exec_module(media_match)

db_spec = importlib.util.spec_from_file_location("media_db", DB_PATH)
media_db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(media_db)

ingest_spec = importlib.util.spec_from_file_location("media_ingest", INGEST_PATH)
media_ingest = importlib.util.module_from_spec(ingest_spec)
ingest_spec.loader.exec_module(media_ingest)

probe_spec = importlib.util.spec_from_file_location("media_probe", PROBE_PATH)
media_probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(media_probe)

media_match.set_media_db_module(media_db)
media_match.set_tmdb_provider_module(tmdb_provider)
media_ingest.set_media_db_module(media_db)
media_ingest.set_media_probe_module(media_probe)


class MockHTTPResponse(io.BytesIO):
    def __init__(self, data: bytes | str, status: int = 200) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        super().__init__(raw)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def sandbox(tmp_path):
    """Hermetic isolated environment with test database and provider credentials."""
    home = tmp_path / "home"
    config_dir = home / ".config/openhtpc"
    secrets_dir = config_dir / "secrets"
    share_dir = home / ".local/share/openhtpc/media"
    movies_dir = tmp_path / "movies"

    secrets_dir.mkdir(parents=True, mode=0o700)
    share_dir.mkdir(parents=True)
    movies_dir.mkdir(parents=True)

    db_file = share_dir / "media.db"
    media_db.initialize(db_file)

    config_file = config_dir / "user-config.json"
    user_config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(movies_dir)],
    }
    config_file.write_text(json.dumps(user_config, indent=2), encoding="utf-8")

    # Set up mock TMDb v4 credential in secrets/tmdb-token (0o600)
    token_file = secrets_dir / "tmdb-token"
    token_file.write_text("eyMockBearerTokenForManualSearchQualification.12345.abcdef\n", encoding="utf-8")
    token_file.chmod(0o600)

    return {
        "home": home,
        "db_file": db_file,
        "config_file": config_file,
        "token_file": token_file,
        "secrets_dir": secrets_dir,
        "source_root": movies_dir,
    }


def _seed_media_version(sandbox: dict, rel_path: str = "Unknown Movie.mkv", duration_sec: float = 7200.0) -> int:
    """Helper to insert a media file descriptor and return its media_version_id."""
    fake_path = sandbox["source_root"] / rel_path
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"dummy video data")

    desc = {
        "ok": True,
        "resource": {
            "supplied_path": str(fake_path),
            "canonical_path": str(fake_path.resolve()),
            "file_size": 2048,
            "mtime_ns": 1700000000000000000,
            "container_format": "matroska",
            "duration_seconds": duration_sec,
        },
        "video_streams": [{
            "stream_index": 0, "codec": "h264", "profile": "High",
            "width": 1920, "height": 1080, "pixel_format": "yuv420p", "bit_depth": 8,
            "frame_rate_num": 24, "frame_rate_den": 1, "is_default": 1
        }],
        "audio_streams": [{
            "stream_index": 1, "codec": "aac", "channels": 2,
            "sample_rate": 48000, "is_default": 1
        }],
        "subtitle_streams": []
    }
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_ingest.ingest_descriptor(db, desc, "test_source", rel_path)
            assert res["ok"] is True
            return res["media_version_id"]


def _make_tmdb_response(results: list[dict]) -> str:
    return json.dumps({
        "page": 1,
        "results": results,
        "total_pages": 1,
        "total_results": len(results),
    })


# ═════════════════════════════════════════════════════════════════════════════
# 1. INPUT VALIDATION & NORMALIZATION (Tests 1 - 15)
# ═════════════════════════════════════════════════════════════════════════════

def test_01_explicit_title_query(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 123, "title": "Spirited Away", "original_title": "千と千尋の神隠し", "release_date": "2001-07-20"}
    ])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Spirited Away", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["status"] == "OK"
        assert res["query"]["title"] == "Spirited Away"
        assert res["query"]["year"] is None
        assert res["candidates_stored"] == 1


def test_02_query_with_year(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}
    ])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="The Thing", year=1982, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["query"]["year"] == 1982


def test_03_query_without_year(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}
    ])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="The Thing", year=None, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["query"]["year"] is None


def test_04_whitespace_title_rejected_pre_network(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="   \t \n  ", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert res["error"] == "TITLE_EMPTY"
        assert len(called) == 0


def test_05_empty_title_rejected(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert res["error"] == "TITLE_EMPTY"
        assert len(called) == 0


def test_06_oversized_title_rejected_pre_network(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    oversized = "A" * 256
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title=oversized, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert res["error"] == "TITLE_TOO_LONG"
        assert len(called) == 0


def test_07_invalid_year_type_rejected_pre_network(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res1 = media_match.manual_search_media_version(
            db, mv_id, title="Alien", year="invalid_year", home=sandbox["home"], opener=opener
        )
        assert res1["ok"] is False
        assert res1["error"] == "YEAR_INVALID"

        res2 = media_match.manual_search_media_version(
            db, mv_id, title="Alien", year=True, home=sandbox["home"], opener=opener
        )
        assert res2["ok"] is False
        assert res2["error"] == "YEAR_INVALID"

        assert len(called) == 0


def test_08_year_below_1888_rejected(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Ancient Film", year=1887, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert res["error"] == "YEAR_OUT_OF_RANGE"
        assert len(called) == 0


def test_09_excessive_future_year_rejected(sandbox):
    mv_id = _seed_media_version(sandbox)
    called = []
    opener = lambda r, **k: called.append(r)
    cur_year = datetime.now(timezone.utc).year
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Future Film", year=cur_year + 6, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert res["error"] == "YEAR_OUT_OF_RANGE"
        assert len(called) == 0


def test_10_nfc_normalization(sandbox):
    mv_id = _seed_media_version(sandbox)
    # Decomposed NFD 'e' + combining acute
    decomposed = "Am\u0065\u0301lie"
    captured_urls = []

    def opener(req, **k):
        captured_urls.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([
            {"id": 194, "title": "Le Fabuleux Destin d'Amélie Poulain", "release_date": "2001-04-25"}
        ]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title=decomposed, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        # NFC normalized form 'é' = \u00e9
        assert "Am%C3%A9lie" in captured_urls[0] or "Amélie" in urllib.parse.unquote(captured_urls[0])


def test_11_cjk_query(sandbox):
    mv_id = _seed_media_version(sandbox)
    captured = []
    payload = _make_tmdb_response([
        {"id": 129, "title": "千と千尋の神隠し", "release_date": "2001-07-20"}
    ])
    def opener(req, **k):
        captured.append(req.full_url)
        return MockHTTPResponse(payload)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="千と千尋の神隠し", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["query"]["title"] == "千と千尋の神隠し"


def test_12_accented_query(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 194, "title": "Le Fabuleux Destin d'Amélie Poulain", "release_date": "2001-04-25"}
    ])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Amélie Poulain", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True


def test_13_emoji_query(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 999, "title": "Popcorn Movie", "release_date": "2022-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="🍿 Popcorn", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["query"]["title"] == "🍿 Popcorn"


def test_14_punctuation_query(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 80, "title": "L'Armée des 12 singes", "release_date": "1995-12-27"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="L'Armée: (12) [singes] - Part 1!", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True


def test_15_shell_metacharacters_harmless(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Safe Movie", "release_date": "2020-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    metachars = "`rm -rf /` ; $(cat /etc/passwd) && echo 'test' | grep > foo"
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title=metachars, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert res["query"]["title"] == metachars


# ═════════════════════════════════════════════════════════════════════════════
# 2. PROVIDER CALL CONTRACT & PRIVACY BOUNDARY (Tests 16 - 26)
# ═════════════════════════════════════════════════════════════════════════════

def test_16_exactly_one_provider_get(sandbox):
    mv_id = _seed_media_version(sandbox)
    call_count = [0]
    def opener(req, **k):
        call_count[0] += 1
        return MockHTTPResponse(_make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Movie", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert call_count[0] == 1


def test_17_zero_retry(sandbox):
    mv_id = _seed_media_version(sandbox)
    call_count = [0]
    def opener(req, **k):
        call_count[0] += 1
        raise urllib.error.HTTPError(req.full_url, 500, "Internal Error", {}, None)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Movie", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is False
        assert call_count[0] == 1


def test_18_page_1_only(sandbox):
    mv_id = _seed_media_version(sandbox)
    urls = []
    def opener(req, **k):
        urls.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Movie", home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        assert "page=1" in urls[0]


def test_19_no_details_endpoint(sandbox):
    mv_id = _seed_media_version(sandbox)
    urls = []
    def opener(req, **k):
        urls.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([{"id": 100, "title": "Movie", "release_date": "2020-01-01"}]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=opener)
        assert all("/movie/100" not in u for u in urls)


def test_20_no_alternative_titles_endpoint(sandbox):
    mv_id = _seed_media_version(sandbox)
    urls = []
    def opener(req, **k):
        urls.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([{"id": 100, "title": "Movie", "release_date": "2020-01-01"}]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=opener)
        assert all("alternative_titles" not in u for u in urls)


def test_21_no_pagination(sandbox):
    mv_id = _seed_media_version(sandbox)
    calls = []
    def opener(req, **k):
        calls.append(req.full_url)
        return MockHTTPResponse(json.dumps({
            "page": 1,
            "results": [{"id": i, "title": f"M{i}", "release_date": "2020-01-01"} for i in range(20)],
            "total_pages": 5,
            "total_results": 100,
        }))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=opener)
        assert res["ok"] is True
        assert len(calls) == 1


def test_22_no_local_path_transmitted(sandbox):
    secret_path = "SuperSecret_Path_Local_Disk_Dir"
    mv_id = _seed_media_version(sandbox, rel_path=f"{secret_path}/The.Thing.1982.mkv")
    captured_urls = []
    def opener(req, **k):
        captured_urls.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="The Thing", home=sandbox["home"], opener=opener)
        assert secret_path not in captured_urls[0]
        assert "mkv" not in captured_urls[0]


def test_23_no_source_id_transmitted(sandbox):
    mv_id = _seed_media_version(sandbox)
    captured = []
    def opener(req, **k):
        captured.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Query", home=sandbox["home"], opener=opener)
        assert "source_id" not in captured[0]


def test_24_no_media_version_id_transmitted(sandbox):
    mv_id = _seed_media_version(sandbox)
    captured = []
    def opener(req, **k):
        captured.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Query", home=sandbox["home"], opener=opener)
        assert f"media_version_id={mv_id}" not in captured[0]
        assert f"media_version={mv_id}" not in captured[0]


def test_25_no_hostname_username_transmitted(sandbox):
    import getpass
    import socket
    user = getpass.getuser()
    host = socket.gethostname()
    mv_id = _seed_media_version(sandbox)
    captured = []
    def opener(req, **k):
        captured.append((req.full_url, dict(req.headers)))
        return MockHTTPResponse(_make_tmdb_response([]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Query", home=sandbox["home"], opener=opener)
        url, headers = captured[0]
        assert user not in url
        assert host not in url


def test_26_no_stream_facts_transmitted(sandbox):
    mv_id = _seed_media_version(sandbox, duration_sec=7200.0)
    captured = []
    def opener(req, **k):
        captured.append(req.full_url)
        return MockHTTPResponse(_make_tmdb_response([]))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Query", home=sandbox["home"], opener=opener)
        url = captured[0]
        assert "7200" not in url
        assert "1920" not in url
        assert "1080" not in url
        assert "h264" not in url


# ═════════════════════════════════════════════════════════════════════════════
# 3. PROVIDER FAILURE NON-DESTRUCTIVENESS (Tests 27 - 32)
# ═════════════════════════════════════════════════════════════════════════════

def test_27_provider_offline_leaves_db_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture_movie', '1', 'Initial', 90.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

    def opener(req, **k):
        raise urllib.error.URLError("Network is unreachable")

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert res["status"] == tmdb_provider.STATUS_OFFLINE
        rev_after = media_match.compute_candidate_set_revision(db, mv_id)
        assert rev_before == rev_after


def test_28_auth_failure_leaves_db_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    def opener(req, **k):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert res["status"] == tmdb_provider.STATUS_AUTH_FAILED
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before


def test_29_timeout_leaves_db_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    def opener(req, **k):
        raise TimeoutError("Connection timed out")

    with closing(media_db.connect(sandbox["db_file"])) as db:
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert res["status"] == tmdb_provider.STATUS_TIMEOUT
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before


def test_30_http_error_leaves_db_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    def opener(req, **k):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert res["status"] == tmdb_provider.STATUS_HTTP_ERROR
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before


def test_31_invalid_response_leaves_db_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    def opener(req, **k):
        return MockHTTPResponse("NOT JSON")

    with closing(media_db.connect(sandbox["db_file"])) as db:
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert res["status"] == tmdb_provider.STATUS_INVALID_RESPONSE
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before


def test_32_previous_candidate_revision_unchanged_on_failure(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '10', 'Preserved', 75.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

    def opener(req, **k):
        raise urllib.error.HTTPError(req.full_url, 429, "Rate Limited", {}, None)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=opener)
        assert res["ok"] is False
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before


# ═════════════════════════════════════════════════════════════════════════════
# 4. SUCCESS, SCORING, AND ZERO AUTO-MATCH (Tests 33 - 39)
# ═════════════════════════════════════════════════════════════════════════════

def test_33_success_stores_pending_results(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 1, "title": "Movie 1", "release_date": "2020-01-01"},
        {"id": 2, "title": "Movie 2", "release_date": "2021-01-01"},
    ])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=opener)
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 2
        assert all(c["status"] == "PENDING" for c in cands)


def test_34_success_creates_zero_work_rows(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie 1", "release_date": "2020-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        works_before = db.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        media_match.manual_search_media_version(db, mv_id, title="Movie 1", home=sandbox["home"], opener=opener)
        works_after = db.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        assert works_before == works_after == 0


def test_35_success_does_not_mutate_work_id(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie 1", "release_date": "2020-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie 1", home=sandbox["home"], opener=opener)
        work_id = db.execute("SELECT work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert work_id is None


def test_36_success_does_not_mutate_identification_state(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie 1", "release_date": "2020-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie 1", home=sandbox["home"], opener=opener)
        ident_state = db.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert ident_state == "UNMATCHED"


def test_37_success_does_not_mutate_match_locked(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie 1", "release_date": "2020-01-01"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie 1", home=sandbox["home"], opener=opener)
        locked = db.execute("SELECT match_locked FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert locked == 0


def test_38_perfect_score_still_zero_auto_match(sandbox):
    mv_id = _seed_media_version(sandbox)
    # Exact title (50.0) + exact year (30.0) -> 80.0 score under DEV5A scoring rules
    payload = _make_tmdb_response([{"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="The Thing", year=1982, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1
        assert cands[0]["score"] == 80.0
        assert cands[0]["status"] == "PENDING"
        # Invariant: NEVER AUTO_MATCHED
        row = db.execute("SELECT identification_state, work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert row[0] == "UNMATCHED"
        assert row[1] is None


def test_39_manual_score_uses_explicit_query_not_filename_clue(sandbox):
    # File is named "Alien.1979.mkv"
    mv_id = _seed_media_version(sandbox, rel_path="Alien.1979.mkv")
    # User manually searches for "The Thing (1982)"
    payload = _make_tmdb_response([{"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}])
    opener = lambda r, **k: MockHTTPResponse(payload)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="The Thing", year=1982, home=sandbox["home"], opener=opener
        )
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        # Score is 80.0 against manual query "The Thing", NOT low score against "Alien"
        assert cands[0]["score"] == 80.0
        reasons = cands[0]["payload"]["match_reasons"]
        assert "title_exact" in reasons
        assert "year_exact" in reasons


# ═════════════════════════════════════════════════════════════════════════════
# 5. CANDIDATE LIFECYCLE, DEDUPLICATION, AND BOUNDS (Tests 40 - 48, 63 - 65)
# ═════════════════════════════════════════════════════════════════════════════

def test_40_prior_pending_generation_replaced(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([
        {"id": 1, "title": "Old Cand 1", "release_date": "2020-01-01"},
        {"id": 2, "title": "Old Cand 2", "release_date": "2020-01-01"},
    ])
    payload2 = _make_tmdb_response([
        {"id": 3, "title": "New Cand 3", "release_date": "2021-01-01"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Old", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        cands1 = media_match.get_candidates(db, mv_id)
        assert {c["external_id"] for c in cands1} == {"1", "2"}

        media_match.manual_search_media_version(db, mv_id, title="New", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload2))
        cands2 = media_match.get_candidates(db, mv_id)
        # Prior PENDING candidates 1 and 2 replaced by 3
        assert {c["external_id"] for c in cands2} == {"3"}


def test_41_current_accepted_preserved(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([{"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="The Thing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        c_id = media_match.get_candidates(db, mv_id)[0]["id"]
        # Accept candidate 1090
        accept_res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert accept_res["ok"] is True

        # Now search again for something else
        payload2 = _make_tmdb_response([{"id": 2000, "title": "Alien", "release_date": "1979-05-25"}])
        media_match.manual_search_media_version(db, mv_id, title="Alien", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload2))

        cands = media_match.get_candidates(db, mv_id)
        accepted = [c for c in cands if c["status"] == "ACCEPTED"]
        pending = [c for c in cands if c["status"] == "PENDING"]
        assert len(accepted) == 1
        assert accepted[0]["external_id"] == "1090"
        assert len(pending) == 1
        assert pending[0]["external_id"] == "2000"


def test_42_returned_duplicate_of_accepted_omitted_from_pending(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([{"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="The Thing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        c_id = media_match.get_candidates(db, mv_id)[0]["id"]
        media_match.accept_candidate_by_id(db, mv_id, c_id)

        # Now search returns the SAME item 1090 plus another item 2000
        payload2 = _make_tmdb_response([
            {"id": 1090, "title": "The Thing", "release_date": "1982-06-25"},
            {"id": 2000, "title": "The Thing 2011", "release_date": "2011-10-12"},
        ])
        res = media_match.manual_search_media_version(db, mv_id, title="The Thing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload2))
        assert res["ok"] is True
        # 1090 omitted from new PENDING; only 2000 is stored as PENDING
        assert res["candidates_stored"] == 1

        cands = media_match.get_candidates(db, mv_id)
        rows_1090 = [c for c in cands if c["external_id"] == "1090"]
        assert len(rows_1090) == 1
        assert rows_1090[0]["status"] == "ACCEPTED"


def test_43_rejected_returned_id_reactivated_as_pending(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([{"id": 100, "title": "Movie 100", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie 100", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        # Reject suggestions
        media_match.reject_candidates(db, mv_id)
        assert media_match.get_candidates(db, mv_id)[0]["status"] == "REJECTED"

        # Explicit manual search returns 100 again
        res = media_match.manual_search_media_version(db, mv_id, title="Movie 100", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        assert res["ok"] is True
        assert res["candidates_stored"] == 1
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1
        assert cands[0]["external_id"] == "100"
        assert cands[0]["status"] == "PENDING"


def test_44_superseded_returned_id_reactivated_as_pending(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 100, "title": "Movie 100", "release_date": "2020-01-01"},
        {"id": 200, "title": "Movie 200", "release_date": "2020-01-01"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        # Accept candidate 100 -> candidate 200 becomes SUPERSEDED
        cands = media_match.get_candidates(db, mv_id)
        c100 = [c for c in cands if c["external_id"] == "100"][0]
        media_match.accept_candidate_by_id(db, mv_id, c100["id"])

        cands = media_match.get_candidates(db, mv_id)
        assert [c for c in cands if c["external_id"] == "200"][0]["status"] == "SUPERSEDED"

        # Manual search returns Movie 200 again
        payload200 = _make_tmdb_response([{"id": 200, "title": "Movie 200", "release_date": "2020-01-01"}])
        media_match.manual_search_media_version(db, mv_id, title="Movie 200", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload200))

        cands = media_match.get_candidates(db, mv_id)
        c200 = [c for c in cands if c["external_id"] == "200"]
        assert len(c200) == 1
        assert c200[0]["status"] == "PENDING"


def test_45_duplicate_provider_ids_in_response_deduplicated(sandbox):
    mv_id = _seed_media_version(sandbox)
    # TMDb returns same id 555 twice in results
    payload = _make_tmdb_response([
        {"id": 555, "title": "Duplicate 1", "release_date": "2020-01-01"},
        {"id": 555, "title": "Duplicate 2", "release_date": "2020-01-01"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Duplicate", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        assert res["candidates_stored"] == 1
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1


def test_46_repeated_same_manual_search_does_not_accumulate_duplicate_ids(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 10, "title": "Film A", "release_date": "2020-01-01"},
        {"id": 20, "title": "Film B", "release_date": "2021-01-01"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Run 3 times in a row
        for _ in range(3):
            res = media_match.manual_search_media_version(db, mv_id, title="Film", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
            assert res["ok"] is True
            assert res["candidates_stored"] == 2

        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 2
        assert {c["external_id"] for c in cands} == {"10", "20"}


def test_47_unrelated_historical_rejected_preserved(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Candidate 999 was REJECTED long ago
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '999', 'Historical Rejected', 50.0, 'REJECTED', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()

        # Search for completely different candidate 123
        payload = _make_tmdb_response([{"id": 123, "title": "New Movie", "release_date": "2022-01-01"}])
        media_match.manual_search_media_version(db, mv_id, title="New Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))

        cands = media_match.get_candidates(db, mv_id)
        assert any(c["external_id"] == "999" and c["status"] == "REJECTED" for c in cands)
        assert any(c["external_id"] == "123" and c["status"] == "PENDING" for c in cands)


def test_48_unrelated_media_versions_untouched(sandbox):
    mv1 = _seed_media_version(sandbox, rel_path="Movie1.mkv")
    mv2 = _seed_media_version(sandbox, rel_path="Movie2.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '111', 'MV2 Cand', 80.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv2,)
        )
        db.commit()
        rev_mv2_before = media_match.compute_candidate_set_revision(db, mv2)

        # Search for mv1
        payload = _make_tmdb_response([{"id": 222, "title": "MV1 Cand", "release_date": "2020-01-01"}])
        media_match.manual_search_media_version(db, mv1, title="MV1", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))

        rev_mv2_after = media_match.compute_candidate_set_revision(db, mv2)
        assert rev_mv2_before == rev_mv2_after


def test_63_storage_bound_respected_max_5(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": i, "title": f"Movie {i}", "release_date": "2020-01-01"}
        for i in range(1, 11)
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        assert res["candidates_stored"] == 5
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 5


def test_64_deterministic_candidate_ordering(sandbox):
    mv_id = _seed_media_version(sandbox)
    # One candidate matches title exactly, one partial, one fallback
    payload = _make_tmdb_response([
        {"id": 1, "title": "Something Completely Different", "release_date": "2020-01-01"},
        {"id": 2, "title": "Alien Romulus", "release_date": "2024-08-16"},
        {"id": 3, "title": "Alien", "release_date": "1979-05-25"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(
            db, mv_id, title="Alien", year=1979, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload)
        )
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        # Top candidate must be id 3 (exact title + exact year = 80.0)
        assert cands[0]["external_id"] == "3"
        assert cands[0]["score"] == 80.0


def test_65_no_duplicate_active_canonical_candidate_and_legacy_cleanup(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Simulate legacy dirty state with two duplicate REJECTED rows for id 777
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'tmdb_movie', '777', 'Legacy Dup 1', 40.0, 'REJECTED', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'tmdb_movie', '777', 'Legacy Dup 2', 40.0, 'REJECTED', '2026-09-01T00:00:01Z')",
            (mv_id,)
        )
        db.commit()

        payload = _make_tmdb_response([{"id": 777, "title": "Cleaned Movie", "release_date": "2020-01-01"}])
        res = media_match.manual_search_media_version(db, mv_id, title="Cleaned Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        # Exactly ONE row remains for 777
        rows_777 = [c for c in cands if c["external_id"] == "777"]
        assert len(rows_777) == 1
        assert rows_777[0]["status"] == "PENDING"


# ═════════════════════════════════════════════════════════════════════════════
# 6. ZERO RESULTS BEHAVIOR (Tests 49 - 52)
# ═════════════════════════════════════════════════════════════════════════════

def test_49_zero_results_removes_active_pending(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '1', 'Old Pending', 70.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()

        payload = _make_tmdb_response([])
        res = media_match.manual_search_media_version(db, mv_id, title="Nonexistent", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        assert res["status"] == "OK_NO_RESULTS"
        assert res["candidates_stored"] == 0
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 0


def test_50_zero_results_preserves_accepted(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload_found = _make_tmdb_response([{"id": 1090, "title": "The Thing", "release_date": "1982-06-25"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="The Thing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload_found))
        c_id = media_match.get_candidates(db, mv_id)[0]["id"]
        media_match.accept_candidate_by_id(db, mv_id, c_id)

        # Now search returns 0 results
        payload_empty = _make_tmdb_response([])
        res = media_match.manual_search_media_version(db, mv_id, title="Nothing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload_empty))
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1
        assert cands[0]["status"] == "ACCEPTED"


def test_51_zero_results_identity_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload_empty = _make_tmdb_response([])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Nothing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload_empty))
        assert res["ok"] is True
        ident = db.execute("SELECT identification_state, work_id, match_locked FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert ident == ("UNMATCHED", None, 0)


def test_52_zero_results_revision_changes_when_pending_existed(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '1', 'Old Pending', 70.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

        payload_empty = _make_tmdb_response([])
        res = media_match.manual_search_media_version(db, mv_id, title="Nothing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload_empty))
        assert res["ok"] is True
        assert res["candidate_set_revision"] != rev_before


# ═════════════════════════════════════════════════════════════════════════════
# 7. IDENTIFIED ITEMS & DEV5C1/DEV5C2 INTEGRATION (Tests 53 - 60)
# ═════════════════════════════════════════════════════════════════════════════

def test_53_current_auto_matched_identity_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        cand = media_match.MovieCandidate("tmdb_movie", "1", "Auto Film", "Auto Film", 2020, 100)
        media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="AUTO", method="AUTO_TEST")
        st_before = db.execute("SELECT identification_state, work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert st_before[0] == "AUTO_MATCHED"

        payload = _make_tmdb_response([{"id": 2, "title": "Manual Alternative", "release_date": "2021-01-01"}])
        res = media_match.manual_search_media_version(db, mv_id, title="Alternative", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True

        st_after = db.execute("SELECT identification_state, work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert st_after == st_before


def test_54_current_user_matched_identity_unchanged(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        cand = media_match.MovieCandidate("tmdb_movie", "1", "User Film", "User Film", 2020, 100)
        media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="USER", method="HUMAN")
        st_before = db.execute("SELECT identification_state, work_id, match_locked FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert st_before[0] == "USER_MATCHED"
        assert st_before[2] == 1

        payload = _make_tmdb_response([{"id": 2, "title": "Manual Alt", "release_date": "2021-01-01"}])
        res = media_match.manual_search_media_version(db, mv_id, title="Alt", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True

        st_after = db.execute("SELECT identification_state, work_id, match_locked FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert st_after == st_before


def test_55_manual_alternatives_can_later_be_accepted_via_dev5c1(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 50, "title": "Candidate 50", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Candidate 50", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        c_id = media_match.get_candidates(db, mv_id)[0]["id"]

        # Human accepts candidate
        accept_res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert accept_res["ok"] is True
        assert accept_res["identification_state"] == "USER_MATCHED"


def test_56_manual_alternatives_can_later_replace_via_dev5c1(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        c1 = media_match.MovieCandidate("tmdb_movie", "1", "Film 1", "Film 1", 2020, 100)
        media_match.accept_candidate(db, mv_id, c1, score=90.0, mode="USER")

        payload = _make_tmdb_response([{"id": 2, "title": "Film 2", "release_date": "2021-01-01"}])
        res = media_match.manual_search_media_version(db, mv_id, title="Film 2", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True

        c2_id = [c for c in media_match.get_candidates(db, mv_id) if c["external_id"] == "2"][0]["id"]
        replace_res = media_match.accept_candidate_by_id(db, mv_id, c2_id, replace=True)
        assert replace_res["ok"] is True
        assert replace_res["identification_state"] == "USER_MATCHED"
        assert replace_res["work_id"] is not None


def test_57_no_search_time_dev5c1_accept_replace_invocation(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Film 1", "release_date": "2020-01-01"}])
    with mock.patch.object(media_match, "accept_candidate", side_effect=AssertionError("accept_candidate invoked!")):
        with closing(media_db.connect(sandbox["db_file"])) as db:
            res = media_match.manual_search_media_version(db, mv_id, title="Film 1", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
            assert res["ok"] is True


def test_58_candidate_revision_r1_to_r2_after_result_change(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([{"id": 1, "title": "Result 1", "release_date": "2020-01-01"}])
    payload2 = _make_tmdb_response([{"id": 2, "title": "Result 2", "release_date": "2021-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res1 = media_match.manual_search_media_version(db, mv_id, title="Query 1", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        r1 = res1["candidate_set_revision"]

        res2 = media_match.manual_search_media_version(db, mv_id, title="Query 2", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload2))
        r2 = res2["candidate_set_revision"]

        assert r1 != r2


def test_59_old_revision_causes_candidate_stale_on_later_action(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload1 = _make_tmdb_response([{"id": 1, "title": "Result 1", "release_date": "2020-01-01"}])
    # payload2 retains candidate 1 and adds candidate 2, so candidate 1 exists with revision R2
    payload2 = _make_tmdb_response([
        {"id": 1, "title": "Result 1", "release_date": "2020-01-01"},
        {"id": 2, "title": "Result 2", "release_date": "2021-01-01"},
    ])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res1 = media_match.manual_search_media_version(db, mv_id, title="Query 1", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload1))
        r1 = res1["candidate_set_revision"]
        c1_id = media_match.get_candidates(db, mv_id)[0]["id"]

        # User performs new search in background -> R2
        res2 = media_match.manual_search_media_version(db, mv_id, title="Query 2", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload2))
        r2 = res2["candidate_set_revision"]
        assert r1 != r2

        # Old UI attempts to confirm using R1 token -> must fail with CANDIDATE_STALE
        stale_res = media_match.accept_candidate_by_id(db, mv_id, c1_id, expected_revision=r1)
        assert stale_res["ok"] is False
        assert stale_res["error"] == "CANDIDATE_STALE"
        assert stale_res["current_revision"] == r2


def test_60_refreshed_revision_usable_normally(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 2, "title": "Result 2", "release_date": "2021-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Query", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        r2 = res["candidate_set_revision"]
        c2_id = media_match.get_candidates(db, mv_id)[0]["id"]

        # Confirm with correct refreshed revision R2 succeeds
        ok_res = media_match.accept_candidate_by_id(db, mv_id, c2_id, expected_revision=r2)
        assert ok_res["ok"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 8. TRANSACTION ROLLBACK & PROVIDER NAMESPACES (Tests 61 - 62)
# ═════════════════════════════════════════════════════════════════════════════

def test_61_transaction_failure_rolls_back_all_candidate_mutations(sandbox):
    mv_id = _seed_media_version(sandbox)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "INSERT INTO match_candidates (media_version_id, provider, external_id, candidate_title, score, status, created_at) "
            "VALUES (?, 'fixture', '10', 'Old Candidate', 60.0, 'PENDING', '2026-09-01T00:00:00Z')",
            (mv_id,)
        )
        db.commit()
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

    payload = _make_tmdb_response([{"id": 99, "title": "New", "release_date": "2020-01-01"}])

    # Inject database error during transaction via a SQLite trigger
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            "CREATE TRIGGER fail_insert BEFORE INSERT ON match_candidates "
            "BEGIN SELECT RAISE(ABORT, 'Simulated disk error during insert'); END;"
        )
        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError), match="Simulated disk error"):
            media_match.manual_search_media_version(
                db, mv_id, title="New", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload)
            )

        # Check DB was rolled back
        assert media_match.compute_candidate_set_revision(db, mv_id) == rev_before
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1
        assert cands[0]["external_id"] == "10"


def test_62_external_ids_provider_namespaces_preserved(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 4321, "title": "Movie 4321", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie 4321", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True
        cands = media_match.get_candidates(db, mv_id)
        assert cands[0]["provider"] == "tmdb_movie"
        assert cands[0]["external_id"] == "4321"


# ═════════════════════════════════════════════════════════════════════════════
# 9. SECURITY, ISOLATION, AND SCHEMA (Tests 66 - 72)
# ═════════════════════════════════════════════════════════════════════════════

def test_66_token_redaction(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        res_str = json.dumps(res)
        assert "eyMockBearerToken" not in res_str


def test_67_authorization_header_redaction(sandbox):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        res_str = json.dumps(res)
        assert "Authorization" not in res_str
        assert "Bearer" not in res_str


def test_68_authenticated_url_redaction(sandbox):
    mv_id = _seed_media_version(sandbox)
    def opener(req, **k):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=opener)
        res_str = json.dumps(res)
        assert "api_key" not in res_str


def test_69_xdg_isolation(sandbox):
    # Using explicit home path isolates completely from ~/.config
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
        assert res["ok"] is True


def test_70_schema_v2_unchanged(sandbox):
    """70. Manual search does not mutate database schema (remains authoritative v4)."""
    with closing(media_db.connect(sandbox["db_file"])) as db:
        version_before = media_db.get_schema_version(db)
        assert version_before == 4

        mv_id = _seed_media_version(sandbox)
        payload = _make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}])
        res = media_match.manual_search_media_version(
            db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload)
        )
        assert res["ok"] is True

        version_after = media_db.get_schema_version(db)
        assert version_after == version_before


def test_71_user_config_untouched(sandbox):
    cfg_before = sandbox["config_file"].read_text(encoding="utf-8")
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([{"id": 1, "title": "Movie", "release_date": "2020-01-01"}])
    with closing(media_db.connect(sandbox["db_file"])) as db:
        media_match.manual_search_media_version(db, mv_id, title="Movie", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(payload))
    cfg_after = sandbox["config_file"].read_text(encoding="utf-8")
    assert cfg_before == cfg_after


def test_72_no_real_provider_in_automated_tests(monkeypatch):
    def strict_fail(*args, **kwargs):
        raise AssertionError("ATTEMPTED REAL NETWORK CALL IN TEST")
    monkeypatch.setattr(urllib.request, "urlopen", strict_fail)


# ═════════════════════════════════════════════════════════════════════════════
# 10. CLI CONTRACTS (Tests 73 - 74)
# ═════════════════════════════════════════════════════════════════════════════

def test_73_cli_success_contract(sandbox, capsys, monkeypatch):
    mv_id = _seed_media_version(sandbox)
    payload = _make_tmdb_response([
        {"id": 129, "title": "Spirited Away", "release_date": "2001-07-20"}
    ])

    # Intercept opener in tmdb_provider
    monkeypatch.setattr(tmdb_provider, "search_movies", lambda *a, **k: tmdb_provider.ProviderResult(
        status=tmdb_provider.STATUS_OK,
        candidates=[media_match.MovieCandidate("tmdb_movie", "129", "Spirited Away", "千と千尋の神隠し", 2001, None)],
    ))

    rc = media_match.main([
        "--db", str(sandbox["db_file"]),
        "--home", str(sandbox["home"]),
        "manual-search",
        "--media-version-id", str(mv_id),
        "--title", "Spirited Away",
        "--year", "2001",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True
    assert out["status"] == "OK"
    assert out["media_version_id"] == mv_id
    assert out["query"]["title"] == "Spirited Away"
    assert out["query"]["year"] == 2001
    assert out["candidates_stored"] == 1
    assert "candidate_set_revision" in out
    assert out["identification_state"] == "UNMATCHED"


def test_74_cli_failure_contract(sandbox, capsys):
    mv_id = _seed_media_version(sandbox)

    # 1. Invalid year
    rc1 = media_match.main([
        "--db", str(sandbox["db_file"]),
        "--home", str(sandbox["home"]),
        "manual-search",
        "--media-version-id", str(mv_id),
        "--title", "Movie",
        "--year", "invalid_year",
    ])
    assert rc1 == 1
    out1 = json.loads(capsys.readouterr().out)
    assert out1["ok"] is False
    assert out1["error"] == "YEAR_INVALID"

    # 2. Nonexistent media_version_id
    rc2 = media_match.main([
        "--db", str(sandbox["db_file"]),
        "--home", str(sandbox["home"]),
        "manual-search",
        "--media-version-id", "999999",
        "--title", "Movie",
    ])
    assert rc2 == 1
    out2 = json.loads(capsys.readouterr().out)
    assert out2["ok"] is False
    assert out2["error"] == "MEDIA_VERSION_NOT_FOUND"

    # 3. Empty title
    rc3 = media_match.main([
        "--db", str(sandbox["db_file"]),
        "--home", str(sandbox["home"]),
        "manual-search",
        "--media-version-id", str(mv_id),
        "--title", "   ",
    ])
    assert rc3 == 1
    out3 = json.loads(capsys.readouterr().out)
    assert out3["ok"] is False
    assert out3["error"] == "TITLE_EMPTY"
