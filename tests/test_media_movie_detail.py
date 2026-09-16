# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic qualification test suite for OPENHTPC DEV6B3 Movie Detail Page.

Verifies:
1. Activating identified media opens MEDIA_D submenu
2. Detail LIRE LE FILM uses exact existing resource token
3. Detail page valid cached poster
4. Poster cache miss fallback
5. Correct display title
6. Original title omitted when identical
7. Original title shown when different
8. Runtime formatting
9. Date/year formatting
10. Genre formatting
11. Synopsis displayed
12. Long synopsis safely bounded
13. UTF-8 synopsis safely bounded
14. Semicolon/newline injection sanitized
15. All detail INI lines <= 198 bytes
16. Resolver action targets canonical MEDIA_R section
17. Unmatched -> IDENTIFIER LE FILM
18. Matched -> CHANGER L’IDENTIFICATION
19. RETOUR uses :back
20. Missing presentation remains playable
21. Malformed presentation remains playable
22. Missing poster remains playable
23. Zero network during media generation
24. Zero DB mutation
25. Existing parent MEDIA context action preserved
26. Same exact playback command/token semantics preserved
27. No second Flex/helper process
28. Playback lifecycle architecture retains detail current_menu
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


media_db = _load_module(PAYLOAD / "openhtpc-media-db.py", "media_db_detail_test")
session_engine = _load_module(PAYLOAD / "openhtpc-session-engine.py", "session_engine_detail_test")
media_artwork = _load_module(PAYLOAD / "openhtpc-media-artwork.py", "media_artwork_detail_test")

JPEG_SYNTHETIC = b"\xff\xd8" + b"A" * 1024 + b"\xff\xd9"
NOW = "2026-09-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def guard_network():
    """Guarantee zero network calls during DEV6B3 tests (Invariant 57)."""
    orig_connect = socket.socket.connect

    def guarded_connect(*args, **kwargs):
        raise AssertionError("Network contact strictly forbidden in DEV6B3 tests")

    with mock.patch("socket.socket.connect", guarded_connect):
        yield


@pytest.fixture
def env(tmp_path):
    """Hermetic isolated environment for movie detail page tests."""
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir(parents=True)

    # Copy relevant scripts into install directory
    for name in (
        "openhtpc-media-db.py", "openhtpc-session-engine.py", "openhtpc-media-artwork.py",
        "openhtpc-media-match-ui", "openhtpc-optical.py", "openhtpc-ui.py", "openhtpc-theme.py",
    ):
        src = PAYLOAD / name
        if src.is_file():
            dest = install / name
            dest.write_bytes(src.read_bytes())
            dest.chmod(0o755)

    (install / "assets/ui").mkdir(parents=True)
    media_icon = install / "assets/ui/media.png"
    media_icon.write_bytes(b"dummy-png")

    db_dir = home / ".local/share/openhtpc/media"
    db_dir.mkdir(parents=True)
    db_file = db_dir / "media.db"
    media_db.initialize(db_file)

    sources_dir = tmp_path / "movies"
    sources_dir.mkdir()

    config_dir = home / ".config/openhtpc"
    config_dir.mkdir(parents=True)

    uid = os.getuid()
    short_icon = Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(media_icon)
    except OSError:
        pass

    user_config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(sources_dir)],
    }
    (config_dir / "user-config.json").write_text(json.dumps(user_config, indent=2))

    created_aliases: list[Path] = []

    def track_alias(work_id: int) -> Path:
        p = Path(f"/tmp/ohtpc-{uid}-p{work_id}.jpg")
        created_aliases.append(p)
        return p

    yield {
        "home": home,
        "install": install,
        "db_file": db_file,
        "sources_dir": sources_dir,
        "media_icon": media_icon,
        "uid": uid,
        "track_alias": track_alias,
    }

    # Teardown: clean up any ephemeral test aliases in /tmp
    for alias in created_aliases:
        if alias.is_symlink():
            try:
                alias.unlink(missing_ok=True)
            except OSError:
                pass


def _seed_movie(env: dict, filename: str = "The Thing (1982).mkv", work_id: int = 1, external_id: str = "1091", title: str = "The Thing", year: int = 1982, state: str = "USER_MATCHED"):
    """Seed resources, media_versions, works, external_ids for a movie."""
    db_file = env["db_file"]
    sources_dir = env["sources_dir"]
    media_file = sources_dir / filename
    media_file.write_bytes(b"video-data")

    with closing(media_db.connect(db_file)) as db:
        existing_work = db.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
        if not existing_work:
            db.execute("INSERT INTO works VALUES (?, 'MOVIE', ?, ?, ?, ?, ?, ?)",
                       (work_id, title, title, title.lower(), year, NOW, NOW))
            db.execute("INSERT INTO external_ids VALUES (?, ?, 'tmdb_movie', ?, 'EXACT', ?)",
                       (work_id, work_id, external_id, NOW))

        mv_id = work_id
        db.execute(
            "INSERT INTO media_versions (id, work_id, provisional_title, provisional_year, identification_state, match_method, match_locked, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'USER_CONFIRMATION', 1, ?, ?)",
            (mv_id, work_id, title, year, state, NOW, NOW),
        )
        source_id = session_engine.media_source_id(sources_dir.resolve())
        db.execute(
            "INSERT INTO resources (media_version_id, resource_kind, source_id, relative_path, file_size, mtime_ns, created_at) "
            "VALUES (?, 'FILE', ?, ?, 10, 1000, ?)",
            (mv_id, source_id, filename, NOW),
        )
        db.commit()
    return media_file


def _seed_presentation(
    env: dict,
    work_id: int = 1,
    external_id_id: int = 1,
    poster_path: str = "/the_thing.jpg",
    display_title: str = "The Thing",
    display_original_title: str = "The Thing",
    release_date: str = "1982-06-25",
    runtime_minutes: int | None = 109,
    overview: str = "Un classique du cinéma d'horreur et de science-fiction.",
    genres_json: str = '["Horreur", "Mystère", "Science-Fiction"]',
    kind: str = "MOVIE_DETAILS",
    provider: str = "tmdb_movie",
    locale: str = "fr-FR",
    malformed_json: bool = False,
):
    """Seed provider_snapshots and work_presentations for a work."""
    db_file = env["db_file"]
    snap_id = work_id
    payload = {"id": 1091, "poster_path": poster_path, "title": display_title}
    payload_str = "{bad json" if malformed_json else json.dumps(payload)

    with closing(media_db.connect(db_file)) as db:
        db.execute(
            "INSERT INTO provider_snapshots (id, external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (snap_id, external_id_id, kind, locale, payload_str, NOW, NOW, NOW),
        )
        db.execute(
            "INSERT INTO work_presentations (id, work_id, locale, source_snapshot_id, display_title, display_original_title, release_date, runtime_minutes, overview, genres_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (work_id, work_id, locale, snap_id, display_title, display_original_title, release_date, runtime_minutes, overview, genres_json, NOW, NOW),
        )
        db.commit()


def _write_canonical_cache(home: Path, poster_path: str, data: bytes = JPEG_SYNTHETIC) -> Path:
    """Write synthetic JPEG to canonical cache."""
    material = f"tmdb_movie|poster|w500|{poster_path}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    cache_file = home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500" / f"{digest}.jpg"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(data)
    return cache_file


def _get_section_lines(sections_text: str, section_header: str) -> list[str]:
    """Extract entry lines from a specific INI section."""
    lines = sections_text.splitlines()
    in_section = False
    result = []
    for line in lines:
        if line.strip() == section_header:
            in_section = True
            continue
        if in_section:
            if line.startswith("["):
                break
            if line.strip():
                result.append(line)
    return result


# ==============================================================================
# 1. ACTIVATING IDENTIFIED MEDIA OPENS MEDIA_D SUBMENU
# ==============================================================================

def test_01_activating_identified_media_opens_media_d_submenu(env):
    """1. Activating movie row in MEDIA navigates to :submenu MEDIA_D<item_id[:8]>."""
    _seed_movie(env)
    _seed_presentation(env)
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])

    # Find the parent row in MEDIA
    movie_lines = [l for l in sections_text.splitlines() if "The Thing" in l and ":submenu MEDIA_D" in l]
    assert len(movie_lines) == 1
    parts = movie_lines[0].split(";")
    assert parts[2].startswith(":submenu MEDIA_D")

    # Detail section must exist in output
    detail_sec_name = parts[2].replace(":submenu ", "")
    assert f"[{detail_sec_name}]" in sections_text


# ==============================================================================
# 2. DETAIL LIRE LE FILM USES EXACT EXISTING RESOURCE TOKEN
# ==============================================================================

def test_02_detail_lire_le_film_uses_exact_existing_resource_token(env):
    """2. Entry 1 in detail page is LIRE LE FILM invoking exact pre-registered action token."""
    _seed_movie(env)
    _seed_presentation(env)
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], generation="gen42")

    detail_lines = [l for l in sections_text.splitlines() if "LIRE LE FILM" in l]
    assert len(detail_lines) == 1
    entry1 = detail_lines[0]
    parts = entry1.split(";")
    assert parts[0] == "Entry1=LIRE LE FILM"
    assert parts[2].startswith("$HOME/.local/lib/openhtpc/openhtpc-play mact_")


# ==============================================================================
# 3. DETAIL PAGE VALID CACHED POSTER
# ==============================================================================

def test_03_detail_page_valid_cached_poster(env):
    """3. Valid cached poster projection appears as icon on detail Entry 1."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/poster123.jpg")
    _write_canonical_cache(env["home"], "/poster123.jpg")
    alias = env["track_alias"](1)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    entry1 = [l for l in sections_text.splitlines() if "LIRE LE FILM" in l][0]
    parts = entry1.split(";")
    assert parts[1] == str(alias)
    assert alias.is_symlink()


# ==============================================================================
# 4. POSTER CACHE MISS FALLBACK
# ==============================================================================

def test_04_poster_cache_miss_fallback(env):
    """4. Poster cache miss falls back to generic media icon on detail page."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/missing_poster.jpg")
    alias = env["track_alias"](1)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    entry1 = [l for l in sections_text.splitlines() if "LIRE LE FILM" in l][0]
    parts = entry1.split(";")
    assert str(alias) not in parts[1]
    assert "ohtpc-" in parts[1] or str(env["media_icon"]) in parts[1]


# ==============================================================================
# 5. CORRECT DISPLAY TITLE
# ==============================================================================

def test_05_correct_display_title(env):
    """5. Movie detail page displays localized display_title from work_presentations."""
    _seed_movie(env)
    _seed_presentation(env, display_title="The Thing (1982)", display_original_title="The Thing")

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    title_line = lines[1]
    assert title_line.startswith("Entry2=The Thing (1982)")
    assert ":fork true" in title_line


# ==============================================================================
# 6. ORIGINAL TITLE OMITTED WHEN IDENTICAL
# ==============================================================================

def test_06_original_title_omitted_when_identical(env):
    """6. Original title is omitted when effectively identical to display_title."""
    _seed_movie(env)
    _seed_presentation(env, display_title="The Thing", display_original_title="the thing")

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    title_line = lines[1]
    assert title_line.split(";")[0] == "Entry2=The Thing"
    assert "Titre original" not in title_line


# ==============================================================================
# 7. ORIGINAL TITLE SHOWN WHEN DIFFERENT
# ==============================================================================

def test_07_original_title_shown_when_different(env):
    """7. Original title is displayed when meaningfully different from display_title."""
    _seed_movie(env)
    _seed_presentation(env, display_title="La Chose", display_original_title="The Thing")

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    title_line = lines[1]
    assert title_line.split(";")[0] == "Entry2=La Chose · Titre original : The Thing"


# ==============================================================================
# 8. RUNTIME FORMATTING
# ==============================================================================

def test_08_runtime_formatting(env):
    """8. Runtime formatting follows couch standard (109 -> '1 h 49', 45 -> '45 min', etc.)."""
    assert session_engine._format_runtime(109) == "1 h 49"
    assert session_engine._format_runtime(45) == "45 min"
    assert session_engine._format_runtime(60) == "1 h"
    assert session_engine._format_runtime(65) == "1 h 05"
    assert session_engine._format_runtime(120) == "2 h"
    assert session_engine._format_runtime(0) is None
    assert session_engine._format_runtime(-5) is None
    assert session_engine._format_runtime(None) is None
    assert session_engine._format_runtime("not-a-number") is None

    _seed_movie(env)
    _seed_presentation(env, runtime_minutes=109)
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    meta_line = lines[2]
    assert "1 h 49" in meta_line


# ==============================================================================
# 9. DATE / YEAR FORMATTING
# ==============================================================================

def test_09_date_year_formatting(env):
    """9. Date/year extraction extracts 4-digit year from release_date or fallback."""
    assert session_engine._extract_year("1982-06-25") == "1982"
    assert session_engine._extract_year("1982") == "1982"
    assert session_engine._extract_year("", fallback_year=1982) == "1982"
    assert session_engine._extract_year(None, fallback_year=1982) == "1982"
    assert session_engine._extract_year("invalid-date", fallback_year=1982) == "1982"
    assert session_engine._extract_year("invalid-date", fallback_year=None) is None

    _seed_movie(env)
    _seed_presentation(env, release_date="1982-06-25")
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    meta_line = lines[2]
    assert meta_line.startswith("Entry3=1982")


# ==============================================================================
# 10. GENRE FORMATTING
# ==============================================================================

def test_10_genre_formatting(env):
    """10. Genres are safely parsed from JSON and formatted as comma-separated text."""
    genres = '["Horreur", "Mystère", "Science-Fiction"]'
    assert session_engine._format_genres(genres) == "Horreur, Mystère, Science-Fiction"
    assert session_engine._format_genres('["Action"]') == "Action"
    assert session_engine._format_genres('{invalid') is None
    assert session_engine._format_genres('123') is None
    assert session_engine._format_genres('[]') is None
    assert session_engine._format_genres(None) is None

    _seed_movie(env)
    _seed_presentation(env, genres_json=genres)
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    meta_line = lines[2]
    assert "Horreur, Mystère, Science-Fiction" in meta_line


# ==============================================================================
# 11. SYNOPSIS DISPLAYED
# ==============================================================================

def test_11_synopsis_displayed(env):
    """11. Overview from work_presentations is displayed on detail page."""
    overview = "Une équipe de chercheurs en Antarctique fait face à une forme de vie extraterrestre."
    _seed_movie(env)
    _seed_presentation(env, overview=overview)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    synopsis_line = lines[3]
    assert overview in synopsis_line
    assert ":fork true" in synopsis_line


# ==============================================================================
# 12. LONG SYNOPSIS SAFELY BOUNDED
# ==============================================================================

def test_12_long_synopsis_safely_bounded(env):
    """12. Long synopsis is chunked into at most two rows and bounded safely."""
    long_overview = (
        "Au cœur de l'Antarctique, une équipe de scientifiques découvre un vaisseau spatial "
        "enfoui sous la glace depuis des millénaires. En explorant l'épave, ils libèrent accidentellement "
        "une créature extraterrestre capable d'assimiler et d'imiter parfaitement toute forme de vie. "
        "La paranoïa s'installe alors parmi les membres de la base isolée du reste du monde."
    )
    chunks = session_engine._chunk_synopsis(long_overview, max_row_bytes=120, max_rows=2)
    assert 1 <= len(chunks) <= 2
    assert all(len(c.encode("utf-8")) <= 120 for c in chunks)
    if len(chunks) == 2:
        assert chunks[1].endswith("…")

    _seed_movie(env)
    _seed_presentation(env, overview=long_overview)
    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)
    synopsis_entries = [l for l in lines if l.startswith("Entry4=") or l.startswith("Entry5=")]
    assert len(synopsis_entries) >= 1


# ==============================================================================
# 13. UTF-8 SYNOPSIS SAFELY BOUNDED
# ==============================================================================

def test_13_utf8_synopsis_safely_bounded(env):
    """13. Multi-byte accented French overview is safely chunked without splitting code points."""
    french_text = "Éléphant à l'orée d'une forêt où brûle l'été méditerranéen. " * 5
    chunks = session_engine._chunk_synopsis(french_text, max_row_bytes=100, max_rows=2)
    for c in chunks:
        assert len(c.encode("utf-8")) <= 100
        # Check valid UTF-8 roundtrip
        assert c.encode("utf-8").decode("utf-8") == c


# ==============================================================================
# 14. SEMICOLON / NEWLINE INJECTION SANITIZED
# ==============================================================================

def test_14_semicolon_newline_injection_sanitized(env):
    """14. Injected semicolons and newlines in provider metadata are safely sanitized."""
    malicious_title = "Injected;rm -rf /;Title\nWith\rNewlines"
    malicious_overview = "Overview;with;semicolons\nand\r\nnewlines"
    malicious_genres = '["Horreur;Action", "Comédie\nDrame"]'

    _seed_movie(env)
    _seed_presentation(
        env,
        display_title=malicious_title,
        overview=malicious_overview,
        genres_json=malicious_genres,
    )

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    for line in lines:
        assert "\n" not in line
        assert "\r" not in line
        parts = line.split(";")
        # No extra fields injected into Flex entry
        assert len(parts) in (3, 5)


# ==============================================================================
# 15. ALL DETAIL INI LINES <= 198 BYTES
# ==============================================================================

def test_15_all_detail_ini_lines_le_198_bytes(env):
    """15. Every line in the generated detail section is <= 198 UTF-8 bytes."""
    huge_title = "Très long titre de film " * 10
    huge_orig = "Very long original film title " * 10
    huge_genres = '["' + '", "'.join(["Genre " + str(i) for i in range(20)]) + '"]'
    huge_overview = "Synopsis extrêmement long avec beaucoup de détails textuels. " * 15

    _seed_movie(env)
    _seed_presentation(
        env,
        display_title=huge_title,
        display_original_title=huge_orig,
        genres_json=huge_genres,
        overview=huge_overview,
    )

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    for line in lines:
        byte_len = len(line.encode("utf-8"))
        assert byte_len <= 198, f"Line exceeds 198 bytes ({byte_len}): {line}"


# ==============================================================================
# 16. RESOLVER ACTION TARGETS CANONICAL MEDIA_R SECTION
# ==============================================================================

def test_16_resolver_action_targets_canonical_media_r_section(env):
    """16. Detail identification action command targets existing canonical MEDIA_R section."""
    _seed_movie(env)
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    ident_lines = [l for l in lines if "CHANGER L’IDENTIFICATION" in l]
    assert len(ident_lines) == 1
    parts = ident_lines[0].split(";")
    assert parts[2].startswith(":submenu MEDIA_R")

    res_sec_header = f"[{parts[2].replace(':submenu ', '')}]"
    assert res_sec_header in sections_text


# ==============================================================================
# 17. UNMATCHED -> IDENTIFIER LE FILM
# ==============================================================================

def test_17_unmatched_exposes_identifier_le_film(env):
    """17. Unmatched video exposes IDENTIFIER LE FILM and local un-identified synopsis."""
    sources_dir = env["sources_dir"]
    raw_file = sources_dir / "UnknownMovie.2024.mkv"
    raw_file.write_bytes(b"data")

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    assert any("IDENTIFIER LE FILM" in l for l in lines)
    assert any("Fichier local non identifié." in l for l in lines)
    assert lines[0].startswith("Entry1=LIRE LE FILM;")


# ==============================================================================
# 18. MATCHED -> CHANGER L’IDENTIFICATION
# ==============================================================================

def test_18_matched_exposes_changer_identification(env):
    """18. Matched video exposes CHANGER L’IDENTIFICATION."""
    _seed_movie(env, state="USER_MATCHED")
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    assert any("CHANGER L’IDENTIFICATION" in l for l in lines)
    assert not any("IDENTIFIER LE FILM" in l for l in lines)


# ==============================================================================
# 19. RETOUR USES :back
# ==============================================================================

def test_19_retour_uses_back(env):
    """19. RETOUR entry uses Flex internal :back command."""
    _seed_movie(env)
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    retour_line = lines[-1]
    assert "RETOUR" in retour_line
    assert retour_line.endswith(";:back")


# ==============================================================================
# 20. MISSING PRESENTATION REMAINS PLAYABLE
# ==============================================================================

def test_20_missing_presentation_remains_playable(env):
    """20. Movie with matched work but no presentation row remains fully playable."""
    _seed_movie(env)
    # No presentation seeded

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    assert lines[0].startswith("Entry1=LIRE LE FILM;")
    assert "openhtpc-play" in lines[0]
    assert any("Aucun synopsis disponible." in l for l in lines)


# ==============================================================================
# 21. MALFORMED PRESENTATION REMAINS PLAYABLE
# ==============================================================================

def test_21_malformed_presentation_remains_playable(env):
    """21. Movie with malformed presentation row falls back safely and remains playable."""
    _seed_movie(env)
    _seed_presentation(env, malformed_json=True)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    assert lines[0].startswith("Entry1=LIRE LE FILM;")
    assert "openhtpc-play" in lines[0]
    assert any("Présentation non disponible." in l for l in lines)


# ==============================================================================
# 22. MISSING POSTER REMAINS PLAYABLE
# ==============================================================================

def test_22_missing_poster_remains_playable(env):
    """22. Movie without cached poster remains playable with generic media icon."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="")

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    detail_sec = [l for l in sections_text.splitlines() if l.startswith("[MEDIA_D")][0]
    lines = _get_section_lines(sections_text, detail_sec)

    assert lines[0].startswith("Entry1=LIRE LE FILM;")
    assert "openhtpc-play" in lines[0]


# ==============================================================================
# 23. ZERO NETWORK DURING MEDIA GENERATION
# ==============================================================================

def test_23_zero_network_during_media_generation(env):
    """23. Zero network sockets or HTTP requests during media detail generation."""
    _seed_movie(env)
    _seed_presentation(env)

    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("urllib called")):
        with mock.patch("urllib.request.build_opener", side_effect=AssertionError("build_opener called")):
            session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])


# ==============================================================================
# 24. ZERO DB MUTATION
# ==============================================================================

def test_24_zero_db_mutation(env):
    """24. Database SHA256 is bit-for-bit identical before and after detail page generation."""
    _seed_movie(env)
    _seed_presentation(env)

    db_path = env["db_file"]
    before_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()

    config_path = env["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.publish_flex_config(config_path, env["home"], [env["sources_dir"]], env["install"])

    after_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before_sha == after_sha


# ==============================================================================
# 25. EXISTING PARENT MEDIA CONTEXT ACTION PRESERVED
# ==============================================================================

def test_25_existing_parent_media_context_action_preserved(env):
    """25. Parent MEDIA row preserves right-arrow resolver context action."""
    _seed_movie(env)
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    movie_row = [l for l in sections_text.splitlines() if "The Thing" in l and ":submenu MEDIA_D" in l][0]
    parts = movie_row.split(";")
    assert len(parts) == 5
    assert parts[3].startswith(":submenu MEDIA_R")
    assert parts[4] == "CHANGER L’IDENTIFICATION"


# ==============================================================================
# 26. SAME EXACT PLAYBACK COMMAND / TOKEN SEMANTICS PRESERVED
# ==============================================================================

def test_26_same_exact_playback_command_token_semantics_preserved(env):
    """26. Detail LIRE LE FILM action token corresponds exactly to recorded media action."""
    _seed_movie(env)
    _seed_presentation(env)

    actions_manifest = env["home"] / ".config/openhtpc/actions.json"
    _root, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], generation="gen26", manifest_target=actions_manifest
    )

    detail_play = [l for l in sections_text.splitlines() if "LIRE LE FILM" in l][0]
    token = detail_play.split(";")[2].split()[-1]

    assert actions_manifest.is_file()
    actions_data = json.loads(actions_manifest.read_text(encoding="utf-8"))
    assert token in actions_data["items"]
    assert actions_data["items"][token]["item_type"] == "file"


# ==============================================================================
# 27. NO SECOND FLEX / HELPER PROCESS
# ==============================================================================

def test_27_no_second_flex_or_helper_process(env):
    """27. INI configuration contains zero flex-launcher launches or helper processes."""
    _seed_movie(env)
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    for line in sections_text.splitlines():
        if line.startswith("Entry"):
            assert "flex-launcher" not in line


# ==============================================================================
# 28. PLAYBACK LIFECYCLE ARCHITECTURE RETAINS DETAIL CURRENT_MENU
# ==============================================================================

def test_28_playback_lifecycle_architecture_retains_detail_current_menu(env):
    """28. Flex lifecycle retains current_menu=MEDIA_D... upon MPV termination."""
    _seed_movie(env)
    _seed_presentation(env)

    _root, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"])
    # Parent row transitions to MEDIA_D
    parent_line = [l for l in sections_text.splitlines() if ":submenu MEDIA_D" in l][0]
    target_menu = parent_line.split(";")[2].replace(":submenu ", "")

    # In MEDIA_D, Entry 1 is synchronous openhtpc-play command (tracked by Flex lifecycle)
    detail_lines = _get_section_lines(sections_text, f"[{target_menu}]")
    play_line = detail_lines[0]
    assert play_line.startswith("Entry1=LIRE LE FILM;")
    assert "$HOME/.local/lib/openhtpc/openhtpc-play" in play_line

    # RETOUR command is :back, allowing pop back to parent
    retour_line = detail_lines[-1]
    assert retour_line.endswith(";:back")
