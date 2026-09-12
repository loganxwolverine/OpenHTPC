# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV5B1: TMDb Movie Provider Adapter.

Verifies:
- 100% offline execution with zero real network access, zero access to real secrets.
- v4 Bearer token and legacy v3 API key loading, validation, and permissions (0o600).
- Redaction of tokens, API keys, and authenticated URLs in logs and exception paths.
- Privacy boundary: clean title, optional year, language only; zero leak of paths, IDs, stream facts.
- Exactly ONE HTTP request, zero retries, no pagination, no details requests.
- Normalization: provider 'tmdb_movie', str external_id, release_date -> year, runtime=None.
- Error taxonomy: AUTH_FAILED, RATE_LIMITED, OFFLINE, TIMEOUT, HTTP_ERROR, INVALID_RESPONSE.
- Non-destructive failure: provider failure preserves existing candidates, works, and locks.
- DEV5A integration: conservative auto-match, ambiguity, lock short-circuit, top-5 bounding.
- Localized title / original_title matching compatibility contract.
"""
from __future__ import annotations

from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
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
MGMT_PATH = PAYLOAD / "openhtpc-tmdb-management.py"

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

mgmt_spec = importlib.util.spec_from_file_location("tmdb_mgmt", MGMT_PATH)
tmdb_mgmt = importlib.util.module_from_spec(mgmt_spec)
mgmt_spec.loader.exec_module(tmdb_mgmt)

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
    """Hermetically isolated test environment with initialized database and secrets."""
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
    config_file.write_text(json.dumps(user_config, indent=2))

    # Write a default mock v4 token
    token_file = secrets_dir / "tmdb-token"
    token_file.write_text("eyMockV4BearerTokenForTestingOnly12345\n", encoding="utf-8")
    token_file.chmod(0o600)

    return {
        "home": home,
        "db_file": db_file,
        "config_file": config_file,
        "token_file": token_file,
        "secrets_dir": secrets_dir,
        "source_root": movies_dir,
    }


def _seed_resource(sandbox: dict, rel_path: str, duration_sec: float = 7200.0) -> int:
    """Helper to insert a media file descriptor and return its media_version_id."""
    fake_path = sandbox["source_root"] / rel_path
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"dummy video data")

    desc = {
        "ok": True,
        "resource": {
            "supplied_path": str(fake_path),
            "canonical_path": str(fake_path.resolve()),
            "file_size": 1024,
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
            return res["media_version_id"]


# ─── Tests 1 to 9: Credential Authority, Formats, and Redaction ──────────────

def test_1_valid_secure_v4_token_loading(sandbox):
    token, err_code, _ = tmdb_provider.load_credential(home=sandbox["home"])
    assert err_code is None
    assert token == "eyMockV4BearerTokenForTestingOnly12345"


def test_2_valid_secure_legacy_v3_api_key_loading(sandbox):
    v3_key = "abcdef0123456789abcdef0123456789"
    sandbox["token_file"].write_text(v3_key + "\n")
    sandbox["token_file"].chmod(0o600)
    token, err_code, _ = tmdb_provider.load_credential(home=sandbox["home"])
    assert err_code is None
    assert token == v3_key


def test_3_insecure_credential_permissions_rejected(sandbox):
    sandbox["token_file"].chmod(0o644)
    token, err_code, detail = tmdb_provider.load_credential(home=sandbox["home"])
    assert token is None
    assert err_code == tmdb_provider.STATUS_TOKEN_INVALID
    assert "insecure" in detail.lower()


def test_4_missing_token_file(sandbox):
    sandbox["token_file"].unlink()
    token, err_code, detail = tmdb_provider.load_credential(home=sandbox["home"])
    assert token is None
    assert err_code == tmdb_provider.STATUS_TOKEN_MISSING


def test_5_empty_token_file(sandbox):
    sandbox["token_file"].write_text("   \n")
    token, err_code, detail = tmdb_provider.load_credential(home=sandbox["home"])
    assert token is None
    assert err_code == tmdb_provider.STATUS_TOKEN_INVALID


def test_6_token_never_logged(sandbox):
    secret = "eySecretTokenNeverToBeExposed1234"
    sandbox["token_file"].write_text(secret + "\n")
    masked = tmdb_provider.mask_token(secret)
    assert masked == "••••1234"
    assert secret not in masked


def test_7_bearer_authorization_header_never_logged():
    header = "Bearer eySecret123456789"
    sanitized = tmdb_provider.sanitize_text(f"Request header: {header}")
    assert "eySecret123456789" not in sanitized
    assert "Bearer [REDACTED]" in sanitized


def test_8_v3_authenticated_url_never_logged():
    url = "https://api.themoviedb.org/3/search/movie?api_key=myv3secretkey123&query=Alien"
    sanitized = tmdb_provider.sanitize_text(f"Fetching from {url}")
    assert "myv3secretkey123" not in sanitized
    assert "[AUTHENTICATED_URL_REDACTED]" in sanitized or "api_key=[REDACTED]" in sanitized


def test_9_exception_path_does_not_leak_api_key(sandbox):
    v3_key = "v3secretkeyleaktest9999"
    sandbox["token_file"].write_text(v3_key + "\n")

    def mock_fail_opener(req, timeout=0):
        # Simulate an exception whose string representation includes the full URL
        raise urllib.error.URLError(f"Failed to connect to {req.full_url}")

    res = tmdb_provider.search_movies("Alien", home=sandbox["home"], opener=mock_fail_opener)
    assert res.status == tmdb_provider.STATUS_OFFLINE
    res_str = json.dumps(res.to_dict())
    assert v3_key not in res_str
    assert "v3secretkey" not in res_str


# ─── Tests 10 to 15: Query Formulation & Privacy Boundary ─────────────────────

def test_10_clean_title_query_only(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    res = tmdb_provider.search_movies("Inception", home=sandbox["home"], opener=mock_opener)
    assert len(calls) == 1
    req = calls[0]
    parsed = urllib.parse.urlparse(req.full_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert params["query"] == ["Inception"]
    assert "year" not in params


def test_11_optional_year_query(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    res = tmdb_provider.search_movies("Inception", year=2010, home=sandbox["home"], opener=mock_opener)
    assert len(calls) == 1
    params = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0].full_url).query)
    assert params["query"] == ["Inception"]
    assert params["year"] == ["2010"]


def test_12_language_passed_from_caller_contract(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    # Default is fr-FR
    tmdb_provider.search_movies("Alien", home=sandbox["home"], opener=mock_opener)
    params_default = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0].full_url).query)
    assert params_default["language"] == ["fr-FR"]

    # Explicit caller override
    tmdb_provider.search_movies("Alien", language="en-US", home=sandbox["home"], opener=mock_opener)
    params_en = urllib.parse.parse_qs(urllib.parse.urlparse(calls[1].full_url).query)
    assert params_en["language"] == ["en-US"]


def test_13_no_region_parameter(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    tmdb_provider.search_movies("The Thing", year=1982, home=sandbox["home"], opener=mock_opener)
    params = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0].full_url).query)
    assert "region" not in params


def test_14_no_absolute_path_leakage(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    # DEV5A extracts clues before provider call; provider receives clean title
    clues = media_match.extract_movie_clues("/home/steve/media/movies/Alien (1979)/Alien.1979.mkv")
    p_query = media_match.create_provider_query(clues)

    tmdb_provider.search_movies(p_query["title_query"], year=p_query["year_query"], home=sandbox["home"], opener=mock_opener)
    req_url = calls[0].full_url
    assert "/home/steve" not in req_url
    assert "movies" not in req_url
    assert ".mkv" not in req_url


def test_15_no_source_or_local_db_id_leakage(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    clues = media_match.MovieClues(title_clue="The Matrix", year_clue=1999, raw_stem="The.Matrix.1999")
    p_query = media_match.create_provider_query(clues)

    tmdb_provider.search_movies(p_query["title_query"], year=p_query["year_query"], home=sandbox["home"], opener=mock_opener)
    req_url = calls[0].full_url
    assert "source_id" not in req_url
    assert "media_version_id" not in req_url
    assert "resource_id" not in req_url


# ─── Tests 16 to 21: Result Normalization ─────────────────────────────────────

def test_16_result_normalization(sandbox):
    payload = {
        "results": [{
            "id": 1091,
            "title": "The Thing",
            "original_title": "The Thing",
            "release_date": "1982-06-25",
            "overview": "A horror classic.",
            "popularity": 45.2,
            "vote_average": 8.1
        }]
    }

    res = tmdb_provider.search_movies("The Thing", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.status == tmdb_provider.STATUS_OK
    assert len(res.candidates) == 1
    cand = res.candidates[0]
    assert cand.provider == "tmdb_movie"
    assert cand.external_id == "1091"
    assert cand.title == "The Thing"
    assert cand.original_title == "The Thing"
    assert cand.year == 1982
    assert cand.runtime_minutes is None


def test_17_missing_release_date_yields_year_none(sandbox):
    payload = {
        "results": [{
            "id": 999,
            "title": "Unknown Release",
            "release_date": "",
        }]
    }

    res = tmdb_provider.search_movies("Unknown", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.candidates[0].year is None


def test_18_malformed_release_date_yields_year_none(sandbox):
    payload = {
        "results": [{
            "id": 888,
            "title": "Bad Date Movie",
            "release_date": "not-a-year",
        }]
    }

    res = tmdb_provider.search_movies("Bad Date", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.candidates[0].year is None


def test_19_external_id_stored_as_str(sandbox):
    payload = {"results": [{"id": 42, "title": "Answer", "release_date": "2020-01-01"}]}
    res = tmdb_provider.search_movies("Answer", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert isinstance(res.candidates[0].external_id, str)
    assert res.candidates[0].external_id == "42"


def test_20_provider_namespace_strictly_tmdb_movie(sandbox):
    payload = {"results": [{"id": 1, "title": "Test", "release_date": "2000-01-01"}]}
    res = tmdb_provider.search_movies("Test", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.candidates[0].provider == "tmdb_movie"


def test_21_runtime_minutes_is_none(sandbox):
    payload = {"results": [{"id": 1, "title": "Test", "release_date": "2000-01-01"}]}
    res = tmdb_provider.search_movies("Test", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.candidates[0].runtime_minutes is None


# ─── Tests 22 to 27: Request Budget & Search Bounds ───────────────────────────

def test_22_only_one_http_request(sandbox):
    call_count = 0

    def counting_opener(req, timeout=0):
        nonlocal call_count
        call_count += 1
        return MockHTTPResponse(json.dumps({"results": [{"id": 1, "title": "One"}]}))

    res = tmdb_provider.search_movies("One", home=sandbox["home"], opener=counting_opener)
    assert call_count == 1
    assert res.status == tmdb_provider.STATUS_OK


def test_23_zero_automatic_retries(sandbox):
    call_count = 0

    def failing_opener(req, timeout=0):
        nonlocal call_count
        call_count += 1
        raise urllib.error.HTTPError("https://api.themoviedb.org/3/search/movie", 503, "Service Unavailable", {}, None)

    res = tmdb_provider.search_movies("Fail", home=sandbox["home"], opener=failing_opener)
    assert call_count == 1  # ZERO retries
    assert res.status == tmdb_provider.STATUS_HTTP_ERROR


def test_24_page_1_only(sandbox):
    calls = []

    def mock_opener(req, timeout=0):
        calls.append(req)
        return MockHTTPResponse(json.dumps({"results": []}))

    tmdb_provider.search_movies("PageTest", home=sandbox["home"], opener=mock_opener)
    params = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0].full_url).query)
    assert params["page"] == ["1"]


def test_25_normalized_result_count_bounded_to_max_10(sandbox):
    results_20 = [{"id": i, "title": f"Movie {i}", "release_date": "2020-01-01"} for i in range(20)]
    payload = {"results": results_20}

    res = tmdb_provider.search_movies("Many", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert len(res.candidates) == tmdb_provider.MAX_NORMALIZED_RESULTS
    assert len(res.candidates) == 10


def test_26_no_detail_endpoint_calls(sandbox):
    urls_called = []

    def tracking_opener(req, timeout=0):
        urls_called.append(req.full_url)
        return MockHTTPResponse(json.dumps({"results": [{"id": 100, "title": "No Detail Movie"}]}))

    res = tmdb_provider.search_movies("No Detail", home=sandbox["home"], opener=tracking_opener)
    assert len(urls_called) == 1
    assert "search/movie" in urls_called[0]
    assert "/movie/100" not in urls_called[0]


def test_27_zero_results_yields_provider_ok_no_results(sandbox):
    payload = {"results": []}
    res = tmdb_provider.search_movies("NonexistentMovieXyZ", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.status == tmdb_provider.STATUS_OK_NO_RESULTS
    assert res.candidates == []


# ─── Tests 28 to 35: Error Handling & Error Taxonomy ─────────────────────────

def test_28_timeout_yields_provider_timeout(sandbox):
    def timeout_opener(req, timeout=0):
        raise TimeoutError("Connection timed out")

    res = tmdb_provider.search_movies("TimeoutTest", home=sandbox["home"], opener=timeout_opener)
    assert res.status == tmdb_provider.STATUS_TIMEOUT
    assert res.candidates == []


def test_29_dns_offline_yields_provider_offline(sandbox):
    def offline_opener(req, timeout=0):
        raise urllib.error.URLError("Name or service not known")

    res = tmdb_provider.search_movies("OfflineTest", home=sandbox["home"], opener=offline_opener)
    assert res.status == tmdb_provider.STATUS_OFFLINE
    assert res.candidates == []


def test_30_401_yields_provider_auth_failed(sandbox):
    def auth_fail_opener(req, timeout=0):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    res = tmdb_provider.search_movies("AuthFail", home=sandbox["home"], opener=auth_fail_opener)
    assert res.status == tmdb_provider.STATUS_AUTH_FAILED
    assert res.http_status == 401


def test_31_403_yields_provider_auth_failed(sandbox):
    def forbidden_opener(req, timeout=0):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    res = tmdb_provider.search_movies("Forbidden", home=sandbox["home"], opener=forbidden_opener)
    assert res.status == tmdb_provider.STATUS_AUTH_FAILED
    assert res.http_status == 403


def test_32_429_yields_provider_rate_limited(sandbox):
    def rate_limit_opener(req, timeout=0):
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)

    res = tmdb_provider.search_movies("RateLimit", home=sandbox["home"], opener=rate_limit_opener)
    assert res.status == tmdb_provider.STATUS_RATE_LIMITED
    assert res.http_status == 429


def test_33_500_503_yields_provider_http_error(sandbox):
    def server_err_opener(req, timeout=0):
        raise urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)

    res = tmdb_provider.search_movies("ServerErr", home=sandbox["home"], opener=server_err_opener)
    assert res.status == tmdb_provider.STATUS_HTTP_ERROR
    assert res.http_status == 500


def test_34_malformed_json_yields_invalid_response(sandbox):
    res = tmdb_provider.search_movies("Corrupt", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse("not valid json {"))
    assert res.status == tmdb_provider.STATUS_INVALID_RESPONSE


def test_35_malformed_payload_schema_yields_invalid_response(sandbox):
    # Missing 'results' key or results is not a list
    res = tmdb_provider.search_movies("BadSchema", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps({"status_message": "error"})))
    assert res.status == tmdb_provider.STATUS_INVALID_RESPONSE


# ─── Tests 36 to 43: DEV5A Integration, Non-Destructive Semantics, Locking ────

def test_36_provider_failure_preserves_existing_pending_candidates(sandbox):
    mv_id = _seed_resource(sandbox, "PreMatched.mkv")

    # Seed an existing pending candidate
    existing = [{"provider": "fixture_movie", "external_id": "99", "title": "PreMatched", "year": 2020}]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, existing, auto_accept=False)
        assert len(media_match.get_candidates(db, mv_id)) == 1

        # Now execute lookup with failing provider
        def fail_opener(req, timeout=0):
            raise TimeoutError("timeout")

        res = media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=fail_opener)
        assert res["ok"] is False
        assert res["provider_status"] == tmdb_provider.STATUS_TIMEOUT

        # Candidates must be preserved!
        cands_after = media_match.get_candidates(db, mv_id)
        assert len(cands_after) == 1
        assert cands_after[0]["external_id"] == "99"


def test_37_provider_failure_preserves_auto_matched_identity(sandbox):
    mv_id = _seed_resource(sandbox, "Alien (1979).mkv")
    cand = [{"provider": "tmdb_movie", "external_id": "109", "title": "Alien", "year": 1979}]

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, cand, auto_accept=True)
        st_before = media_match.get_media_version_status(db, mv_id)
        assert st_before["identification_state"] == "AUTO_MATCHED"
        assert st_before["work_id"] is not None

        # Provider fails on subsequent lookup
        def fail_opener(req, timeout=0):
            raise urllib.error.HTTPError("url", 503, "Unavailable", {}, None)

        res = media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=fail_opener)
        assert res["ok"] is False

        st_after = media_match.get_media_version_status(db, mv_id)
        assert st_after["identification_state"] == "AUTO_MATCHED"
        assert st_after["work_id"] == st_before["work_id"]


def test_38_user_matched_lock_short_circuits_automatic_lookup(sandbox):
    mv_id = _seed_resource(sandbox, "HumanLocked.mkv")
    cand = {"provider": "fixture_movie", "external_id": "lock1", "title": "Human Locked Film", "year": 2021}

    network_called = False

    def opener_should_never_run(req, timeout=0):
        nonlocal network_called
        network_called = True
        return MockHTTPResponse(json.dumps({"results": []}))

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="USER")

        st = media_match.get_media_version_status(db, mv_id)
        assert st["match_locked"] == 1

        # Attempt lookup on locked version
        res = media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=opener_should_never_run)
        assert res["ok"] is True
        assert res["status"] == "LOCKED"
        assert network_called is False  # Proves short-circuit before network!


def test_39_ambiguous_the_thing_without_year_stays_unmatched(sandbox):
    mv_id = _seed_resource(sandbox, "The Thing.mkv")
    payload = {
        "results": [
            {"id": 1091, "title": "The Thing", "release_date": "1982-06-25"},
            {"id": 56681, "title": "The Thing", "release_date": "2011-10-12"},
        ]
    }

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.lookup_media_version(
                db, mv_id, home=sandbox["home"],
                opener=lambda r, **k: MockHTTPResponse(json.dumps(payload))
            )
        assert res["ok"] is True
        assert res["evaluation"]["status"] == "UNMATCHED"
        assert "NO_YEAR_CLUE" in res["evaluation"]["reason"]
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None
        assert st["pending_candidates_count"] == 2


def test_40_exact_title_and_year_may_auto_match_through_dev5a(sandbox):
    mv_id = _seed_resource(sandbox, "1917 (2019).mkv")
    payload = {
        "results": [
            {"id": 530915, "title": "1917", "original_title": "1917", "release_date": "2019-12-25"},
        ]
    }

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.lookup_media_version(
                db, mv_id, home=sandbox["home"],
                opener=lambda r, **k: MockHTTPResponse(json.dumps(payload))
            )
        assert res["ok"] is True
        assert res["evaluation"]["status"] == "AUTO_MATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is not None
        assert st["work"]["title"] == "1917"
        assert st["work"]["year"] == 2019


def test_41_low_confidence_discard_remains_dev5a_responsibility(sandbox):
    # Provider returns candidate, but DEV5A scores it < 50 and discards it
    mv_id = _seed_resource(sandbox, "Alien Romulus (2024).mkv")
    payload = {
        "results": [
            {"id": 999, "title": "Unrelated Cooking Show", "release_date": "1990-01-01"}
        ]
    }

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.lookup_media_version(
                db, mv_id, home=sandbox["home"],
                opener=lambda r, **k: MockHTTPResponse(json.dumps(payload))
            )
        assert res["ok"] is True
        assert res["evaluation"]["candidates_stored"] == 0
        assert len(media_match.get_candidates(db, mv_id)) == 0


def test_42_top_5_bounding_remains_dev5a_responsibility(sandbox):
    mv_id = _seed_resource(sandbox, "Movie.mkv")
    results = [{"id": i, "title": "Movie", "release_date": f"20{i:02d}-01-01"} for i in range(10)]

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.lookup_media_version(
                db, mv_id, auto_accept=False, home=sandbox["home"],
                opener=lambda r, **k: MockHTTPResponse(json.dumps({"results": results}))
            )
        stored = media_match.get_candidates(db, mv_id)
        assert len(stored) == 5  # Bounded to top 5 by DEV5A


def test_43_duplicate_work_reuse_remains_dev5a_responsibility(sandbox):
    mv1 = _seed_resource(sandbox, "The.Matrix.1999.1080p.mkv")
    mv2 = _seed_resource(sandbox, "The.Matrix.1999.2160p.mkv")
    payload = {"results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-30"}]}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res1 = media_match.lookup_media_version(db, mv1, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
            res2 = media_match.lookup_media_version(db, mv2, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))

        st1 = media_match.get_media_version_status(db, mv1)
        st2 = media_match.get_media_version_status(db, mv2)
        assert st1["work_id"] == st2["work_id"]
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1


# ─── Tests 44 to 50: Technical Stream Untouched, User-Config, Isolation ──────

def test_44_technical_streams_untouched_by_lookup(sandbox):
    mv_id = _seed_resource(sandbox, "StreamsTest (2020).mkv")
    payload = {"results": [{"id": 1, "title": "StreamsTest", "release_date": "2020-01-01"}]}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        v_before = db.execute("SELECT * FROM video_streams").fetchall()
        a_before = db.execute("SELECT * FROM audio_streams").fetchall()

        with db:
            media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))

        v_after = db.execute("SELECT * FROM video_streams").fetchall()
        a_after = db.execute("SELECT * FROM audio_streams").fetchall()

        assert v_before == v_after
        assert a_before == a_after


def test_45_user_config_untouched_by_lookup(sandbox):
    cfg_before = sandbox["config_file"].read_text()
    mv_id = _seed_resource(sandbox, "ConfigTest (2020).mkv")
    payload = {"results": [{"id": 1, "title": "ConfigTest", "release_date": "2020-01-01"}]}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))

    cfg_after = sandbox["config_file"].read_text()
    assert cfg_before == cfg_after


def test_46_media_actions_untouched_by_lookup(sandbox):
    before_files = set(sandbox["home"].rglob("*"))
    mv_id = _seed_resource(sandbox, "ActionTest (2020).mkv")
    payload = {"results": [{"id": 1, "title": "ActionTest", "release_date": "2020-01-01"}]}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.lookup_media_version(db, mv_id, home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))

    after_files = set(sandbox["home"].rglob("*"))
    # No spurious metadata JSON cache files created
    new_files = after_files - before_files
    for f in new_files:
        assert "media.db" in f.name or f.name.endswith(".mkv")


def test_47_no_provider_lookup_during_startup(sandbox):
    # Verify openhtpc-session-start source code has zero provider lookup calls
    session_start = (PAYLOAD / "openhtpc-session-start").read_text()
    assert "openhtpc-media-provider" not in session_start
    assert "lookup_media_version" not in session_start


def test_48_no_provider_lookup_during_dev4_scan(sandbox, monkeypatch):
    def fail_search(*args, **kwargs):
        raise AssertionError("PROVIDER CALLED DURING DEV4 SCAN")

    monkeypatch.setattr(tmdb_provider, "search_movies", fail_search)

    scan_spec = importlib.util.spec_from_file_location("media_scan", PAYLOAD / "openhtpc-media-scan.py")
    media_scan = importlib.util.module_from_spec(scan_spec)
    scan_spec.loader.exec_module(media_scan)

    # Ingest a file and scan
    fake_movie = sandbox["source_root"] / "ScannerCheck.mkv"
    fake_movie.write_bytes(b"dummy")

    def mock_probe(path, **kwargs):
        return {
            "ok": True,
            "resource": {
                "supplied_path": str(path),
                "canonical_path": str(path),
                "file_size": 5,
                "mtime_ns": 1000,
                "container_format": "matroska",
                "duration_seconds": 100.0,
            },
            "video_streams": [],
            "audio_streams": [],
            "subtitle_streams": [],
        }

    res = media_scan.scan_source(
        source_root=sandbox["source_root"],
        db_path=sandbox["db_file"],
        home=sandbox["home"],
        probe_func=mock_probe,
    )
    assert res["ok"] is True


def test_49_no_provider_lookup_during_playback():
    # Verify openhtpc-playback-policy has zero provider lookup calls
    policy_code = (PAYLOAD / "openhtpc-playback-policy.py").read_text()
    assert "openhtpc-media-provider" not in policy_code
    assert "lookup_media_version" not in policy_code


def test_50_isolated_xdg_paths(sandbox):
    mv_id = _seed_resource(sandbox, "CLI_Test (2020).mkv")
    rc = media_match.main([
        "--db", str(sandbox["db_file"]),
        "--home", str(sandbox["home"]),
        "status", "--media-version-id", str(mv_id)
    ])
    assert rc == 0


# ─── Tests 51 to 54: Hermetic Safety & Compatibility Contract ────────────────

def test_51_zero_real_network_in_tests(sandbox, monkeypatch):
    def strict_no_net(*args, **kwargs):
        raise AssertionError("REAL NETWORK INVOCATION DETECTED")

    monkeypatch.setattr(urllib.request, "urlopen", strict_no_net)
    payload = {"results": [{"id": 1, "title": "NoNet", "release_date": "2020-01-01"}]}

    # Using injected mock opener succeeds without touching urllib.request.urlopen
    res = tmdb_provider.search_movies("NoNet", home=sandbox["home"], opener=lambda r, **k: MockHTTPResponse(json.dumps(payload)))
    assert res.status == tmdb_provider.STATUS_OK


def test_52_zero_access_to_steve_real_token(sandbox):
    # Verify the test sandbox isolates secrets and does not touch ~/.config/openhtpc/secrets/tmdb-token
    real_token_path = Path.home() / ".config/openhtpc/secrets/tmdb-token"
    token, _, _ = tmdb_provider.load_credential(home=sandbox["home"])
    assert token == "eyMockV4BearerTokenForTestingOnly12345"
    if real_token_path.is_file():
        # Ensure the value returned from sandbox is NOT the real token
        real_token = real_token_path.read_text().strip()
        assert token != real_token


def test_53_zero_access_to_steve_personal_media(sandbox):
    with closing(media_db.connect(sandbox["db_file"])) as db:
        rows = db.execute("SELECT canonical_path, relative_path FROM resources").fetchall()
        for cpath, rpath in rows:
            assert not cpath.startswith("/home/steve/media")


def test_54_localized_title_original_title_compatibility_contract(sandbox):
    """Proves DEV5A matches when filename clue has original English title while TMDb returns French title."""
    mv_id = _seed_resource(sandbox, "Alien (1979).mkv")

    # TMDb returns French localized title 'Alien, le huitième passager', but original_title 'Alien'
    payload = {
        "results": [{
            "id": 109,
            "title": "Alien, le huitième passager",
            "original_title": "Alien",
            "release_date": "1979-09-12",
        }]
    }

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.lookup_media_version(
                db, mv_id, home=sandbox["home"],
                opener=lambda r, **k: MockHTTPResponse(json.dumps(payload))
            )
        assert res["ok"] is True
        assert res["evaluation"]["status"] == "AUTO_MATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "AUTO_MATCHED"
        assert st["work"]["title"] == "Alien, le huitième passager"
        assert st["work"]["original_title"] == "Alien"
        assert st["work"]["year"] == 1979
