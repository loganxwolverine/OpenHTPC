# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


ui_module = load_module("rc7_ui", PAYLOAD / "openhtpc-ui.py")
session_engine = load_module("rc7_session_engine", PAYLOAD / "openhtpc-session-engine.py")


class Rc7AboutUxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        self.font_path = PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf"

    def test_01_about_page_png_generation(self):
        """Verify that the about page generates a valid, loadable 1920x1080 PNG image."""
        target = self.home / "system-about.png"
        model = {
            "technical": {"version": "1.2.0-rc2"},
            "product": {"health": "PRÊT", "version": "1.2.0-rc2", "overall": "READY"},
            "available": True,
        }
        ui_module.system_page_png(model, target, self.font_path, "about")
        self.assertTrue(target.is_file())
        self.assertGreater(target.stat().st_size, 1000)

        with Image.open(target) as img:
            self.assertEqual(img.size, (1920, 1080))
            self.assertEqual(img.mode, "RGB")

    def test_02_about_page_content_and_geometry_separation(self):
        """Verify that all expected content is present and cards leave the central button corridor clear."""
        # Capture drawn rectangles and text elements during rendering
        drawn_rects = []
        drawn_texts = []

        class DrawInterceptor:
            def __init__(self, real_draw):
                self._real = real_draw

            def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1):
                drawn_rects.append(("rounded_rectangle", xy, fill, outline, width))
                return self._real.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

            def rectangle(self, xy, fill=None, outline=None, width=1):
                drawn_rects.append(("rectangle", xy, fill, outline, width))
                return self._real.rectangle(xy, fill=fill, outline=outline, width=width)

            def text(self, xy, text, font=None, fill=None, **kwargs):
                drawn_texts.append((xy, text, fill))
                return self._real.text(xy, text, font=font, fill=fill, **kwargs)

            def textlength(self, text, font=None, **kwargs):
                return self._real.textlength(text, font=font, **kwargs)

        target = self.home / "system-about.png"
        model = {
            "technical": {"version": "1.2.0-rc2"},
            "product": {"health": "PRÊT", "version": "1.2.0-rc2", "overall": "READY"},
            "available": True,
        }

        from PIL import ImageDraw
        original_draw = ImageDraw.Draw

        def intercept_draw(image, *args, **kwargs):
            real = original_draw(image, *args, **kwargs)
            return DrawInterceptor(real)

        ImageDraw.Draw = intercept_draw
        try:
            ui_module.system_page_png(model, target, self.font_path, "about")
        finally:
            ImageDraw.Draw = original_draw

        # 1. Content presence check
        all_text_values = [t[1] for t in drawn_texts]
        self.assertIn("OPENHTPC", all_text_values)
        self.assertIn("À PROPOS", all_text_values)
        self.assertIn("PROJET", all_text_values)
        self.assertIn("1.2.0-rc2", all_text_values)
        self.assertIn("Projet créé par Steve Dehanne", all_text_values)
        self.assertIn("LICENCE & DÉPÔT", all_text_values)
        self.assertIn("Copyright 2026 Steve Dehanne", all_text_values)
        self.assertIn("Apache 2.0", all_text_values)
        self.assertIn("github.com/loganxwolverine/OpenHTPC", all_text_values)

        # 2. Geometric isolation of the RETOUR button corridor
        # Flex Launcher renders the RETOUR button in the horizontal center:
        # Center x = 960. With icon (184px) + highlight padding (24px * 2) = 232px box.
        # Button bounding box spans roughly x in [844, 1076], y in [426, 654].
        button_x_min = 844
        button_x_max = 1076

        # Identify content cards (excluding top banner)
        content_cards = [
            rect[1] for rect in drawn_rects
            if rect[0] == "rounded_rectangle" and rect[1][1] >= 170
        ]
        self.assertEqual(len(content_cards), 2, "Expected exactly 2 side cards on À PROPOS page")

        left_card = min(content_cards, key=lambda r: r[0])
        right_card = max(content_cards, key=lambda r: r[0])

        # Left card must end well before the RETOUR button
        self.assertLess(left_card[2], button_x_min)
        self.assertGreaterEqual(button_x_min - left_card[2], 30, "Safe margin between left card and button")

        # Right card must start well after the RETOUR button
        self.assertGreater(right_card[0], button_x_max)
        self.assertGreaterEqual(right_card[0] - button_x_max, 30, "Safe margin between right card and button")

        # Check all drawn content text coordinates do NOT fall within the button corridor
        for pos, text, _ in drawn_texts:
            if pos[1] >= 170:  # Below header
                # Text should be either inside the left card or right card, never in button corridor [844..1076]
                self.assertTrue(
                    pos[0] < button_x_min or pos[0] > button_x_max,
                    f"Text '{text}' at x={pos[0]} overlaps the central button corridor [{button_x_min}..{button_x_max}]"
                )

    def test_03_flex_ini_about_menu_definition(self):
        """Verify that the session engine creates the correct SYSTEM_ABOUT menu section in Flex config."""
        config_path = self.home / ".config/openhtpc/flex-v1.ini"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        written = session_engine.write_flex_config(config_path, self.home, [], install=PAYLOAD)
        self.assertTrue(written)
        self.assertTrue(config_path.is_file())

        content = config_path.read_text(encoding="utf-8")
        self.assertIn("[SYSTEME]", content)
        self.assertIn("Entry9=À PROPOS;", content)
        self.assertIn(":submenu SYSTEM_ABOUT", content)

        self.assertIn("[SYSTEM_ABOUT]", content)
        section = content.split("[SYSTEM_ABOUT]", 1)[1].split("[", 1)[0]
        self.assertIn("BackgroundImage=", section)
        self.assertIn("system-about.png", section)
        self.assertIn("Entry1=RETOUR;", section)
        self.assertIn(":back", section)

    def test_04_other_system_pages_render_without_regression(self):
        """Verify that all standard system pages continue to render correctly."""
        model = {
            "technical": {
                "version": "1.2.0-rc2", "build": "rc2-test", "schema": "1", "probe": "1",
                "generated": "2026-09-05", "connector": "HDMI-A-1", "vulkan_driver": "RADV",
                "vaapi_driver": "radeonsi", "mpv": "0.38", "ffmpeg": "7.0",
            },
            "product": {"health": "PRÊT", "version": "1.2.0-rc2", "overall": "READY"},
            "overview": {"machine": "Host", "cpu": "AMD", "ram": "16G", "gpu": "AMD", "graphics": "Vulkan", "display": "1080p"},
            "display": {"connector": "HDMI-A-1", "resolution": "1920x1080", "refresh": "60Hz", "scale": "100%", "depth": "8bpc", "hdr_current": "OFF", "hdr_capable": "Non", "hdr_pipeline": "Standard"},
            "audio_section": {"audio_output": "HDMI", "audio_backend": "PipeWire", "connection": "HDMI", "channels": "2.0", "requested_mode": "PCM", "passthrough": "Désactivé", "receiver": "Stéréo"},
            "processing": {"profile": "PURE", "output": "1080p", "benchmark": "Pass", "recommendation": "PURE"},
            "playback_policy": {"presentation_mode": "PURE", "audio_language_policy": "AUTO", "subtitle_policy": "AUTO"},
            "diagnostics": {"overall": "PRÊT", "snapshot": "À jour", "last_action": "Aucune", "checks": []},
            "hardware": {"machine": "PC", "manufacturer": "AMD", "cpu": "Ryzen", "architecture": "x86_64", "logical_cores": "8", "ram": "16G", "gpus": [], "vulkan": "Oui", "vaapi": "Oui"},
            "available": True,
        }
        for page in ("root", "overview", "codecs", "display", "audio", "media_optical", "processing", "playback", "diagnostics", "technical", "hardware", "metadata", "tmdb"):
            target = self.home / f"test-{page}.png"
            ui_module.system_page_png(model, target, self.font_path, page)
            self.assertTrue(target.is_file(), f"Page {page} failed to render")
            self.assertGreater(target.stat().st_size, 500, f"Page {page} rendered empty file")


if __name__ == "__main__":
    unittest.main()
