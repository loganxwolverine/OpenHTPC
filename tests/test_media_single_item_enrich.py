# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic qualification tests for on-demand single-item presentation enrichment.

Verifies:
1. Candidate acceptance remains offline and deterministic.
2. Successful accepted identity can trigger single-item enrichment.
3. Single-item enrichment:
   - fetches presentation
   - creates work_presentations
   - stores provider snapshot
   - obtains poster
   - caches artwork
   - regenerates Flex
4. Resulting MEDIA_D contains:
   - real poster (symlink to cached JPEG)
   - title
   - original title
   - metadata (year, runtime, genres)
   - synopsis
   - playback action (LIRE LE FILM)
5. Network failure after identity acceptance:
   USER_MATCHED remains persisted.
6. TMDb detail failure:
   identity remains valid and fallback UI remains usable.
7. Poster failure:
   metadata still persists;
   fallback poster remains usable;
   no corruption.
8. Repeated enrichment is idempotent.
9. Existing batch enrichment remains unchanged/regression-free.
10. Offline resolver contract preserved.
"""
from __future__ import annotations

from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
from typing import Any
from unittest import mock
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


import importlib.machinery
import importlib.util


def _load_module(path: Path, name: str) -> Any:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


media_db = _load_module(PAYLOAD / "openhtpc-media-db.py", "media_db_single_test")
tmdb_provider = _load_module(PAYLOAD / "openhtpc-media-provider-tmdb.py", "tmdb_single_test")
media_match = _load_module(PAYLOAD / "openhtpc-media-match.py", "media_match_single_test")
media_pres = _load_module(PAYLOAD / "openhtpc-media-presentation.py", "media_pres_single_test")
media_art = _load_module(PAYLOAD / "openhtpc-media-artwork.py", "media_art_single_test")
media_enrich = _load_module(PAYLOAD / "openhtpc-media-enrich.py", "media_enrich_single_test")
media_match_ui = _load_module(PAYLOAD / "openhtpc-media-match-ui", "media_match_ui_single_test")
session_engine = _load_module(PAYLOAD / "openhtpc-session-engine.py", "session_engine_single_test")

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
media_enrich.set_media_match_ui_module(media_match_ui)

media_match_ui.set_media_db_module(media_db)
media_match_ui.set_media_match_module(media_match)
media_match_ui.set_session_engine_module(session_engine)

SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

TMDB_DETAILS_PAYLOAD = {
    "id": 9378,
    "title": "13 fantômes",
    "original_title": "Thir13en Ghosts",
    "overview": "Arthur Kriticos et ses deux enfants héritent d'une étrange maison...",
    "release_date": "2001-10-26",
    "runtime": 91,
    "genres": [{"id": 27, "name": "Horreur"}, {"id": 9648, "name": "Mystère"}],
    "poster_path": "/thirteen_ghosts_poster.jpg",
}


@pytest.fixture(autouse=True)
def fail_closed_network_guard(monkeypatch):
    """Enforce real network socket connection strictly forbidden in hermetic tests."""
    def no_socket(*args, **kwargs):
        raise RuntimeError("Real network socket connection strictly forbidden in hermetic tests")
    monkeypatch.setattr(socket, "socket", no_socket)


class MockHTTPResponse(io.BytesIO):
    def __init__(self, data: bytes | str, status: int = 200) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        super().__init__(raw)
        self.status = status
        self.code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def make_mock_opener(details_data: dict[str, Any] | None = None, image_bytes: bytes = SYNTHETIC_JPEG, fail_details: bool = False, fail_image: bool = False):
    details_dict = details_data or TMDB_DETAILS_PAYLOAD

    def handler(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.themoviedb.org" in url:
            if fail_details:
                raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
            return MockHTTPResponse(json.dumps(details_dict), 200)
        elif "image.tmdb.org" in url:
            if fail_image:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return MockHTTPResponse(image_bytes, 200)
        raise urllib.error.URLError(f"Unexpected mock url: {url}")

    return handler


@pytest.fixture
def test_env(tmp_path):
    """Create isolated hermetic environment for media enrichment tests."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    sources_dir = tmp_path / "sources" / "Films"
    sources_dir.mkdir(parents=True)
    install_dir = tmp_path / "install"
    install_dir.mkdir(parents=True)

    # Copy relevant scripts into install directory
    for src in (
        PAYLOAD / "openhtpc-media-match.py",
        PAYLOAD / "openhtpc-media-match-ui",
        PAYLOAD / "openhtpc-media-db.py",
        PAYLOAD / "openhtpc-media-ingest.py",
        PAYLOAD / "openhtpc-media-probe.py",
        PAYLOAD / "openhtpc-session-engine.py",
        PAYLOAD / "openhtpc-optical.py",
        PAYLOAD / "openhtpc-ui.py",
        PAYLOAD / "openhtpc-theme.py",
        PAYLOAD / "openhtpc-media-enrich.py",
        PAYLOAD / "openhtpc-media-presentation.py",
        PAYLOAD / "openhtpc-media-artwork.py",
        PAYLOAD / "openhtpc-media-provider-tmdb.py",
    ):
        dest = install_dir / src.name
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o755)

    (install_dir / "assets/ui").mkdir(parents=True, exist_ok=True)
    raw_media_icon = install_dir / "assets/ui/media.png"
    raw_media_icon.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    for name in ("optical-empty.png", "optical-dvd.png", "optical-bluray.png", "optical-uhd.png", "eject.png"):
        (install_dir / "assets/ui" / name).write_bytes(b"PNG")
    (install_dir / "flex/assets/icons").mkdir(parents=True, exist_ok=True)
    (install_dir / "flex/assets/icons/drive-empty.png").write_bytes(b"PNG")
    (install_dir / "flex/assets/fonts").mkdir(parents=True, exist_ok=True)
    (install_dir / "flex/assets/fonts/OpenSans-Regular.ttf").write_bytes(b"TTF")

    uid = os.getuid()
    short_icon = Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(raw_media_icon)
    except OSError:
        pass

    # Set up user-config
    cfg_dir = home / ".config/openhtpc"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "user-config.json").write_text(
        json.dumps({"local_media_sources": [str(sources_dir)]}, indent=2),
        encoding="utf-8",
    )

    # Set up media.db
    db_dir = home / ".local/share/openhtpc/media"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "media.db"
    media_db.initialize(db_path)

    # Set up mock TMDb secret token
    sec_dir = home / ".config/openhtpc/secrets"
    sec_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    tok_file = sec_dir / "tmdb-token"
    tok_file.write_text("ey_mock_tmdb_token\n", encoding="utf-8")
    tok_file.chmod(0o600)

    # Create dummy movie file
    movie_file = sources_dir / "13.Fantomes.2001.mkv"
    movie_file.write_bytes(b"dummy mkv content")

    src_id = media_enrich.compute_source_id(sources_dir)
    now_iso = "2026-01-01T00:00:00+00:00"

    # Ingest movie file
    db = media_db.connect(db_path)
    res_mv = db.execute(
        """
        INSERT INTO media_versions (
            work_id, provisional_title, provisional_year, edition_title,
            identification_state, match_confidence, match_method, match_locked,
            duration_seconds, created_at, updated_at
        ) VALUES (NULL, '13 fantômes', 2001, NULL, 'UNMATCHED', NULL, NULL, 0, 5460.0, ?, ?)
        """,
        (now_iso, now_iso),
    )
    mv_id = res_mv.lastrowid
    db.execute(
        """
        INSERT INTO resources (
            media_version_id, resource_kind, source_id, relative_path,
            canonical_path, file_size, mtime_ns, container_format,
            availability_status, created_at
        ) VALUES (?, 'FILE', ?, '13.Fantomes.2001.mkv', ?, 1024000, 1700000000, 'matroska', 'AVAILABLE', ?)
        """,
        (mv_id, src_id, str(movie_file), now_iso),
    )
    cand_payload = {
        "id": "9378",
        "title": "13 fantômes",
        "original_title": "Thir13en Ghosts",
        "release_date": "2001-10-26",
        "runtime_minutes": 91,
    }
    db.execute(
        """
        INSERT INTO match_candidates (
            media_version_id, provider, external_id,
            candidate_title, candidate_year,
            candidate_payload_json, score, status, created_at
        ) VALUES (?, 'tmdb_movie', '9378', '13 fantômes', 2001, ?, 95.0, 'PENDING', ?)
        """,
        (mv_id, json.dumps(cand_payload), now_iso),
    )
    db.commit()
    db.close()

    # Generate initial Flex config and manifest
    flex_config = cfg_dir / "flex-v1.ini"
    session_engine.write_flex_config(flex_config, home, [sources_dir], install_dir)
    session_engine.activate_media_manifest(flex_config, home)

    return {
        "home": home,
        "sources_dir": sources_dir,
        "install_dir": install_dir,
        "db_path": db_path,
        "mv_id": mv_id,
        "source_id": src_id,
        "flex_config": flex_config,
    }


def test_1_candidate_acceptance_remains_offline_and_deterministic(test_env):
    """1. Candidate acceptance is strictly offline and deterministic."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    # dispatch_action runs with fail_closed_network_guard active (no mocks needed)
    exit_code = media_match_ui.dispatch_action(home, token, install=test_env["install_dir"])
    assert exit_code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        row = db.execute("SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        assert row[0] == "USER_MATCHED"
        assert row[1] == 1
        assert row[2] is not None


def test_2_successful_accepted_identity_triggers_single_item_enrichment(test_env):
    """2. Successful accepted identity can trigger single-item enrichment."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    mock_opener = make_mock_opener()

    # Call enrich_action_token
    exit_code = media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=mock_opener,
    )
    assert exit_code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        row = db.execute("SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        assert row[0] == "USER_MATCHED"
        work_id = row[2]
        assert work_id is not None

        # Verify presentation record exists
        pres = db.execute("SELECT display_title, overview, runtime_minutes FROM work_presentations WHERE work_id = ?", (work_id,)).fetchone()
        assert pres is not None
        assert pres[0] == "13 fantômes"
        assert "Arthur Kriticos" in pres[1]
        assert pres[2] == 91


def test_3_single_item_enrichment_creates_records_and_poster(test_env):
    """3. Single-item enrichment creates work_presentations, provider snapshot, and caches artwork."""
    # First accept candidate offline
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)
    assert media_match_ui.dispatch_action(home, token, install=test_env["install_dir"]) == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        work_id = db.execute("SELECT work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()[0]

        mock_opener = make_mock_opener()
        res = media_enrich.enrich_work(
            db,
            work_id,
            home=home,
            opener=mock_opener,
            install=test_env["install_dir"],
        )
        assert res["ok"] is True
        assert res["presentation_status"] == "REFRESHED"
        assert res["poster_status"] == "DOWNLOADED"

        # Check DB records
        pres_count = db.execute("SELECT COUNT(*) FROM work_presentations WHERE work_id = ?", (work_id,)).fetchone()[0]
        assert pres_count == 1

        snap_count = db.execute("SELECT COUNT(*) FROM provider_snapshots WHERE snapshot_kind = 'MOVIE_DETAILS'").fetchone()[0]
        assert snap_count == 1

    # Check artwork cache on disk
    artwork_dir = home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500"
    assert artwork_dir.is_dir()
    cached_posters = list(artwork_dir.glob("*.jpg"))
    assert len(cached_posters) == 1
    assert cached_posters[0].read_bytes() == SYNTHETIC_JPEG


def test_4_resulting_media_d_contains_enriched_fields(test_env):
    """4. Verify resulting MEDIA_D contains real poster, title, original title, metadata, synopsis, and playback action."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    mock_opener = make_mock_opener()
    exit_code = media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=mock_opener,
    )
    assert exit_code == 0

    # Read regenerated flex-v1.ini
    flex_ini = (home / ".config/openhtpc/flex-v1.ini").read_text(encoding="utf-8")
    assert "Layout=MovieDetail" in flex_ini
    assert "Title=13 fantômes" in flex_ini
    assert "OriginalTitle=Thir13en Ghosts" in flex_ini
    assert "Metadata=2001 · 1 h 31 · Horreur, Mystère" in flex_ini
    assert "Synopsis1=Arthur Kriticos et ses deux enfants héritent d'une étrange maison..." in flex_ini
    assert "Entry1=LIRE LE FILM" in flex_ini
    # Poster must point to the cached JPEG symlink, not the fallback icon
    assert "/tmp/ohtpc-" in flex_ini
    assert "ohtpc-1000-m.png" not in flex_ini or "Poster=/tmp/ohtpc-" in flex_ini
    # Verify Poster property is not default media icon
    detail_lines = [l for l in flex_ini.splitlines() if l.startswith("Poster=")]
    assert any("m.png" not in l for l in detail_lines)


def test_5_network_failure_after_identity_acceptance_preserves_user_matched(test_env):
    """5. Network failure after identity acceptance: USER_MATCHED remains persisted and locked."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    # Mock opener that simulates complete network failure
    failing_opener = make_mock_opener(fail_details=True)

    exit_code = media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=failing_opener,
    )
    # The action must succeed from user perspective (identity committed, fallback UI displayed)
    assert exit_code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        row = db.execute("SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        assert row[0] == "USER_MATCHED"
        assert row[1] == 1
        work_id = row[2]
        assert work_id is not None

        # Presentation record was not created due to network failure
        pres_count = db.execute("SELECT COUNT(*) FROM work_presentations WHERE work_id = ?", (work_id,)).fetchone()[0]
        assert pres_count == 0

    # Fallback UI must still be operational
    flex_ini = (home / ".config/openhtpc/flex-v1.ini").read_text(encoding="utf-8")
    assert "LIRE LE FILM" in flex_ini
    assert "Aucun synopsis disponible." in flex_ini


def test_6_tmdb_detail_failure_preserves_identity_and_fallback_ui(test_env):
    """6. TMDb detail failure: identity remains valid and fallback UI remains usable."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    # Mock opener returning HTTP 404 for details
    def not_found_opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    exit_code = media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=not_found_opener,
    )
    assert exit_code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        row = db.execute("SELECT identification_state, match_locked FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        assert row[0] == "USER_MATCHED"
        assert row[1] == 1

    flex_ini = (home / ".config/openhtpc/flex-v1.ini").read_text(encoding="utf-8")
    assert "LIRE LE FILM" in flex_ini


def test_7_poster_failure_preserves_presentation_metadata(test_env):
    """7. Poster failure: presentation metadata still persists; fallback poster used without corruption."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    # Details succeed, but poster image download fails (HTTP 404)
    opener = make_mock_opener(fail_image=True)

    exit_code = media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=opener,
    )
    assert exit_code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        row = db.execute("SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        assert row[0] == "USER_MATCHED"
        work_id = row[2]

        # Metadata was persisted despite artwork failure
        pres = db.execute("SELECT display_title, runtime_minutes FROM work_presentations WHERE work_id = ?", (work_id,)).fetchone()
        assert pres is not None
        assert pres[0] == "13 fantômes"
        assert pres[1] == 91

    # In flex ini, metadata is present but fallback poster is used
    flex_ini = (home / ".config/openhtpc/flex-v1.ini").read_text(encoding="utf-8")
    assert "Title=13 fantômes" in flex_ini
    assert "Metadata=2001 · 1 h 31 · Horreur, Mystère" in flex_ini
    assert "LIRE LE FILM" in flex_ini


def test_8_repeated_enrichment_is_idempotent(test_env):
    """8. Repeated enrichment is idempotent."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    mock_opener = make_mock_opener()

    # First run
    media_enrich.enrich_action_token(home, token, install=test_env["install_dir"], opener=mock_opener)

    with closing(media_db.connect(test_env["db_path"])) as db:
        work_id = db.execute("SELECT work_id FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()[0]

        # Second run: should be a no-op / cache hit
        res2 = media_enrich.enrich_work(
            db,
            work_id,
            home=home,
            opener=mock_opener,
            install=test_env["install_dir"],
        )
        assert res2["ok"] is True
        assert res2["presentation_status"] == "ALREADY_PRESENT"
        assert res2["poster_status"] == "CACHE_HIT"

        # Still exactly 1 row in work_presentations
        count = db.execute("SELECT COUNT(*) FROM work_presentations WHERE work_id = ?", (work_id,)).fetchone()[0]
        assert count == 1


def test_9_existing_batch_enrichment_remains_unchanged(test_env):
    """9. Existing batch enrichment remains regression-free."""
    home = test_env["home"]
    db_path = test_env["db_path"]
    src_id = test_env["source_id"]

    mock_opener = make_mock_opener()

    # Run batch enrichment on the source
    with closing(media_enrich.connect_db(db_path, home=home)) as db:
        result = media_enrich.enrich_source(
            db,
            src_id,
            home=home,
            opener=mock_opener,
        )
        assert result["ok"] is True
        assert result["mode"] == "EXECUTE"
        assert result["considered"] >= 1


def test_10_offline_resolver_contract_preserved(test_env):
    """10. Offline candidate resolver contract preserved."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    # Calling dispatch_action directly does NOT perform network operations
    code = media_match_ui.dispatch_action(home, token, install=test_env["install_dir"])
    assert code == 0

    with closing(media_db.connect(test_env["db_path"])) as db:
        st = media_match.get_media_version_status(db, test_env["mv_id"])
        assert st["identification_state"] == "USER_MATCHED"
        assert st["match_locked"] == 1


def test_11_stale_token_does_not_cross_enrichment_boundary(test_env):
    """A stale accept keeps its local notice behavior but performs no enrichment."""
    home = test_env["home"]
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    with closing(media_db.connect(test_env["db_path"])) as db:
        db.execute(
            """
            INSERT INTO match_candidates (
                media_version_id, provider, external_id, candidate_title,
                candidate_year, candidate_payload_json, score, status, created_at
            ) VALUES (?, 'tmdb_movie', '9999', 'Different candidate', 2002,
                      '{}', 80.0, 'PENDING', '2026-01-02T00:00:00+00:00')
            """,
            (test_env["mv_id"],),
        )
        db.commit()

    forbidden_opener = mock.Mock(side_effect=AssertionError("network must not run"))
    with mock.patch.object(media_enrich, "enrich_work") as enrich_mock:
        code = media_enrich.enrich_action_token(
            home,
            token,
            install=test_env["install_dir"],
            opener=forbidden_opener,
        )

    assert code == 0
    enrich_mock.assert_not_called()
    forbidden_opener.assert_not_called()
    with closing(media_db.connect(test_env["db_path"])) as db:
        state = db.execute(
            "SELECT identification_state, work_id FROM media_versions WHERE id = ?",
            (test_env["mv_id"],),
        ).fetchone()
        assert state == ("UNMATCHED", None)


def test_12_forged_unknown_token_fails_closed(test_env):
    """A token absent from the active manifest cannot trigger enrichment."""
    forbidden_opener = mock.Mock(side_effect=AssertionError("network must not run"))
    with mock.patch.object(media_enrich, "enrich_work") as enrich_mock:
        code = media_enrich.enrich_action_token(
            test_env["home"],
            "iact_forged_unknown",
            install=test_env["install_dir"],
            opener=forbidden_opener,
        )

    assert code == 1
    enrich_mock.assert_not_called()
    forbidden_opener.assert_not_called()


@pytest.mark.parametrize(
    ("field", "malformed_value"),
    (("media_version_id", True), ("candidate_id", False)),
)
def test_13_boolean_manifest_ids_are_invalid(test_env, field, malformed_value):
    """JSON booleans must not pass persisted integer-ID validation."""
    manifest_path = test_env["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)
    manifest["items"][token][field] = malformed_value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with mock.patch.object(media_enrich, "enrich_work") as enrich_mock:
        code = media_enrich.enrich_action_token(
            test_env["home"],
            token,
            install=test_env["install_dir"],
            opener=mock.Mock(side_effect=AssertionError("network must not run")),
        )

    assert code == 1
    enrich_mock.assert_not_called()


def test_14_accepted_result_crosses_single_item_boundary(test_env):
    """Only an explicitly ACCEPTED result proceeds to enrich_work."""
    manifest_path = test_env["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)
    enrichment_result = {
        "ok": True,
        "presentation_status": "REFRESHED",
        "poster_status": "DOWNLOADED",
    }

    with mock.patch.object(media_enrich, "enrich_work", return_value=enrichment_result) as enrich_mock:
        code = media_enrich.enrich_action_token(
            test_env["home"], token, install=test_env["install_dir"]
        )

    assert code == 0
    enrich_mock.assert_called_once()
    with closing(media_db.connect(test_env["db_path"])) as db:
        state = db.execute(
            "SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?",
            (test_env["mv_id"],),
        ).fetchone()
        assert state[0:2] == ("USER_MATCHED", 1)
        assert state[2] is not None


def test_15_reject_action_does_not_enrich(test_env):
    """A successful candidate rejection is explicit and never enriches a work."""
    manifest_path = test_env["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("action") == "reject")

    with mock.patch.object(media_enrich, "enrich_work") as enrich_mock:
        code = media_enrich.enrich_action_token(
            test_env["home"], token, install=test_env["install_dir"]
        )

    assert code == 0
    enrich_mock.assert_not_called()
    with closing(media_db.connect(test_env["db_path"])) as db:
        state = db.execute(
            "SELECT identification_state, work_id FROM media_versions WHERE id = ?",
            (test_env["mv_id"],),
        ).fetchone()
        assert state == ("UNMATCHED", None)


def test_16_regeneration_failure_after_acceptance_preserves_identity(test_env):
    """UI regeneration failure cannot roll back an already committed identity."""
    manifest_path = test_env["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    with mock.patch.object(media_match_ui, "_regenerate_ui", return_value=False):
        code = media_enrich.enrich_action_token(
            test_env["home"],
            token,
            install=test_env["install_dir"],
            opener=make_mock_opener(),
        )

    assert code == 0
    with closing(media_db.connect(test_env["db_path"])) as db:
        state = db.execute(
            "SELECT identification_state, match_locked, work_id FROM media_versions WHERE id = ?",
            (test_env["mv_id"],),
        ).fetchone()
        assert state[0:2] == ("USER_MATCHED", 1)
        assert state[2] is not None
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def _trace_rows(home: Path) -> list[dict[str, Any]]:
    target = home / ".local/state/openhtpc/ui-action-timing.jsonl"
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]


def _enable_trace(monkeypatch, home: Path) -> None:
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv("OPENHTPC_UI_ACTION_OPERATION_ID", "uiaq-4242-987654321")
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", "5151")
    monkeypatch.setenv("OPENHTPC_HOME", str(home))


def _assert_python_local_trace(rows: list[dict[str, Any]]) -> str:
    operation_ids = {row["operation_id"] for row in rows}
    assert len(operation_ids) == 1
    operation_id = operation_ids.pop()
    assert operation_id.startswith(f"uiaq-python-{os.getpid()}-")
    assert all("child_pid" not in row for row in rows)
    return operation_id


def test_17_trace_disabled_creates_no_diagnostic(test_env, monkeypatch):
    """Normal accepted behavior creates no trace output unless explicitly enabled."""
    monkeypatch.delenv("OPENHTPC_TRACE_UI_ACTION", raising=False)
    manifest_path = test_env["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    assert media_enrich.enrich_action_token(
        test_env["home"],
        token,
        install=test_env["install_dir"],
        opener=make_mock_opener(),
    ) == 0
    assert not (test_env["home"] / ".local/state/openhtpc/ui-action-timing.jsonl").exists()


def test_18_trace_enabled_records_accepted_core_markers_without_sensitive_data(test_env, monkeypatch):
    """Accepted flow is fully timed without recording identity or provider data."""
    home = test_env["home"]
    _enable_trace(monkeypatch, home)
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)

    assert media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=make_mock_opener(),
    ) == 0

    rows = _trace_rows(home)
    events = [row["event"] for row in rows]
    expected = [
        "active_manifest_loaded",
        "action_token_validated",
        "identity_dispatch_begin",
        "identity_transaction_begin",
        "identity_commit",
        "first_flex_regeneration_begin",
        "first_flex_regeneration_end",
        "tmdb_movie_details_begin",
        "tmdb_movie_details_end",
        "presentation_commit",
        "poster_cache_begin",
        "poster_cache_end",
        "second_flex_regeneration_begin",
        "second_flex_regeneration_end",
    ]
    positions = [events.index(event) for event in expected]
    assert positions == sorted(positions)
    _assert_python_local_trace(rows)
    assert all(type(row["mono_ns"]) is int and row["mono_ns"] > 0 for row in rows)

    raw_trace = (home / ".local/state/openhtpc/ui-action-timing.jsonl").read_text(encoding="utf-8")
    forbidden = (
        token,
        "13 fantômes",
        json.dumps("13 fantômes")[1:-1],
        str(test_env["sources_dir"] / "13.Fantomes.2001.mkv"),
        "13.Fantomes.2001.mkv",
        "api.themoviedb.org",
        "image.tmdb.org",
        "ey_mock_tmdb_token",
    )
    assert all(value not in raw_trace for value in forbidden)


def test_19_cli_entry_and_exit_markers_are_bounded(test_env, monkeypatch):
    """The CLI wrapper covers Python entry and every normal return path."""
    home = test_env["home"]
    _enable_trace(monkeypatch, home)
    assert media_enrich.main([
        "--home", str(home),
        "--install", str(test_env["install_dir"]),
        "--token", "iact_forged_sensitive_value",
    ]) == 1
    events = [row["event"] for row in _trace_rows(home)]
    assert events[0] == "python_entry"
    assert "action_token_invalid" in events
    assert events[-1] == "python_exit"
    raw_trace = (home / ".local/state/openhtpc/ui-action-timing.jsonl").read_text(encoding="utf-8")
    assert "iact_forged_sensitive_value" not in raw_trace


def test_20_stale_trace_has_no_enrichment_markers(test_env, monkeypatch):
    """A stale token records validation/dispatch only, never enrichment success."""
    home = test_env["home"]
    _enable_trace(monkeypatch, home)
    manifest_path = home / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") is not None)
    with closing(media_db.connect(test_env["db_path"])) as db:
        db.execute(
            """INSERT INTO match_candidates (
                   media_version_id, provider, external_id, candidate_title,
                   candidate_year, candidate_payload_json, score, status, created_at
               ) VALUES (?, 'tmdb_movie', '9999', 'Different candidate', 2002,
                         '{}', 80.0, 'PENDING', '2026-01-02T00:00:00+00:00')""",
            (test_env["mv_id"],),
        )
        db.commit()

    assert media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
        opener=mock.Mock(side_effect=AssertionError("network must not run")),
    ) == 0
    events = {row["event"] for row in _trace_rows(home)}
    assert "identity_commit" not in events
    assert "tmdb_movie_details_begin" not in events
    assert "presentation_commit" not in events
    assert "poster_cache_begin" not in events
    assert "second_flex_regeneration_begin" not in events


def test_21_rejected_trace_has_no_enrichment_markers(test_env, monkeypatch):
    """A successful explicit rejection never emits accepted enrichment phases."""
    home = test_env["home"]
    _enable_trace(monkeypatch, home)
    manifest = json.loads(
        (home / ".local/state/openhtpc/media-actions/current.json").read_text(encoding="utf-8")
    )
    token = next(k for k, v in manifest["items"].items() if v.get("action") == "reject")

    assert media_enrich.enrich_action_token(
        home,
        token,
        install=test_env["install_dir"],
    ) == 0
    events = {row["event"] for row in _trace_rows(home)}
    assert "identity_commit" not in events
    assert "first_flex_regeneration_begin" not in events
    assert "tmdb_movie_details_begin" not in events
    assert "presentation_commit" not in events
    assert "poster_cache_begin" not in events
    assert "second_flex_regeneration_begin" not in events


@pytest.mark.parametrize(
    "child_pid",
    [
        "9" * 5000,
        "not-a-pid",
        "+1",
        "-1",
        "0",
        "2147483648",
        "١٢٣",
    ],
)
def test_22_malformed_child_pid_is_total_and_uses_local_fallback(tmp_path, monkeypatch, child_pid):
    """Untrusted child PID text cannot raise or claim authoritative ownership."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv(
        "OPENHTPC_UI_ACTION_OPERATION_ID",
        f"uiaq-{os.getppid()}-123456789",
    )
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", child_pid)
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))

    media_enrich._ui_action_trace("python_entry")
    rows = _trace_rows(tmp_path)
    assert [row["event"] for row in rows] == ["python_entry"]
    _assert_python_local_trace(rows)


def test_23_pid_mismatch_uses_local_fallback(tmp_path, monkeypatch):
    """A valid-looking operation cannot claim a different child process."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv(
        "OPENHTPC_UI_ACTION_OPERATION_ID",
        f"uiaq-{os.getppid()}-123456789",
    )
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", str(os.getpid() + 1))
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))

    media_enrich._ui_action_trace("python_entry")
    _assert_python_local_trace(_trace_rows(tmp_path))


@pytest.mark.parametrize(
    "operation_id",
    [
        "uiaq-" + ("9" * 5000) + "-1",
        "uiaq-+1-1",
        "uiaq-0-1",
        "uiaq-١-1",
        "uiaq-python-1-1",
        "not-an-operation",
    ],
)
def test_24_malformed_operation_id_uses_local_fallback(
    tmp_path, monkeypatch, operation_id
):
    """Only the bounded canonical C form is eligible for Flex provenance."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv("OPENHTPC_UI_ACTION_OPERATION_ID", operation_id)
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", str(os.getpid()))
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))

    media_enrich._ui_action_trace("python_entry")
    _assert_python_local_trace(_trace_rows(tmp_path))


def test_25_parent_mismatch_uses_local_fallback(tmp_path, monkeypatch):
    """The operation's embedded parent PID must be the actual Python parent."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv(
        "OPENHTPC_UI_ACTION_OPERATION_ID",
        f"uiaq-{os.getppid() + 1}-123456789",
    )
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", str(os.getpid()))
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))

    media_enrich._ui_action_trace("python_entry")
    _assert_python_local_trace(_trace_rows(tmp_path))


def test_26_direct_python_trace_has_local_operation_without_child_pid(tmp_path, monkeypatch):
    """Direct developer invocation is traceable without impersonating Flex."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.delenv("OPENHTPC_UI_ACTION_OPERATION_ID", raising=False)
    monkeypatch.delenv("OPENHTPC_UI_ACTION_CHILD_PID", raising=False)
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))

    media_enrich._ui_action_trace("python_entry")
    media_enrich._ui_action_trace("python_exit")
    rows = _trace_rows(tmp_path)
    assert [row["event"] for row in rows] == ["python_entry", "python_exit"]
    _assert_python_local_trace(rows)


def test_27_parent_executable_failure_uses_local_fallback(tmp_path, monkeypatch):
    """Unavailable process ancestry evidence fails open to local diagnostics."""
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv(
        "OPENHTPC_UI_ACTION_OPERATION_ID",
        f"uiaq-{os.getppid()}-123456789",
    )
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", str(os.getpid()))
    monkeypatch.setenv("OPENHTPC_HOME", str(tmp_path))
    monkeypatch.setattr(
        media_enrich,
        "_ui_action_parent_executable",
        mock.Mock(side_effect=PermissionError),
    )

    media_enrich._ui_action_trace("python_entry")
    _assert_python_local_trace(_trace_rows(tmp_path))


def test_28_trace_writer_failure_does_not_change_cli_result(test_env, monkeypatch):
    """Trace destination failures cannot change normal CLI failure semantics."""
    _enable_trace(monkeypatch, test_env["home"])
    monkeypatch.setattr(media_enrich.os, "open", mock.Mock(side_effect=PermissionError))

    assert media_enrich.main([
        "--home", str(test_env["home"]),
        "--install", str(test_env["install_dir"]),
        "--token", "iact_forged_sensitive_value",
    ]) == 1


def test_29_malformed_entry_correlation_preserves_cli_and_exit(test_env, monkeypatch):
    """Malformed entry provenance cannot prevent CLI handling or final tracing."""
    home = test_env["home"]
    monkeypatch.setenv("OPENHTPC_TRACE_UI_ACTION", "1")
    monkeypatch.setenv("OPENHTPC_UI_ACTION_OPERATION_ID", "uiaq-1-1")
    monkeypatch.setenv("OPENHTPC_UI_ACTION_CHILD_PID", "7" * 5000)
    monkeypatch.setenv("OPENHTPC_HOME", str(home))

    assert media_enrich.main([
        "--home", str(home),
        "--install", str(test_env["install_dir"]),
        "--token", "iact_forged_sensitive_value",
    ]) == 1
    rows = _trace_rows(home)
    assert [row["event"] for row in rows] == [
        "python_entry",
        "active_manifest_loaded",
        "action_token_invalid",
        "python_exit",
    ]
    _assert_python_local_trace(rows)
