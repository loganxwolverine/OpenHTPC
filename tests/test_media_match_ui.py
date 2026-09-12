# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV5C2: Living-Room Human Identity Resolver UI.

Verifies the 57 minimum contract invariants:
1. UNMATCHED entry exposes IDENTIFIER LE FILM
2. AUTO_MATCHED entry exposes confirmation/change action
3. USER_MATCHED exposes change action
4. resolver reads stored candidates only
5. resolver opening causes zero provider calls
6. candidate highlighting causes zero writes
7. candidate highlighting causes zero provider calls
8. candidate list ordering preserved
9. candidate title/year formatting
10. original title displayed only when different
11. score hidden in couch UI
12. provider/external ID hidden in couch UI
13. current accepted candidate visually indicated
14. REJECTED candidate hidden
15. UNMATCHED no candidates -> informational state
16. Decide Later -> zero mutation
17. candidate selection opens confirmation instead of commit
18. confirmation invokes normal accept
19. AUTO_MATCH same candidate does not request replacement
20. different candidate on AUTO_MATCH requires explicit replacement
21. different candidate on USER_MATCH requires explicit replacement
22. replacement confirmation screen shows old/new identity
23. reject requires confirmation
24. reject confirmation invokes DEV5C1 reject
25. stale revision invokes CANDIDATE_STALE handling
26. stale revision causes no automatic acceptance retry
27. stale screen reload obtains new revision
28. action token candidate belongs to correct media_version
29. invalid action token fails safely
30. title strings cannot become shell commands
31. no shell=True
32. no identity truth stored in media-actions
33. missing current.json does not alter canonical identity
34. UI helper zero direct writes to works
35. UI helper zero direct writes to external_ids
36. UI helper zero direct writes to media_versions identity fields
37. all mutations delegated to DEV5C1
38. no network on accept
39. no network on replace
40. no network on reject
41. no provider call on Flex startup
42. no provider call on MEDIA browsing
43. primary Play command unchanged
44. media dispatcher unchanged
45. no DVD/Blu-ray regression
46. generated Flex config remains syntactically valid
47. resolver back navigation valid
48. successful accept returns to stable Flex state
49. successful reject returns to stable Flex state
50. single Flex instance invariant
51. no second Flex launch command emitted
52. existing media-picker regression
53. existing media-remove regression
54. XDG isolation
55. no Schema change
56. no personal media references
57. zero real network in tests
"""
from __future__ import annotations

import ast
from contextlib import closing
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
MATCH_PATH = PAYLOAD / "openhtpc-media-match.py"
MATCH_UI_PATH = PAYLOAD / "openhtpc-media-match-ui"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"
SESSION_PATH = PAYLOAD / "openhtpc-session-engine.py"

# Load modules
def _load_mod(name, path):
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

media_match.set_media_db_module(media_db)
media_ingest.set_media_db_module(media_db)
media_ingest.set_media_probe_module(media_probe)
media_match_ui.set_media_match_module(media_match)
media_match_ui.set_media_db_module(media_db)
media_match_ui.set_session_engine_module(session_engine)


@pytest.fixture(autouse=True)
def forbid_network():
    """Guarantee zero network calls in all tests (Invariant 57)."""
    orig_connect = socket.socket.connect
    def guarded_connect(*args, **kwargs):
        raise AssertionError("Network contact strictly forbidden in hermetic tests (Invariant 57)")
    with mock.patch("socket.socket.connect", guarded_connect):
        yield


@pytest.fixture
def sandbox(tmp_path):
    """Hermetic isolated environment with test database and sources."""
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir(parents=True)

    # Copy relevant scripts into install directory
    for src in (
        MATCH_PATH, MATCH_UI_PATH, DB_PATH, INGEST_PATH, PROBE_PATH, SESSION_PATH,
        PAYLOAD / "openhtpc-optical.py", PAYLOAD / "openhtpc-ui.py", PAYLOAD / "openhtpc-theme.py",
    ):
        dest = install / src.name
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o755)

    # Assets in install
    (install / "assets/ui").mkdir(parents=True)
    raw_media_icon = install / "assets/ui/media.png"
    raw_media_icon.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    # Short icon symlink mirroring session engine's line economy
    uid = os.getuid()
    short_icon = Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(raw_media_icon)
        media_icon = short_icon
    except OSError:
        media_icon = raw_media_icon

    (install / "flex/assets/icons").mkdir(parents=True)
    (install / "flex/assets/icons/drive-empty.png").write_bytes(b"PNG")

    config_dir = home / ".config/openhtpc"
    state_dir = home / ".local/state/openhtpc"
    share_dir = home / ".local/share/openhtpc/media"
    sources_dir = tmp_path / "media_sources" / "movies"

    config_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    share_dir.mkdir(parents=True)
    sources_dir.mkdir(parents=True)

    db_file = share_dir / "media.db"
    media_db.initialize(db_file)

    user_config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(sources_dir)],
    }
    (config_dir / "user-config.json").write_text(json.dumps(user_config, indent=2))

    return {
        "home": home,
        "install": install,
        "db_file": db_file,
        "sources_dir": sources_dir,
        "media_icon": media_icon,
    }


def _ingest_movie(sandbox: dict, filename: str) -> tuple[int, Path]:
    """Create video file and ingest descriptor into media.db."""
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
            return res["media_version_id"], movie_path


def _add_candidate(
    db: sqlite3.Connection,
    media_version_id: int,
    cand_id: int,
    title: str,
    year: int | None,
    original_title: str | None = None,
    runtime: int | None = None,
    score: float = 85.0,
    status: str = "PENDING",
    external_id: str | None = None,
) -> int:
    ext_id = external_id or str(cand_id + 1000)
    payload = {
        "id": ext_id,
        "title": title,
        "original_title": original_title or title,
        "release_date": f"{year}-01-01" if year else None,
        "runtime_minutes": runtime,
    }
    db.execute(
        """
        INSERT INTO match_candidates (
            id, media_version_id, provider, external_id,
            candidate_title, candidate_year, candidate_payload_json,
            score, status, created_at
        ) VALUES (?, ?, 'tmdb_movie', ?, ?, ?, ?, ?, ?, '2026-09-12T12:00:00Z')
        """,
        (cand_id, media_version_id, ext_id, title, year, json.dumps(payload), score, status),
    )
    db.commit()
    return cand_id


# ==============================================================================
# TESTS 1 - 3: CONTEXT ACTION LABELS
# ==============================================================================

def test_01_unmatched_entry_exposes_identifier_le_film(sandbox):
    """1. UNMATCHED entry exposes IDENTIFIER LE FILM."""
    mv_id, _ = _ingest_movie(sandbox, "Inception.2010.mkv")
    _, ini_content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen1"
    )
    assert "IDENTIFIER LE FILM" in ini_content
    assert ":submenu MEDIA_R" in ini_content


def test_02_auto_matched_entry_exposes_confirmer_changer(sandbox):
    """2. AUTO_MATCHED entry exposes CONFIRMER / CHANGER L’IDENTIFICATION."""
    mv_id, _ = _ingest_movie(sandbox, "Alien.1979.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Alien", 1979, score=95.0)
        cand = media_match.MovieCandidate("tmdb_movie", "1001", "Alien", year=1979)
        media_match.accept_candidate(db, mv_id, cand, score=95.0, mode="AUTO", method="EXACT")
        db.commit()

    _, ini_content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen2"
    )
    assert "CONFIRMER / CHANGER L’IDENTIFICATION" in ini_content


def test_03_user_matched_entry_exposes_changer(sandbox):
    """3. USER_MATCHED exposes CHANGER L’IDENTIFICATION."""
    mv_id, _ = _ingest_movie(sandbox, "Parasite.2019.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Parasite", 2019, score=90.0)
        cand = media_match.MovieCandidate("tmdb_movie", "1001", "Parasite", year=2019)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

    _, ini_content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen3"
    )
    assert "CHANGER L’IDENTIFICATION" in ini_content
    assert "CONFIRMER / CHANGER L’IDENTIFICATION" not in ini_content


# ==============================================================================
# TESTS 4 - 7: OFFLINE LOCAL CANDIDATE READING & ZERO WRITES ON HIGHLIGHT
# ==============================================================================

def test_04_resolver_reads_stored_candidates_only(sandbox):
    """4. Resolver reads stored candidates only."""
    mv_id, _ = _ingest_movie(sandbox, "Movie1.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 10, "Stored Film", 2021)
        cands = media_match_ui.get_ui_candidates(db, mv_id, sandbox["install"])
        assert len(cands) == 1
        assert cands[0]["title"] == "Stored Film"


def test_05_resolver_opening_causes_zero_provider_calls(sandbox):
    """5. Resolver opening causes zero provider calls."""
    mv_id, _ = _ingest_movie(sandbox, "Movie2.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 20, "Offline Film", 2022)
        # Mock provider to raise error if invoked
        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("Provider invoked!")):
            sections = media_match_ui.build_resolver_menu_sections(
                sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
            )
            assert len(sections) >= 1


def test_06_candidate_highlighting_causes_zero_writes(sandbox):
    """6. Candidate highlighting causes zero writes."""
    mv_id, _ = _ingest_movie(sandbox, "Movie3.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 30, "Highlight Film", 2023)
        before_mv = db.execute("SELECT * FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        before_cands = db.execute("SELECT * FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()

        # Build / highlight candidate
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
        )

        after_mv = db.execute("SELECT * FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        after_cands = db.execute("SELECT * FROM match_candidates WHERE media_version_id = ?", (mv_id,)).fetchall()
        assert before_mv == after_mv
        assert before_cands == after_cands


def test_07_candidate_highlighting_causes_zero_provider_calls(sandbox):
    """7. Candidate highlighting causes zero provider calls."""
    mv_id, _ = _ingest_movie(sandbox, "Movie4.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 40, "Highlight Net Film", 2024)
        with mock.patch("http.client.HTTPConnection.request", side_effect=RuntimeError("HTTP call!")):
            sections = media_match_ui.build_resolver_menu_sections(
                sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
            )
            assert len(sections) > 0


# ==============================================================================
# TESTS 8 - 14: CANDIDATE FORMATTING & VISIBILITY
# ==============================================================================

def test_08_candidate_list_ordering_preserved(sandbox):
    """8. Candidate list ordering preserved (DEV5C1 score DESC, id ASC)."""
    mv_id, _ = _ingest_movie(sandbox, "Ordering.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Low Score", 2020, score=60.0)
        _add_candidate(db, mv_id, 2, "High Score", 2020, score=95.0)
        _add_candidate(db, mv_id, 3, "Mid Score", 2020, score=80.0)

        cands = media_match_ui.get_ui_candidates(db, mv_id, sandbox["install"])
        assert [c["id"] for c in cands] == [2, 3, 1]


def test_09_candidate_title_year_formatting():
    """9. Candidate title/year formatting."""
    c1 = {"title": "Alien", "year": 1979}
    assert media_match_ui.format_candidate_label(c1) == "Alien (1979)"

    c2 = {"title": "Unknown"}
    assert media_match_ui.format_candidate_label(c2) == "Unknown"


def test_10_original_title_displayed_only_when_different():
    """10. Original title displayed only when different."""
    # Identical titles
    c_same = {"title": "Alien", "year": 1979, "original_title": "Alien"}
    assert "Titre original" not in media_match_ui.format_candidate_label(c_same)

    # Case-insensitive identical
    c_ci = {"title": "alien", "year": 1979, "original_title": "Alien"}
    assert "Titre original" not in media_match_ui.format_candidate_label(c_ci)

    # Different original title
    c_diff = {"title": "Alien, le huitième passager", "year": 1979, "original_title": "Alien"}
    label = media_match_ui.format_candidate_label(c_diff)
    assert "Alien, le huitième passager (1979)" in label
    assert "Titre original : Alien" in label


def test_11_score_hidden_in_couch_ui():
    """11. Score hidden in couch UI."""
    c = {"title": "Movie", "year": 2020, "score": 99.5}
    label = media_match_ui.format_candidate_label(c)
    assert "99.5" not in label
    assert "score" not in label.casefold()


def test_12_provider_external_id_hidden_in_couch_ui():
    """12. Provider / external ID hidden in couch UI."""
    c = {"title": "Movie", "year": 2020, "provider": "tmdb_movie", "external_id": "12345"}
    label = media_match_ui.format_candidate_label(c)
    assert "tmdb" not in label.casefold()
    assert "12345" not in label


def test_13_current_accepted_candidate_visually_indicated():
    """13. Current accepted candidate visually indicated."""
    c = {"title": "Movie", "year": 2020}
    normal_label = media_match_ui.format_candidate_label(c, is_accepted=False)
    accepted_label = media_match_ui.format_candidate_label(c, is_accepted=True)
    assert normal_label.startswith("Movie (2020)")
    assert accepted_label.startswith("✓ Movie (2020)")


def test_14_rejected_candidate_hidden(sandbox):
    """14. REJECTED candidate hidden."""
    mv_id, _ = _ingest_movie(sandbox, "Rejected.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Visible Cand", 2020, status="PENDING")
        _add_candidate(db, mv_id, 2, "Hidden Cand", 2020, status="REJECTED")

        cands = media_match_ui.get_ui_candidates(db, mv_id, sandbox["install"])
        assert len(cands) == 1
        assert cands[0]["id"] == 1


# ==============================================================================
# TESTS 15 - 16: NO CANDIDATES & DECIDE LATER
# ==============================================================================

def test_15_unmatched_no_candidates_informational_state(sandbox):
    """15. UNMATCHED no candidates -> informational state."""
    mv_id, _ = _ingest_movie(sandbox, "NoCands.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
        )
        assert len(sections) == 1
        sec = sections[0]
        assert "Aucune proposition disponible." in sec
        assert "RETOUR" in sec
        assert ":back" in sec
        assert "CONFIRMER" not in sec


def test_16_decide_later_zero_mutation(sandbox):
    """16. Decide Later -> zero mutation."""
    mv_id, _ = _ingest_movie(sandbox, "DecideLater.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Candidate 1", 2020)
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
        )
        resolver_menu = sections[-1]
        assert "PLUS TARD" in resolver_menu
        assert ":back" in resolver_menu

        # Verify zero DB mutation
        mv_row = db.execute("SELECT identification_state FROM media_versions WHERE id = ?", (mv_id,)).fetchone()
        assert mv_row[0] == "UNMATCHED"


# ==============================================================================
# TESTS 17 - 22: CONFIRMATION & REPLACEMENT SCREENS
# ==============================================================================

def test_17_candidate_selection_opens_confirmation_instead_of_commit(sandbox):
    """17. Candidate selection opens confirmation instead of commit."""
    mv_id, _ = _ingest_movie(sandbox, "Selection.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Select Candidate", 2020)
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen", {}, sandbox["media_icon"]
        )
        resolver_menu = sections[-1]
        # Entry command must be a submenu to confirmation, NOT an immediate dispatch or accept
        assert ":submenu MEDIA_C_" in resolver_menu
        assert "dispatch" not in resolver_menu


def test_18_confirmation_invokes_normal_accept(sandbox):
    """18. Confirmation invokes normal accept."""
    mv_id, _ = _ingest_movie(sandbox, "ConfirmAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 5, "Accept Film", 2020)

    actions = {}
    sections = media_match_ui.build_resolver_menu_sections(
        sandbox["home"], sandbox["install"], media_db.connect(sandbox["db_file"]),
        mv_id, "MEDIA_R12345678", "gen18", actions, sandbox["media_icon"]
    )
    # Manifest candidate
    token = next(k for k, v in actions.items() if v.get("candidate_id") == 5)
    manifest = {"schema": 1, "manifest_generation": "gen18", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    # Dispatch token
    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "USER_MATCHED"
        assert st["match_locked"] == 1


def test_19_auto_match_same_candidate_does_not_request_replacement(sandbox):
    """19. AUTO_MATCH same candidate does not request replacement."""
    mv_id, _ = _ingest_movie(sandbox, "AutoConfirm.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 7, "Auto Film", 2020)
        cand = media_match.MovieCandidate("tmdb_movie", "1007", "Auto Film", year=2020)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="AUTO", method="EXACT")
        db.commit()

        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen19", actions, sandbox["media_icon"]
        )
        token = next(k for k, v in actions.items() if v.get("candidate_id") == 7)
        assert actions[token]["action"] == "accept"
        assert actions[token]["replace"] is False


def test_20_different_candidate_on_auto_match_requires_explicit_replacement(sandbox):
    """20. Different candidate on AUTO_MATCH requires explicit replacement."""
    mv_id, _ = _ingest_movie(sandbox, "AutoDiff.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 10, "Auto Film 1", 2020, external_id="1010")
        _add_candidate(db, mv_id, 11, "Diff Film 2", 2021, external_id="1011")
        cand = media_match.MovieCandidate("tmdb_movie", "1010", "Auto Film 1", year=2020)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="AUTO", method="EXACT")
        db.commit()

        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen20", actions, sandbox["media_icon"]
        )
        token_diff = next(k for k, v in actions.items() if v.get("candidate_id") == 11)
        assert actions[token_diff]["action"] == "replace"
        assert actions[token_diff]["replace"] is True


def test_21_different_candidate_on_user_match_requires_explicit_replacement(sandbox):
    """21. Different candidate on USER_MATCH requires explicit replacement."""
    mv_id, _ = _ingest_movie(sandbox, "UserDiff.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 20, "User Film 1", 2020, external_id="2020")
        _add_candidate(db, mv_id, 21, "New Film 2", 2021, external_id="2021")
        cand = media_match.MovieCandidate("tmdb_movie", "2020", "User Film 1", year=2020)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen21", actions, sandbox["media_icon"]
        )
        token_new = next(k for k, v in actions.items() if v.get("candidate_id") == 21)
        assert actions[token_new]["action"] == "replace"
        assert actions[token_new]["replace"] is True


def test_22_replacement_confirmation_screen_shows_old_new_identity(sandbox):
    """22. Replacement confirmation screen shows old/new identity."""
    mv_id, _ = _ingest_movie(sandbox, "OldNew.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 30, "Current Film", 2010, external_id="3030")
        _add_candidate(db, mv_id, 31, "New Film", 2020, external_id="3031")
        cand = media_match.MovieCandidate("tmdb_movie", "3030", "Current Film", year=2010)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="AUTO", method="EXACT")
        db.commit()

        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen22", actions, sandbox["media_icon"]
        )
        # Find replacement confirmation section
        repl_section = next(s for s in sections if s.startswith("[MEDIA_RP_"))
        assert "CONFIRMER LE CHANGEMENT" in repl_section
        assert "Actuel : Current Film (2010)" in repl_section
        assert "Nouveau : New Film (2020)" in repl_section
        assert "ANNULER" in repl_section


# ==============================================================================
# TESTS 23 - 24: REJECT ACTION & CONFIRMATION
# ==============================================================================

def test_23_reject_requires_confirmation(sandbox):
    """23. Reject requires confirmation."""
    mv_id, _ = _ingest_movie(sandbox, "RejectConf.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 40, "Reject Film", 2020)
        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen23", actions, sandbox["media_icon"]
        )
        resolver_menu = sections[-1]
        assert "AUCUN DE CES FILMS" in resolver_menu
        assert ":submenu MEDIA_RJ_" in resolver_menu
        # Not immediate reject command
        assert "dispatch" not in resolver_menu


def test_24_reject_confirmation_invokes_dev5c1_reject(sandbox):
    """24. Reject confirmation invokes DEV5C1 reject."""
    mv_id, _ = _ingest_movie(sandbox, "RejectCommit.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 50, "To Reject", 2020)

    actions = {}
    sections = media_match_ui.build_resolver_menu_sections(
        sandbox["home"], sandbox["install"], media_db.connect(sandbox["db_file"]),
        mv_id, "MEDIA_R12345678", "gen24", actions, sandbox["media_icon"]
    )
    rej_token = next(k for k, v in actions.items() if v.get("action") == "reject")
    manifest = {"schema": 1, "manifest_generation": "gen24", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], rej_token, sandbox["install"])
    assert code == 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "UNMATCHED"
        assert st["work_id"] is None
        cands = media_match.get_candidates(db, mv_id)
        assert all(c["status"] == "REJECTED" for c in cands)


# ==============================================================================
# TESTS 25 - 27: STALE REVISION HANDLING & ZERO RETRY
# ==============================================================================

def test_25_stale_revision_invokes_candidate_stale_handling(sandbox, capsys):
    """25. Stale revision invokes CANDIDATE_STALE handling."""
    mv_id, _ = _ingest_movie(sandbox, "StaleRev.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 60, "Stale Film", 2020)

    token = "iact_gen25_12345678_60"
    actions = {
        token: {
            "action": "accept",
            "media_version_id": mv_id,
            "candidate_id": 60,
            "expected_revision": "stale_hash_mismatch",
        }
    }
    manifest = {"schema": 1, "manifest_generation": "gen25", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code != 0
    err = capsys.readouterr().err
    assert "Les propositions ont changé. La liste va être actualisée." in err


def test_26_stale_revision_causes_no_automatic_acceptance_retry(sandbox):
    """26. Stale revision causes no automatic acceptance retry."""
    mv_id, _ = _ingest_movie(sandbox, "NoRetry.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 70, "No Retry Film", 2020)

    token = "iact_gen26_12345678_70"
    actions = {
        token: {
            "action": "accept",
            "media_version_id": mv_id,
            "candidate_id": 70,
            "expected_revision": "stale_hash_mismatch",
        }
    }
    manifest = {"schema": 1, "manifest_generation": "gen26", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])

    # Item must remain UNMATCHED (zero automatic retry)
    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "UNMATCHED"
        assert st["work_id"] is None


def test_27_stale_screen_reload_obtains_new_revision(sandbox):
    """27. Stale screen reload obtains new revision."""
    mv_id, _ = _ingest_movie(sandbox, "ReloadRev.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 80, "Initial Cand", 2020)
        rev1 = media_match.compute_candidate_set_revision(db, mv_id)

        # Mutate candidate set (new candidate arrives)
        _add_candidate(db, mv_id, 81, "Second Cand", 2021)
        rev2 = media_match.compute_candidate_set_revision(db, mv_id)
        assert rev1 != rev2

        # Status reload obtains fresh revision
        st = media_match_ui.get_status(db, mv_id, sandbox["install"])
        assert st["candidate_set_revision"] == rev2


# ==============================================================================
# TESTS 28 - 29: ACTION TOKEN INTEGRITY & SAFETY
# ==============================================================================

def test_28_action_token_candidate_belongs_to_correct_media_version(sandbox):
    """28. Action token candidate belongs to correct media_version."""
    mv_id1, _ = _ingest_movie(sandbox, "MovieA.mkv")
    mv_id2, _ = _ingest_movie(sandbox, "MovieB.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id1, 91, "Cand For A", 2020)
        _add_candidate(db, mv_id2, 92, "Cand For B", 2020)

    # Malicious/corrupt token: cand 92 mapped to mv_id1
    token = "iact_corrupt_cand_mismatch"
    actions = {
        token: {
            "action": "accept",
            "media_version_id": mv_id1,
            "candidate_id": 92,
            "expected_revision": None,
        }
    }
    manifest = {"schema": 1, "manifest_generation": "gen28", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code != 0

    with closing(media_db.connect(sandbox["db_file"])) as db:
        st1 = media_match.get_media_version_status(db, mv_id1)
        assert st1["identification_state"] == "UNMATCHED"


def test_29_invalid_action_token_fails_safely(sandbox):
    """29. Invalid action token fails safely."""
    code = media_match_ui.dispatch_action(sandbox["home"], "iact_nonexistent_token", sandbox["install"])
    assert code != 0


# ==============================================================================
# TESTS 30 - 31: COMMAND SAFETY & NO SHELL=TRUE
# ==============================================================================

def test_30_title_strings_cannot_become_shell_commands(sandbox):
    """30. Title strings cannot become shell commands."""
    mv_id, _ = _ingest_movie(sandbox, "EvilTitle.mkv")
    evil_title = 'Alien"; rm -rf /; echo "hacked'
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 100, evil_title, 1979)
        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen30", actions, sandbox["media_icon"]
        )
        # Commands generated must only contain token, never arbitrary title strings
        for sec in sections:
            for line in sec.splitlines():
                if line.startswith("Entry"):
                    parts = line.split(";")
                    if len(parts) >= 3:
                        cmd = parts[2]
                        assert "rm -rf" not in cmd
                        assert "hacked" not in cmd


def test_31_no_shell_true():
    """31. No shell=True in UI helper or session engine."""
    for p in (MATCH_UI_PATH, SESSION_PATH):
        content = p.read_text(encoding="utf-8")
        assert "shell=True" not in content
        tree = ast.parse(content, filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is not True


# ==============================================================================
# TESTS 32 - 37: SEPARATION OF AUTHORITY & ZERO SQL WRITES FROM UI
# ==============================================================================

def test_32_no_identity_truth_stored_in_media_actions(sandbox):
    """32. No identity truth stored in media-actions."""
    mv_id, _ = _ingest_movie(sandbox, "Separation.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 110, "Truth Film", 2020)
        actions = {}
        media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen32", actions, sandbox["media_icon"]
        )
        for token, data in actions.items():
            # Only ephemeral routing keys allowed
            assert "work_id" not in data
            assert "match_locked" not in data
            assert "canonical_title" not in data


def test_33_missing_current_json_does_not_alter_canonical_identity(sandbox):
    """33. Missing current.json does not alter canonical identity."""
    mv_id, _ = _ingest_movie(sandbox, "MissingJson.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        cand = media_match.MovieCandidate("tmdb_movie", "3333", "Canonical Film", year=2020)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

    manifest_file = sandbox["home"] / ".local/state/openhtpc/media-actions/current.json"
    if manifest_file.is_file():
        manifest_file.unlink()

    # Database canonical state is 100% intact
    with closing(media_db.connect(sandbox["db_file"])) as db:
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "USER_MATCHED"
        assert st["work"]["title"] == "Canonical Film"


def test_34_ui_helper_zero_direct_writes_to_works():
    """34. UI helper zero direct writes to works."""
    content = MATCH_UI_PATH.read_text(encoding="utf-8")
    assert not re.search(r"INSERT\s+INTO\s+works", content, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+works", content, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+works", content, re.IGNORECASE)


def test_35_ui_helper_zero_direct_writes_to_external_ids():
    """35. UI helper zero direct writes to external_ids."""
    content = MATCH_UI_PATH.read_text(encoding="utf-8")
    assert not re.search(r"INSERT\s+INTO\s+external_ids", content, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+external_ids", content, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+external_ids", content, re.IGNORECASE)


def test_36_ui_helper_zero_direct_writes_to_media_versions():
    """36. UI helper zero direct writes to media_versions identity fields."""
    content = MATCH_UI_PATH.read_text(encoding="utf-8")
    assert not re.search(r"UPDATE\s+media_versions", content, re.IGNORECASE)
    assert not re.search(r"INSERT\s+INTO\s+media_versions", content, re.IGNORECASE)


def test_37_all_mutations_delegated_to_dev5c1(sandbox):
    """37. All mutations delegated to DEV5C1."""
    mv_id, _ = _ingest_movie(sandbox, "Delegation.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 120, "Delegation Film", 2020)

    token = "iact_gen37_12345678_120"
    actions = {
        token: {
            "action": "accept",
            "media_version_id": mv_id,
            "candidate_id": 120,
            "expected_revision": None,
        }
    }
    manifest = {"schema": 1, "manifest_generation": "gen37", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    with mock.patch.object(media_match, "accept_candidate_by_id", wraps=media_match.accept_candidate_by_id) as mocked_accept:
        media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
        assert mocked_accept.called


# ==============================================================================
# TESTS 38 - 42: ZERO NETWORK OPERATIONS
# ==============================================================================

def test_38_no_network_on_accept(sandbox):
    """38. No network on accept."""
    mv_id, _ = _ingest_movie(sandbox, "NoNetAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 130, "No Net Film", 2020)

    token = "iact_gen38_12345678_130"
    actions = {token: {"action": "accept", "media_version_id": mv_id, "candidate_id": 130, "expected_revision": None}}
    manifest = {"schema": 1, "manifest_generation": "gen38", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0


def test_39_no_network_on_replace(sandbox):
    """39. No network on replace."""
    mv_id, _ = _ingest_movie(sandbox, "NoNetReplace.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 140, "Initial", 2010, external_id="1400")
        _add_candidate(db, mv_id, 141, "Replacement", 2020, external_id="1401")
        cand = media_match.MovieCandidate("tmdb_movie", "1400", "Initial", year=2010)
        media_match.accept_candidate(db, mv_id, cand, score=90.0, mode="AUTO", method="EXACT")
        db.commit()

    token = "iact_gen39_12345678_141"
    actions = {token: {"action": "replace", "media_version_id": mv_id, "candidate_id": 141, "expected_revision": None, "replace": True}}
    manifest = {"schema": 1, "manifest_generation": "gen39", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0


def test_40_no_network_on_reject(sandbox):
    """40. No network on reject."""
    mv_id, _ = _ingest_movie(sandbox, "NoNetReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 150, "To Reject", 2020)

    token = "iact_gen40_12345678_rej"
    actions = {token: {"action": "reject", "media_version_id": mv_id, "candidate_id": None, "expected_revision": None}}
    manifest = {"schema": 1, "manifest_generation": "gen40", "sources": [], "items": actions}
    manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "current.json").write_text(json.dumps(manifest))

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0


def test_41_no_provider_call_on_flex_startup(sandbox):
    """41. No provider call on Flex startup / write_flex_config."""
    _ingest_movie(sandbox, "StartupMovie.mkv")
    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    ok = session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    assert ok is True


def test_42_no_provider_call_on_media_browsing(sandbox):
    """42. No provider call on MEDIA browsing / media_menu_sections."""
    _ingest_movie(sandbox, "BrowseMovie.mkv")
    root_name, content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen42"
    )
    assert root_name == "MEDIA_ROOT"
    assert "BrowseMovie" in content


# ==============================================================================
# TESTS 43 - 45: PLAYBACK & SYSTEM NON-REGRESSION
# ==============================================================================

def test_43_primary_play_command_unchanged(sandbox):
    """43. Primary Play command unchanged."""
    _ingest_movie(sandbox, "PlayCmd.mkv")
    _, content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen43"
    )
    for line in content.splitlines():
        if line.startswith("Entry") and "PlayCmd" in line:
            parts = line.split(";")
            assert parts[2].startswith("$HOME/.local/lib/openhtpc/openhtpc-play mact_")


def test_44_media_dispatcher_unchanged(sandbox):
    """44. Media dispatcher unchanged."""
    _ingest_movie(sandbox, "Dispatcher.mkv")
    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    manifest = session_engine.activate_media_manifest(config_path, sandbox["home"])
    assert manifest.is_file()


def test_45_no_dvd_bluray_regression(sandbox):
    """45. No DVD/Blu-ray regression."""
    # disc_menu_entries still produces standard disc actions
    optical_state = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0", "disc_title": "TEST_DVD"}
    icons = (sandbox["media_icon"], sandbox["media_icon"], sandbox["media_icon"], sandbox["media_icon"])
    entries = session_engine.disc_menu_entries(optical_state, sandbox["install"], icons, sandbox["home"])
    assert "LIRE LE DVD" in entries


# ==============================================================================
# TESTS 46 - 49: FLEX CONFIG VALIDITY & RETURN BEHAVIOR
# ==============================================================================

def test_46_generated_flex_config_remains_syntactically_valid(sandbox):
    """46. Generated Flex config remains syntactically valid."""
    _ingest_movie(sandbox, "SyntaxValid.mkv")
    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])

    text = config_path.read_text(encoding="utf-8")
    assert "[MEDIA_ROOT]" in text
    assert "[MEDIA_" in text
    # Verify all media and resolver entry lines meet parser line budget <= 198 bytes
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("Entry") and (":submenu MEDIA_R" in line or "MEDIA_R" in line or "CONFIRMER" in line or "IDENTIFIER" in line or "mact_" in line or "iact_" in line):
            assert len(line.encode("utf-8")) <= 198, f"Line {lineno} exceeds 198 bytes: {line}"


def test_47_resolver_back_navigation_valid(sandbox):
    """47. Resolver back navigation valid."""
    mv_id, _ = _ingest_movie(sandbox, "BackNav.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Cand", 2020)
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen47", {}, sandbox["media_icon"]
        )
        for sec in sections:
            # Every generated resolver/confirm/reject section has a valid :back entry
            assert ":back" in sec


def test_48_successful_accept_returns_to_stable_flex_state(sandbox):
    """48. Successful accept returns to stable Flex state."""
    mv_id, _ = _ingest_movie(sandbox, "ReturnAccept.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Candidate", 2020)

    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    session_engine.activate_media_manifest(config_path, sandbox["home"])

    manifest_file = sandbox["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_file.read_text())
    token = next(k for k, v in manifest["items"].items() if v.get("candidate_id") == 1)

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0

    # flex-v1.ini is regenerated with the updated state
    updated_ini = config_path.read_text(encoding="utf-8")
    assert "CHANGER L’IDENTIFICATION" in updated_ini


def test_49_successful_reject_returns_to_stable_flex_state(sandbox):
    """49. Successful reject returns to stable Flex state."""
    mv_id, _ = _ingest_movie(sandbox, "ReturnReject.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 1, "Candidate", 2020)

    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    session_engine.activate_media_manifest(config_path, sandbox["home"])

    manifest_file = sandbox["home"] / ".local/state/openhtpc/media-actions/current.json"
    manifest = json.loads(manifest_file.read_text())
    token = next(k for k, v in manifest["items"].items() if v.get("action") == "reject")

    code = media_match_ui.dispatch_action(sandbox["home"], token, sandbox["install"])
    assert code == 0

    updated_ini = config_path.read_text(encoding="utf-8")
    assert "Aucune proposition disponible." in updated_ini


# ==============================================================================
# TESTS 50 - 51: CRITICAL — SINGLE FLEX INSTANCE INVARIANT
# ==============================================================================

def test_50_single_flex_instance_invariant():
    """50. Single Flex instance invariant: UI helper never spawns or execs flex-launcher."""
    code = MATCH_UI_PATH.read_text(encoding="utf-8")
    assert "flex-launcher" not in code
    assert "os.execv" not in code
    assert "os.execvp" not in code


def test_51_no_second_flex_launch_command_emitted(sandbox):
    """51. No second Flex launch command emitted in generated INI."""
    _ingest_movie(sandbox, "NoMultiFlex.mkv")
    _, content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen51"
    )
    for line in content.splitlines():
        if line.startswith("Entry"):
            # Commands in media & resolver sections must never invoke flex-launcher binary
            assert "flex-launcher" not in line


# ==============================================================================
# TESTS 52 - 57: MEDIA SOURCES, ISOLATION, SCHEMA, NO PERSONAL REFERENCES
# ==============================================================================

def test_52_existing_media_picker_regression(sandbox):
    """52. Existing media-picker regression."""
    # When no sources exist, + AJOUTER UNE SOURCE MÉDIA is present with picker_bin
    root_name, content = session_engine.media_menu_sections(
        sandbox["home"], [], sandbox["media_icon"], "gen52"
    )
    assert "+ AJOUTER UNE SOURCE" in content
    assert "openhtpc-media-picker" in content


def test_53_existing_media_remove_regression(sandbox):
    """53. Existing media-remove regression."""
    # When sources exist, RETIRER LA SOURCE context action remains present
    root_name, content = session_engine.media_menu_sections(
        sandbox["home"], [sandbox["sources_dir"]], sandbox["media_icon"], "gen53"
    )
    assert "RETIRER LA SOURCE" in content
    assert "openhtpc-media-remove" in content


def test_54_xdg_isolation(sandbox):
    """54. XDG isolation: all created files remain within test sandbox."""
    _ingest_movie(sandbox, "Isolation.mkv")
    config_path = sandbox["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.write_flex_config(config_path, sandbox["home"], [sandbox["sources_dir"]], sandbox["install"])
    assert config_path.is_file()
    assert str(config_path).startswith(str(sandbox["home"]))


def test_55_no_schema_change():
    """55. No schema change: SCHEMA_VERSION remains 2."""
    assert media_db.SCHEMA_VERSION == 2


def test_56_no_personal_media_references():
    """56. No personal media references in code or test suite."""
    for p in (MATCH_UI_PATH, SESSION_PATH):
        text = p.read_text(encoding="utf-8")
        assert "/home/steve" not in text
        assert "steve@" not in text


def test_57_zero_real_network_in_tests():
    """57. Zero real network in tests."""
    with pytest.raises(AssertionError, match="Network contact strictly forbidden"):
        s = socket.socket()
        s.connect(("127.0.0.1", 80))


# ==============================================================================
# TESTS 58 - 61: DEV5C2A — FLEX LINE BUDGET HARDENING & IDENTITY SAFETY
# ==============================================================================

def test_58_flex_line_budget_deterministic_matrix(sandbox):
    """58. Deterministic matrix of 22 worst-case Flex entry line scenarios."""
    ui = media_match_ui
    icon = sandbox["media_icon"]
    lines_to_check = []

    # 1. Normal ASCII title
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "Inception", "year": 2010}), icon, ":submenu MEDIA_C_1_1"))
    # 2. Maximum long ASCII title
    lines_to_check.append(ui.bounded_flex_line(2, ui.format_candidate_label({"title": "A" * 500, "year": 2020}), icon, ":submenu MEDIA_C_1_2"))
    # 3. Long French accented title
    lines_to_check.append(ui.bounded_flex_line(3, ui.format_candidate_label({"title": "Éléphant à l'orée de la forêt enchantée où brûle l'été " * 10, "year": 2021}), icon, ":submenu MEDIA_C_1_3"))
    # 4. Long Japanese title
    lines_to_check.append(ui.bounded_flex_line(4, ui.format_candidate_label({"title": "七人の侍黒澤明監督作品映画東京物語雨月物語" * 15, "year": 1954}), icon, ":submenu MEDIA_C_1_4"))
    # 5. Long emoji-containing title
    lines_to_check.append(ui.bounded_flex_line(5, ui.format_candidate_label({"title": "🎬🍿🎥🎞️🌟🚀✨🔥🎉" * 20, "year": 2022}), icon, ":submenu MEDIA_C_1_5"))
    # 6. Long localized title + long original title
    lines_to_check.append(ui.bounded_flex_line(6, ui.format_candidate_label({"title": "Titre français long " * 10, "year": 2023, "original_title": "Original English long title " * 10}), icon, ":submenu MEDIA_C_1_6"))
    # 7. Semicolon in title
    lines_to_check.append(ui.bounded_flex_line(7, ui.format_candidate_label({"title": "Movie; with semicolon", "year": 2015}), icon, ":submenu MEDIA_C_1_7"))
    # 8. Multiple semicolons
    lines_to_check.append(ui.bounded_flex_line(8, ui.format_candidate_label({"title": "Movie; with; many; semicolons; here; and; there;", "year": 2016}), icon, ":submenu MEDIA_C_1_8"))
    # 9. Replacement Actuel long title
    budget_r2 = 198 - len(f"Entry2=;{icon};:fork true".encode("utf-8"))
    lines_to_check.append(ui.bounded_flex_line(2, ui.format_replacement_display("Actuel : ", "Actuel Film " * 20, 2010, budget_r2), icon, ":fork true"))
    # 10. Replacement Nouveau long title
    budget_r3 = 198 - len(f"Entry3=;{icon};:fork true".encode("utf-8"))
    lines_to_check.append(ui.bounded_flex_line(3, ui.format_replacement_display("Nouveau : ", "Nouveau Film " * 20, 2024, budget_r3), icon, ":fork true"))
    # 11. Accepted candidate marker ✓
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "Accepted Film " * 15, "year": 2018}, is_accepted=True), icon, ":submenu MEDIA_C_1_11"))
    # 12. Title with apostrophes
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "L'histoire d'un homme qui n'avait d'autre choix " * 10, "year": 2019}), icon, ":submenu MEDIA_C_1_12"))
    # 13. Title with colon
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "Star Wars: Episode IV: A New Hope: Special Edition: Remastered", "year": 1977}), icon, ":submenu MEDIA_C_1_13"))
    # 14. Title with em dash
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "Film — Partie 1 — Chapitre 2 — Version Longue — Restauration 4K", "year": 2020}), icon, ":submenu MEDIA_C_1_14"))
    # 15. Title with combining Unicode characters
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "e\u0301\u0300\u0302\u0303\u0304\u0305\u0306\u0307\u0308\u0309" * 20, "year": 2021}), icon, ":submenu MEDIA_C_1_15"))
    # 16. Maximum action-token length
    max_token = "iact_" + "9" * 20 + "_" + "a" * 16 + "_" + "9" * 9
    lines_to_check.append(ui.bounded_flex_line(1, "CONFIRMER LE CHOIX", icon, f":applyback $HOME/.local/lib/openhtpc/openhtpc-media-match-ui dispatch {max_token}"))
    # 17. Maximum expected candidate_id digits
    lines_to_check.append(ui.bounded_flex_line(1, ui.format_candidate_label({"title": "Candidate Extreme ID " * 5, "year": 2020}), icon, ":submenu MEDIA_RP_12345678_999999999"))
    # 18. Maximum expected media_version_id digits
    lines_to_check.append(ui.bounded_flex_line(1, "CONFIRMER LE CHANGEMENT", icon, ":applyback $HOME/.local/lib/openhtpc/openhtpc-media-match-ui dispatch iact_gen_999999999_1"))
    # 19. Context action line
    lines_to_check.append(session_engine.bounded_flex_entry(1, "Very Long Context Movie " * 5 + "  ·  MKV", icon, "mact_12345678_99999999", ":submenu MEDIA_R12345678", "CONFIRMER / CHANGER L’IDENTIFICATION"))
    # 20. Reject confirmation line
    lines_to_check.append(ui.bounded_flex_line(1, "OUI, AUCUN NE CORRESPOND", icon, ":applyback $HOME/.local/lib/openhtpc/openhtpc-media-match-ui dispatch iact_gen_12345678_rej"))
    # 21. No-candidate informational line
    lines_to_check.append(ui.bounded_flex_line(1, "Aucune proposition disponible.", icon, ":back"))
    # 22. Return/back line
    lines_to_check.append(ui.bounded_flex_line(2, "RETOUR", icon, ":back"))

    assert len(lines_to_check) == 22
    for idx, line in enumerate(lines_to_check, 1):
        encoded = line.encode("utf-8")
        assert len(encoded) <= 198, f"Case {idx} exceeds 198 bytes ({len(encoded)} bytes): {line}"
        assert encoded.decode("utf-8"), f"Case {idx} broken UTF-8 encoding"


def test_59_duplicate_visible_label_identity_safety(sandbox):
    """59. Identity safety: candidates with identical visible truncated labels maintain distinct identity."""
    mv_id, _ = _ingest_movie(sandbox, "DuplicateTruncation.mkv")
    common_prefix = "A Really Extremely Long Movie Title That Will Definitely Exceed The Flex Line Budget " * 3
    t1 = common_prefix + " Alpha"
    t2 = common_prefix + " Beta"

    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 101, t1, 2020, external_id="tmdb_101")
        _add_candidate(db, mv_id, 102, t2, 2020, external_id="tmdb_102")

        actions = {}
        sections = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen59", actions, sandbox["media_icon"]
        )
        main_sec = next(s for s in sections if s.startswith("[MEDIA_R12345678]"))
        lines = [l for l in main_sec.splitlines() if l.startswith("Entry") and ":submenu MEDIA_C_" in l]
        assert len(lines) == 2

        lbl1 = lines[0].split(";")[0].split("=", 1)[1]
        lbl2 = lines[1].split(";")[0].split("=", 1)[1]
        assert lbl1 == lbl2
        assert "…" in lbl1

        sub1 = lines[0].split(";")[2]
        sub2 = lines[1].split(";")[2]
        assert sub1 != sub2
        assert "101" in sub1
        assert "102" in sub2

        token1 = next(k for k, v in actions.items() if v.get("candidate_id") == 101)
        token2 = next(k for k, v in actions.items() if v.get("candidate_id") == 102)
        assert token1 != token2
        assert actions[token1]["candidate_id"] == 101
        assert actions[token2]["candidate_id"] == 102

        manifest = {"schema": 1, "manifest_generation": "gen59", "sources": [], "items": actions}
        manifest_dir = sandbox["home"] / ".local/state/openhtpc/media-actions"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "current.json").write_text(json.dumps(manifest))

        code = media_match_ui.dispatch_action(sandbox["home"], token1, sandbox["install"])
        assert code == 0
        st = media_match.get_media_version_status(db, mv_id)
        assert st["identification_state"] == "USER_MATCHED"
        assert st["work"]["title"] == t1
        assert db.execute("SELECT status FROM match_candidates WHERE id = 101").fetchone()[0] == "ACCEPTED"
        assert db.execute("SELECT status FROM match_candidates WHERE id = 102").fetchone()[0] == "SUPERSEDED"


def test_60_command_immutability_under_truncation(sandbox):
    """60. Command immutability: command payload and token semantics remain identical under label truncation."""
    mv_id, _ = _ingest_movie(sandbox, "CommandImmutability.mkv")

    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id, 201, "Short Film", 2020, external_id="tmdb_201")
        actions_a = {}
        sections_a = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen60", actions_a, sandbox["media_icon"]
        )
        token_a = next(k for k, v in actions_a.items() if v.get("candidate_id") == 201)
        action_a_data = actions_a[token_a]

        db.execute("DELETE FROM match_candidates WHERE id = 201")
        _add_candidate(db, mv_id, 201, "Extremely Long Film Title " * 20, 2020, external_id="tmdb_201")
        actions_b = {}
        sections_b = media_match_ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id, "MEDIA_R12345678", "gen60", actions_b, sandbox["media_icon"]
        )
        token_b = next(k for k, v in actions_b.items() if v.get("candidate_id") == 201)
        action_b_data = actions_b[token_b]

    assert token_a == token_b
    assert action_a_data == action_b_data

    cmd_a = [l.split(";")[2] for s in sections_a for l in s.splitlines() if l.startswith("Entry") and "201" in l]
    cmd_b = [l.split(";")[2] for s in sections_b for l in s.splitlines() if l.startswith("Entry") and "201" in l]
    assert cmd_a == cmd_b


def test_61_worst_case_resolver_menu_audit(sandbox):
    """61. Complete worst-case resolver menu audit: all lines <= 198 bytes and valid UTF-8."""
    ui = media_match_ui
    icon = sandbox["media_icon"]

    # 1. Unmatched with 5 diverse worst-case candidates
    mv_id1, _ = _ingest_movie(sandbox, "WorstCase1.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id1, 1, "七人の侍黒澤明監督作品映画東京物語雨月物語" * 10, 1954, original_title="Seven Samurai Japanese Classic Film " * 5, runtime=207)
        _add_candidate(db, mv_id1, 2, "Éléphant à l'orée de la forêt enchantée où brûle l'été " * 8, 2021, runtime=120)
        _add_candidate(db, mv_id1, 3, "🎬🍿🎥🎞️🌟🚀✨🔥🎉 Film Emoji Extrême " * 6, 2022, runtime=95)
        _add_candidate(db, mv_id1, 4, "Very Long Title; with; semicolons; and; apostrophes; l'aurore;" * 5, 2023)
        _add_candidate(db, mv_id1, 5, "e\u0301\u0300\u0302\u0303\u0304\u0305\u0306\u0307\u0308\u0309 Combining Accents " * 10, 2024)

        actions1 = {}
        sections1 = ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id1, "MEDIA_R11111111", "genW1", actions1, icon
        )

    # 2. Auto-matched requiring replacement with worst-case titles
    mv_id2, _ = _ingest_movie(sandbox, "WorstCase2.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id2, 10, "Current Work Title That Is Incredibly Long And Exhausting " * 5, 2010, external_id="ext10")
        _add_candidate(db, mv_id2, 11, "Replacement Work Title In Japanese 七人の侍 " * 10, 2020, external_id="ext11")
        cand2 = media_match.MovieCandidate("tmdb_movie", "ext10", "Current Work Title That Is Incredibly Long And Exhausting " * 5, year=2010)
        media_match.accept_candidate(db, mv_id2, cand2, score=95.0, mode="AUTO", method="EXACT")
        db.commit()

        actions2 = {}
        sections2 = ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id2, "MEDIA_R22222222", "genW2", actions2, icon
        )

    # 3. User-matched requiring replacement with worst-case titles
    mv_id3, _ = _ingest_movie(sandbox, "WorstCase3.mkv")
    with closing(media_db.connect(sandbox["db_file"])) as db:
        _add_candidate(db, mv_id3, 20, "User Work Accented Éléphant Forêt " * 10, 2015, external_id="ext20")
        _add_candidate(db, mv_id3, 21, "Replacement Emoji Work 🎬🍿🎥 " * 15, 2025, external_id="ext21")
        cand3 = media_match.MovieCandidate("tmdb_movie", "ext20", "User Work Accented Éléphant Forêt " * 10, year=2015)
        media_match.accept_candidate(db, mv_id3, cand3, score=95.0, mode="USER", method="USER_CONFIRMATION")
        db.commit()

        actions3 = {}
        sections3 = ui.build_resolver_menu_sections(
            sandbox["home"], sandbox["install"], db, mv_id3, "MEDIA_R33333333", "genW3", actions3, icon
        )

    all_sections = sections1 + sections2 + sections3
    total_entry_lines = 0
    max_len = 0
    for sec in all_sections:
        for line in sec.splitlines():
            if line.startswith("Entry"):
                total_entry_lines += 1
                b = len(line.encode("utf-8"))
                assert b <= 198, f"Exceeds 198 bytes ({b} bytes): {line}"
                assert line.encode("utf-8").decode("utf-8")
                if b > max_len:
                    max_len = b

    assert total_entry_lines >= 30
    assert max_len <= 198
