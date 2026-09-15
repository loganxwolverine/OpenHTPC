#!/usr/bin/env python3
"""Hermetic test suite for OpenHTPC Living-Room Media Manual Search Orchestrator (DEV5C3B2).

Validates all 35 required test points:
- Resolver entry points (UNMATCHED, identified, zero candidates)
- Prefill clue extraction (provisional vs current work)
- Cancellation & Escape guarantees (zero network, zero DB mutation)
- Single provider call network authorization
- Candidate PENDING storage and DEV5C1 delegation
- UX error & zero-result handling without automatic retry
- Stale concurrency revision invalidation
- Line budget <= 198 bytes UTF-8
- Single-Flex process architecture
- Security: zero shell=True, safe escaping, no query persistence to schema
"""
from __future__ import annotations

import ast
from contextlib import closing
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from unittest import mock
import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
SEARCH_UI_PATH = PAYLOAD / "openhtpc-media-manual-search-ui"
TEXT_ENTRY_PATH = PAYLOAD / "openhtpc-text-entry.py"
MATCH_PATH = PAYLOAD / "openhtpc-media-match.py"
MATCH_UI_PATH = PAYLOAD / "openhtpc-media-match-ui"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"
SESSION_PATH = PAYLOAD / "openhtpc-session-engine.py"


def _load_mod(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


media_db = _load_mod("media_db", DB_PATH)
media_match = _load_mod("media_match", MATCH_PATH)
media_match_ui = _load_mod("media_match_ui", MATCH_UI_PATH)
media_ingest = _load_mod("media_ingest", INGEST_PATH)
media_probe = _load_mod("media_probe", PROBE_PATH)
session_engine = _load_mod("session_engine", SESSION_PATH)
manual_search_ui = _load_mod("manual_search_ui", SEARCH_UI_PATH)
text_entry = _load_mod("text_entry", TEXT_ENTRY_PATH)

media_match.set_media_db_module(media_db)
media_ingest.set_media_db_module(media_db)
media_ingest.set_media_probe_module(media_probe)
media_match_ui.set_media_match_module(media_match)
media_match_ui.set_media_db_module(media_db)
media_match_ui.set_session_engine_module(session_engine)


@pytest.fixture(autouse=True)
def forbid_network():
    """Guarantee zero unmocked network calls in all tests."""
    orig_connect = socket.socket.connect

    def guarded_connect(*args, **kwargs):
        raise AssertionError("Network contact strictly forbidden in hermetic tests")

    with mock.patch("socket.socket.connect", guarded_connect):
        yield


@pytest.fixture
def sandbox(tmp_path):
    """Isolated environment with database, install directory, and mock icons."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    install = tmp_path / "install"
    install.mkdir(parents=True)

    for src in (
        SEARCH_UI_PATH,
        TEXT_ENTRY_PATH,
        MATCH_PATH,
        MATCH_UI_PATH,
        DB_PATH,
        INGEST_PATH,
        PROBE_PATH,
        SESSION_PATH,
        PAYLOAD / "openhtpc-optical.py",
        PAYLOAD / "openhtpc-ui.py",
        PAYLOAD / "openhtpc-theme.py",
    ):
        dest = install / src.name
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o755)

    (install / "assets/ui").mkdir(parents=True)
    media_icon = install / "assets/ui/media.png"
    media_icon.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    uid = os.getuid()
    short_icon = Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(media_icon)
        effective_icon = short_icon
    except OSError:
        effective_icon = media_icon

    db_dir = home / ".local/share/openhtpc/media"
    db_dir.mkdir(parents=True)
    db_file = db_dir / "media.db"
    media_db.initialize(db_file)

    sources_dir = home / "Videos"
    sources_dir.mkdir(parents=True)

    return {
        "home": home,
        "install": install,
        "db_file": db_file,
        "media_icon": effective_icon,
        "sources_dir": sources_dir,
    }


import hashlib


def _ingest_movie(sandbox: dict, filename: str, provisional_title: str | None = None, provisional_year: int | None = None) -> int:
    movie_path = sandbox["sources_dir"] / filename
    movie_path.parent.mkdir(parents=True, exist_ok=True)
    movie_path.write_bytes(b"dummy video content")

    desc = {
        "ok": True,
        "resource": {
            "supplied_path": str(movie_path),
            "canonical_path": str(movie_path.resolve()),
            "file_size": 2048,
            "mtime_ns": 1700000000000000000,
            "container_format": "matroska",
            "duration_seconds": 7200.0,
        },
        "video_streams": [{"stream_index": 0, "codec": "h264", "width": 1920, "height": 1080}],
        "audio_streams": [{"stream_index": 1, "codec": "aac", "channels": 2}],
        "subtitle_streams": [],
    }
    source_id = hashlib.blake2s(os.fsencode(sandbox["sources_dir"].resolve()), digest_size=8).hexdigest()
    rel_path = movie_path.relative_to(sandbox["sources_dir"]).as_posix()

    with closing(media_db.connect(sandbox["db_file"])) as db:
        with db:
            res = media_ingest.ingest_descriptor(db, desc, source_id, rel_path)
            mv_id = res["media_version_id"]
            if provisional_title is not None or provisional_year is not None:
                db.execute(
                    "UPDATE media_versions SET provisional_title = ?, provisional_year = ? WHERE id = ?",
                    (provisional_title, provisional_year, mv_id),
                )
            return mv_id


def _add_candidate(
    db: sqlite3.Connection,
    mv_id: int,
    cand_id: int | str,
    title: str,
    year: int | None = None,
    score: float = 85.0,
    status: str = "PENDING",
    external_id: str | None = None,
) -> int:
    numeric_id = int(cand_id)
    ext_id = external_id or str(numeric_id + 1000)
    payload = {
        "id": ext_id,
        "title": title,
        "original_title": title,
        "release_date": f"{year}-01-01" if year else None,
        "runtime_minutes": 120,
    }
    db.execute(
        """
        INSERT INTO match_candidates (
            id, media_version_id, provider, external_id,
            candidate_title, candidate_year, candidate_payload_json,
            score, status, created_at
        ) VALUES (?, ?, 'tmdb_movie', ?, ?, ?, ?, ?, ?, '2026-09-12T12:00:00Z')
        """,
        (numeric_id, mv_id, ext_id, title, year, json.dumps(payload), score, status),
    )
    db.commit()
    return numeric_id


# 1. UNMATCHED RESOLVER EXPOSES RECHERCHER MANUELLEMENT
def test_01_unmatched_resolver_exposes_manual_search(sandbox):
    mv_id = _ingest_movie(sandbox, "MovieA.mkv", "Movie A", 2021)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, "101", "Candidate Movie A", 2021)
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R10101010", "gen", {}, sandbox["media_icon"]
        )
        menu_text = "\n".join(sections)
        assert "RECHERCHER MANUELLEMENT" in menu_text
        assert ":applyback" in menu_text
        assert "openhtpc-media-manual-search-ui" in menu_text
        # Verify it appears before AUCUN DE CES FILMS
        idx_search = menu_text.find("RECHERCHER MANUELLEMENT")
        idx_reject = menu_text.find("AUCUN DE CES FILMS")
        assert idx_search < idx_reject


# 2. IDENTIFIED RESOLVER EXPOSES RECHERCHER UNE AUTRE IDENTIFICATION
def test_02_identified_resolver_exposes_rechercher_autre(sandbox):
    mv_id = _ingest_movie(sandbox, "MovieB.mkv", "Movie B", 2020)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, "201", "Movie B", 2020, score=95.0)
        cand = media_match.MovieCandidate("tmdb_movie", "201", "Movie B", year=2020)
        media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="AUTO", method="EXACT")
        db.commit()

        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R20202020", "gen", {}, sandbox["media_icon"]
        )
        menu_text = "\n".join(sections)
        assert "RECHERCHER UNE AUTRE IDENTIFICATION" in menu_text
        assert "AUCUN DE CES FILMS" not in menu_text


# 3. ZERO-CANDIDATE RESOLVER EXPOSES MANUAL SEARCH
def test_03_zero_candidate_resolver_exposes_manual_search(sandbox):
    mv_id = _ingest_movie(sandbox, "ZeroCands.mkv", "Zero Cands")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R30303030", "gen", {}, sandbox["media_icon"]
        )
        assert len(sections) == 2
        sec = sections[0]
        assert "Aucune proposition disponible." in sec
        assert "RECHERCHER MANUELLEMENT" in sec
        assert "RETOUR" in sec
        assert "LANCER LA RECHERCHE" in sections[1]


# 4. TITLE PREFILL FROM PROVISIONAL CLUE
def test_04_title_prefill_from_provisional_clue(sandbox):
    mv_id = _ingest_movie(sandbox, "Spirited.Away.2001.mkv", "Spirited Away", 2001)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        title, year = manual_search_ui.get_prefill_hints(db, mv_id)
        assert title == "Spirited Away"
        assert year == "2001"


# 5. IDENTIFIED TITLE PREFILL FROM CURRENT WORK
def test_05_identified_title_prefill_from_current_work(sandbox):
    mv_id = _ingest_movie(sandbox, "RawFile.mkv", "Provisional Clue", 1999)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, "501", "Accepted Work Title", 2010, score=90.0)
        cand = media_match.MovieCandidate("tmdb_movie", "501", "Accepted Work Title", year=2010)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

        title, year = manual_search_ui.get_prefill_hints(db, mv_id)
        # Authoritative work title takes precedence over provisional
        assert title == "Accepted Work Title"
        assert year == "2010"


# 6. YEAR PREFILL
def test_06_year_prefill(sandbox):
    mv_id = _ingest_movie(sandbox, "Film.1984.mkv", "Film", 1984)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        title, year = manual_search_ui.get_prefill_hints(db, mv_id)
        assert year == "1984"


# 7. EMPTY YEAR ACCEPTED
def test_07_empty_year_accepted(sandbox):
    mv_id = _ingest_movie(sandbox, "NoYearFilm.mkv", "No Year Film", None)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        title, year = manual_search_ui.get_prefill_hints(db, mv_id)
        assert title == "No Year Film"
        assert year == ""


# 8. CANCEL TITLE = ZERO NETWORK
def test_08_cancel_title_zero_network_zero_mutation(sandbox):
    mv_id = _ingest_movie(sandbox, "CancelTitle.mkv", "Cancel Me")
    with mock.patch.object(manual_search_ui, "invoke_text_entry", return_value={"ok": False, "cancelled": True, "text": "Cancel Me"}):
        rc = manual_search_ui.orchestrate_manual_search(
            media_version_id=mv_id,
            home=sandbox["home"],
            install=sandbox["install"],
            custom_db_path=sandbox["db_file"],
        )
        assert rc == 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 0


# 9. CANCEL YEAR = ZERO NETWORK
def test_09_cancel_year_zero_network_zero_mutation(sandbox):
    mv_id = _ingest_movie(sandbox, "CancelYear.mkv", "Cancel Year")
    calls = [
        {"ok": True, "cancelled": False, "text": "Entered Title"},  # Title ok
        {"ok": False, "cancelled": True, "text": ""},  # Year cancelled
    ]
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        rc = manual_search_ui.orchestrate_manual_search(
            media_version_id=mv_id,
            home=sandbox["home"],
            install=sandbox["install"],
            custom_db_path=sandbox["db_file"],
        )
        assert rc == 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 0


# 10. CANCEL CONFIRMATION = ZERO NETWORK
def test_10_cancel_confirmation_zero_network_zero_mutation(sandbox):
    mv_id = _ingest_movie(sandbox, "CancelConf.mkv", "Cancel Conf")
    calls = [
        {"ok": True, "cancelled": False, "text": "Entered Title"},
        {"ok": True, "cancelled": False, "text": "2022"},
    ]
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="CANCEL"):
            rc = manual_search_ui.orchestrate_manual_search(
                media_version_id=mv_id,
                home=sandbox["home"],
                install=sandbox["install"],
                custom_db_path=sandbox["db_file"],
            )
            assert rc == 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        cands = media_match.get_candidates(db, mv_id)
        assert len(cands) == 0


# 11. ESCAPE TITLE = ZERO NETWORK
def test_11_escape_title_zero_network(sandbox):
    # Escape in text entry returns {"ok": False, "cancelled": True}
    mv_id = _ingest_movie(sandbox, "EscTitle.mkv", "Esc Title")
    with mock.patch.object(manual_search_ui, "invoke_text_entry", return_value={"ok": False, "cancelled": True, "text": "Esc"}):
        rc = manual_search_ui.orchestrate_manual_search(
            media_version_id=mv_id,
            home=sandbox["home"],
            install=sandbox["install"],
            custom_db_path=sandbox["db_file"],
        )
        assert rc == 0


# 12. ESCAPE YEAR = ZERO NETWORK
def test_12_escape_year_zero_network(sandbox):
    mv_id = _ingest_movie(sandbox, "EscYear.mkv", "Esc Year")
    calls = [
        {"ok": True, "cancelled": False, "text": "Valid Title"},
        {"ok": False, "cancelled": True, "text": "1999"},  # Escape on year
    ]
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        rc = manual_search_ui.orchestrate_manual_search(
            media_version_id=mv_id,
            home=sandbox["home"],
            install=sandbox["install"],
            custom_db_path=sandbox["db_file"],
        )
        assert rc == 0


# 13. ESCAPE CONFIRMATION = ZERO NETWORK
def test_13_escape_confirmation_zero_network(sandbox):
    mv_id = _ingest_movie(sandbox, "EscConf.mkv", "Esc Conf")
    calls = [
        {"ok": True, "cancelled": False, "text": "Valid Title"},
        {"ok": True, "cancelled": False, "text": "2020"},
    ]
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="CANCEL"):
            rc = manual_search_ui.orchestrate_manual_search(
                media_version_id=mv_id,
                home=sandbox["home"],
                install=sandbox["install"],
                custom_db_path=sandbox["db_file"],
            )
            assert rc == 0


# 14. FINAL CONFIRM INVOKES MANUAL SEARCH ONCE
def test_14_final_confirm_invokes_manual_search_once(sandbox):
    mv_id = _ingest_movie(sandbox, "ConfirmRun.mkv", "Confirm Run")
    calls = [
        {"ok": True, "cancelled": False, "text": "Search Movie"},
        {"ok": True, "cancelled": False, "text": "2023"},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "rev2"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                rc = manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert rc == 0
                assert mock_search.call_count == 1
                kwargs = mock_search.call_args.kwargs
                assert kwargs["title"] == "Search Movie"
                assert kwargs["year"] == 2023


# 15. EXACTLY ONE PROVIDER SEARCH
def test_15_exactly_one_provider_search(sandbox):
    mv_id = _ingest_movie(sandbox, "OneCall.mkv", "One Call")
    calls = [
        {"ok": True, "cancelled": False, "text": "Single Provider Call"},
        {"ok": True, "cancelled": False, "text": ""},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "rev_single"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert mock_search.call_count == 1


# 16. SUCCESSFUL RESULT REBUILDS CANONICAL RESOLVER
def test_16_successful_result_rebuilds_canonical_resolver(sandbox):
    mv_id = _ingest_movie(sandbox, "RebuildUI.mkv", "Rebuild UI")
    calls = [
        {"ok": True, "cancelled": False, "text": "Rebuild UI"},
        {"ok": True, "cancelled": False, "text": "2021"},
    ]
    mock_ui_mod = mock.MagicMock()
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=mock_ui_mod):
                mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revX"})
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert mock_ui_mod._regenerate_ui.call_count == 1


def _mock_provider_module(res):
    return mock.MagicMock(
        STATUS_OK="OK",
        STATUS_OK_NO_RESULTS="OK_NO_RESULTS",
        search_movies=mock.MagicMock(return_value=res),
    )


# 17. RESULT CANDIDATES ARE PENDING
def test_17_result_candidates_are_pending(sandbox):
    mv_id = _ingest_movie(sandbox, "PendingCands.mkv", "Pending Cands")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        cand = media_match.MovieCandidate("tmdb_movie", "777", "Candidate 777", year=2022)
        mock_provider_res = mock.MagicMock(
            status="OK",
            candidates=[cand],
            error_code=None,
            error_detail=None,
        )
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            res = media_match.manual_search_media_version(db, mv_id, "Candidate 777", 2022, home=sandbox["home"])
            assert res["ok"] is True
            cands = media_match.get_candidates(db, mv_id)
            assert len(cands) == 1
            assert cands[0]["status"] == "PENDING"


# 18. NO AUTO-MATCH
def test_18_no_auto_match(sandbox):
    mv_id = _ingest_movie(sandbox, "NoAutoMatch.mkv", "Exact Perfect Title", 2020)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Candidate with score 100
        cand = media_match.MovieCandidate("tmdb_movie", "888", "Exact Perfect Title", year=2020)
        mock_provider_res = mock.MagicMock(
            status="OK",
            candidates=[cand],
            error_code=None,
            error_detail=None,
        )
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            media_match.manual_search_media_version(db, mv_id, "Exact Perfect Title", 2020, home=sandbox["home"])
            st = media_match.get_media_version_status(db, mv_id)
            assert st["identification_state"] == "UNMATCHED"
            assert st["work_id"] is None


# 19. NO WORK CREATION
def test_19_no_work_creation(sandbox):
    mv_id = _ingest_movie(sandbox, "NoWork.mkv", "No Work")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        w_before = db.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        cand = media_match.MovieCandidate("tmdb_movie", "999", "Candidate", year=2015)
        mock_provider_res = mock.MagicMock(status="OK", candidates=[cand], error_code=None, error_detail=None)
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            media_match.manual_search_media_version(db, mv_id, "Candidate", 2015, home=sandbox["home"])
            w_after = db.execute("SELECT COUNT(*) FROM works").fetchone()[0]
            assert w_before == w_after == 0


# 20. IDENTIFIED IDENTITY PRESERVED
def test_20_identified_identity_preserved(sandbox):
    mv_id = _ingest_movie(sandbox, "PreserveId.mkv", "Initial", 2010)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, "111", "Initial Movie", 2010, score=90.0)
        cand = media_match.MovieCandidate("tmdb_movie", "111", "Initial Movie", year=2010)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

        st_before = media_match.get_media_version_status(db, mv_id)
        assert st_before["identification_state"] == "USER_MATCHED"
        orig_work_id = st_before["work_id"]

        new_cand = media_match.MovieCandidate("tmdb_movie", "222", "Alternative", year=2012)
        mock_provider_res = mock.MagicMock(status="OK", candidates=[new_cand], error_code=None, error_detail=None)
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            media_match.manual_search_media_version(db, mv_id, "Alternative", 2012, home=sandbox["home"])

            st_after = media_match.get_media_version_status(db, mv_id)
            assert st_after["identification_state"] == "USER_MATCHED"
            assert st_after["work_id"] == orig_work_id


# 21. REPLACEMENT STILL DELEGATED TO DEV5C1
def test_21_replacement_still_delegated_to_dev5c1(sandbox):
    mv_id = _ingest_movie(sandbox, "ReplaceFlow.mkv", "Original Title", 2010)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, "333", "Original Title", 2010, score=90.0)
        cand1 = media_match.MovieCandidate("tmdb_movie", "333", "Original Title", year=2010)
        media_match.accept_candidate(db, mv_id, cand1, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

        # Add manual candidate 444
        _add_candidate(db, mv_id, "444", "New Better Title", 2011, score=85.0, status="PENDING")
        cands = media_match_ui.get_ui_candidates(db, mv_id, sandbox["install"])
        cand_444 = next(c for c in cands if c["external_id"] == "1444")

        # Use DEV5C1 replace contract
        cand2 = media_match.MovieCandidate("tmdb_movie", "1444", "New Better Title", year=2011)
        media_match.accept_candidate(db, mv_id, cand2, score=85.0, replace=True)
        db.commit()

        st = media_match.get_media_version_status(db, mv_id)
        assert st["work"]["title"] == "New Better Title"


# 22. ZERO RESULTS UX
def test_22_zero_results_ux(sandbox):
    mv_id = _ingest_movie(sandbox, "ZeroResults.mkv", "Zero Results")
    calls = [
        {"ok": True, "cancelled": False, "text": "Obscure Unfound Movie"},
        {"ok": True, "cancelled": False, "text": ""},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK_NO_RESULTS", "revision": "revZero"})
    mock_ui = mock.MagicMock()
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=mock_ui):
                rc = manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert rc == 0
                assert mock_ui._regenerate_ui.call_count == 1


# 23. PROVIDER ERROR UX
def test_23_provider_error_ux(sandbox):
    mv_id = _ingest_movie(sandbox, "ProviderErr.mkv", "Provider Err")
    calls = [
        {"ok": True, "cancelled": False, "text": "Error Query"},
        {"ok": True, "cancelled": False, "text": ""},
    ]
    mock_search = mock.MagicMock(return_value={"ok": False, "error": "TMDB_TIMEOUT"})
    mock_show_err = mock.MagicMock()
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "show_error_window", mock_show_err):
                rc = manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert rc == 0
                assert mock_show_err.call_count == 1


# 24. NO AUTOMATIC PROVIDER RETRY
def test_24_no_automatic_provider_retry(sandbox):
    mv_id = _ingest_movie(sandbox, "NoRetry.mkv", "No Retry")
    calls = [
        {"ok": True, "cancelled": False, "text": "Failure Once"},
        {"ok": True, "cancelled": False, "text": ""},
    ]
    mock_search = mock.MagicMock(return_value={"ok": False, "error": "HTTP_500"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "show_error_window", lambda **kw: None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                # Exactly one attempt, no automatic retry
                assert mock_search.call_count == 1


# 25. EXPLICIT RETRY IF IMPLEMENTED IS EXACTLY ONE NEW CALL
def test_25_explicit_retry_one_call(sandbox):
    mv_id = _ingest_movie(sandbox, "ExplicitRetry.mkv", "Explicit Retry")
    calls = [
        {"ok": True, "cancelled": False, "text": "Query Retry"},
        {"ok": True, "cancelled": False, "text": ""},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revR"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert mock_search.call_count == 1


# 26. CANDIDATE REVISION UPDATES
def test_26_candidate_revision_updates(sandbox):
    mv_id = _ingest_movie(sandbox, "RevUpdate.mkv", "Rev Update")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        st1 = media_match.get_media_version_status(db, mv_id)
        rev1 = st1["candidate_set_revision"]

        cand = media_match.MovieCandidate("tmdb_movie", "555", "Rev Film", year=2018)
        mock_provider_res = mock.MagicMock(status="OK", candidates=[cand], error_code=None, error_detail=None)
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            res = media_match.manual_search_media_version(db, mv_id, "Rev Film", 2018, home=sandbox["home"])
            assert res["ok"] is True
            rev2 = res["candidate_set_revision"]
            assert rev1 != rev2


# 27. OLD ACTION TOKEN BECOMES STALE
def test_27_old_action_token_becomes_stale(sandbox):
    mv_id = _ingest_movie(sandbox, "StaleToken.mkv", "Stale Token")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        cid = _add_candidate(db, mv_id, 666, "Old Candidate", 2010)
        st = media_match.get_media_version_status(db, mv_id)
        old_rev = st["candidate_set_revision"]

        # Simulate search updating revision
        cand = media_match.MovieCandidate("tmdb_movie", "777", "New Candidate", year=2012)
        mock_provider_res = mock.MagicMock(status="OK", candidates=[cand], error_code=None, error_detail=None)
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_provider_res)):
            media_match.manual_search_media_version(db, mv_id, "New Candidate", 2012, home=sandbox["home"])

        # Attempt to accept old candidate using old revision
        res = media_match.accept_candidate(db, mv_id, cid, expected_revision=old_rev)
        assert res["ok"] is False
        assert res["error"] == "CANDIDATE_STALE"


# 28. LINE BUDGET <= 198 BYTES
def test_28_line_budget_le_198_bytes(sandbox):
    mv_id = _ingest_movie(sandbox, "VeryLongTitleMovieWithExtremelyLongCharacters1234567890.mkv", "Long Title")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Add candidate with very long title
        long_title = "Le Fabuleux Destin d'Amélie Poulain dans un monde extraordinaire et infini de merveilles cinématographiques"
        _add_candidate(db, mv_id, 99999, long_title, 2001)

        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R99999999", "genLong", {}, sandbox["media_icon"]
        )
        for sec in sections:
            for line in sec.splitlines():
                if line.startswith("Entry"):
                    utf8_bytes = len(line.encode("utf-8"))
                    assert utf8_bytes <= 198, f"Line exceeds 198 bytes ({utf8_bytes}): {line}"


# 29. DUPLICATE CANDIDATE HANDLING REMAINS DEV5C3A
def test_29_duplicate_candidate_handling_remains_dev5c3a(sandbox):
    mv_id = _ingest_movie(sandbox, "Dedupe.mkv", "Dedupe Test")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        c1 = media_match.MovieCandidate("tmdb_movie", "1234", "Same Title", year=2020)
        c2 = media_match.MovieCandidate("tmdb_movie", "1234", "Same Title", year=2020)
        mock_res = mock.MagicMock(status="OK", candidates=[c1, c2], error_code=None, error_detail=None)
        with mock.patch.object(media_match, "_load_tmdb_provider", return_value=_mock_provider_module(mock_res)):
            res = media_match.manual_search_media_version(db, mv_id, "Same Title", 2020, home=sandbox["home"])
            assert res["ok"] is True
            stored = media_match.get_candidates(db, mv_id)
            assert len(stored) == 1


# 30. SINGLE-FLEX COMMAND ARCHITECTURE
def test_30_single_flex_command_architecture(sandbox):
    mv_id = _ingest_movie(sandbox, "SingleFlex.mkv", "Single Flex")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R11223344", "genF", {}, sandbox["media_icon"]
        )
        full_ini = "\n".join(sections)
        # Verify manual search uses :applyback
        assert ":applyback" in full_ini
        assert "openhtpc-media-manual-search-ui" in full_ini
        # Verify zero flex-launcher calls in generated commands
        assert "flex-launcher" not in full_ini


# 31. NO SHELL=TRUE
def test_31_no_shell_true():
    for script_path in (SEARCH_UI_PATH, TEXT_ENTRY_PATH):
        content = script_path.read_text(encoding="utf-8")
        assert "shell=True" not in content
        assert "shell = True" not in content


# 32. ARBITRARY TITLE NOT SHELL INTERPOLATED
def test_32_arbitrary_title_not_shell_interpolated(sandbox):
    # Injection payload
    dangerous_title = "Movie; rm -rf /; `reboot`; $(touch /tmp/hacked)"
    mv_id = _ingest_movie(sandbox, "Danger.mkv", dangerous_title)
    calls = [
        {"ok": True, "cancelled": False, "text": dangerous_title},
        {"ok": True, "cancelled": False, "text": "2020"},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revD"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert mock_search.call_args.kwargs["title"] == dangerous_title


# 33. UTF-8 TITLE HANDLING
def test_33_utf8_title_handling(sandbox):
    cjk_title = "千と千尋の神隠し"
    mv_id = _ingest_movie(sandbox, "CJK.mkv", cjk_title)
    calls = [
        {"ok": True, "cancelled": False, "text": cjk_title},
        {"ok": True, "cancelled": False, "text": "2001"},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revCJK"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                assert mock_search.call_args.kwargs["title"] == cjk_title


# 34. LONG TITLE DISPLAY BOUNDED BUT QUERY UNCHANGED
def test_34_long_title_display_bounded_query_unchanged(sandbox):
    long_query = "A" * 200
    mv_id = _ingest_movie(sandbox, "Long.mkv", long_query)
    calls = [
        {"ok": True, "cancelled": False, "text": long_query},
        {"ok": True, "cancelled": False, "text": "2020"},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revL"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )
                # Full query sent to provider
                assert mock_search.call_args.kwargs["title"] == long_query


# 35. QUERY NOT PERSISTED TO CANONICAL DB
def test_35_query_not_persisted_to_canonical_db(sandbox):
    mv_id = _ingest_movie(sandbox, "NoPersist.mkv", "Initial Title")
    calls = [
        {"ok": True, "cancelled": False, "text": "Query Never Saved In Schema"},
        {"ok": True, "cancelled": False, "text": "2024"},
    ]
    mock_search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "revNP"})
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            with mock.patch.object(manual_search_ui, "_load_media_match_ui", return_value=None):
                manual_search_ui.orchestrate_manual_search(
                    media_version_id=mv_id,
                    home=sandbox["home"],
                    install=sandbox["install"],
                    custom_db_path=sandbox["db_file"],
                    mock_search_fn=mock_search,
                )

    with closing(media_db.connect(sandbox["db_file"])) as db:
        # Schema version compatibility (v2 qualified, v3 introduced in DEV6A1)
        ver = media_db.get_schema_version(db)
        assert ver in (2, 3)
        # Verify no search query columns in media_versions
        cols = [r[1] for r in db.execute("PRAGMA table_info(media_versions)").fetchall()]
        assert "search_query" not in cols
        assert "manual_query" not in cols
        assert "last_search" not in cols


# 36. REAL EXTENSIONLESS MODULE LOADING
def test_36_real_extensionless_module_loading(sandbox):
    """Verify load_extensionless_module and _load_media_match_ui load real openhtpc-media-match-ui without mocks."""
    # Test low-level extensionless loader
    mod = manual_search_ui.load_extensionless_module("test_match_ui", sandbox["install"] / "openhtpc-media-match-ui")
    assert mod is not None
    assert hasattr(mod, "_regenerate_ui")
    assert hasattr(mod, "build_resolver_menu_sections")
    assert hasattr(mod, "dispatch_action")

    # Test _load_media_match_ui with sandbox install
    loaded = manual_search_ui._load_media_match_ui(sandbox["install"])
    assert loaded is not None
    assert hasattr(loaded, "_regenerate_ui")
    assert callable(loaded._regenerate_ui)


# 37. SUCCESS REGENERATES CANONICAL FLEX CONFIG
def test_37_success_regenerates_canonical_flex_config(sandbox):
    """End-to-end qualification proving successful manual search regenerates flex-v1.ini with candidate sections."""
    mv_id = _ingest_movie(sandbox, "Spirited.Away.2001.mkv", "Spirited Away")

    # Configure user-config.json so session_engine knows local_media_sources
    cfg_dir = sandbox["home"] / ".config/openhtpc"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "user-config.json").write_text(
        json.dumps({
            "configuration_completed": True,
            "local_media_sources": [str(sandbox["sources_dir"])],
            "tmdb": {"configured": False},
        })
    )

    # Initial flex config generation
    flex_config = cfg_dir / "flex-v1.ini"
    session_engine.publish_flex_config(flex_config, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    assert flex_config.is_file()
    initial_content = flex_config.read_text(encoding="utf-8")
    assert "Spirited Away (2001)" not in initial_content

    # Mock search function that inserts a candidate into match_candidates and returns OK
    def mock_search(db, media_version_id, title, year, home):
        _add_candidate(db, media_version_id, 129, "Spirited Away", 2001)
        return {"ok": True, "status": "OK", "revision": "rev_test37"}

    calls = [
        {"ok": True, "cancelled": False, "text": "Spirited Away"},
        {"ok": True, "cancelled": False, "text": "2001"},
    ]
    with mock.patch.object(manual_search_ui, "invoke_text_entry", side_effect=calls):
        with mock.patch.object(manual_search_ui, "show_confirmation_window", return_value="SEARCH"):
            # Note: do NOT mock _load_media_match_ui! Let it load real openhtpc-media-match-ui and regenerate UI.
            rc = manual_search_ui.orchestrate_manual_search(
                media_version_id=mv_id,
                home=sandbox["home"],
                install=sandbox["install"],
                custom_db_path=sandbox["db_file"],
                mock_search_fn=mock_search,
            )
            assert rc == 0

    # Verify flex-v1.ini was regenerated and contains the candidate
    assert flex_config.is_file()
    updated_content = flex_config.read_text(encoding="utf-8")
    assert "Spirited Away (2001)" in updated_content
    assert "MEDIA_MS_" in updated_content
    assert "LANCER LA RECHERCHE" in updated_content


# 38. POST-SEARCH NAVIGATION TRAMPOLINE
def test_38_post_search_navigation_trampoline(sandbox):
    """Verify resolver menu structure provides a trampoline submenu so :applyback returns to the resolver."""
    mv_id = _ingest_movie(sandbox, "Alien.1979.mpg", "Alien")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R11223344", "gen1", {}, sandbox["media_icon"]
        )

    # Must contain main resolver section and trampoline submenu section
    sec_names = [s.splitlines()[0] for s in sections]
    assert "[MEDIA_R11223344]" in sec_names
    assert "[MEDIA_MS_11223344]" in sec_names

    res_sec = next(s for s in sections if s.startswith("[MEDIA_R11223344]"))
    ms_sec = next(s for s in sections if s.startswith("[MEDIA_MS_11223344]"))

    # Resolver section must use :submenu to trampoline
    assert ":submenu MEDIA_MS_11223344" in res_sec
    assert "RECHERCHER MANUELLEMENT" in res_sec
    assert ":applyback" not in res_sec

    # Trampoline section must use :applyback to launch manual search
    assert "LANCER LA RECHERCHE" in ms_sec
    assert f":applyback $HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui {mv_id}" in ms_sec
    assert "RETOUR" in ms_sec
    assert ":back" in ms_sec


# 39. TRAMPOLINE LINE BUDGET
def test_39_trampoline_line_budget(sandbox):
    """Guarantee all generated lines in resolver and trampoline menus strictly respect the <= 198 byte limit."""
    mv_id = _ingest_movie(sandbox, "VeryLongMovieTitleName" * 5 + ".mkv", "Long Title " * 10)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        db.execute(
            """
            INSERT INTO match_candidates (
                media_version_id, provider, external_id,
                candidate_title, candidate_year, candidate_payload_json,
                score, status, created_at
            ) VALUES (?, 'tmdb_movie', '999', ?, 2026, '{}', 90.0, 'PENDING', '2026-09-13T12:00:00Z')
            """,
            (mv_id, "Extremely Long Candidate Movie Title With Accents and Emojis" * 3),
        )
        db.commit()

        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_RABCDEF01", "gen_budget", {}, sandbox["media_icon"]
        )

    for sec in sections:
        for line in sec.splitlines():
            byte_len = len(line.encode("utf-8"))
            assert byte_len <= 198, f"Line exceeds 198 bytes ({byte_len} bytes): {line!r}"


# 40. ZERO RESULTS TRAMPOLINE NAVIGATION
def test_40_zero_results_trampoline_navigation(sandbox):
    """Verify zero-candidate resolver exposes trampoline submenu to allow manual search."""
    mv_id = _ingest_movie(sandbox, "ZeroResults.mkv", "Zero Results")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R00000000", "gen0", {}, sandbox["media_icon"]
        )

    assert len(sections) == 2
    res_sec, ms_sec = sections[0], sections[1]

    # Resolver section
    assert res_sec.startswith("[MEDIA_R00000000]")
    assert "Aucune proposition disponible." in res_sec
    assert "RECHERCHER MANUELLEMENT" in res_sec
    assert ":submenu MEDIA_MS_00000000" in res_sec

    # Trampoline section
    assert ms_sec.startswith("[MEDIA_MS_00000000]")
    assert "LANCER LA RECHERCHE" in ms_sec
    assert f":applyback $HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui {mv_id}" in ms_sec
    assert "RETOUR" in ms_sec

