#!/usr/bin/env python3
"""OPENHTPC Flex Unicode/CJK fallback font regression checks."""

from __future__ import annotations

import ctypes
import ctypes.util
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
FLEX = ROOT / "vendor/flex-launcher"
OPEN_SANS = FLEX / "assets/fonts/OpenSans-Regular.ttf"


def load(name: str, filename: str):
    path = PAYLOAD / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


session = load("unicode_session", "openhtpc-session-engine.py")
theme = load("unicode_theme", "openhtpc-theme.py")


def test_fedora_cjk_fallback_resolution_is_optional_and_canonical():
    path = session.flex_cjk_fallback_font()
    if path is None:
        pytest.skip("Noto Sans CJK package absent on this test host")
    assert path.is_absolute()
    assert path.is_file()
    assert "NotoSansCJK" in path.name


def test_title_block_declares_fallback_only_when_available(tmp_path):
    primary = tmp_path / "OpenSans-Regular.ttf"
    fallback = tmp_path / "NotoSansCJK-VF.ttc"
    block = theme.title_block(primary, 28, 12, fallback)
    assert f"Font={primary}" in block
    assert f"FallbackFont={fallback}" in block
    assert theme.title_block(primary, 28, 12, None).count("FallbackFont=") == 0


def test_generated_flex_config_contains_system_fallback_when_installed(tmp_path):
    fallback = session.flex_cjk_fallback_font()
    if fallback is None:
        pytest.skip("Noto Sans CJK package absent on this test host")
    home = tmp_path / "home"
    target = home / ".config/openhtpc/flex-v1.ini"
    target.parent.mkdir(parents=True)
    session.write_flex_config(target, home, [], PAYLOAD, media_generation="unicode-test")
    text = target.read_text(encoding="utf-8")
    assert f"FallbackFont={fallback}" in text
    assert "Font=" in text


def test_flex_cjk_fallback_is_generic_and_glyph_driven():
    image_h = (FLEX / "src/image.h").read_text(encoding="utf-8")
    image_c = (FLEX / "src/image.c").read_text(encoding="utf-8")
    launcher_c = (FLEX / "src/launcher.c").read_text(encoding="utf-8")
    launcher_h = (FLEX / "src/launcher.h").read_text(encoding="utf-8")
    util_c = (FLEX / "src/util.c").read_text(encoding="utf-8")

    assert "char **fallback_font_path;" in image_h
    assert "char *title_fallback_font_path;" in launcher_h
    assert "TTF_GlyphIsProvided32" in image_c
    assert "font_supports_utf8" in image_c
    assert "fallback_font_for_text" in image_c
    assert "config.title_fallback_font_path" in launcher_c
    assert "SETTING_TITLE_FALLBACK_FONT" in util_c
    assert "free(config.title_fallback_font_path);" in launcher_c
    assert "detail_original_title" not in image_c


def test_wrapped_movie_detail_text_uses_same_fallback_contract():
    image_h = (FLEX / "src/image.h").read_text(encoding="utf-8")
    image_c = (FLEX / "src/image.c").read_text(encoding="utf-8")
    launcher_c = (FLEX / "src/launcher.c").read_text(encoding="utf-8")
    assert "const char *fallback_font_path" in image_h
    assert "fallback_font_for_text(font, p, fallback_font_path, font_size)" in image_c
    assert launcher_c.count("config.title_fallback_font_path") >= 5


def test_installer_guarantees_noto_cjk_package():
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    assert "google-noto-sans-cjk-vf-fonts" in installer


def test_real_sdl_ttf_fonts_confirm_hangul_fallback():
    fallback = session.flex_cjk_fallback_font()
    if fallback is None:
        pytest.skip("Noto Sans CJK package absent on this test host")
    libname = ctypes.util.find_library("SDL2_ttf")
    if not libname:
        pytest.skip("SDL2_ttf unavailable")
    ttf = ctypes.CDLL(libname)
    ttf.TTF_Init.restype = ctypes.c_int
    ttf.TTF_OpenFont.argtypes = [ctypes.c_char_p, ctypes.c_int]
    ttf.TTF_OpenFont.restype = ctypes.c_void_p
    ttf.TTF_GlyphIsProvided32.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ttf.TTF_GlyphIsProvided32.restype = ctypes.c_int
    ttf.TTF_CloseFont.argtypes = [ctypes.c_void_p]
    ttf.TTF_Quit.argtypes = []

    assert ttf.TTF_Init() == 0
    primary = ttf.TTF_OpenFont(str(OPEN_SANS).encode(), 24)
    cjk = ttf.TTF_OpenFont(str(fallback).encode(), 24)
    assert primary and cjk
    try:
        hangul_an = 0xC548
        assert ttf.TTF_GlyphIsProvided32(primary, hangul_an) == 0
        assert ttf.TTF_GlyphIsProvided32(cjk, hangul_an) != 0
    finally:
        ttf.TTF_CloseFont(primary)
        ttf.TTF_CloseFont(cjk)
        ttf.TTF_Quit()
