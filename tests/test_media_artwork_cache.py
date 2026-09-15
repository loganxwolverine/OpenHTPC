# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic DEV6B1 poster-cache qualification against the production component."""
from __future__ import annotations

from contextlib import closing
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import socket
import urllib.error
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


art = load(ROOT / "payload/openhtpc-media-artwork.py", "media_artwork")
media_db = load(ROOT / "payload/openhtpc-media-db.py", "media_db_artwork")
JPEG = b"\xff\xd8synthetic-jpeg\xff\xd9"
TABLES = ("works", "external_ids", "media_versions", "resources", "video_streams",
          "audio_streams", "subtitle_streams", "match_candidates", "provider_snapshots", "work_presentations")


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, data=JPEG, error=None):
        self.data = data
        self.error = error
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return Response(self.data)


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    db_path = home / ".local/share/openhtpc/media/media.db"
    media_db.initialize(db_path)
    now = "2026-09-01T00:00:00+00:00"
    with closing(media_db.connect(db_path)) as db:
        db.execute("INSERT INTO works VALUES (1,'MOVIE','Fixture','Fixture','fixture',2000,?,?)", (now, now))
        db.execute("INSERT INTO external_ids VALUES (1,1,'tmdb_movie','1091','EXACT',?)", (now,))
        db.execute("INSERT INTO media_versions (id,work_id,identification_state,match_locked,created_at,updated_at) VALUES (1,1,'USER_MATCHED',1,?,?)", (now, now))
        db.execute("INSERT INTO resources (id,media_version_id,resource_kind,created_at) VALUES (1,1,'FILE',?)", (now,))
        db.execute("INSERT INTO match_candidates (id,media_version_id,provider,external_id,candidate_title,score,created_at) VALUES (1,1,'tmdb_movie','1091','Fixture',100,?)", (now,))
        db.execute("INSERT INTO provider_snapshots VALUES (1,1,'MOVIE_DETAILS','fr-FR',?,?,?,?)",
                   (json.dumps({"id": 1091, "poster_path": "/abcDEF_12.jpg"}), now, now, now))
        db.execute("INSERT INTO work_presentations (id,work_id,locale,source_snapshot_id,display_title,created_at,updated_at) VALUES (1,1,'fr-FR',1,'Fixture',?,?)", (now, now))
        db.commit()
    db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    yield home, db
    db.close()


def rows(db):
    return {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in TABLES}


def update_snapshot(env, **changes):
    home, db = env
    db.close()
    path = home / ".local/share/openhtpc/media/media.db"
    with closing(media_db.connect(path)) as writable:
        if "raw" in changes:
            writable.execute("UPDATE provider_snapshots SET payload_json=? WHERE id=1", (changes["raw"],))
        if "source_id" in changes:
            writable.execute("UPDATE work_presentations SET source_snapshot_id=? WHERE id=1", (changes["source_id"],))
        if "provider" in changes:
            writable.execute("UPDATE external_ids SET provider=? WHERE id=1", (changes["provider"],))
        if "kind" in changes:
            writable.execute("UPDATE provider_snapshots SET snapshot_kind=? WHERE id=1", (changes["kind"],))
        writable.commit()
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def test_deterministic_key_and_work_independence(tmp_path):
    a = art.cache_path("/abcDEF_12.jpg", home=tmp_path)
    assert a == art.cache_path("/abcDEF_12.jpg", home=tmp_path)
    assert a != art.cache_path("/other.jpg", home=tmp_path)
    assert a.parent.name == "w500" and a.parent.parent.name == "poster" and a.parent.parent.parent.name == "tmdb_movie"
    assert a.name == art.hashlib.sha256(b"tmdb_movie|poster|w500|/abcDEF_12.jpg").hexdigest() + ".jpg"
    assert "Fixture" not in str(a) and "1091" not in str(a)


def test_resolution_zero_network_and_same_token_for_other_work(env):
    home, db = env
    with patch.object(art.urllib.request, "urlopen", side_effect=AssertionError("network")):
        first = art.resolve_work_poster(db, 1, home=home)
    assert first["status"] == "POSTER_RESOLVED"
    assert first["cache_path"] == art.cache_path("/abcDEF_12.jpg", home=home)
    assert art.cache_path(first["poster_path"], home=home) == first["cache_path"]


def test_cache_miss_hit_privacy_atomic_permissions_and_db_immutable(env):
    home, db = env
    before = rows(db)
    opener = Opener()
    result = art.ensure_work_poster(db, 1, home=home, opener=opener)
    assert result["status"] == "OK_DOWNLOADED"
    assert len(opener.requests) == 1
    request, timeout = opener.requests[0]
    assert request.full_url == "https://image.tmdb.org/t/p/w500/abcDEF_12.jpg"
    assert timeout == 8
    assert request.get_method() == "GET"
    assert "authorization" not in {k.lower() for k in request.headers}
    assert "1091" not in request.full_url and "Fixture" not in request.full_url
    target = result["cache_path"]
    assert target.read_bytes() == JPEG and target.stat().st_mode & 0o777 == 0o600
    assert not list(target.parent.glob(".poster-*"))
    hit = art.ensure_work_poster(db, 1, home=home, opener=Opener(error=AssertionError("network")))
    assert hit["status"] == "OK_CACHE_HIT" and hit["cache_path"] == target
    assert rows(db) == before


def test_cache_deletion_reproduces_identical_path_and_preserves_db(env):
    home, db = env
    before = rows(db)
    first = art.ensure_work_poster(db, 1, home=home, opener=Opener())
    shutil.rmtree(home / ".cache/openhtpc")
    opener = Opener()
    second = art.ensure_work_poster(db, 1, home=home, opener=opener)
    assert second["status"] == "OK_DOWNLOADED"
    assert second["cache_path"] == first["cache_path"]
    assert len(opener.requests) == 1 and rows(db) == before


@pytest.mark.parametrize("token", [None, "", " ", "https://evil/x.jpg", "javascript:bad", "/../x.jpg", "/a/b.jpg", "/abc.jpg?x=1", "/abc\\x.jpg", "//evil.jpg", "/abc.png", "/" + "a" * 129 + ".jpg"], ids=["none", "empty", "space", "url", "scheme", "traversal", "nested", "query", "backslash", "double-slash", "extension", "too-long"])
def test_invalid_tokens_are_rejected_without_network(env, token):
    home, db = env
    raw = json.dumps({"id": 1091, "poster_path": token})
    fresh = update_snapshot(env, raw=raw)
    opener = Opener()
    result = art.ensure_work_poster(fresh, 1, home=home, opener=opener)
    assert result["status"] in ("NO_POSTER", "INVALID_POSTER_PATH")
    assert opener.requests == []
    fresh.close()


@pytest.mark.parametrize("change,status", [
    ({"source_id": None}, "NO_SOURCE_SNAPSHOT"),
    ({"raw": "{"}, "INVALID_SNAPSHOT_JSON"),
    ({"raw": json.dumps({"id": 999, "poster_path": "/abc.jpg"})}, "WRONG_PROVIDER_PROVENANCE"),
    ({"provider": "other"}, "WRONG_PROVIDER_PROVENANCE"),
    ({"kind": "OTHER"}, "WRONG_PROVIDER_PROVENANCE"),
])
def test_missing_or_invalid_provenance(env, change, status):
    home, db = env
    fresh = update_snapshot(env, **change)
    opener = Opener()
    assert art.ensure_work_poster(fresh, 1, home=home, opener=opener)["status"] == status
    assert opener.requests == []
    fresh.close()


def test_missing_presentation_and_snapshot(env):
    home, db = env
    assert art.ensure_work_poster(db, 1, locale="en-US", home=home)["status"] == "NO_PRESENTATION"
    assert art.ensure_work_poster(db, 2, home=home)["status"] == "NO_PRESENTATION"
    fresh = update_snapshot(env, source_id=None)
    assert art.ensure_work_poster(fresh, 1, home=home)["status"] == "NO_SOURCE_SNAPSHOT"
    fresh.close()


@pytest.mark.parametrize("code", [404, 429, 500])
def test_http_errors_one_request_no_partial_file(env, code):
    home, db = env
    error = urllib.error.HTTPError("https://image.tmdb.org", code, "error", {}, None)
    opener = Opener(error=error)
    assert art.ensure_work_poster(db, 1, home=home, opener=opener) == {"status": "HTTP_ERROR", "http_status": code}
    assert len(opener.requests) == 1 and not art.cache_path("/abcDEF_12.jpg", home=home).exists()


@pytest.mark.parametrize("error,status", [
    (socket.timeout(), "TIMEOUT"),
    (urllib.error.URLError("offline"), "OFFLINE"),
    (urllib.error.URLError(socket.timeout()), "TIMEOUT"),
    (RuntimeError("transport failed"), "OFFLINE"),
])
def test_transport_errors_one_request_no_retry(env, error, status):
    home, db = env
    opener = Opener(error=error)
    assert art.ensure_work_poster(db, 1, home=home, opener=opener)["status"] == status
    assert len(opener.requests) == 1 and not art.cache_path("/abcDEF_12.jpg", home=home).exists()


@pytest.mark.parametrize("data", [b"bad", b"\xff\xd8missing-end", b"\xff\xd8" + b"x" * 5_000_000 + b"\xff\xd9"], ids=["bad", "missing-eoi", "oversized"])
def test_invalid_or_oversized_bytes_fail_closed(env, data):
    home, db = env
    opener = Opener(data=data)
    assert art.ensure_work_poster(db, 1, home=home, opener=opener)["status"] == "INVALID_IMAGE"
    assert len(opener.requests) == 1 and not art.cache_path("/abcDEF_12.jpg", home=home).exists()


def test_partial_read_failure_and_atomic_replace_failure_cleanup(env):
    home, db = env
    class Broken(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def read(self, *args): raise OSError("broken read")
    opener = Opener()
    opener.data = JPEG
    with patch.object(Opener, "__call__", return_value=Broken(JPEG)):
        assert art.ensure_work_poster(db, 1, home=home, opener=opener)["status"] == "OFFLINE"
    target = art.cache_path("/abcDEF_12.jpg", home=home)
    assert not target.exists()
    with patch.object(art.os, "replace", side_effect=OSError("replace failed")):
        assert art.ensure_work_poster(db, 1, home=home, opener=Opener())["status"] == "CACHE_WRITE_FAILED"
    assert not target.exists() and not list(target.parent.glob(".poster-*"))


def test_no_flex_config_mutation(env):
    home, db = env
    config = home / ".config/openhtpc/flex-v1.ini"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"unchanged-flex")
    before = (config.read_bytes(), config.stat().st_mtime_ns)
    assert art.ensure_work_poster(db, 1, home=home, opener=Opener())["status"] == "OK_DOWNLOADED"
    assert (config.read_bytes(), config.stat().st_mtime_ns) == before


def test_symlinked_cache_parent_is_rejected_before_network(env, tmp_path):
    home, db = env
    outside = tmp_path / "outside"
    outside.mkdir()
    cache = home / ".cache"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.symlink_to(outside, target_is_directory=True)
    opener = Opener()
    assert art.ensure_work_poster(db, 1, home=home, opener=opener)["status"] == "CACHE_WRITE_FAILED"
    assert opener.requests == [] and list(outside.iterdir()) == []


def test_artwork_component_is_in_both_deployment_authorities():
    name = "openhtpc-media-artwork.py"
    managed = (ROOT / "payload/managed-files.txt").read_text().splitlines()
    installer = (ROOT / "payload/install-openhtpc-fedora.sh").read_text()
    products = re.search(r"readonly PRODUCT_FILES=\(([^)]*)\)", installer).group(1).split()
    assert managed.count(name) == 1 and products.count(name) == 1


def test_production_redirect_handler_refuses_second_http_request():
    handler = art._NoRedirect()
    request = art.urllib.request.Request("https://image.tmdb.org/t/p/w500/abc.jpg")
    assert handler.redirect_request(request, None, 302, "redirect", {}, "https://other.example/image") is None
