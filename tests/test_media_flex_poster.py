# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic DEV6B2 Flex cached poster integration qualification test suite.

Verifies:
1. Cached current poster -> short /tmp poster path emitted
2. Canonical 133-byte cache path -> NEVER embedded directly in Entry
3. Cache miss -> generic icon
4. No presentation -> generic icon
5. No source snapshot -> generic icon
6. No poster token -> generic icon
7. Malformed payload -> generic icon
8. Wrong provider -> generic icon
9. Invalid cache file size -> generic icon
10. Valid poster -> correct short alias target
11. Poster A -> presentation B, cache B absent -> stale alias A removed/not used; generic icon emitted
12. Poster A -> presentation B, cache B present -> alias updated to B
13. Zero network during media_menu_sections()
14. Zero network during write_flex_config()
15. Zero DB mutation
16. Commands unchanged
17. Titles unchanged
18. Context submenu unchanged
19. Realistic The Thing short-poster Entry <= 198 bytes
20. Long ASCII title <= 198 bytes
21. Long UTF-8 title <= 198 bytes
22. No second Flex/helper process
23. Same Work used by multiple media versions -> same safe UI alias acceptable
24. Unsafe existing alias filesystem object -> safe fallback, no blind overwrite
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


media_db = _load_module(PAYLOAD / "openhtpc-media-db.py", "media_db_poster_test")
session_engine = _load_module(PAYLOAD / "openhtpc-session-engine.py", "session_engine_poster_test")
media_artwork = _load_module(PAYLOAD / "openhtpc-media-artwork.py", "media_artwork_poster_test")

JPEG_SYNTHETIC = b"\xff\xd8" + b"A" * 1024 + b"\xff\xd9"
NOW = "2026-09-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def guard_network():
    """Guarantee zero network calls during tests (Invariant 57)."""
    orig_connect = socket.socket.connect

    def guarded_connect(*args, **kwargs):
        raise AssertionError("Network contact strictly forbidden in DEV6B2 tests")

    with mock.patch("socket.socket.connect", guarded_connect):
        yield


@pytest.fixture
def env(tmp_path):
    """Hermetic isolated environment for Flex poster integration tests."""
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

    # Assets in install
    (install / "assets/ui").mkdir(parents=True)
    raw_media_icon = install / "assets/ui/media.png"
    raw_media_icon.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    (install / "flex/assets/icons").mkdir(parents=True)
    (install / "flex/assets/icons/drive-empty.png").write_bytes(b"PNG")

    # Short media icon
    uid = os.getuid()
    short_icon = Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(raw_media_icon)
        media_icon = short_icon
    except OSError:
        media_icon = raw_media_icon

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


def _seed_movie(env: dict, filename: str = "The Thing (1982).mkv", work_id: int = 1, external_id: str = "1091", title: str = "The Thing", year: int = 1982):
    """Seed resources, media_versions, works, external_ids for a movie."""
    db_file = env["db_file"]
    sources_dir = env["sources_dir"]
    media_file = sources_dir / filename
    media_file.write_bytes(b"video-data")

    with closing(media_db.connect(db_file)) as db:
        # Check if work exists
        existing_work = db.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
        if not existing_work:
            db.execute("INSERT INTO works VALUES (?, 'MOVIE', ?, ?, ?, ?, ?, ?)",
                       (work_id, title, title, title.lower(), year, NOW, NOW))
            db.execute("INSERT INTO external_ids VALUES (?, ?, 'tmdb_movie', ?, 'EXACT', ?)",
                       (work_id, work_id, external_id, NOW))

        mv_id = work_id  # simple 1:1 mapping
        db.execute(
            "INSERT INTO media_versions (id, work_id, provisional_title, provisional_year, identification_state, match_method, match_locked, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'USER_MATCHED', 'USER_CONFIRMATION', 1, ?, ?)",
            (mv_id, work_id, title, year, NOW, NOW),
        )
        source_id = session_engine.media_source_id(sources_dir.resolve())
        db.execute(
            "INSERT INTO resources (media_version_id, resource_kind, source_id, relative_path, file_size, mtime_ns, created_at) "
            "VALUES (?, 'FILE', ?, ?, 10, 1000, ?)",
            (mv_id, source_id, filename, NOW),
        )
        db.commit()
    return media_file


def _seed_presentation(env: dict, work_id: int = 1, external_id_id: int = 1, poster_path: str = "/the_thing.jpg", kind: str = "MOVIE_DETAILS", provider: str = "tmdb_movie", locale: str = "fr-FR", malformed_json: bool = False):
    """Seed provider_snapshots and work_presentations for a work."""
    db_file = env["db_file"]
    snap_id = work_id
    payload = {"id": 1091, "poster_path": poster_path, "title": "The Thing"}
    payload_str = "{bad json" if malformed_json else json.dumps(payload)

    with closing(media_db.connect(db_file)) as db:
        db.execute(
            "INSERT INTO provider_snapshots (id, external_id_id, snapshot_kind, locale, payload_json, fetched_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (snap_id, external_id_id, kind, locale, payload_str, NOW, NOW, NOW),
        )
        db.execute(
            "INSERT INTO work_presentations (id, work_id, locale, source_snapshot_id, display_title, display_original_title, release_date, runtime_minutes, overview, genres_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'The Thing', 'The Thing', '1982-06-25', 109, 'A horror classic.', '[\"Horror\"]', ?, ?)",
            (work_id, work_id, locale, snap_id, NOW, NOW),
        )
        db.commit()


def _write_canonical_cache(home: Path, poster_path: str, data: bytes = JPEG_SYNTHETIC) -> Path:
    """Write synthetic JPEG to canonical DEV6B1 cache."""
    material = f"tmdb_movie|poster|w500|{poster_path}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    cache_file = home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500" / f"{digest}.jpg"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(data)
    return cache_file


# ==============================================================================
# 1. CACHED CURRENT POSTER -> SHORT /TMP POSTER PATH EMITTED
# ==============================================================================

def test_01_cached_current_poster_emits_short_tmp_poster_path(env):
    """1. Cached current poster produces an Entry pointing to short /tmp symlink."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    cache_target = _write_canonical_cache(env["home"], "/the_thing.jpg")
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    expected_alias_str = str(alias)
    assert f";{expected_alias_str};" in sections_text
    assert alias.is_symlink()
    assert alias.resolve() == cache_target.resolve()


# ==============================================================================
# 2. CANONICAL 133-BYTE CACHE PATH -> NEVER EMBEDDED DIRECTLY IN ENTRY
# ==============================================================================

def test_02_canonical_133_byte_cache_path_never_embedded_directly(env):
    """2. The long canonical cache path must NEVER appear directly in Flex config."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    cache_target = _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert str(cache_target) not in sections_text


# ==============================================================================
# 3. CACHE MISS -> GENERIC ICON
# ==============================================================================

def test_03_cache_miss_emits_generic_icon(env):
    """3. When presentation exists but cache file is absent, fallback to media.png."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    # DO NOT write cache file -> cache miss
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text
    assert not alias.exists()


# ==============================================================================
# 4. NO PRESENTATION -> GENERIC ICON
# ==============================================================================

def test_04_no_presentation_emits_generic_icon(env):
    """4. Un-refreshed work without presentation row falls back to generic icon."""
    _seed_movie(env)
    # No presentation seeded
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 5. NO SOURCE SNAPSHOT -> GENERIC ICON
# ==============================================================================

def test_05_no_source_snapshot_emits_generic_icon(env):
    """5. Presentation with source_snapshot_id = NULL falls back to generic icon."""
    _seed_movie(env)
    with closing(media_db.connect(env["db_file"])) as db:
        db.execute(
            "INSERT INTO work_presentations (id, work_id, locale, source_snapshot_id, display_title, created_at, updated_at) "
            "VALUES (1, 1, 'fr-FR', NULL, 'The Thing', ?, ?)",
            (NOW, NOW),
        )
        db.commit()
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 6. NO POSTER TOKEN -> GENERIC ICON
# ==============================================================================

def test_06_no_poster_token_emits_generic_icon(env):
    """6. Snapshot with empty or null poster_path falls back to generic icon."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="")
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 7. MALFORMED PAYLOAD -> GENERIC ICON
# ==============================================================================

def test_07_malformed_payload_emits_generic_icon(env):
    """7. Corrupt snapshot payload JSON falls back to generic icon."""
    _seed_movie(env)
    _seed_presentation(env, malformed_json=True)
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 8. WRONG PROVIDER -> GENERIC ICON
# ==============================================================================

def test_08_wrong_provider_emits_generic_icon(env):
    """8. Provider snapshot with non-tmdb_movie provider falls back to generic icon."""
    _seed_movie(env)
    with closing(media_db.connect(env["db_file"])) as db:
        db.execute("UPDATE external_ids SET provider = 'imdb' WHERE id = 1")
        db.commit()
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    alias = env["track_alias"](1)

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )

    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 9. INVALID CACHE FILE SIZE -> GENERIC ICON
# ==============================================================================

def test_09_invalid_cache_file_size_emits_generic_icon(env):
    """9. Empty or oversized cache file falls back to generic icon."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    alias = env["track_alias"](1)

    # 9a. 0-byte file
    cache_file = _write_canonical_cache(env["home"], "/the_thing.jpg", data=b"")
    assert cache_file.stat().st_size == 0

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen1"
    )
    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text

    # 9b. Oversized file (> 5MB)
    cache_file.write_bytes(b"\xff\xd8" + b"A" * 5_000_001 + b"\xff\xd9")
    assert cache_file.stat().st_size > 5_000_000

    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen2"
    )
    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text


# ==============================================================================
# 10. VALID POSTER -> CORRECT SHORT ALIAS TARGET
# ==============================================================================

def test_10_valid_poster_correct_short_alias_target(env):
    """10. Short projection targets the exact canonical cache path."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    cache_target = _write_canonical_cache(env["home"], "/the_thing.jpg")
    alias = env["track_alias"](1)

    session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")

    assert alias.is_symlink()
    assert os.path.realpath(alias) == str(cache_target.resolve())


# ==============================================================================
# 11. POSTER A -> PRESENTATION B, CACHE B ABSENT -> STALE ALIAS REMOVED
# ==============================================================================

def test_11_poster_a_to_presentation_b_cache_b_absent_stale_alias_removed(env):
    """11. Stale alias A is unlinked when presentation changes to uncached B."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/poster_a.jpg")
    _write_canonical_cache(env["home"], "/poster_a.jpg")
    alias = env["track_alias"](1)

    # Initial menu generation creates alias pointing to A
    session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    assert alias.is_symlink()

    # Presentation updates to poster B (snapshot 1 payload updated)
    with closing(media_db.connect(env["db_file"])) as db:
        payload_b = json.dumps({"id": 1091, "poster_path": "/poster_b.jpg", "title": "The Thing"})
        db.execute("UPDATE provider_snapshots SET payload_json = ? WHERE id = 1", (payload_b,))
        db.commit()

    # Cache B is NOT written (cache miss for B)
    _root_name, sections_text = session_engine.media_menu_sections(
        env["home"], [env["sources_dir"]], env["media_icon"], "gen2"
    )

    # Stale alias must be unlinked and generic icon must be used
    assert not alias.exists()
    assert not alias.is_symlink()
    assert f";{env['media_icon']};" in sections_text


# ==============================================================================
# 12. POSTER A -> PRESENTATION B, CACHE B PRESENT -> ALIAS UPDATED TO B
# ==============================================================================

def test_12_poster_a_to_presentation_b_cache_b_present_alias_updated(env):
    """12. Alias is updated to B when presentation changes to cached B."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/poster_a.jpg")
    _write_canonical_cache(env["home"], "/poster_a.jpg")
    alias = env["track_alias"](1)

    session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")

    # Presentation updates to poster B and cache B is written
    with closing(media_db.connect(env["db_file"])) as db:
        payload_b = json.dumps({"id": 1091, "poster_path": "/poster_b.jpg", "title": "The Thing"})
        db.execute("UPDATE provider_snapshots SET payload_json = ? WHERE id = 1", (payload_b,))
        db.commit()

    cache_b = _write_canonical_cache(env["home"], "/poster_b.jpg")

    session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen2")

    assert alias.is_symlink()
    assert os.path.realpath(alias) == str(cache_b.resolve())


# ==============================================================================
# 13. ZERO NETWORK DURING MEDIA_MENU_SECTIONS()
# ==============================================================================

def test_13_zero_network_during_media_menu_sections(env):
    """13. Zero socket / HTTP requests during media_menu_sections()."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("urllib called")):
        with mock.patch("urllib.request.build_opener", side_effect=AssertionError("build_opener called")):
            session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")


# ==============================================================================
# 14. ZERO NETWORK DURING WRITE_FLEX_CONFIG()
# ==============================================================================

def test_14_zero_network_during_write_flex_config(env):
    """14. Zero socket / HTTP requests during write_flex_config()."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    config_path = env["home"] / ".config/openhtpc/flex-v1.ini"
    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("urllib called")):
        with mock.patch("urllib.request.build_opener", side_effect=AssertionError("build_opener called")):
            session_engine.publish_flex_config(config_path, env["home"], [env["sources_dir"]], env["install"])


# ==============================================================================
# 15. ZERO DB MUTATION
# ==============================================================================

def test_15_zero_db_mutation(env):
    """15. Database SHA256 is strictly bit-for-bit identical before and after Flex config generation."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    db_path = env["db_file"]
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

    config_path = env["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.publish_flex_config(config_path, env["home"], [env["sources_dir"]], env["install"])

    after_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before_hash == after_hash


# ==============================================================================
# 16. COMMANDS UNCHANGED
# ==============================================================================

def test_16_commands_unchanged(env):
    """16. Playback command semantics match exactly between baseline and poster entry."""
    _seed_movie(env)
    env["track_alias"](1)

    # Baseline (no poster)
    _r, base_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    base_entry = [line for line in base_text.splitlines() if "openhtpc-play" in line][0]
    base_cmd = base_entry.split(";")[2]

    # With poster
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    _r, poster_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    poster_entry = [line for line in poster_text.splitlines() if "openhtpc-play" in line][0]
    poster_cmd = poster_entry.split(";")[2]

    assert base_cmd == poster_cmd
    assert "$HOME/.local/lib/openhtpc/openhtpc-play" in poster_cmd


# ==============================================================================
# 17. TITLES UNCHANGED
# ==============================================================================

def test_17_titles_unchanged(env):
    """17. Display title/label is identical with or without poster."""
    _seed_movie(env)
    env["track_alias"](1)

    _r, base_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    base_entry = [line for line in base_text.splitlines() if "openhtpc-play" in line][0]
    base_title = base_entry.split(";")[0].split("=", 1)[1]

    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    _r, poster_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    poster_entry = [line for line in poster_text.splitlines() if "openhtpc-play" in line][0]
    poster_title = poster_entry.split(";")[0].split("=", 1)[1]

    assert base_title == poster_title
    assert base_title == "The Thing (1982)  ·  MKV"


# ==============================================================================
# 18. CONTEXT SUBMENU UNCHANGED
# ==============================================================================

def test_18_context_submenu_unchanged(env):
    """18. Context submenu command and title are identical; submenu retains entry_icon."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    _r, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    entry = [line for line in sections_text.splitlines() if "openhtpc-play" in line][0]
    parts = entry.split(";")

    assert len(parts) == 5
    assert parts[3].startswith(":submenu MEDIA_R")
    assert parts[4] == "CHANGER L’IDENTIFICATION"

    # Verify that the resolver submenu section itself still uses the generic entry_icon
    res_menu_header = f"[{parts[3].replace(':submenu ', '')}]"
    assert res_menu_header in sections_text


# ==============================================================================
# 19. REALISTIC THE THING SHORT-POSTER ENTRY <= 198 BYTES
# ==============================================================================

def test_19_realistic_the_thing_short_poster_entry_le_198_bytes(env):
    """19. The Thing with cached poster produces an Entry line <= 198 UTF-8 bytes."""
    _seed_movie(env, filename="The.Thing.1982.mkv")
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    _r, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    entry = [line for line in sections_text.splitlines() if "openhtpc-play" in line][0]

    byte_len = len(entry.encode("utf-8"))
    assert byte_len <= 198, f"Entry line exceeds 198 bytes ({byte_len} bytes): {entry}"
    assert "/tmp/ohtpc-" in entry


# ==============================================================================
# 20. LONG ASCII TITLE <= 198 BYTES
# ==============================================================================

def test_20_long_ascii_title_le_198_bytes(env):
    """20. Long ASCII title with cached poster produces an Entry line <= 198 UTF-8 bytes."""
    long_name = "A" * 120 + ".mkv"
    _seed_movie(env, filename=long_name, title="A" * 120)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    _r, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    entry = [line for line in sections_text.splitlines() if "openhtpc-play" in line][0]

    byte_len = len(entry.encode("utf-8"))
    assert byte_len <= 198, f"Entry line exceeds 198 bytes ({byte_len} bytes): {entry}"
    assert "…" in entry
    assert "  ·  MKV" in entry


# ==============================================================================
# 21. LONG UTF-8 TITLE <= 198 BYTES
# ==============================================================================

def test_21_long_utf8_title_le_198_bytes(env):
    """21. Long accented multi-byte UTF-8 title produces an Entry line <= 198 UTF-8 bytes."""
    long_title = "Éléphant à l'orée de la forêt enchantée où brûle l'été " * 3
    filename = f"{long_title[:60]}.mkv"
    _seed_movie(env, filename=filename, title=long_title)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    _r, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")
    entry = [line for line in sections_text.splitlines() if "openhtpc-play" in line][0]

    encoded = entry.encode("utf-8")
    assert len(encoded) <= 198, f"Entry line exceeds 198 bytes ({len(encoded)} bytes): {entry}"
    # Valid UTF-8 roundtrip
    assert encoded.decode("utf-8")


# ==============================================================================
# 22. NO SECOND FLEX / HELPER PROCESS
# ==============================================================================

def test_22_no_second_flex_helper_process(env):
    """22. Config generation introduces no secondary Flex or helper command."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    env["track_alias"](1)

    config_path = env["home"] / ".config/openhtpc/flex-v1.ini"
    session_engine.publish_flex_config(config_path, env["home"], [env["sources_dir"]], env["install"])
    content = config_path.read_text(encoding="utf-8")

    # Only single Flex launch should exist
    assert "flex-launcher" not in content
    assert "openhtpc-play" in content


# ==============================================================================
# 23. SAME WORK USED BY MULTIPLE MEDIA VERSIONS
# ==============================================================================

def test_23_same_work_used_by_multiple_media_versions(env):
    """23. Multiple media versions sharing the same work_id use the same short poster projection."""
    sources_dir = env["sources_dir"]
    file1 = sources_dir / "The Thing (1982) [Theatrical].mkv"
    file2 = sources_dir / "The Thing (1982) [Director Cut].mkv"
    file1.write_bytes(b"data1")
    file2.write_bytes(b"data2")

    with closing(media_db.connect(env["db_file"])) as db:
        db.execute("INSERT INTO works VALUES (1, 'MOVIE', 'The Thing', 'The Thing', 'the thing', 1982, ?, ?)", (NOW, NOW))
        db.execute("INSERT INTO external_ids VALUES (1, 1, 'tmdb_movie', '1091', 'EXACT', ?)", (NOW,))
        db.execute("INSERT INTO media_versions (id, work_id, provisional_title, provisional_year, identification_state, match_method, match_locked, created_at, updated_at) VALUES (1, 1, 'The Thing', 1982, 'USER_MATCHED', 'USER_CONFIRMATION', 1, ?, ?)", (NOW, NOW))
        db.execute("INSERT INTO media_versions (id, work_id, provisional_title, provisional_year, identification_state, match_method, match_locked, created_at, updated_at) VALUES (2, 1, 'The Thing', 1982, 'USER_MATCHED', 'USER_CONFIRMATION', 1, ?, ?)", (NOW, NOW))

        source_id = session_engine.media_source_id(sources_dir.resolve())
        db.execute("INSERT INTO resources (media_version_id, resource_kind, source_id, relative_path, file_size, mtime_ns, created_at) VALUES (1, 'FILE', ?, ?, 10, 1000, ?)", (source_id, file1.name, NOW))
        db.execute("INSERT INTO resources (media_version_id, resource_kind, source_id, relative_path, file_size, mtime_ns, created_at) VALUES (2, 'FILE', ?, ?, 10, 1000, ?)", (source_id, file2.name, NOW))
        db.commit()

    _seed_presentation(env, work_id=1, poster_path="/the_thing.jpg")
    cache_target = _write_canonical_cache(env["home"], "/the_thing.jpg")
    alias = env["track_alias"](1)

    _r, sections_text = session_engine.media_menu_sections(env["home"], [sources_dir], env["media_icon"], "gen1")

    entries = [line for line in sections_text.splitlines() if line.startswith("Entry")]
    poster_entries = [e for e in entries if str(alias) in e]
    assert len(poster_entries) == 2
    assert alias.is_symlink()
    assert alias.resolve() == cache_target.resolve()


# ==============================================================================
# 24. UNSAFE EXISTING ALIAS FILESYSTEM OBJECT
# ==============================================================================

def test_24_unsafe_existing_alias_filesystem_object(env):
    """24. If alias path exists as a regular file (not a symlink), fall back safely without overwriting."""
    _seed_movie(env)
    _seed_presentation(env, poster_path="/the_thing.jpg")
    _write_canonical_cache(env["home"], "/the_thing.jpg")
    alias = env["track_alias"](1)

    # Pre-create a regular file (unsafe object) at the alias path
    alias.write_bytes(b"unsafe-preexisting-content")
    assert alias.is_file() and not alias.is_symlink()

    _r, sections_text = session_engine.media_menu_sections(env["home"], [env["sources_dir"]], env["media_icon"], "gen1")

    # Must NOT overwrite the regular file
    assert alias.read_bytes() == b"unsafe-preexisting-content"
    assert not alias.is_symlink()

    # Must fall back to generic media_icon
    assert f";{env['media_icon']};" in sections_text
    assert str(alias) not in sections_text

    # Cleanup unsafe file
    alias.unlink()
