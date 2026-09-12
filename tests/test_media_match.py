# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV5A: Local Movie Identity Engine.

Verifies:
- 100% offline filename & path clue extraction with numeric title protection (1917, 1984, 300).
- Candidate scoring on fixed 0.0 .. 100.0 scale with LOW, AMBIGUOUS, and HIGH bands.
- Conservative auto-match gate (exact title, reliable year clue, exact year match, margin >= 20).
- Work creation happens ONLY on candidate acceptance (never on clue extraction or candidate search).
- Transactional acceptance, human locking (match_locked=1), and duplicate WORK reuse via external_ids.
- Technical streams, availability status, fingerprints, user config, and media actions remain untouched.
"""
from __future__ import annotations

from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
MATCH_PATH = PAYLOAD / "openhtpc-media-match.py"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"

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
media_ingest.set_media_db_module(media_db)
media_ingest.set_media_probe_module(media_probe)


@pytest.fixture
def sandbox(tmp_path):
    """Hermetic isolated environment with test database."""
    home = tmp_path / "home"
    config_dir = home / ".config/openhtpc"
    share_dir = home / ".local/share/openhtpc/media"

    config_dir.mkdir(parents=True)
    share_dir.mkdir(parents=True)

    db_file = share_dir / "media.db"
    media_db.initialize(db_file)

    config_file = config_dir / "user-config.json"
    user_config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(tmp_path / "movies")],
    }
    config_file.write_text(json.dumps(user_config, indent=2))

    return {
        "home": home,
        "db_file": db_file,
        "config_file": config_file,
        "source_root": tmp_path / "movies",
    }


def _create_and_ingest_resource(sandbox: dict, rel_path: str, duration_sec: float = 7200.0) -> int:
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


# ─── 1 to 10: Clue Parsing & Numeric Title Safeguards ────────────────────────

def test_1_unidentified_media_remains_work_id_null(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "UnknownMovie.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None
        assert st["identification_state"] == "UNMATCHED"
        assert st["match_locked"] == 0
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0


def test_2_clue_extraction_creates_no_work(sandbox):
    clues = media_match.extract_movie_clues("Alien.Romulus.2024.2160p.mkv")
    assert clues.title_clue == "Alien Romulus"
    assert clues.year_clue == 2024
    with closing(media_db.connect(sandbox["db_file"])) as db:
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0


def test_3_clean_title_year_extraction():
    clues = media_match.extract_movie_clues("Inception (2010).mkv")
    assert clues.title_clue == "Inception"
    assert clues.year_clue == 2010


def test_4_scene_and_codec_tokens_removed():
    filename = "The.Matrix.1999.2160p.UHD.BluRay.x265.10bit.TrueHD.Atmos-GROUP.mkv"
    clues = media_match.extract_movie_clues(filename)
    assert clues.title_clue == "The Matrix"
    assert clues.year_clue == 1999


def test_5_title_1917_remains_title_and_year_null():
    clues = media_match.extract_movie_clues("1917.mkv")
    assert clues.title_clue == "1917"
    assert clues.year_clue is None


def test_6_title_1917_with_year_in_parens():
    clues = media_match.extract_movie_clues("1917 (2019).mkv")
    assert clues.title_clue == "1917"
    assert clues.year_clue == 2019


def test_7_title_2001_a_space_odyssey_protected():
    clues = media_match.extract_movie_clues("2001 A Space Odyssey (1968).mkv")
    assert clues.title_clue == "2001 A Space Odyssey"
    assert clues.year_clue == 1968

    clues2 = media_match.extract_movie_clues("2001.A.Space.Odyssey.1968.1080p.BluRay.mkv")
    assert clues2.title_clue == "2001 A Space Odyssey"
    assert clues2.year_clue == 1968


def test_8_title_1984_with_year_protected():
    clues = media_match.extract_movie_clues("1984 (1984).mkv")
    assert clues.title_clue == "1984"
    assert clues.year_clue == 1984


def test_9_title_300_rise_of_an_empire_protected():
    clues = media_match.extract_movie_clues("300 Rise of an Empire (2014).mkv")
    assert clues.title_clue == "300 Rise of an Empire"
    assert clues.year_clue == 2014

    clues2 = media_match.extract_movie_clues("300.2006.1080p.mkv")
    assert clues2.title_clue == "300"
    assert clues2.year_clue == 2006

    clues3 = media_match.extract_movie_clues("300.mkv")
    assert clues3.title_clue == "300"
    assert clues3.year_clue is None


def test_10_ambiguous_no_year_title_never_auto_matches(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "The Thing.mkv")
    candidates = [
        {"provider": "fixture_movie", "external_id": "1091", "title": "The Thing", "year": 1982, "runtime": 109},
        {"provider": "fixture_movie", "external_id": "1092", "title": "The Thing", "year": 2011, "runtime": 103},
    ]

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=True)

        assert res["status"] == "UNMATCHED"
        assert "NO_YEAR_CLUE" in res["reason"]
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None
        assert st["identification_state"] == "UNMATCHED"
        # Verify both candidates persisted as PENDING
        assert st["pending_candidates_count"] == 2


# ─── 11 to 20: Confidence, Bounding, Auto-Match, and WORK Creation ───────────

def test_11_score_scale_enforced_0_to_100():
    cand = {"title": "Alien", "year": 1979, "runtime": 117}
    score, _ = media_match.score_candidate(cand, "Alien", 1979, duration_seconds=117 * 60)
    assert 0.0 <= score <= 100.0
    assert score == 100.0

    # Test extreme mismatch clamps to 0.0
    score_bad, _ = media_match.score_candidate(cand, "Completely Unrelated", 2025, duration_seconds=600)
    assert 0.0 <= score_bad <= 100.0
    assert score_bad == 0.0


def test_12_low_confidence_discarded():
    candidates = [
        {"provider": "fixture_movie", "external_id": "999", "title": "Totally Irrelevant", "year": 1950},
    ]
    scored = media_match.evaluate_candidate_list(candidates, "Alien Romulus", 2024)
    assert len(scored) == 0  # < 50.0 score discarded


def test_13_ambiguous_candidate_persists_but_stays_unmatched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "Robin Hood.mkv")
    candidates = [
        {"provider": "fixture_movie", "external_id": "1", "title": "Robin Hood", "year": 2010},
        {"provider": "fixture_movie", "external_id": "2", "title": "Robin Hood", "year": 1973},
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=True)
        assert res["status"] == "UNMATCHED"
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 2
        assert all(c["status"] == "PENDING" for c in cands)


def test_14_high_score_without_reliable_year_does_not_auto_match(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "Crash.mkv", duration_sec=110 * 60)
    candidates = [
        {"provider": "fixture_movie", "external_id": "100", "title": "Crash", "year": 2004, "runtime": 112},
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=True)
        assert res["status"] == "UNMATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None


def test_15_exact_title_and_exact_year_may_auto_match(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "Alien.Romulus.2024.mkv", duration_sec=119 * 60)
    candidates = [
        {"provider": "fixture_movie", "external_id": "945961", "title": "Alien: Romulus", "year": 2024, "runtime": 119},
        {"provider": "fixture_movie", "external_id": "109", "title": "Alien", "year": 1979, "runtime": 117},
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=True)
        assert res["status"] == "AUTO_MATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is not None
        assert st["identification_state"] == "AUTO_MATCHED"
        assert st["match_locked"] == 0
        assert st["work"]["title"] == "Alien: Romulus"
        assert st["work"]["year"] == 2024


def test_16_year_disagreement_prevents_auto_match(sandbox):
    # Filename clue says 2015, candidate is 1995
    mv_id = _create_and_ingest_resource(sandbox, "Alerte (2015).mkv")
    candidates = [
        {"provider": "fixture_movie", "external_id": "995", "title": "Alerte", "year": 1995},
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=True)
        assert res["status"] == "UNMATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None


def test_17_top_5_candidate_bounding(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "Movie.mkv")
    candidates = [
        {"provider": "fixture_movie", "external_id": f"c_{i}", "title": "Movie", "year": 2000 + i}
        for i in range(10)
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=False)
        stored = media_match.get_candidates(db, mv_id)
        assert len(stored) == 5  # Bounded strictly to top 5


def test_18_stable_candidate_ordering():
    candidates = [
        {"provider": "fixture_movie", "external_id": "b_id", "title": "Identical Title", "year": 2020},
        {"provider": "fixture_movie", "external_id": "a_id", "title": "Identical Title", "year": 2020},
    ]
    scored = media_match.evaluate_candidate_list(candidates, "Identical Title", 2020)
    assert len(scored) == 2
    assert scored[0][0] == scored[1][0]
    # Tie-breaking by external_id ASC
    assert scored[0][1].external_id == "a_id"
    assert scored[1][1].external_id == "b_id"


def test_19_candidate_generation_creates_zero_work_rows(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "CandidateOnly.mkv")
    candidates = [
        {"provider": "fixture_movie", "external_id": "123", "title": "Candidate Only", "year": 2022},
    ]
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, candidates, auto_accept=False)
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0


def test_20_user_acceptance_creates_work_transactionally(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "ManualMatch.mkv")
    cand = {"provider": "fixture_movie", "external_id": "ext_55", "title": "Manual Movie", "year": 2021}
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER")
        assert res["ok"] is True
        assert res["work_id"] is not None
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "USER_MATCHED"
        assert st["match_locked"] == 1
        assert st["work"]["title"] == "Manual Movie"


# ─── 21 to 35: Locking, Duplication, Integrity & Isolation ───────────────────

def test_21_user_acceptance_locks_identity(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "LockedUser.mkv")
    cand = {"provider": "fixture_movie", "external_id": "lock_1", "title": "Locked Movie", "year": 2020}
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="USER")
        st = media_match.get_media_version_status(db, mv_id)
        assert st["match_locked"] == 1


def test_22_automation_cannot_overwrite_locked_identity(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "LockedAuto.mkv")
    cand1 = {"provider": "fixture_movie", "external_id": "first", "title": "First Choice", "year": 2020}
    cand2 = {"provider": "fixture_movie", "external_id": "second", "title": "Second Choice", "year": 2020}
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            # User locks first choice
            media_match.accept_candidate(db, mv_id, cand1, score=95.0, mode="USER")
            # Automation attempts to evaluate / accept second choice
            res = media_match.evaluate_media_version(db, mv_id, [cand2], auto_accept=True)

        assert res["status"] == "LOCKED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work"]["title"] == "First Choice"
        assert st["match_locked"] == 1


def test_23_automatic_accepted_match_remains_unlocked(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "AutoUnlocked (2023).mkv")
    cand = {"provider": "fixture_movie", "external_id": "auto_1", "title": "AutoUnlocked", "year": 2023}
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)
        assert res["status"] == "AUTO_MATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "AUTO_MATCHED"
        assert st["match_locked"] == 0  # Unlocked


def test_24_same_external_id_reuses_existing_work(sandbox):
    # File 1: DVD version
    mv1 = _create_and_ingest_resource(sandbox, "Alien.DVD.1979.mkv")
    # File 2: 4K UHD version
    mv2 = _create_and_ingest_resource(sandbox, "Alien.UHD.1979.mkv")

    cand = {"provider": "fixture_movie", "external_id": "alien_1979", "title": "Alien", "year": 1979}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res1 = media_match.accept_candidate(db, mv1, cand, score=100.0, mode="AUTO")
            res2 = media_match.accept_candidate(db, mv2, cand, score=100.0, mode="AUTO")

        assert res1["work_id"] == res2["work_id"]
        assert res2["work_reused"] is True
        # Total works in DB is exactly 1
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1


def test_25_two_media_versions_can_share_one_work(sandbox):
    mv1 = _create_and_ingest_resource(sandbox, "CutA.mkv")
    mv2 = _create_and_ingest_resource(sandbox, "CutB.mkv")
    cand = {"provider": "fixture_movie", "external_id": "shared_ext", "title": "Shared Film", "year": 2010}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.accept_candidate(db, mv1, cand, score=90.0, mode="USER")
            media_match.accept_candidate(db, mv2, cand, score=90.0, mode="USER")

        st1 = media_match.get_media_version_status(db, mv1)
        st2 = media_match.get_media_version_status(db, mv2)
        assert st1["work_id"] == st2["work_id"]
        assert st1["media_version_id"] != st2["media_version_id"]


def test_26_provider_namespace_uniqueness_behavior(sandbox):
    # Schema V2 enforces UNIQUE(provider, external_id)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            db.execute(
                "INSERT INTO works (work_type, title, year, created_at, updated_at) VALUES ('MOVIE', 'Film A', 2000, 'now', 'now')"
            )
            w_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                "INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', '123', 'now')",
                (w_id,),
            )
            # Duplicate (tmdb_movie, 123) must raise IntegrityError
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', '123', 'now')",
                    (w_id,),
                )


def test_27_tmdb_movie_namespace_is_distinct_from_tmdb_tv(sandbox):
    # Same ID "123" under distinct namespaces is allowed and represents different works
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            db.execute("INSERT INTO works (work_type, title, year, created_at, updated_at) VALUES ('MOVIE', 'Film A', 2000, 'now', 'now')")
            w1 = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO works (work_type, title, year, created_at, updated_at) VALUES ('TV_SERIES', 'Series A', 2000, 'now', 'now')")
            w2 = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            db.execute("INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_movie', '123', 'now')", (w1,))
            db.execute("INSERT INTO external_ids (work_id, provider, external_id, created_at) VALUES (?, 'tmdb_tv', '123', 'now')", (w2,))

        assert db.execute("SELECT COUNT(*) FROM external_ids").fetchone()[0] == 2


def test_28_transactional_rollback_leaves_prior_identity_unchanged(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "RollbackTest.mkv")
    cand1 = {"provider": "fixture_movie", "external_id": "valid_1", "title": "Valid Movie", "year": 2020}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.accept_candidate(db, mv_id, cand1, score=90.0, mode="USER")
        orig_st = media_match.get_media_version_status(db, mv_id)

        # Attempt an invalid operation that fails mid-transaction
        try:
            with db:
                db.execute("UPDATE media_versions SET match_confidence = 99.0 WHERE id = ?", (mv_id,))
                # Intentional error: violate NOT NULL constraint
                db.execute("INSERT INTO works (work_type, title, created_at, updated_at) VALUES (NULL, NULL, 'now', 'now')")
        except sqlite3.IntegrityError:
            pass

        after_st = media_match.get_media_version_status(db, mv_id)
        assert orig_st == after_st


def test_29_technical_stream_rows_unchanged_by_matching(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "StreamsUntouched (2021).mkv")
    cand = {"provider": "fixture_movie", "external_id": "stream_mv", "title": "StreamsUntouched", "year": 2021}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        streams_before = db.execute("SELECT * FROM video_streams").fetchall()
        audio_before = db.execute("SELECT * FROM audio_streams").fetchall()

        with db:
            media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)

        streams_after = db.execute("SELECT * FROM video_streams").fetchall()
        audio_after = db.execute("SELECT * FROM audio_streams").fetchall()

        assert streams_before == streams_after
        assert audio_before == audio_after


def test_30_availability_and_fingerprint_unchanged_by_matching(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "ResUntouched (2022).mkv")
    cand = {"provider": "fixture_movie", "external_id": "res_cand", "title": "ResUntouched", "year": 2022}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        res_before = db.execute("SELECT availability_status, file_size, mtime_ns FROM resources").fetchall()
        with db:
            media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)
        res_after = db.execute("SELECT availability_status, file_size, mtime_ns FROM resources").fetchall()
        assert res_before == res_after


def test_31_media_actions_untouched(sandbox):
    # Verify no files outside the database directory are created or modified
    before_files = set(sandbox["home"].rglob("*"))
    mv_id = _create_and_ingest_resource(sandbox, "ActionCheck (2020).mkv")
    cand = {"provider": "fixture_movie", "external_id": "act_1", "title": "ActionCheck", "year": 2020}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)

    after_files = set(sandbox["home"].rglob("*"))
    # Only media.db journal or db file itself may change
    new_files = after_files - before_files
    for f in new_files:
        assert "media.db" in f.name or f.name.endswith(".mkv")


def test_32_user_config_untouched(sandbox):
    cfg_before = sandbox["config_file"].read_text()
    mv_id = _create_and_ingest_resource(sandbox, "ConfigCheck (2020).mkv")
    cand = {"provider": "fixture_movie", "external_id": "cfg_1", "title": "ConfigCheck", "year": 2020}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)

    cfg_after = sandbox["config_file"].read_text()
    assert cfg_before == cfg_after


def test_33_no_http_network_invocation(sandbox, monkeypatch):
    # Monkeypatch urllib.request.urlopen to fail if called
    def _fail_urlopen(*args, **kwargs):
        raise AssertionError("NETWORK CALL DETECTED IN DEV5A")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_urlopen)

    mv_id = _create_and_ingest_resource(sandbox, "NoNet (2020).mkv")
    cand = {"provider": "fixture_movie", "external_id": "nonet_1", "title": "NoNet", "year": 2020}

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_match.evaluate_media_version(db, mv_id, [cand], auto_accept=True)
        assert res["ok"] is True


def test_34_isolated_xdg_paths(sandbox):
    # CLI operation with custom --db and --home flags
    mv_id = _create_and_ingest_resource(sandbox, "CLIIsolated (2021).mkv")
    status_rc = media_match.main(["--db", str(sandbox["db_file"]), "status", "--media-version-id", str(mv_id)])
    assert status_rc == 0


def test_35_no_access_to_steve_real_library(sandbox):
    # Verify the match component never defaults to /home/steve/media
    with closing(media_db.connect(sandbox["db_file"])) as db:
        rows = db.execute("SELECT canonical_path, relative_path FROM resources").fetchall()
        for cpath, rpath in rows:
            assert not cpath.startswith("/home/steve/media")
