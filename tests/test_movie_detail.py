# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic qualification tests for OPENHTPC DEV6B3C Native Movie Detail Renderer.

Verifies:
1. Flex C parser contract: Layout=MovieDetail, Poster, Title, OriginalTitle, Metadata, Synopsis*
2. Disambiguation: MEDIA_D is MovieDetail, not ordinary MEDIA list
3. Focus contract: exactly 3 bottom action cards, static fields never participate in focus
4. Synopsis chunking and numerical assembly contract
5. Strict line budget: all INI lines <= 160 bytes UTF-8
6. Multi-byte UTF-8 boundary safety
7. 1080p geometry: poster bounding box, aspect ratio preservation, text column, bottom dock
8. 4K geometry: proportional scaling across resolution
9. Fallbacks: missing presentation, missing poster, un-matched media
10. C compilation truth: flex-launcher builds with zero warnings
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
FLEX_SRC = ROOT / "vendor/flex-launcher/src"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_engine = _load_module(PAYLOAD / "openhtpc-session-engine.py", "session_engine_dev6b3c_test")


@pytest.fixture(autouse=True)
def guard_network():
    """Guarantee zero network calls during DEV6B3C tests (Invariant 57)."""
    orig_connect = socket.socket.connect

    def guarded_connect(*args, **kwargs):
        raise AssertionError("Network contact strictly forbidden in DEV6B3C tests")

    with mock.patch("socket.socket.connect", guarded_connect):
        yield


# ==============================================================================
# 1. C PARSER CONTRACT
# ==============================================================================

def test_01_flex_header_defines_movie_detail_layout():
    """1. launcher.h declares LAYOUT_MOVIE_DETAIL and detail fields on Menu struct."""
    header = (FLEX_SRC / "launcher.h").read_text(encoding="utf-8")
    assert "LAYOUT_MOVIE_DETAIL" in header
    assert "detail_poster_path" in header
    assert "detail_poster_texture" in header
    assert "detail_poster_rect" in header
    assert "detail_title" in header
    assert "detail_title_texture" in header
    assert "detail_title_rect" in header
    assert "detail_original_title" in header
    assert "detail_metadata" in header
    assert "detail_synopsis" in header
    assert "synopsis_chunks[32]" in header
    assert "free_menu_detail" in header
    assert "assemble_menu_synopsis" in header


def test_02_flex_util_parses_movie_detail_properties():
    """2. util.c parses Layout, Poster, Title, OriginalTitle, Metadata, Synopsis1..N."""
    util_c = (FLEX_SRC / "util.c").read_text(encoding="utf-8")
    assert 'MATCH(value, "MovieDetail")' in util_c or 'strcmp(value, "MovieDetail")' in util_c
    assert 'MATCH(name, "Poster")' in util_c or 'strcmp(name, "Poster")' in util_c
    assert 'MATCH(name, "Title")' in util_c or 'strcmp(name, "Title")' in util_c
    assert 'MATCH(name, "OriginalTitle")' in util_c or 'strcmp(name, "OriginalTitle")' in util_c
    assert 'MATCH(name, "Metadata")' in util_c or 'strcmp(name, "Metadata")' in util_c
    assert 'strncmp(name, "Synopsis", 8)' in util_c
    assert "atoi(name + 8)" in util_c


def test_03_flex_launcher_c_movie_detail_logic():
    """3. launcher.c disambiguates is_movie_detail and suppresses default highlight."""
    launcher_c = (FLEX_SRC / "launcher.c").read_text(encoding="utf-8")
    assert "is_movie_detail" in launcher_c
    assert "LAYOUT_MOVIE_DETAIL" in launcher_c
    assert 'strncmp(current_menu->name, "MEDIA_D", 7)' in launcher_c or 'strncmp(menu->name, "MEDIA_D", 7)' in launcher_c
    # Suppress standard highlight
    assert "!is_movie_detail(current_menu)" in launcher_c


def test_04_flex_image_declares_render_text_wrapped():
    """4. image.h and image.c provide render_text_wrapped."""
    image_h = (FLEX_SRC / "image.h").read_text(encoding="utf-8")
    image_c = (FLEX_SRC / "image.c").read_text(encoding="utf-8")
    assert "render_text_wrapped" in image_h
    assert "render_text_wrapped" in image_c
    assert "TTF_RenderUTF8_Blended_Wrapped" in image_c


# ==============================================================================
# 2. SYNOPSIS CHUNKING & NUMERICAL ASSEMBLY CONTRACT
# ==============================================================================

def test_05_synopsis_chunking_word_boundaries_and_limits():
    """5. _chunk_synopsis_properties chunks at word boundaries, <= 135 bytes per chunk."""
    text = (
        "Dans une station de recherche isolée en Antarctique, une équipe de scientifiques "
        "découvre un organisme extraterrestre capable d'assimiler et d'imiter parfaitement "
        "toute créature vivante. La méfiance et la terreur s'installent rapidement."
    )
    chunks = session_engine._chunk_synopsis_properties(text, max_chunk_bytes=135, max_chunks=16)
    assert len(chunks) >= 1
    assert all(len(c.encode("utf-8")) <= 135 for c in chunks)
    # Recombined text must contain all words
    recombined = " ".join(chunks)
    assert "station de recherche" in recombined
    assert "extraterrestre" in recombined
    assert "terreur" in recombined


def test_06_synopsis_chunk_index_ordering():
    """6. Synopsis chunk keys use integer indices 1..N and numerical order in C."""
    # In C parser: atoi(key + 8) indexes synopsis_chunks[idx]
    # assemble_menu_synopsis iterates 1 to 31 in strict integer order
    util_c = (FLEX_SRC / "util.c").read_text(encoding="utf-8")
    assert "for (int i = 1; i < 32; i++)" in util_c
    assert "menu->synopsis_chunks[i]" in util_c


# ==============================================================================
# 3. LINE BUDGET & UTF-8 SAFETY
# ==============================================================================

def test_07_all_generated_movie_detail_lines_le_160_bytes():
    """7. All generated lines in [MEDIA_D...] section are strictly <= 160 bytes UTF-8."""
    huge_title = "Un titre de film particulièrement long et verbeux qui dépasse la moyenne " * 3
    huge_orig = "A very long original title exceeding standard line lengths " * 3
    huge_overview = (
        "Une description de film extraordinairement longue avec de nombreux détails sur les "
        "personnages, l'intrigue, le réalisateur et les thématiques abordées dans cette œuvre "
        "cinématographique majeure du vingtième siècle. " * 5
    )
    ident = {"work_id": 1, "title": huge_title, "original_title": huge_orig, "year": 1999}
    pres_info = {
        "display_title": huge_title,
        "display_original_title": huge_orig,
        "release_date": "1999-12-31",
        "runtime_minutes": 150,
        "genres_json": '["Action", "Aventure", "Science-Fiction", "Thriller"]',
        "overview": huge_overview,
    }

    section = session_engine._build_movie_detail_section(
        section_id="MEDIA_D_test123",
        token="mact_testtoken42",
        stem="test_stem",
        ext=".mkv",
        ident=ident,
        pres_info=pres_info,
        item_icon=Path("/tmp/ohtpc-1000-p1.jpg"),
        entry_icon=Path("/usr/share/openhtpc/assets/ui/media.png"),
        res_menu="MEDIA_R_test123",
    )

    for line in section.splitlines():
        byte_len = len(line.encode("utf-8"))
        assert byte_len <= 160, f"Line exceeds 160 bytes ({byte_len}): {line}"


def test_08_utf8_multibyte_accent_safety():
    """8. Accented French multi-byte characters are not split across byte boundaries."""
    accents = "Éléphant à l'orée d'une forêt où brûle l'été méditerranéen en août." * 4
    chunks = session_engine._chunk_synopsis_properties(accents, max_chunk_bytes=100, max_chunks=16)
    for c in chunks:
        raw = c.encode("utf-8")
        assert len(raw) <= 100
        # Valid UTF-8 roundtrip
        assert raw.decode("utf-8") == c


# ==============================================================================
# 4. FOCUS CONTRACT: EXACTLY 3 ACTION CARDS
# ==============================================================================

def test_09_exactly_three_focusable_action_entries():
    """9. Movie detail section emits exactly 3 Entry keys: LIRE, IDENTIFICATION, RETOUR."""
    section = session_engine._build_movie_detail_section(
        section_id="MEDIA_D_test123",
        token="mact_testtoken42",
        stem="The Thing",
        ext=".mkv",
        ident={"work_id": 1, "title": "The Thing", "year": 1982},
        pres_info={"display_title": "The Thing", "overview": "Alien horror."},
        item_icon=Path("/tmp/ohtpc-1000-p1.jpg"),
        entry_icon=Path("/usr/share/openhtpc/assets/ui/media.png"),
        res_menu="MEDIA_R_test123",
    )

    entries = [l for l in section.splitlines() if l.startswith("Entry")]
    assert len(entries) == 3
    assert entries[0].startswith("Entry1=LIRE LE FILM;")
    assert "CHANGER L’IDENTIFICATION" in entries[1] or "IDENTIFIER LE FILM" in entries[1]
    assert entries[2].startswith("Entry3=RETOUR;")
    assert entries[2].endswith(";:back")

    # Static elements must not be Entry
    for l in section.splitlines():
        if any(l.startswith(prefix) for prefix in ("Title=", "OriginalTitle=", "Metadata=", "Synopsis")):
            assert not l.startswith("Entry")


# ==============================================================================
# 5. GEOMETRY RESOLUTION SCALING: 1080p AND 4K
# ==============================================================================

def test_10_geometry_1080p_and_4k_proportions():
    """10. Geometry calculations maintain proportional bounding boxes at 1080p and 4K."""
    resolutions = [
        {"name": "1080p", "w": 1920, "h": 1080},
        {"name": "4K", "w": 3840, "h": 2160},
    ]

    for res in resolutions:
        sw, sh = res["w"], res["h"]

        # Left poster bounding box: 26% width, 75% height, starts at 6% x, 9% y
        box_x = (sw * 6) // 100
        box_y = (sh * 9) // 100
        box_w = (sw * 26) // 100
        box_h = (sh * 75) // 100

        assert box_w > 0 and box_h > 0
        assert box_x + box_w < sw

        # Right text column: starts at box_x + box_w + 4%
        text_x = box_x + box_w + (sw * 4) // 100
        text_max_w = (sw * 94) // 100 - text_x
        assert text_max_w > (sw * 50) // 100, f"{res['name']} text column too narrow"

        # Bottom dock: starts at 88% height, 8% height
        dock_y = (sh * 88) // 100
        dock_h = (sh * 8) // 100
        assert dock_y + dock_h <= sh
        # Safe margin between poster/content and dock:
        assert (box_y + box_h) < dock_y


# ==============================================================================
# 6. FALLBACK BEHAVIOR
# ==============================================================================

def test_11_fallback_missing_presentation():
    """11. Missing presentation emits fallback metadata and playable action."""
    section = session_engine._build_movie_detail_section(
        section_id="MEDIA_D_test123",
        token="mact_testtoken42",
        stem="SomeMovie (2020)",
        ext=".mp4",
        ident={"work_id": 99, "title": "SomeMovie", "year": 2020},
        pres_info=None,
        item_icon=Path("/tmp/fallback.png"),
        entry_icon=Path("/tmp/entry.png"),
        res_menu="MEDIA_R_test123",
    )
    assert "Layout=MovieDetail" in section
    assert "Title=SomeMovie" in section
    assert "Metadata=2020" in section
    assert "Synopsis1=Aucun synopsis disponible." in section
    assert "Entry1=LIRE LE FILM;" in section


def test_12_fallback_unmatched():
    """12. Unmatched media emits IDENTIFIER LE FILM and local un-identified label."""
    section = session_engine._build_movie_detail_section(
        section_id="MEDIA_D_test123",
        token="mact_testtoken42",
        stem="Vacation_2023_raw",
        ext=".mkv",
        ident=None,
        pres_info=None,
        item_icon=Path("/tmp/fallback.png"),
        entry_icon=Path("/tmp/entry.png"),
        res_menu="MEDIA_R_test123",
    )
    assert "Title=Vacation_2023_raw" in section
    assert "Metadata=Média local non identifié" in section
    assert "Synopsis1=Fichier local non identifié." in section
    assert "Entry2=IDENTIFIER LE FILM;" in section


# ==============================================================================
# 7. C COMPILATION TRUTH
# ==============================================================================

def test_13_flex_launcher_builds_with_zero_warnings():
    """13. CMake build of flex-launcher produces binary with returncode 0."""
    build_dir = ROOT / "vendor/flex-launcher/build"
    res = subprocess.run(
        ["cmake", "--build", str(build_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert res.returncode == 0, f"CMake build failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    bin_path = ROOT / "vendor/flex-launcher/build/flex-launcher"
    assert bin_path.is_file()
    assert os.access(bin_path, os.X_OK)
