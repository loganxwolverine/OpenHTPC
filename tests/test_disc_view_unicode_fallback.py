"""Regression checks for Unicode/CJK rendering in the cinematic optical sheet."""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont, ImageChops

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
VIEW_PATH = PAYLOAD / "openhtpc-disc-view.py"
OPEN_SANS = PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf"


def load_view():
    loader = importlib.machinery.SourceFileLoader("disc_view_unicode", str(VIEW_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


VIEW = load_view()


def test_cinematic_cache_version_changes_for_unicode_renderer():
    assert VIEW.VERSION == "cinematic-v3"


def test_cjk_and_hangul_are_split_from_latin_runs():
    assert VIEW.text_runs("杜國威, 林愛華") == [("杜國威", True), (", ", False), ("林愛華", True)]
    assert VIEW.text_runs("金城武 / 지진희 / Eric Tsang") == [
        ("金城武", True), (" / ", False), ("지진희", True), (" / Eric Tsang", False)
    ]


def test_disc_sheet_credit_values_use_fallback_renderer():
    source = VIEW_PATH.read_text(encoding="utf-8")
    assert 'dynamic_text((760,y),safe_text(value),21,"#f0f5fa")' in source
    assert 'fallback_path=cjk_fallback_font()' in source


def test_real_noto_fallback_changes_cjk_rendering_when_installed():
    fallback_path = VIEW.cjk_fallback_font()
    if fallback_path is None:
        pytest.skip("Noto Sans CJK package absent on this test host")
    primary = ImageFont.truetype(str(OPEN_SANS), 34)
    fallback = ImageFont.truetype(str(fallback_path), 34)
    text = "杜國威, 林愛華 / 金城武 / 지진희 / Eric Tsang"
    mixed = Image.new("RGB", (1000, 80), "black")
    primary_only = Image.new("RGB", (1000, 80), "black")
    VIEW.draw_text_fallback(ImageDraw.Draw(mixed), (5, 10), text, primary, fallback, "white")
    ImageDraw.Draw(primary_only).text((5, 10), text, font=primary, fill="white")
    assert ImageChops.difference(mixed, primary_only).getbbox() is not None
