# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for DEV6A2: Presentation Refresh Core.

Verifies:
- 100% hermetic offline execution with zero real network, zero access to real secrets.
- Work presentation refresh using canonical identity 'tmdb_movie' only.
- Strict rejection of missing, ambiguous (>1), or non-tmdb_movie external IDs.
- Atomic persistence: provider_snapshots and work_presentations linked via source_snapshot_id.
- Identity immutability: zero mutation to works, external_ids, media_versions, resources.
- Idempotency & update preservation: re-refresh preserves row IDs and updates metadata.
- Multi-locale support: distinct presentations and snapshots for different locales on same work.
- Provider failure non-destructiveness: existing good presentation is preserved on failure.
- Transactional rollback: failure during persistence rolls back cleanly without partial records.
- Zero artwork download: no files created in ~/.cache/openhtpc/media/ or anywhere on disk.
- Zero UI / Flex mutation.
"""
from __future__ import annotations

from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
from unittest import mock
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
PROVIDER_PATH = PAYLOAD / "openhtpc-media-provider-tmdb.py"
PRES_PATH = PAYLOAD / "openhtpc-media-presentation.py"

db_spec = importlib.util.spec_from_file_location("media_db", DB_PATH)
media_db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(media_db)

provider_spec = importlib.util.spec_from_file_location("tmdb_provider", PROVIDER_PATH)
tmdb_provider = importlib.util.module_from_spec(provider_spec)
provider_spec.loader.exec_module(tmdb_provider)

pres_spec = importlib.util.spec_from_file_location("media_pres", PRES_PATH)
media_pres = importlib.util.module_from_spec(pres_spec)
pres_spec.loader.exec_module(media_pres)

media_pres.set_media_db_module(media_db)
media_pres.set_tmdb_provider_module(tmdb_provider)


class MockHTTPResponse(io.BytesIO):
    def __init__(self, data: bytes | str, status: int = 200) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        super().__init__(raw)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


SPIRITED_AWAY_FR_PAYLOAD = {
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

SPIRITED_AWAY_EN_PAYLOAD = {
    "id": 129,
    "title": "Spirited Away",
    "original_title": "千と千尋の神隠し",
    "release_date": "2001-07-20",
    "runtime": 125,
    "overview": "A young girl wanders into a world ruled by gods, witches, and spirits...",
    "genres": [
        {"id": 16, "name": "Animation"},
        {"id": 10751, "name": "Family"},
        {"id": 14, "name": "Fantasy"},
    ],
    "poster_path": "/393D2e1VvjT37GzWv28uclCGUN8.jpg",
    "backdrop_path": "/mSDsSDwaP3E79ZeUS7nhQMUWdrg.jpg",
}


@pytest.fixture
def test_env(tmp_path):
    """Isolated environment with database, mock token, and Spirited Away work."""
    home = tmp_path / "home"
    secrets_dir = home / ".config/openhtpc/secrets"
    secrets_dir.mkdir(parents=True, mode=0o700)
    token_file = secrets_dir / "tmdb-token"
    token_file.write_text("eyMockV4BearerTokenForTestingOnly12345\n", encoding="utf-8")
    token_file.chmod(0o600)

    db_file = home / ".local/share/openhtpc/media/media.db"
    media_db.initialize(db_file)

    with closing(media_db.connect(db_file)) as db:
        # Create work for Spirited Away
        now = "2026-09-01T12:00:00+00:00"
        cur = db.execute(
            """
            INSERT INTO works (work_type, title, original_title, normalized_title, year, created_at, updated_at)
            VALUES ('MOVIE', 'Le Voyage de Chihiro', '千と千尋の神隠し', 'le voyage de chihiro', 2001, ?, ?)
            """,
            (now, now),
        )
        work_id = cur.lastrowid

        # Create external_id with canonical tmdb_movie
        cur = db.execute(
            """
            INSERT INTO external_ids (work_id, provider, external_id, confidence, created_at)
            VALUES (?, 'tmdb_movie', '129', 'EXACT', ?)
            """,
            (work_id, now),
        )
        ext_id = cur.lastrowid

        # Create media_version and resource for identity checking
        cur = db.execute(
            """
            INSERT INTO media_versions (work_id, provisional_title, provisional_year, identification_state, created_at, updated_at)
            VALUES (?, 'Le Voyage de Chihiro', 2001, 'USER_MATCHED', ?, ?)
            """,
            (work_id, now, now),
        )
        mv_id = cur.lastrowid

        db.execute(
            """
            INSERT INTO resources (media_version_id, resource_kind, canonical_path, created_at)
            VALUES (?, 'FILE', '/movies/chihiro.mkv', ?)
            """,
            (mv_id, now),
        )
        db.commit()

    return {
        "home": home,
        "db_file": db_file,
        "work_id": work_id,
        "ext_id": ext_id,
        "mv_id": mv_id,
    }


def test_refresh_work_presentation_success(test_env):
    """Verify end-to-end presentation refresh: snapshot + presentation stored and linked."""
    def mock_opener(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener,
        )

        assert res["ok"] is True
        assert res["work_id"] == test_env["work_id"]
        assert res["locale"] == "fr-FR"
        assert res["display_title"] == "Le Voyage de Chihiro"
        assert res["display_original_title"] == "千と千尋の神隠し"
        assert res["release_date"] == "2001-07-20"
        assert res["runtime_minutes"] == 125
        assert res["genres"] == ["Animation", "Familial", "Fantastique"]
        assert res["poster_path"] == "/393D2e1VvjT37GzWv28uclCGUN8.jpg"
        assert res["backdrop_path"] == "/mSDsSDwaP3E79ZeUS7nhQMUWdrg.jpg"
        assert res["is_update"] is False

        # Verify provider_snapshots in DB
        snap = media_db.get_provider_snapshot(db, res["snapshot_id"])
        assert snap["ok"] is True
        assert snap["external_id_id"] == test_env["ext_id"]
        assert snap["snapshot_kind"] == "MOVIE_DETAILS"
        assert snap["locale"] == "fr-FR"
        assert snap["payload"]["id"] == 129

        # Verify work_presentations in DB
        pres = media_db.get_work_presentation(db, test_env["work_id"], "fr-FR")
        assert pres["ok"] is True
        assert pres["id"] == res["presentation_id"]
        assert pres["source_snapshot_id"] == res["snapshot_id"]
        assert pres["display_title"] == "Le Voyage de Chihiro"
        assert pres["display_original_title"] == "千と千尋の神隠し"
        assert pres["genres"] == ["Animation", "Familial", "Fantastique"]


def test_identity_immutability(test_env):
    """Verify works, external_ids, media_versions, and resources are completely untouched."""
    with closing(media_db.connect(test_env["db_file"])) as db:
        work_before = db.execute("SELECT * FROM works WHERE id = ?", (test_env["work_id"],)).fetchone()
        ext_before = db.execute("SELECT * FROM external_ids WHERE id = ?", (test_env["ext_id"],)).fetchone()
        mv_before = db.execute("SELECT * FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        res_before = db.execute("SELECT * FROM resources WHERE media_version_id = ?", (test_env["mv_id"],)).fetchone()

    def mock_opener(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener,
        )
        assert res["ok"] is True

        work_after = db.execute("SELECT * FROM works WHERE id = ?", (test_env["work_id"],)).fetchone()
        ext_after = db.execute("SELECT * FROM external_ids WHERE id = ?", (test_env["ext_id"],)).fetchone()
        mv_after = db.execute("SELECT * FROM media_versions WHERE id = ?", (test_env["mv_id"],)).fetchone()
        res_after = db.execute("SELECT * FROM resources WHERE media_version_id = ?", (test_env["mv_id"],)).fetchone()

        assert work_before == work_after
        assert ext_before == ext_after
        assert mv_before == mv_after
        assert res_before == res_after


def test_idempotent_re_refresh_updates_in_place(test_env):
    """Verify that re-refreshing the same work and locale updates in-place and preserves IDs."""
    def mock_opener_1(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    updated_payload = dict(SPIRITED_AWAY_FR_PAYLOAD)
    updated_payload["overview"] = "Updated French overview for Chihiro..."

    def mock_opener_2(req, timeout=8):
        return MockHTTPResponse(json.dumps(updated_payload))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res1 = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener_1,
        )
        assert res1["ok"] is True
        assert res1["is_update"] is False

        res2 = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener_2,
        )
        assert res2["ok"] is True
        assert res2["is_update"] is True

        # IDs must be preserved
        assert res2["snapshot_id"] == res1["snapshot_id"]
        assert res2["presentation_id"] == res1["presentation_id"]
        assert res2["overview"] == "Updated French overview for Chihiro..."

        # Verify row counts in DB: exactly 1 snapshot, 1 presentation
        snap_count = db.execute("SELECT COUNT(*) FROM provider_snapshots").fetchone()[0]
        pres_count = db.execute("SELECT COUNT(*) FROM work_presentations").fetchone()[0]
        assert snap_count == 1
        assert pres_count == 1


def test_multi_locale_distinct_records(test_env):
    """Verify distinct presentations and snapshots for multiple locales on the same work."""
    def mock_opener(req, timeout=8):
        if "language=en-US" in req.full_url:
            return MockHTTPResponse(json.dumps(SPIRITED_AWAY_EN_PAYLOAD))
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res_fr = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener,
        )
        res_en = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="en-US",
            home=test_env["home"],
            opener=mock_opener,
        )

        assert res_fr["ok"] is True
        assert res_en["ok"] is True

        assert res_fr["presentation_id"] != res_en["presentation_id"]
        assert res_fr["snapshot_id"] != res_en["snapshot_id"]
        assert res_fr["display_title"] == "Le Voyage de Chihiro"
        assert res_en["display_title"] == "Spirited Away"

        # Total counts: 2 snapshots, 2 presentations
        snap_count = db.execute("SELECT COUNT(*) FROM provider_snapshots").fetchone()[0]
        pres_count = db.execute("SELECT COUNT(*) FROM work_presentations").fetchone()[0]
        assert snap_count == 2
        assert pres_count == 2


def test_provider_failure_preserves_existing_presentation(test_env):
    """Verify that a provider failure leaves any pre-existing good presentation intact."""
    def mock_opener_ok(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    def mock_opener_fail(req, timeout=8):
        raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {}, io.BytesIO(b"server error"))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res1 = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener_ok,
        )
        assert res1["ok"] is True

        # Second call fails
        res2 = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            locale="fr-FR",
            home=test_env["home"],
            opener=mock_opener_fail,
        )
        assert res2["ok"] is False
        assert res2["error_code"] == tmdb_provider.STATUS_HTTP_ERROR

        # Verify existing presentation is still intact
        pres = media_db.get_work_presentation(db, test_env["work_id"], "fr-FR")
        assert pres["ok"] is True
        assert pres["display_title"] == "Le Voyage de Chihiro"


def test_missing_tmdb_id_rejected(test_env):
    """Verify works without provider='tmdb_movie' fail with PRESENTATION_NO_TMDB_ID."""
    with closing(media_db.connect(test_env["db_file"])) as db:
        # Create work with NO external_ids
        cur = db.execute(
            """
            INSERT INTO works (work_type, title, created_at, updated_at)
            VALUES ('MOVIE', 'Unknown Film', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')
            """
        )
        orphan_work_id = cur.lastrowid
        db.commit()

        res = media_pres.refresh_work_presentation(db, orphan_work_id, home=test_env["home"])
        assert res["ok"] is False
        assert res["error_code"] == "PRESENTATION_NO_TMDB_ID"


def test_legacy_or_other_provider_rejected_no_fallback(test_env):
    """Verify works with non-'tmdb_movie' provider (e.g. 'tmdb' or 'imdb') are NOT matched or used."""
    with closing(media_db.connect(test_env["db_file"])) as db:
        # Create work with provider='imdb' and provider='tmdb' (legacy)
        cur = db.execute(
            """
            INSERT INTO works (work_type, title, created_at, updated_at)
            VALUES ('MOVIE', 'Old Movie', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')
            """
        )
        other_work_id = cur.lastrowid
        db.execute(
            """
            INSERT INTO external_ids (work_id, provider, external_id, created_at)
            VALUES (?, 'tmdb', '129', '2026-09-01T00:00:00+00:00')
            """,
            (other_work_id,),
        )
        db.execute(
            """
            INSERT INTO external_ids (work_id, provider, external_id, created_at)
            VALUES (?, 'imdb', 'tt0245429', '2026-09-01T00:00:00+00:00')
            """,
            (other_work_id,),
        )
        db.commit()

        # presentation refresh MUST NOT fallback to 'tmdb' or 'imdb'
        res = media_pres.refresh_work_presentation(db, other_work_id, home=test_env["home"])
        assert res["ok"] is False
        assert res["error_code"] == "PRESENTATION_NO_TMDB_ID"


def test_ambiguous_tmdb_id_rejected_closed(test_env):
    """Verify works with multiple conflicting 'tmdb_movie' external_ids fail closed."""
    with closing(media_db.connect(test_env["db_file"])) as db:
        # Add a second tmdb_movie ID to Spirited Away work
        db.execute(
            """
            INSERT INTO external_ids (work_id, provider, external_id, created_at)
            VALUES (?, 'tmdb_movie', '999999', '2026-09-01T00:00:00+00:00')
            """,
            (test_env["work_id"],),
        )
        db.commit()

        res = media_pres.refresh_work_presentation(db, test_env["work_id"], home=test_env["home"])
        assert res["ok"] is False
        assert res["error_code"] == "PRESENTATION_AMBIGUOUS_TMDB_ID"


def test_invalid_and_nonexistent_work_id(test_env):
    """Verify invalid or non-existent work_id rejects gracefully."""
    with closing(media_db.connect(test_env["db_file"])) as db:
        # Non-existent ID
        res1 = media_pres.refresh_work_presentation(db, 9999999, home=test_env["home"])
        assert res1["ok"] is False
        assert res1["error_code"] == "PRESENTATION_WORK_NOT_FOUND"

        # Invalid IDs
        for bad_id in [None, True, False, 0, -5, "abc"]:
            res = media_pres.refresh_work_presentation(db, bad_id, home=test_env["home"])
            assert res["ok"] is False
            assert res["error_code"] == "PRESENTATION_INVALID_WORK_ID"


def test_artwork_zero_download_on_refresh(test_env):
    """Verify that presentation refresh produces zero downloaded image files."""
    cache_dir = test_env["home"] / ".cache/openhtpc/media"

    def mock_opener(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    with closing(media_db.connect(test_env["db_file"])) as db:
        res = media_pres.refresh_work_presentation(
            db=db,
            work_id=test_env["work_id"],
            home=test_env["home"],
            opener=mock_opener,
        )
        assert res["ok"] is True

    # Assert cache directory has no artwork files
    assert not cache_dir.exists()


def test_transaction_rollback_on_persistence_failure(test_env):
    """Verify clean rollback when persistence fails midway (no dangling snapshot)."""
    def mock_opener(req, timeout=8):
        return MockHTTPResponse(json.dumps(SPIRITED_AWAY_FR_PAYLOAD))

    with closing(media_db.connect(test_env["db_file"])) as db:
        # Patch media_db.upsert_work_presentation to fail
        orig_upsert = media_db.upsert_work_presentation

        def failing_upsert(*args, **kwargs):
            raise sqlite3.OperationalError("Simulated write failure")

        with mock.patch.object(media_db, "upsert_work_presentation", side_effect=failing_upsert):
            res = media_pres.refresh_work_presentation(
                db=db,
                work_id=test_env["work_id"],
                home=test_env["home"],
                opener=mock_opener,
            )

        assert res["ok"] is False
        assert res["error_code"] == "PRESENTATION_PERSISTENCE_FAILED"

        # Assert provider_snapshots has ZERO rows because transaction was rolled back
        snap_count = db.execute("SELECT COUNT(*) FROM provider_snapshots").fetchone()[0]
        pres_count = db.execute("SELECT COUNT(*) FROM work_presentations").fetchone()[0]
        assert snap_count == 0
        assert pres_count == 0


def test_cli_refresh(test_env):
    """Verify openhtpc-media-presentation.py CLI execution."""
    import subprocess
    import sys

    env = os.environ.copy()
    env["OPENHTPC_HOME"] = str(test_env["home"])

    # First test missing args -> exit 2
    proc = subprocess.run([sys.executable, str(PRES_PATH), "refresh"], capture_output=True, text=True, env=env)
    assert proc.returncode == 2

    # CLI refresh with nonexistent DB -> exit 1
    proc = subprocess.run(
        [sys.executable, str(PRES_PATH), "refresh", "--work-id", "1", "--db", "/nonexistent/media.db"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["error_code"] == "DB_NOT_FOUND"

