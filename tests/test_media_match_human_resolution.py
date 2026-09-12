# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV5C1: Human Identity Resolution Core.

Verifies the 58 contract invariants for:
- Listing candidates and revision envelope
- Status with candidate state counts and revision
- Zero network calls on listing, status, accept, replace, and reject
- Authority model: Automation never overrides USER_MATCHED; human authority overrides thresholds
- Defect #1 fix: At most one ACCEPTED candidate; PENDING/ACCEPTED/SUPERSEDED become SUPERSEDED; REJECTED preserved
- Defect #2 fix: Prevent silent overwrite of AUTO_MATCHED/USER_MATCHED without --replace
- Auto-match confirmation of same work without --replace
- Concurrency guard: Candidate set revision hash and --expected-revision guard
- Reject semantics ("None of these") and NO_PENDING_CANDIDATES handling
- CLI syntax: candidates, accept, replace, reject with appropriate exit codes and JSON envelopes
- Transactional atomicity under database operational errors
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
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


def _insert_candidate(
    db: sqlite3.Connection,
    media_version_id: int,
    provider: str = "tmdb",
    external_id: str = "101",
    title: str = "Test Movie",
    year: int | None = 2020,
    score: float = 90.0,
    status: str = "PENDING",
    original_title: str | None = "Original Test Movie",
    runtime_minutes: int | None = 120,
    created_at: str = "2026-09-12T12:00:00Z",
) -> int:
    """Helper to directly insert a candidate row into match_candidates."""
    payload = {
        "title": title,
        "original_title": original_title,
        "year": year,
        "runtime_minutes": runtime_minutes,
    }
    cur = db.execute(
        """
        INSERT INTO match_candidates (
            media_version_id, provider, external_id, candidate_title, candidate_year,
            candidate_payload_json, score, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            media_version_id,
            provider,
            external_id,
            title,
            year,
            json.dumps(payload),
            score,
            status,
            created_at,
        ),
    )
    return cur.lastrowid


# ─── 1. Listing Stored Candidates Ordered by Score DESC, ID ASC ───────────────

def test_01_listing_stored_candidates_ordered(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieA.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="1", score=70.0)
            c2 = _insert_candidate(db, mv_id, external_id="2", score=95.0)
            c3 = _insert_candidate(db, mv_id, external_id="3", score=85.0)
            c4 = _insert_candidate(db, mv_id, external_id="4", score=85.0)

        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 4
        # Score DESC, ID ASC
        assert [c["id"] for c in cands] == [c2, c3, c4, c1]
        assert [c["score"] for c in cands] == [95.0, 85.0, 85.0, 70.0]


# ─── 2. Candidates Envelope Includes candidate_set_revision ────────────────────

def test_02_candidates_envelope_includes_candidate_set_revision(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieB.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="10")
            expected_rev = media_match.compute_candidate_set_revision(db, mv_id)

    rc = media_match.main(["--db", str(sandbox["db_file"]), "candidates", "--media-version-id", str(mv_id)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["media_version_id"] == mv_id
    assert out["candidate_set_revision"] == expected_rev
    assert len(out["candidate_set_revision"]) == 64
    assert len(out["candidates"]) == 1


# ─── 3. Candidates List Includes Extended Fields ───────────────────────────────

def test_03_candidates_list_includes_extended_fields(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieC.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(
                db,
                mv_id,
                provider="tmdb",
                external_id="1917",
                title="1917",
                year=2019,
                score=80.0,
                status="PENDING",
                original_title="1917",
                runtime_minutes=119,
            )
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 1
        cand = cands[0]
        assert cand["id"] == c_id
        assert cand["provider"] == "tmdb"
        assert cand["external_id"] == "1917"
        assert cand["title"] == "1917"
        assert cand["original_title"] == "1917"
        assert cand["year"] == 2019
        assert cand["runtime_minutes"] == 119
        assert cand["score"] == 80.0
        assert cand["status"] == "PENDING"


# ─── 4. Zero Network Calls on Operations ───────────────────────────────────────

def test_04_zero_network_calls_on_operations(sandbox, monkeypatch):
    def _fail_net(*args, **kwargs):
        raise AssertionError("ILLEGAL NETWORK CALL IN DEV5C1 CORE")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_net)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _fail_net)

    mv_id = _create_and_ingest_resource(sandbox, "MovieNet.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="net_1")

        # Listing candidates
        media_match.get_candidates(db, mv_id)
        # Status
        media_match.get_media_version_status(db, mv_id)
        # Accept
        with db:
            media_match.accept_candidate_by_id(db, mv_id, c_id)
        # Replace
        with db:
            c2_id = _insert_candidate(db, mv_id, external_id="net_2")
            media_match.accept_candidate_by_id(db, mv_id, c2_id, replace=True)


# ─── 5. Status Returns Counts for All Statuses ────────────────────────────────

def test_05_status_returns_counts_for_all_statuses(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCounts.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="1", status="PENDING")
            _insert_candidate(db, mv_id, external_id="2", status="PENDING")
            _insert_candidate(db, mv_id, external_id="3", status="ACCEPTED")
            _insert_candidate(db, mv_id, external_id="4", status="REJECTED")
            _insert_candidate(db, mv_id, external_id="5", status="SUPERSEDED")

        st = media_match.get_media_version_status(db, mv_id)
        assert st["ok"] is True
        assert st["pending_candidates_count"] == 2
        assert st["accepted_candidates_count"] == 1
        assert st["rejected_candidates_count"] == 1
        assert st["superseded_candidates_count"] == 1
        assert st["total_candidates_count"] == 5


# ─── 6. Status Returns candidate_set_revision ─────────────────────────────────

def test_06_status_returns_candidate_set_revision(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRev.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert "candidate_set_revision" in st
        assert len(st["candidate_set_revision"]) == 64


# ─── 7. Accept Candidate Sets identification_state = 'USER_MATCHED' ───────────

def test_07_accept_candidate_sets_identification_state_user_matched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="701")
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "USER_MATCHED"


# ─── 8. Accept Candidate Sets match_locked = 1 ────────────────────────────────

def test_08_accept_candidate_sets_match_locked_1(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieLock.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="801")
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert res["match_locked"] == 1
        st = media_match.get_media_version_status(db, mv_id)
        assert st["match_locked"] == 1


# ─── 9. Accept Candidate Sets match_method = 'USER_CONFIRMATION' ──────────────

def test_09_accept_candidate_sets_match_method_user_confirmation(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieMethod.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="901")
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert res["match_method"] == "USER_CONFIRMATION"
        st = media_match.get_media_version_status(db, mv_id)
        assert st["match_method"] == "USER_CONFIRMATION"


# ─── 10. Accept Candidate Creates Work Row If None Existed ────────────────────

def test_10_accept_candidate_creates_work_row_if_none_existed(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieWork.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="1001", title="Alien", year=1979)
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        assert res["work_reused"] is False
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1
        w = db.execute("SELECT title, year, work_type FROM works WHERE id = ?", (res["work_id"],)).fetchone()
        assert w == ("Alien", 1979, "MOVIE")


# ─── 11. Accept Candidate Reuses Existing Work Row ────────────────────────────

def test_11_accept_candidate_reuses_existing_work_row(sandbox):
    mv1 = _create_and_ingest_resource(sandbox, "MovieReuse1.mkv")
    mv2 = _create_and_ingest_resource(sandbox, "MovieReuse2.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv1, provider="tmdb", external_id="1101", title="Dune", year=2021)
            c2 = _insert_candidate(db, mv2, provider="tmdb", external_id="1101", title="Dune", year=2021)
            res1 = media_match.accept_candidate_by_id(db, mv1, c1)
            res2 = media_match.accept_candidate_by_id(db, mv2, c2)

        assert res1["work_reused"] is False
        assert res2["work_reused"] is True
        assert res1["work_id"] == res2["work_id"]
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1


# ─── 12. Accept Candidate Links external_ids Table ─────────────────────────────

def test_12_accept_candidate_links_external_ids_table(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieExtId.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, provider="tmdb", external_id="1201")
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        ext = db.execute(
            "SELECT work_id, provider, external_id FROM external_ids WHERE work_id = ?",
            (res["work_id"],),
        ).fetchone()
        assert ext == (res["work_id"], "tmdb", "1201")


# ─── 13. Accept Candidate Updates media_versions.work_id ───────────────────────

def test_13_accept_candidate_updates_media_versions_work_id(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieUpdateWId.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="1301")
            res = media_match.accept_candidate_by_id(db, mv_id, c_id)
        actual_wid = db.execute("SELECT work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert actual_wid == res["work_id"]


# ─── 14. Accept Candidate Leaves media_streams Untouched ───────────────────────

def test_14_accept_candidate_leaves_media_streams_untouched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieStreams.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res_id = db.execute("SELECT id FROM resources WHERE media_version_id = ?", (mv_id,)).fetchone()[0]
        v_streams_before = db.execute("SELECT * FROM video_streams WHERE resource_id = ? ORDER BY id", (res_id,)).fetchall()
        a_streams_before = db.execute("SELECT * FROM audio_streams WHERE resource_id = ? ORDER BY id", (res_id,)).fetchall()
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="1401")
            media_match.accept_candidate_by_id(db, mv_id, c_id)
        v_streams_after = db.execute("SELECT * FROM video_streams WHERE resource_id = ? ORDER BY id", (res_id,)).fetchall()
        a_streams_after = db.execute("SELECT * FROM audio_streams WHERE resource_id = ? ORDER BY id", (res_id,)).fetchall()
        assert v_streams_before == v_streams_after
        assert a_streams_before == a_streams_after


# ─── 15. Accept Candidate Leaves Resources Untouched ───────────────────────────

def test_15_accept_candidate_leaves_resources_untouched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieResource.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res_before = db.execute("SELECT * FROM resources WHERE media_version_id = ?", (mv_id,)).fetchall()
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="1501")
            media_match.accept_candidate_by_id(db, mv_id, c_id)
        res_after = db.execute("SELECT * FROM resources WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert res_before == res_after


# ─── 16. Accept Candidate on Non-Existent media_version Returns Error ───────────

def test_16_accept_candidate_non_existent_media_version_returns_error(sandbox):
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.accept_candidate_by_id(db, 999999, 1)
        assert res["ok"] is False
        assert res["error"] == "MEDIA_VERSION_NOT_FOUND"


# ─── 17. Accept Candidate on Non-Existent Candidate Returns Error ──────────────

def test_17_accept_candidate_non_existent_candidate_returns_error(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieNoCand.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.accept_candidate_by_id(db, mv_id, 999999)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_NOT_FOUND"


# ─── 18. Accept Candidate with Mismatched media_version_id Returns Error ───────

def test_18_accept_candidate_with_mismatched_media_version_id_returns_error(sandbox):
    mv1 = _create_and_ingest_resource(sandbox, "MovieMis1.mkv")
    mv2 = _create_and_ingest_resource(sandbox, "MovieMis2.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv1, external_id="1801")
        res = media_match.accept_candidate_by_id(db, mv2, c1)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_MISMATCH"


# ─── 19. Accept Candidate When AUTO_MATCHED Different Work Requires Replace ────

def test_19_accept_candidate_when_already_auto_matched_different_work_requires_replace(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieAutoGuard.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="1901", title="Original Work")
            c2 = _insert_candidate(db, mv_id, external_id="1902", title="Different Work")
            media_match.accept_candidate(db, mv_id, media_match.MovieCandidate("tmdb", "1901", "Original Work", None, 2020), score=90.0, mode="AUTO")

        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "AUTO_MATCHED"

        # Attempt to accept c2 without replace
        res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=False)
        assert res["ok"] is False
        assert res["error"] == "REPLACEMENT_CONFIRMATION_REQUIRED"


# ─── 20. Accept Candidate When USER_MATCHED Different Work Requires Replace ────

def test_20_accept_candidate_when_already_user_matched_different_work_requires_replace(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieUserGuard.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2001", title="User Work 1")
            c2 = _insert_candidate(db, mv_id, external_id="2002", title="User Work 2")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=False)
        assert res["ok"] is False
        assert res["error"] == "REPLACEMENT_CONFIRMATION_REQUIRED"


# ─── 21. Accept Candidate When AUTO_MATCHED with SAME Work Succeeds ────────────

def test_21_accept_candidate_when_already_auto_matched_same_work_succeeds_without_replace(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieAutoConfirm.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2101", title="Confirm Work", status="ACCEPTED")
            cand = media_match.MovieCandidate("tmdb", "2101", "Confirm Work", None, 2020)
            media_match.accept_candidate(db, mv_id, cand, score=85.0, mode="AUTO")

        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "AUTO_MATCHED"
        assert st["match_locked"] == 0

        # Human confirms the exact same candidate without --replace
        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c1, replace=False)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["match_locked"] == 1
        assert res["match_method"] == "USER_CONFIRMATION"


# ─── 22. Accept Candidate When USER_MATCHED with SAME Work Succeeds ────────────

def test_22_accept_candidate_when_already_user_matched_same_work_succeeds_without_replace(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieUserReconfirm.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2201", title="Same User Work")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c1, replace=False)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"


# ─── 23. Replace Candidate with --replace Succeeds on AUTO_MATCHED ─────────────

def test_23_replace_candidate_with_replace_succeeds_on_auto_matched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieAutoReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2301", title="Old Auto")
            c2 = _insert_candidate(db, mv_id, external_id="2302", title="New Replaced")
            media_match.accept_candidate(db, mv_id, media_match.MovieCandidate("tmdb", "2301", "Old Auto", None, 2020), score=80.0, mode="AUTO")

        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["match_locked"] == 1
        assert res["title"] == "New Replaced"


# ─── 24. Replace Candidate with --replace Succeeds on USER_MATCHED ─────────────

def test_24_replace_candidate_with_replace_succeeds_on_user_matched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieUserReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2401", title="User Pick 1")
            c2 = _insert_candidate(db, mv_id, external_id="2402", title="User Pick 2")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["title"] == "User Pick 2"


# ─── 25. Replace Candidate Updates media_versions.work_id to New Work ──────────

def test_25_replace_candidate_updates_media_versions_work_id_to_new_work(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieNewWorkId.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2501", title="Work A")
            c2 = _insert_candidate(db, mv_id, external_id="2502", title="Work B")
            res1 = media_match.accept_candidate_by_id(db, mv_id, c1)
            old_wid = res1["work_id"]

            res2 = media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)
            new_wid = res2["work_id"]

        assert old_wid != new_wid
        curr_wid = db.execute("SELECT work_id FROM media_versions WHERE id = ?", (mv_id,)).fetchone()[0]
        assert curr_wid == new_wid


# ─── 26. Replace Candidate Keeps Sibling media_versions on Old Work Untouched ──

def test_26_replace_candidate_keeps_sibling_media_versions_on_old_work_untouched(sandbox):
    mv1 = _create_and_ingest_resource(sandbox, "SiblingA.mkv")
    mv2 = _create_and_ingest_resource(sandbox, "SiblingB.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1_1 = _insert_candidate(db, mv1, provider="tmdb", external_id="2601", title="Shared Work")
            c2_1 = _insert_candidate(db, mv2, provider="tmdb", external_id="2601", title="Shared Work")
            c1_2 = _insert_candidate(db, mv1, provider="tmdb", external_id="2602", title="Isolated Work")
            res1 = media_match.accept_candidate_by_id(db, mv1, c1_1)
            res2 = media_match.accept_candidate_by_id(db, mv2, c2_1)
            shared_wid = res1["work_id"]
            assert res2["work_id"] == shared_wid

            # Now replace mv1 only
            media_match.accept_candidate_by_id(db, mv1, c1_2, replace=True)

        mv2_st = media_match.get_media_version_status(db, mv2)
        assert mv2_st["work_id"] == shared_wid
        assert mv2_st["identification_state"] == "USER_MATCHED"


# ─── 27. Replace Candidate Does NOT Delete Old Work ────────────────────────────

def test_27_replace_candidate_does_not_delete_old_work(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieNoDeleteWork.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2701", title="Old Retained Work")
            c2 = _insert_candidate(db, mv_id, external_id="2702", title="New Work")
            res1 = media_match.accept_candidate_by_id(db, mv_id, c1)
            old_wid = res1["work_id"]

            media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)

        old_work = db.execute("SELECT id, title FROM works WHERE id = ?", (old_wid,)).fetchone()
        assert old_work is not None
        assert old_work[1] == "Old Retained Work"


# ─── 28. Replace Command CLI Syntax Functions Identically ─────────────────────

def test_28_replace_command_cli_syntax_functions_identically(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLIReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2801", title="Initial Pick")
            c2 = _insert_candidate(db, mv_id, external_id="2802", title="CLI Replace Pick")
            media_match.accept_candidate_by_id(db, mv_id, c1)

    rc = media_match.main([
        "--db", str(sandbox["db_file"]),
        "replace",
        "--media-version-id", str(mv_id),
        "--candidate-id", str(c2),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["title"] == "CLI Replace Pick"
    assert out["identification_state"] == "USER_MATCHED"


# ─── 29. Fix Defect #1: At Most One Candidate Has status = 'ACCEPTED' ──────────

def test_29_fix_defect_1_at_most_one_candidate_has_status_accepted(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieDefect1.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="2901")
            c2 = _insert_candidate(db, mv_id, external_id="2902")
            c3 = _insert_candidate(db, mv_id, external_id="2903")
            media_match.accept_candidate_by_id(db, mv_id, c1)
            media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)

        accepted_count = db.execute(
            "SELECT COUNT(*) FROM match_candidates WHERE media_version_id = ? AND status = 'ACCEPTED'",
            (mv_id,),
        ).fetchone()[0]
        assert accepted_count == 1


# ─── 30. Sibling PENDING Candidates Transition to 'SUPERSEDED' on Accept ───────

def test_30_sibling_pending_candidates_transition_to_superseded_on_accept(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MoviePendingSuperseded.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="3001", status="PENDING")
            c2 = _insert_candidate(db, mv_id, external_id="3002", status="PENDING")
            c3 = _insert_candidate(db, mv_id, external_id="3003", status="PENDING")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        c1_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c1,)).fetchone()[0]
        c2_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c2,)).fetchone()[0]
        c3_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c3,)).fetchone()[0]
        assert c1_st == "ACCEPTED"
        assert c2_st == "SUPERSEDED"
        assert c3_st == "SUPERSEDED"


# ─── 31. Sibling ACCEPTED Candidate Transitions to 'SUPERSEDED' on New Accept ─

def test_31_sibling_accepted_candidate_transitions_to_superseded_on_new_accept(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieAcceptedSuperseded.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="3101", status="PENDING")
            c2 = _insert_candidate(db, mv_id, external_id="3102", status="PENDING")
            media_match.accept_candidate_by_id(db, mv_id, c1)
            # Now accept c2 with replace
            media_match.accept_candidate_by_id(db, mv_id, c2, replace=True)

        c1_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c1,)).fetchone()[0]
        c2_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c2,)).fetchone()[0]
        assert c1_st == "SUPERSEDED"
        assert c2_st == "ACCEPTED"


# ─── 32. Sibling REJECTED Candidates Remain 'REJECTED' on Accept ───────────────

def test_32_sibling_rejected_candidates_remain_rejected_on_accept(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectedPreserved.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="3201", status="PENDING")
            c2 = _insert_candidate(db, mv_id, external_id="3202", status="REJECTED")
            c3 = _insert_candidate(db, mv_id, external_id="3203", status="PENDING")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        c1_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c1,)).fetchone()[0]
        c2_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c2,)).fetchone()[0]
        c3_st = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c3,)).fetchone()[0]
        assert c1_st == "ACCEPTED"
        assert c2_st == "REJECTED"  # Defect #1 invariant: REJECTED preserved
        assert c3_st == "SUPERSEDED"


# ─── 33. Reject Command Transitions All PENDING Candidates to 'REJECTED' ───────

def test_33_reject_command_transitions_all_pending_candidates_to_rejected(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectAll.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="3301", status="PENDING")
            c2 = _insert_candidate(db, mv_id, external_id="3302", status="PENDING")
            res = media_match.reject_candidates(db, mv_id)

        assert res["ok"] is True
        assert res["rejected_count"] == 2
        statuses = [r[0] for r in db.execute("SELECT status FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()]
        assert statuses == ["REJECTED", "REJECTED"]


# ─── 34. Reject Command Leaves identification_state = 'UNMATCHED' ─────────────

def test_34_reject_command_leaves_identification_state_unmatched(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectUnmatched.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="3401", status="PENDING")
            media_match.reject_candidates(db, mv_id)

        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "UNMATCHED"


# ─── 35. Reject Command Leaves match_locked = 0 ───────────────────────────────

def test_35_reject_command_leaves_match_locked_0(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectLock0.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="3501", status="PENDING")
            media_match.reject_candidates(db, mv_id)

        st = media_match.get_media_version_status(db, mv_id)
        assert st["match_locked"] == 0


# ─── 36. Reject Command Leaves work_id NULL ───────────────────────────────────

def test_36_reject_command_leaves_work_id_null(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectWorkNull.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="3601", status="PENDING")
            media_match.reject_candidates(db, mv_id)

        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None


# ─── 37. Reject Command Creates Zero Works ────────────────────────────────────

def test_37_reject_command_creates_zero_works(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectZeroWorks.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="3701", status="PENDING")
            media_match.reject_candidates(db, mv_id)

        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0


# ─── 38. Reject Command on Identified media_version Returns Error ──────────────

def test_38_reject_command_on_identified_media_version_returns_error(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectIdentified.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="3801", status="PENDING")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        res = media_match.reject_candidates(db, mv_id)
        assert res["ok"] is False
        assert res["error"] == "REPLACEMENT_CONFIRMATION_REQUIRED"


# ─── 39. Reject Command with 0 Pending Candidates Returns Error ───────────────

def test_39_reject_command_with_0_pending_candidates_returns_no_pending_candidates(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRejectZeroPending.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        res = media_match.reject_candidates(db, mv_id)
        assert res["ok"] is False
        assert res["error"] == "NO_PENDING_CANDIDATES"


# ─── 40. Candidate Set Revision Deterministic and Stable Across Identical Calls ─

def test_40_candidate_set_revision_is_deterministic_and_stable(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevStable.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="4001", score=80.0)
            _insert_candidate(db, mv_id, external_id="4002", score=65.0)

        rev1 = media_match.compute_candidate_set_revision(db, mv_id)
        rev2 = media_match.compute_candidate_set_revision(db, mv_id)
        assert rev1 == rev2
        assert len(rev1) == 64


# ─── 41. Candidate Set Revision Changes When Candidate Status Changes ──────────

def test_41_candidate_set_revision_changes_on_accept(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevChangeAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4101")
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c1)
        rev_after = res["candidate_set_revision"]
        assert rev_before != rev_after


# ─── 42. Candidate Set Revision Changes on Reject ──────────────────────────────

def test_42_candidate_set_revision_changes_on_reject(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevChangeReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="4201")
        rev_before = media_match.compute_candidate_set_revision(db, mv_id)

        with db:
            res = media_match.reject_candidates(db, mv_id)
        rev_after = res["candidate_set_revision"]
        assert rev_before != rev_after


# ─── 43. Accept with Correct --expected-revision Succeeds ──────────────────────

def test_43_accept_with_correct_expected_revision_succeeds(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevCorrectAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4301")
        rev = media_match.compute_candidate_set_revision(db, mv_id)

        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c1, expected_revision=rev)
        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"


# ─── 44. Accept with Stale --expected-revision Returns CANDIDATE_STALE ─────────

def test_44_accept_with_stale_expected_revision_returns_candidate_stale(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevStaleAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4401")

        res = media_match.accept_candidate_by_id(db, mv_id, c1, expected_revision="stale" * 16)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_STALE"


# ─── 45. Replace with Correct --expected-revision Succeeds ─────────────────────

def test_45_replace_with_correct_expected_revision_succeeds(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevCorrectReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4501", title="Initial")
            c2 = _insert_candidate(db, mv_id, external_id="4502", title="Replacement")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        rev = media_match.compute_candidate_set_revision(db, mv_id)
        with db:
            res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=True, expected_revision=rev)
        assert res["ok"] is True
        assert res["title"] == "Replacement"


# ─── 46. Replace with Stale --expected-revision Returns CANDIDATE_STALE ────────

def test_46_replace_with_stale_expected_revision_returns_candidate_stale(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevStaleReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4601")
            c2 = _insert_candidate(db, mv_id, external_id="4602")
            media_match.accept_candidate_by_id(db, mv_id, c1)

        res = media_match.accept_candidate_by_id(db, mv_id, c2, replace=True, expected_revision="stale" * 16)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_STALE"


# ─── 47. Reject with Correct --expected-revision Succeeds ──────────────────────

def test_47_reject_with_correct_expected_revision_succeeds(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevCorrectReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="4701")
        rev = media_match.compute_candidate_set_revision(db, mv_id)

        with db:
            res = media_match.reject_candidates(db, mv_id, expected_revision=rev)
        assert res["ok"] is True
        assert res["action"] == "rejected"


# ─── 48. Reject with Stale --expected-revision Returns CANDIDATE_STALE ─────────

def test_48_reject_with_stale_expected_revision_returns_candidate_stale(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRevStaleReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="4801")

        res = media_match.reject_candidates(db, mv_id, expected_revision="stale" * 16)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_STALE"


# ─── 49. Database Error During Accept Rolls Back Atomically ───────────────────

def test_49_database_error_during_accept_rolls_back(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRollbackAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="4901")

        # Inject trigger that aborts during media_versions update
        db.execute(
            """
            CREATE TRIGGER fail_mv_update BEFORE UPDATE ON media_versions
            BEGIN
                SELECT RAISE(ABORT, 'Simulated database failure during media_versions update');
            END;
            """
        )

        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError), match="Simulated database failure"):
            with db:
                media_match.accept_candidate_by_id(db, mv_id, c1)

        # Invariant check after rollback:
        # 1. No work was committed
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0
        # 2. Candidate remains PENDING
        c_status = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c1,)).fetchone()[0]
        assert c_status == "PENDING"
        # 3. media_version remains UNMATCHED and work_id is None
        st = media_match.get_media_version_status(db, mv_id)
        assert st["work_id"] is None
        assert st["identification_state"] == "UNMATCHED"


# ─── 50. Database Error During Reject Rolls Back Atomically ───────────────────

def test_50_database_error_during_reject_rolls_back(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieRollbackReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="5001")

        # Inject trigger that aborts when updating media_versions
        db.execute(
            """
            CREATE TRIGGER fail_mv_reject BEFORE UPDATE OF updated_at ON media_versions
            BEGIN
                SELECT RAISE(ABORT, 'Simulated write error during reject');
            END;
            """
        )

        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError), match="Simulated write error"):
            with db:
                media_match.reject_candidates(db, mv_id)

        # Invariant check after rollback: candidate status is still PENDING
        c_status = db.execute("SELECT status FROM match_candidates WHERE id = ?", (c1,)).fetchone()[0]
        assert c_status == "PENDING"


# ─── 51. Human Accept Overrides Low Score (< 80) ──────────────────────────────

def test_51_human_accept_overrides_low_score(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieLowScore.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            # Score 15.0 is far below auto-match gate of 80.0
            c1 = _insert_candidate(db, mv_id, external_id="5101", title="Obscure Movie", score=15.0)
            res = media_match.accept_candidate_by_id(db, mv_id, c1)

        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["match_locked"] == 1
        assert res["match_confidence"] == 15.0


# ─── 52. Human Accept Overrides Small Margin (< 20) ───────────────────────────

def test_52_human_accept_overrides_small_margin(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieSmallMargin.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            # Score 80 vs 75 -> margin is 5.0 (below required 20.0 for auto-match)
            c1 = _insert_candidate(db, mv_id, external_id="5201", title="Tied 1", score=80.0)
            c2 = _insert_candidate(db, mv_id, external_id="5202", title="Tied 2", score=75.0)
            res = media_match.accept_candidate_by_id(db, mv_id, c1)

        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["match_locked"] == 1


# ─── 53. Human Accept Overrides No-Year Candidate ─────────────────────────────

def test_53_human_accept_overrides_no_year_candidate(sandbox):
    mv_id = _create_and_ingest_resource(sandbox, "MovieNoYear.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="5301", title="No Year Movie", year=None, score=50.0)
            res = media_match.accept_candidate_by_id(db, mv_id, c1)

        assert res["ok"] is True
        assert res["identification_state"] == "USER_MATCHED"
        assert res["year"] is None
        w_year = db.execute("SELECT year FROM works WHERE id = ?", (res["work_id"],)).fetchone()[0]
        assert w_year is None


# ─── 54. CLI candidates Command Prints Valid JSON Envelope ─────────────────────

def test_54_cli_candidates_command_prints_valid_json_envelope(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLICands.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="5401", title="CLI Movie")

    rc = media_match.main(["--db", str(sandbox["db_file"]), "candidates", "--media-version-id", str(mv_id)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["media_version_id"] == mv_id
    assert "candidate_set_revision" in payload
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["title"] == "CLI Movie"


# ─── 55. CLI status Command Prints Valid JSON with Revision and Status Counts ──

def test_55_cli_status_command_prints_valid_json_with_revision_and_status_counts(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLIStatus.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="5501", status="PENDING")

    rc = media_match.main(["--db", str(sandbox["db_file"]), "status", "--media-version-id", str(mv_id)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["pending_candidates_count"] == 1
    assert payload["accepted_candidates_count"] == 0
    assert payload["rejected_candidates_count"] == 0
    assert payload["superseded_candidates_count"] == 0
    assert payload["total_candidates_count"] == 1
    assert "candidate_set_revision" in payload


# ─── 56. CLI accept Command Returns Exit Code 0 on Success ────────────────────

def test_56_cli_accept_command_returns_exit_code_0_on_success(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLIAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c_id = _insert_candidate(db, mv_id, external_id="5601", title="Accepted Film")

    rc = media_match.main([
        "--db", str(sandbox["db_file"]),
        "accept",
        "--media-version-id", str(mv_id),
        "--candidate-id", str(c_id),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["identification_state"] == "USER_MATCHED"
    assert out["match_locked"] == 1


# ─── 57. CLI accept Command Returns Exit Code 1 on Replacement Required ───────

def test_57_cli_accept_command_returns_exit_code_1_on_replacement_confirmation_required(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLIAcceptConflict.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            c1 = _insert_candidate(db, mv_id, external_id="5701", title="Winner 1")
            c2 = _insert_candidate(db, mv_id, external_id="5702", title="Winner 2")
            media_match.accept_candidate_by_id(db, mv_id, c1)

    # Attempt CLI accept of c2 without --replace
    rc = media_match.main([
        "--db", str(sandbox["db_file"]),
        "accept",
        "--media-version-id", str(mv_id),
        "--candidate-id", str(c2),
    ])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["error"] == "REPLACEMENT_CONFIRMATION_REQUIRED"


# ─── 58. CLI reject Command Exit Codes ────────────────────────────────────────

def test_58_cli_reject_command_exit_codes(sandbox, capsys):
    mv_id = _create_and_ingest_resource(sandbox, "MovieCLIReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            _insert_candidate(db, mv_id, external_id="5801", status="PENDING")

    # First reject: succeeds (exit code 0)
    rc1 = media_match.main([
        "--db", str(sandbox["db_file"]),
        "reject",
        "--media-version-id", str(mv_id),
    ])
    assert rc1 == 0
    out1 = json.loads(capsys.readouterr().out)
    assert out1["ok"] is True
    assert out1["action"] == "rejected"
    assert out1["rejected_count"] == 1

    # Second reject: no pending candidates left (exit code 1)
    rc2 = media_match.main([
        "--db", str(sandbox["db_file"]),
        "reject",
        "--media-version-id", str(mv_id),
    ])
    assert rc2 == 1
    out2 = json.loads(capsys.readouterr().out)
    assert out2["ok"] is False
    assert out2["error"] == "NO_PENDING_CANDIDATES"
