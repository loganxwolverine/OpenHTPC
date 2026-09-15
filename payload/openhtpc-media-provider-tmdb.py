#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""TMDb Movie Provider Adapter for OpenHTPC Media Foundation (DEV5B1).

Performs bounded, privacy-safe movie search candidate retrieval from TMDb.
Supplies candidates only — NEVER owns scoring, thresholds, auto-match, or works creation.

Core Rules:
- MOVIE ONLY: Canonical namespace is strictly 'tmdb_movie'.
- Exactly ONE HTTP GET request per lookup (endpoint /3/search/movie).
- Zero automatic retries: deterministic single bounded attempt.
- Standard library only: urllib.request, urllib.parse, urllib.error, json.
- Secret redaction: Bearer tokens, v3 API keys, and authenticated URLs are NEVER logged.
- Bounded inspection: at most MAX_NORMALIZED_RESULTS (10) candidates normalized.
- Privacy boundary: transmits only clean title, optional reliable year, and language.
- Non-destructive failure: provider error never mutates media.db.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

PROVIDER_NAMESPACE = "tmdb_movie"
DEFAULT_TIMEOUT_SECONDS = 8
MAX_NORMALIZED_RESULTS = 10
DEFAULT_LANGUAGE = "fr-FR"
SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
MOVIE_DETAILS_URL_TEMPLATE = "https://api.themoviedb.org/3/movie/{tmdb_id}"

# Error taxonomy
STATUS_OK = "PROVIDER_OK"
STATUS_OK_NO_RESULTS = "PROVIDER_OK_NO_RESULTS"
STATUS_TOKEN_MISSING = "PROVIDER_TOKEN_MISSING"
STATUS_TOKEN_INVALID = "PROVIDER_TOKEN_INVALID"
STATUS_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
STATUS_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
STATUS_OFFLINE = "PROVIDER_OFFLINE"
STATUS_TIMEOUT = "PROVIDER_TIMEOUT"
STATUS_HTTP_ERROR = "PROVIDER_HTTP_ERROR"
STATUS_INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
STATUS_INVALID_ID = "PROVIDER_INVALID_ID"
STATUS_NOT_FOUND = "PROVIDER_NOT_FOUND"
STATUS_ID_MISMATCH = "PROVIDER_ID_MISMATCH"


def sanitize_text(text: str, token: str | None = None) -> str:
    """Sanitize secret tokens, API keys, and raw authenticated URLs from diagnostics."""
    if not text:
        return ""
    s = str(text)
    if token and token in s:
        s = s.replace(token, "[REDACTED]")
    # Redact query param api_key=<key>
    s = re.sub(r"(api_key=)[^&\s'\"]+", r"\1[REDACTED]", s)
    # Redact Authorization: Bearer <token>
    s = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1[REDACTED]", s, flags=re.IGNORECASE)
    # Redact URLs containing api_key
    s = re.sub(r"https?://\S*api_key=\S*", "[AUTHENTICATED_URL_REDACTED]", s)
    return s


def mask_token(token: str | None) -> str:
    """Mask credential for safe logging: ••••<last4>."""
    if not token or len(token) < 4:
        return ""
    return "••••" + token[-4:]


def load_credential(home: Path | None = None) -> tuple[str | None, str | None, str | None]:
    """Load TMDb credential from secure path.

    Returns:
        (token, error_code, error_detail)
        On success: (token, None, None)
        On failure: (None, error_code, error_detail)
    """
    if "XDG_CONFIG_HOME" in os.environ and not home:
        root = Path(os.environ["XDG_CONFIG_HOME"]) / "openhtpc"
    else:
        base_home = home or Path(os.environ.get("OPENHTPC_HOME", Path.home())).resolve()
        root = base_home / ".config/openhtpc"

    token_path = root / "secrets/tmdb-token"

    try:
        if not token_path.is_file():
            return None, STATUS_TOKEN_MISSING, "TMDb credential not configured (secrets/tmdb-token missing)"
    except OSError as exc:
        return None, STATUS_TOKEN_MISSING, f"Cannot access token file: {exc.args[0]}"

    try:
        mode = token_path.stat().st_mode
        if mode & 0o077:
            return None, STATUS_TOKEN_INVALID, "TMDb credential file has insecure permissions (must be 0600)"
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            return None, STATUS_TOKEN_INVALID, "TMDb credential file is empty"
        return token, None, None
    except OSError as exc:
        return None, STATUS_TOKEN_INVALID, f"Failed to read token file: {exc.args[0]}"


class MovieCandidate:
    __slots__ = ("provider", "external_id", "title", "original_title", "year", "runtime_minutes")

    def __init__(
        self,
        provider: str,
        external_id: str | int,
        title: str,
        original_title: str | None = None,
        year: int | None = None,
        runtime_minutes: int | float | None = None,
    ) -> None:
        self.provider = str(provider).strip()
        self.external_id = str(external_id).strip()
        self.title = str(title).strip()
        self.original_title = str(original_title).strip() if original_title else None
        self.year = int(year) if year is not None else None
        self.runtime_minutes = float(runtime_minutes) if runtime_minutes is not None else None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MovieCandidate:
        return cls(
            provider=data.get("provider", PROVIDER_NAMESPACE),
            external_id=data.get("external_id") or data.get("id", ""),
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=data.get("year"),
            runtime_minutes=data.get("runtime_minutes") or data.get("runtime"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "external_id": self.external_id,
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "runtime_minutes": self.runtime_minutes,
        }


class ProviderResult:
    __slots__ = ("status", "candidates", "error_code", "error_detail", "http_status")

    def __init__(
        self,
        status: str,
        candidates: list[MovieCandidate],
        error_code: str | None = None,
        error_detail: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.status = status
        self.candidates = candidates
        self.error_code = error_code
        self.error_detail = error_detail
        self.http_status = http_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "candidates": [c.to_dict() for c in self.candidates],
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "http_status": self.http_status,
        }


def _normalize_movie_item(item: Any) -> MovieCandidate | None:
    """Convert raw TMDb movie search result item into normalized MovieCandidate."""
    if not isinstance(item, dict):
        return None
    raw_id = item.get("id")
    if raw_id is None:
        return None
    ext_id = str(raw_id).strip()
    if not ext_id:
        return None

    title = str(item.get("title") or "").strip()
    orig_title = str(item.get("original_title") or "").strip() or None

    # Derive year strictly from valid release_date
    rel_date = str(item.get("release_date") or "").strip()
    year: int | None = None
    m = re.match(r"^(\d{4})", rel_date)
    if m:
        try:
            y = int(m.group(1))
            if 1888 <= y <= 2100:
                year = y
        except ValueError:
            year = None

    return MovieCandidate(
        provider=PROVIDER_NAMESPACE,
        external_id=ext_id,
        title=title,
        original_title=orig_title,
        year=year,
        runtime_minutes=None,
    )


def search_movies(
    title: str,
    year: int | None = None,
    language: str = DEFAULT_LANGUAGE,
    home: Path | None = None,
    opener=urllib.request.urlopen,
) -> ProviderResult:
    """Execute bounded TMDb movie search.

    Performs exactly ONE HTTP request, zero retries, no pagination, no details calls.
    """
    clean_title = str(title or "").strip()
    if not clean_title:
        return ProviderResult(
            status=STATUS_OK_NO_RESULTS,
            candidates=[],
            error_code=None,
            error_detail="Empty title query",
        )

    token, err_code, err_detail = load_credential(home=home)
    if not token:
        return ProviderResult(
            status=err_code or STATUS_TOKEN_MISSING,
            candidates=[],
            error_code=err_code,
            error_detail=err_detail,
        )

    is_v4 = token.startswith("ey")

    # Build query parameters — privacy safe
    params = [
        ("query", clean_title),
        ("language", language or DEFAULT_LANGUAGE),
        ("page", "1"),
    ]

    if year is not None:
        try:
            y_int = int(year)
            if 1888 <= y_int <= 2100:
                params.append(("year", str(y_int)))
        except (ValueError, TypeError):
            pass

    if not is_v4:
        params.append(("api_key", token))

    query_str = urllib.parse.urlencode(params)
    full_url = f"{SEARCH_MOVIE_URL}?{query_str}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "OpenHTPC/1.2.0",
    }
    if is_v4:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(full_url, headers=headers)

    try:
        with opener(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw_bytes = response.read()
            http_status = getattr(response, "status", 200)

        payload = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(payload, dict) or "results" not in payload or not isinstance(payload["results"], list):
            return ProviderResult(
                status=STATUS_INVALID_RESPONSE,
                candidates=[],
                error_code=STATUS_INVALID_RESPONSE,
                error_detail="Invalid payload structure from TMDb",
                http_status=http_status,
            )

        raw_results = payload["results"]
        if not raw_results:
            return ProviderResult(
                status=STATUS_OK_NO_RESULTS,
                candidates=[],
                http_status=http_status,
            )

        candidates: list[MovieCandidate] = []
        for item in raw_results[:MAX_NORMALIZED_RESULTS]:
            cand = _normalize_movie_item(item)
            if cand is not None:
                candidates.append(cand)

        if not candidates:
            return ProviderResult(
                status=STATUS_OK_NO_RESULTS,
                candidates=[],
                http_status=http_status,
            )

        return ProviderResult(
            status=STATUS_OK,
            candidates=candidates,
            http_status=http_status,
        )

    except urllib.error.HTTPError as exc:
        code = exc.code
        if code in (401, 403):
            return ProviderResult(
                status=STATUS_AUTH_FAILED,
                candidates=[],
                error_code=STATUS_AUTH_FAILED,
                error_detail=f"HTTP {code} Unauthorized / Forbidden",
                http_status=code,
            )
        elif code == 429:
            return ProviderResult(
                status=STATUS_RATE_LIMITED,
                candidates=[],
                error_code=STATUS_RATE_LIMITED,
                error_detail="HTTP 429 Rate Limited",
                http_status=code,
            )
        else:
            return ProviderResult(
                status=STATUS_HTTP_ERROR,
                candidates=[],
                error_code=STATUS_HTTP_ERROR,
                error_detail=f"HTTP {code}",
                http_status=code,
            )

    except (TimeoutError, socket.timeout):
        return ProviderResult(
            status=STATUS_TIMEOUT,
            candidates=[],
            error_code=STATUS_TIMEOUT,
            error_detail="Connection or read timed out",
        )

    except urllib.error.URLError as exc:
        reason_str = str(exc.reason) if hasattr(exc, "reason") else str(exc)
        if "timed out" in reason_str.lower():
            return ProviderResult(
                status=STATUS_TIMEOUT,
                candidates=[],
                error_code=STATUS_TIMEOUT,
                error_detail="Connection or read timed out",
            )
        clean_reason = sanitize_text(reason_str, token)
        clean_reason = re.sub(r"https?://\S+", "[URL_REDACTED]", clean_reason)
        return ProviderResult(
            status=STATUS_OFFLINE,
            candidates=[],
            error_code=STATUS_OFFLINE,
            error_detail=f"Network unreachable: {clean_reason}",
        )

    except (json.JSONDecodeError, UnicodeDecodeError):
        return ProviderResult(
            status=STATUS_INVALID_RESPONSE,
            candidates=[],
            error_code=STATUS_INVALID_RESPONSE,
            error_detail="Malformed JSON in TMDb response",
        )

    except Exception as exc:
        clean_exc = sanitize_text(str(exc), token)
        clean_exc = re.sub(r"https?://\S+", "[URL_REDACTED]", clean_exc)
        return ProviderResult(
            status=STATUS_OFFLINE,
            candidates=[],
            error_code=STATUS_OFFLINE,
            error_detail=f"Transport failure: {type(exc).__name__}",
        )


def validate_tmdb_id(tmdb_id: Any) -> int | None:
    """Validate TMDb ID: positive integer or digits-only string representing int > 0.

    Rejects None, bool, negative numbers, 0, non-numeric strings, floats.
    """
    if tmdb_id is None or isinstance(tmdb_id, bool):
        return None
    if isinstance(tmdb_id, int):
        return tmdb_id if tmdb_id > 0 else None
    if isinstance(tmdb_id, str):
        s = tmdb_id.strip()
        if s.isdigit():
            val = int(s)
            return val if val > 0 else None
        return None
    return None


def normalize_genre_names(raw_genres: Any) -> list[str]:
    """Extract and normalize genre names from TMDb genres list.

    Extracts name from dicts (e.g. {'id': 16, 'name': 'Animation'}) or strings,
    strips whitespace, discards empty strings, deduplicates preserving order.
    """
    if not isinstance(raw_genres, (list, tuple)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_genres:
        name: str | None = None
        if isinstance(item, dict):
            raw_name = item.get("name")
            if isinstance(raw_name, str):
                name = raw_name
        elif isinstance(item, str):
            name = item
        if name:
            stripped = name.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                result.append(stripped)
    return result


class MovieDetails:
    __slots__ = (
        "external_id",
        "title",
        "original_title",
        "release_date",
        "runtime_minutes",
        "overview",
        "genres",
        "poster_path",
        "backdrop_path",
        "locale",
        "raw_payload",
    )

    def __init__(
        self,
        external_id: str | int,
        title: str,
        original_title: str | None = None,
        release_date: str | None = None,
        runtime_minutes: int | None = None,
        overview: str | None = None,
        genres: list[str] | None = None,
        poster_path: str | None = None,
        backdrop_path: str | None = None,
        locale: str = DEFAULT_LANGUAGE,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        self.external_id = str(external_id).strip()
        self.title = str(title or "").strip()
        self.original_title = str(original_title).strip() if original_title else None
        self.release_date = str(release_date).strip() if release_date else None
        self.runtime_minutes = (
            int(runtime_minutes)
            if runtime_minutes is not None and not isinstance(runtime_minutes, bool)
            else None
        )
        self.overview = str(overview).strip() if overview else None
        self.genres = list(genres) if genres else []
        self.poster_path = str(poster_path).strip() if poster_path else None
        self.backdrop_path = str(backdrop_path).strip() if backdrop_path else None
        self.locale = str(locale or DEFAULT_LANGUAGE).strip()
        self.raw_payload = raw_payload if raw_payload is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "original_title": self.original_title,
            "release_date": self.release_date,
            "runtime_minutes": self.runtime_minutes,
            "overview": self.overview,
            "genres": self.genres,
            "poster_path": self.poster_path,
            "backdrop_path": self.backdrop_path,
            "locale": self.locale,
        }


class MovieDetailsResult:
    __slots__ = ("status", "movie", "error_code", "error_detail", "http_status", "raw_payload")

    def __init__(
        self,
        status: str,
        movie: MovieDetails | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        http_status: int | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.movie = movie
        self.error_code = error_code
        self.error_detail = error_detail
        self.http_status = http_status
        self.raw_payload = raw_payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "movie": self.movie.to_dict() if self.movie else None,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "http_status": self.http_status,
        }


def get_movie_details(
    tmdb_id: int | str,
    language: str = DEFAULT_LANGUAGE,
    home: Path | None = None,
    opener=urllib.request.urlopen,
) -> MovieDetailsResult:
    """Fetch movie details from TMDb by ID.

    Performs exactly ONE HTTP GET request to /3/movie/{tmdb_id}?language={language}.
    Zero retries. Secret redaction applied to diagnostics.
    """
    valid_id = validate_tmdb_id(tmdb_id)
    if valid_id is None:
        return MovieDetailsResult(
            status=STATUS_INVALID_ID,
            movie=None,
            error_code=STATUS_INVALID_ID,
            error_detail=f"Invalid TMDb movie ID: {tmdb_id!r}",
        )

    token, err_code, err_detail = load_credential(home=home)
    if not token:
        return MovieDetailsResult(
            status=err_code or STATUS_TOKEN_MISSING,
            movie=None,
            error_code=err_code,
            error_detail=err_detail,
        )

    is_v4 = token.startswith("ey")
    req_lang = (language or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    params = [("language", req_lang)]
    if not is_v4:
        params.append(("api_key", token))

    query_str = urllib.parse.urlencode(params)
    base_url = MOVIE_DETAILS_URL_TEMPLATE.format(tmdb_id=valid_id)
    full_url = f"{base_url}?{query_str}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "OpenHTPC/1.2.0",
    }
    if is_v4:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(full_url, headers=headers)

    try:
        with opener(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw_bytes = response.read()
            http_status = getattr(response, "status", 200)

        payload = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return MovieDetailsResult(
                status=STATUS_INVALID_RESPONSE,
                movie=None,
                error_code=STATUS_INVALID_RESPONSE,
                error_detail="Invalid payload structure from TMDb: root is not an object",
                http_status=http_status,
            )

        raw_payload_id = payload.get("id")
        payload_id = validate_tmdb_id(raw_payload_id)
        if payload_id is None:
            return MovieDetailsResult(
                status=STATUS_INVALID_RESPONSE,
                movie=None,
                error_code=STATUS_INVALID_RESPONSE,
                error_detail=f"TMDb response missing or invalid 'id': {raw_payload_id!r}",
                http_status=http_status,
                raw_payload=payload,
            )
        if payload_id != valid_id:
            return MovieDetailsResult(
                status=STATUS_ID_MISMATCH,
                movie=None,
                error_code=STATUS_ID_MISMATCH,
                error_detail=f"TMDb response ID mismatch: requested {valid_id}, got {payload_id}",
                http_status=http_status,
                raw_payload=payload,
            )

        movie_id = str(payload_id)
        title = str(payload.get("title") or "").strip()
        orig_title = str(payload.get("original_title") or "").strip() or None
        rel_date = str(payload.get("release_date") or "").strip() or None
        overview = str(payload.get("overview") or "").strip() or None
        poster_path = str(payload.get("poster_path") or "").strip() or None
        backdrop_path = str(payload.get("backdrop_path") or "").strip() or None

        raw_runtime = payload.get("runtime")
        runtime_minutes: int | None = None
        if raw_runtime is not None and not isinstance(raw_runtime, bool):
            try:
                rt = int(raw_runtime)
                if rt >= 0:
                    runtime_minutes = rt
            except (ValueError, TypeError):
                runtime_minutes = None

        genres = normalize_genre_names(payload.get("genres"))

        details = MovieDetails(
            external_id=movie_id,
            title=title,
            original_title=orig_title,
            release_date=rel_date,
            runtime_minutes=runtime_minutes,
            overview=overview,
            genres=genres,
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            locale=req_lang,
            raw_payload=payload,
        )

        return MovieDetailsResult(
            status=STATUS_OK,
            movie=details,
            http_status=http_status,
            raw_payload=payload,
        )

    except urllib.error.HTTPError as exc:
        code = exc.code
        if code == 404:
            return MovieDetailsResult(
                status=STATUS_NOT_FOUND,
                movie=None,
                error_code=STATUS_NOT_FOUND,
                error_detail=f"HTTP 404 Not Found (TMDb movie {valid_id} does not exist)",
                http_status=code,
            )
        elif code in (401, 403):
            return MovieDetailsResult(
                status=STATUS_AUTH_FAILED,
                movie=None,
                error_code=STATUS_AUTH_FAILED,
                error_detail=f"HTTP {code} Unauthorized / Forbidden",
                http_status=code,
            )
        elif code == 429:
            return MovieDetailsResult(
                status=STATUS_RATE_LIMITED,
                movie=None,
                error_code=STATUS_RATE_LIMITED,
                error_detail="HTTP 429 Rate Limited",
                http_status=code,
            )
        else:
            return MovieDetailsResult(
                status=STATUS_HTTP_ERROR,
                movie=None,
                error_code=STATUS_HTTP_ERROR,
                error_detail=f"HTTP {code}",
                http_status=code,
            )

    except (TimeoutError, socket.timeout):
        return MovieDetailsResult(
            status=STATUS_TIMEOUT,
            movie=None,
            error_code=STATUS_TIMEOUT,
            error_detail="Connection or read timed out",
        )

    except urllib.error.URLError as exc:
        reason_str = str(exc.reason) if hasattr(exc, "reason") else str(exc)
        if "timed out" in reason_str.lower():
            return MovieDetailsResult(
                status=STATUS_TIMEOUT,
                movie=None,
                error_code=STATUS_TIMEOUT,
                error_detail="Connection or read timed out",
            )
        clean_reason = sanitize_text(reason_str, token)
        clean_reason = re.sub(r"https?://\S+", "[URL_REDACTED]", clean_reason)
        return MovieDetailsResult(
            status=STATUS_OFFLINE,
            movie=None,
            error_code=STATUS_OFFLINE,
            error_detail=f"Network unreachable: {clean_reason}",
        )

    except (json.JSONDecodeError, UnicodeDecodeError):
        return MovieDetailsResult(
            status=STATUS_INVALID_RESPONSE,
            movie=None,
            error_code=STATUS_INVALID_RESPONSE,
            error_detail="Malformed JSON in TMDb response",
        )

    except Exception as exc:
        clean_exc = sanitize_text(str(exc), token)
        clean_exc = re.sub(r"https?://\S+", "[URL_REDACTED]", clean_exc)
        return MovieDetailsResult(
            status=STATUS_OFFLINE,
            movie=None,
            error_code=STATUS_OFFLINE,
            error_detail=f"Transport failure: {type(exc).__name__}",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenHTPC TMDb Movie Provider Adapter (DEV5B1)")
    subparsers = parser.add_subparsers(dest="action", required=True)

    search_p = subparsers.add_parser("search", help="Search TMDb movies")
    search_p.add_argument("--title", required=True, help="Clean movie title clue")
    search_p.add_argument("--year", type=int, default=None, help="Optional 4-digit release year")
    search_p.add_argument("--language", default=DEFAULT_LANGUAGE, help="Locale / language (default: fr-FR)")
    search_p.add_argument("--home", type=Path, default=None, help="OpenHTPC user home directory")

    details_p = subparsers.add_parser("details", help="Get TMDb movie details")
    details_p.add_argument("--id", "--tmdb-id", dest="tmdb_id", required=True, help="TMDb movie ID (positive integer)")
    details_p.add_argument("--language", default=DEFAULT_LANGUAGE, help="Locale / language (default: fr-FR)")
    details_p.add_argument("--home", type=Path, default=None, help="OpenHTPC user home directory")

    args = parser.parse_args(argv)

    if args.action == "search":
        result = search_movies(
            title=args.title,
            year=args.year,
            language=args.language,
            home=args.home,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status in (STATUS_OK, STATUS_OK_NO_RESULTS) else 1

    if args.action == "details":
        res = get_movie_details(
            tmdb_id=args.tmdb_id,
            language=args.language,
            home=args.home,
        )
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status == STATUS_OK else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
