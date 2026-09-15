# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for DEV6A2: TMDb Movie Details Provider.

Verifies:
- 100% offline execution with zero real network access, zero access to real secrets.
- Strict positive integer TMDb ID validation (zero network calls on invalid ID).
- Single HTTP GET request to /3/movie/{id}?language={locale}.
- Zero automatic retries.
- Headers: Accept: application/json, User-Agent: OpenHTPC/1.2.0, Bearer token (v4) / api_key (v3).
- Strict secret redaction in error reporting.
- Normalization: title, original_title, release_date, runtime_minutes, overview, genres.
- Full Unicode support (French accented characters, Japanese CJK kanji).
- Retains poster_path and backdrop_path without downloading artwork.
- Error taxonomy: 404 (NOT_FOUND), 401/403 (AUTH_FAILED), 429 (RATE_LIMITED), 500 (HTTP_ERROR),
  timeout (TIMEOUT), offline (OFFLINE), malformed JSON (INVALID_RESPONSE).
- Privacy boundary: transmits only movie ID and locale; zero leak of host paths or IDs.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import socket
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
PROVIDER_PATH = PAYLOAD / "openhtpc-media-provider-tmdb.py"

provider_spec = importlib.util.spec_from_file_location("tmdb_provider", PROVIDER_PATH)
tmdb_provider = importlib.util.module_from_spec(provider_spec)
provider_spec.loader.exec_module(tmdb_provider)


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
    """Isolated environment with mock token."""
    home = tmp_path / "home"
    secrets_dir = home / ".config/openhtpc/secrets"
    secrets_dir.mkdir(parents=True, mode=0o700)
    token_file = secrets_dir / "tmdb-token"
    token_file.write_text("eyMockV4BearerTokenForTestingOnly12345\n", encoding="utf-8")
    token_file.chmod(0o600)
    return {
        "home": home,
        "token_file": token_file,
    }


SPIRITED_AWAY_PAYLOAD = {
    "id": 129,
    "title": "Le Voyage de Chihiro",
    "original_title": "千と千尋の神隠し",
    "release_date": "2001-07-20",
    "runtime": 125,
    "overview": "Chihiro, une fillette de 10 ans, pénètre dans un monde enchanté...",
    "genres": [
        {"id": 16, "name": "Animation"},
        {"id": 10751, "name": "Familial"},
        {"id": 14, "name": "Fantastique"},
    ],
    "poster_path": "/393D2e1VvjT37GzWv28uclCGUN8.jpg",
    "backdrop_path": "/mSDsSDwaP3E79ZeUS7nhQMUWdrg.jpg",
}


def test_validate_tmdb_id():
    """Verify strict validation of TMDb movie ID."""
    # Valid positive integers
    assert tmdb_provider.validate_tmdb_id(129) == 129
    assert tmdb_provider.validate_tmdb_id(1) == 1
    assert tmdb_provider.validate_tmdb_id("129") == 129
    assert tmdb_provider.validate_tmdb_id("  129  ") == 129

    # Rejects None, bool, 0, negative, non-numeric strings, float
    assert tmdb_provider.validate_tmdb_id(None) is None
    assert tmdb_provider.validate_tmdb_id(True) is None
    assert tmdb_provider.validate_tmdb_id(False) is None
    assert tmdb_provider.validate_tmdb_id(0) is None
    assert tmdb_provider.validate_tmdb_id(-129) is None
    assert tmdb_provider.validate_tmdb_id("-1") is None
    assert tmdb_provider.validate_tmdb_id("0") is None
    assert tmdb_provider.validate_tmdb_id("abc") is None
    assert tmdb_provider.validate_tmdb_id("129a") is None
    assert tmdb_provider.validate_tmdb_id("") is None
    assert tmdb_provider.validate_tmdb_id(129.5) is None


def test_get_movie_details_invalid_id_zero_network(sandbox):
    """Ensure invalid IDs immediately return STATUS_INVALID_ID with zero network calls."""
    mock_opener = mock.MagicMock()

    for bad_id in [None, True, False, 0, -1, "invalid", "", 129.0]:
        res = tmdb_provider.get_movie_details(
            bad_id,
            home=sandbox["home"],
            opener=mock_opener,
        )
        assert res.status == tmdb_provider.STATUS_INVALID_ID
        assert res.error_code == tmdb_provider.STATUS_INVALID_ID
        assert res.movie is None

    mock_opener.assert_not_called()


def test_get_movie_details_success_v4_bearer(sandbox):
    """Test successful movie details retrieval with v4 Bearer token and exact request shape."""
    requested_urls = []

    def mock_opener(req, timeout=8):
        requested_urls.append(req.full_url)
        assert req.headers["Authorization"] == "Bearer eyMockV4BearerTokenForTestingOnly12345"
        assert req.headers["Accept"] == "application/json"
        assert req.headers["User-agent"] == "OpenHTPC/1.2.0"
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_PAYLOAD))

    res = tmdb_provider.get_movie_details(
        129,
        language="fr-FR",
        home=sandbox["home"],
        opener=mock_opener,
    )

    assert res.status == tmdb_provider.STATUS_OK
    assert res.movie is not None
    assert len(requested_urls) == 1
    assert requested_urls[0] == "https://api.themoviedb.org/3/movie/129?language=fr-FR"

    movie = res.movie
    assert movie.external_id == "129"
    assert movie.title == "Le Voyage de Chihiro"
    assert movie.original_title == "千と千尋の神隠し"
    assert movie.release_date == "2001-07-20"
    assert movie.runtime_minutes == 125
    assert movie.overview.startswith("Chihiro, une fillette")
    assert movie.genres == ["Animation", "Familial", "Fantastique"]
    assert movie.poster_path == "/393D2e1VvjT37GzWv28uclCGUN8.jpg"
    assert movie.backdrop_path == "/mSDsSDwaP3E79ZeUS7nhQMUWdrg.jpg"
    assert movie.locale == "fr-FR"


def test_get_movie_details_success_v3_api_key(sandbox):
    """Test movie details retrieval with legacy v3 API key in query params."""
    sandbox["token_file"].write_text("abcdef0123456789abcdef0123456789\n", encoding="utf-8")

    requested_urls = []

    def mock_opener(req, timeout=8):
        requested_urls.append(req.full_url)
        assert "Authorization" not in req.headers
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_PAYLOAD))

    res = tmdb_provider.get_movie_details(
        "129",
        language="ja-JP",
        home=sandbox["home"],
        opener=mock_opener,
    )

    assert res.status == tmdb_provider.STATUS_OK
    assert len(requested_urls) == 1
    parsed = urllib.parse.urlparse(requested_urls[0])
    assert parsed.path == "/3/movie/129"
    q = urllib.parse.parse_qs(parsed.query)
    assert q["language"] == ["ja-JP"]
    assert q["api_key"] == ["abcdef0123456789abcdef0123456789"]


def test_genre_normalization():
    """Verify genre extraction from TMDb formats, deduplication, stripping, and order preservation."""
    raw = [
        {"id": 16, "name": "Animation"},
        {"id": 10751, "name": "  Familial  "},
        {"id": 14, "name": "Fantastique"},
        {"id": 99, "name": "Animation"},  # duplicate
        {"id": 0, "name": ""},            # empty
        {"id": 1, "name": None},          # non-string
        "Aventure",                        # plain string
        "  Aventure  ",                    # duplicate plain string
    ]
    genres = tmdb_provider.normalize_genre_names(raw)
    assert genres == ["Animation", "Familial", "Fantastique", "Aventure"]

    assert tmdb_provider.normalize_genre_names(None) == []
    assert tmdb_provider.normalize_genre_names([]) == []
    assert tmdb_provider.normalize_genre_names("not a list") == []


def test_zero_retries_on_failure(sandbox):
    """Verify that a network failure is attempted exactly once with zero retries."""
    call_count = 0

    def mock_opener(req, timeout=8):
        nonlocal call_count
        call_count += 1
        raise urllib.error.URLError("Connection refused")

    res = tmdb_provider.get_movie_details(
        129,
        home=sandbox["home"],
        opener=mock_opener,
    )

    assert call_count == 1
    assert res.status == tmdb_provider.STATUS_OFFLINE
    assert res.error_code == tmdb_provider.STATUS_OFFLINE


def test_http_404_not_found(sandbox):
    """Verify HTTP 404 maps to STATUS_NOT_FOUND."""
    def mock_opener(req, timeout=8):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"status_message":"The resource you requested could not be found."}')
        )

    res = tmdb_provider.get_movie_details(99999999, home=sandbox["home"], opener=mock_opener)
    assert res.status == tmdb_provider.STATUS_NOT_FOUND
    assert res.error_code == tmdb_provider.STATUS_NOT_FOUND
    assert res.http_status == 404


def test_http_401_auth_failed(sandbox):
    """Verify HTTP 401 maps to STATUS_AUTH_FAILED."""
    def mock_opener(req, timeout=8):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"status_message":"Invalid API key"}')
        )

    res = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_opener)
    assert res.status == tmdb_provider.STATUS_AUTH_FAILED
    assert res.error_code == tmdb_provider.STATUS_AUTH_FAILED
    assert res.http_status == 401


def test_http_429_rate_limited(sandbox):
    """Verify HTTP 429 maps to STATUS_RATE_LIMITED."""
    def mock_opener(req, timeout=8):
        raise urllib.error.HTTPError(
            req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"status_message":"Your request count (#) is over the allowed limit of (40)."}')
        )

    res = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_opener)
    assert res.status == tmdb_provider.STATUS_RATE_LIMITED
    assert res.error_code == tmdb_provider.STATUS_RATE_LIMITED
    assert res.http_status == 429


def test_http_500_server_error(sandbox):
    """Verify HTTP 500 maps to STATUS_HTTP_ERROR."""
    def mock_opener(req, timeout=8):
        raise urllib.error.HTTPError(
            req.full_url, 500, "Internal Server Error", {}, io.BytesIO(b'Server Error')
        )

    res = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_opener)
    assert res.status == tmdb_provider.STATUS_HTTP_ERROR
    assert res.error_code == tmdb_provider.STATUS_HTTP_ERROR
    assert res.http_status == 500


def test_timeout_error(sandbox):
    """Verify socket/urllib timeout maps to STATUS_TIMEOUT."""
    def mock_opener(req, timeout=8):
        raise socket.timeout("timed out")

    res = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_opener)
    assert res.status == tmdb_provider.STATUS_TIMEOUT
    assert res.error_code == tmdb_provider.STATUS_TIMEOUT


def test_malformed_and_non_dict_json(sandbox):
    """Verify malformed JSON or JSON array payload maps to STATUS_INVALID_RESPONSE."""
    # 1. Malformed JSON
    def mock_malformed(req, timeout=8):
        return MockHTTPResponse(b"not json {")

    res1 = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_malformed)
    assert res1.status == tmdb_provider.STATUS_INVALID_RESPONSE

    # 2. JSON array instead of dict
    def mock_array(req, timeout=8):
        return MockHTTPResponse(b'[{"id": 129}]')

    res2 = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_array)
    assert res2.status == tmdb_provider.STATUS_INVALID_RESPONSE


def test_secret_redaction(sandbox):
    """Verify that tokens and authenticated URLs are never exposed in diagnostics."""
    raw_token = "eySuperSecretToken123456789"
    sandbox["token_file"].write_text(f"{raw_token}\n", encoding="utf-8")

    def mock_opener(req, timeout=8):
        raise urllib.error.URLError(f"Failed to connect using {raw_token} at {req.full_url}")

    res = tmdb_provider.get_movie_details(129, home=sandbox["home"], opener=mock_opener)
    assert raw_token not in res.error_detail
    assert "[REDACTED]" in res.error_detail or "[URL_REDACTED]" in res.error_detail


def test_privacy_boundary(sandbox):
    """Verify only movie ID and locale are transmitted; zero machine or local file info."""
    captured_reqs = []

    def mock_opener(req, timeout=8):
        captured_reqs.append(req)
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_PAYLOAD))

    tmdb_provider.get_movie_details(
        129,
        language="fr-FR",
        home=sandbox["home"],
        opener=mock_opener,
    )

    assert len(captured_reqs) == 1
    req = captured_reqs[0]
    parsed = urllib.parse.urlparse(req.full_url)
    assert parsed.path == "/3/movie/129"
    assert urllib.parse.parse_qs(parsed.query) == {"language": ["fr-FR"]}
    assert "home" not in req.full_url
    assert "openhtpc" not in req.full_url.lower()


def test_artwork_zero_download(sandbox, tmp_path):
    """Verify poster_path and backdrop_path are retained, but no artwork files are created."""
    cache_dir = sandbox["home"] / ".cache/openhtpc"

    def mock_opener(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_PAYLOAD))

    res = tmdb_provider.get_movie_details(
        129,
        home=sandbox["home"],
        opener=mock_opener,
    )

    assert res.status == tmdb_provider.STATUS_OK
    assert res.movie.poster_path == "/393D2e1VvjT37GzWv28uclCGUN8.jpg"
    assert res.movie.backdrop_path == "/mSDsSDwaP3E79ZeUS7nhQMUWdrg.jpg"
    # Ensure cache directory was NOT created
    assert not cache_dir.exists()


def test_cli_details(sandbox):
    """Verify openhtpc-media-provider-tmdb.py details CLI execution."""
    import subprocess
    import sys

    # Missing ID -> returncode 2
    proc = subprocess.run([sys.executable, str(PROVIDER_PATH), "details"], capture_output=True, text=True)
    assert proc.returncode == 2

    # Invalid ID -> returncode 1, error_code = PROVIDER_INVALID_ID
    proc = subprocess.run(
        [sys.executable, str(PROVIDER_PATH), "details", "--id", "invalid", "--home", str(sandbox["home"])],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["error_code"] == "PROVIDER_INVALID_ID"

