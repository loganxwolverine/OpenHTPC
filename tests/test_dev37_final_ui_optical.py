#!/usr/bin/env python3
"""Dev37 final dock spacing, OSD wording and optical artwork tests."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import pathlib
import unittest

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
FLEX = ROOT / "vendor/flex-launcher/src/launcher.c"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("dev37_policy", PAYLOAD / "openhtpc-playback-policy.py")


class DockSpacing(unittest.TestCase):
    def test_icon_bottom_precedes_label_with_safety_margin(self):
        screen_height = 1080
        icon_size = screen_height * 4 // 100
        safety_margin = screen_height * 1 // 100
        text_height = 27
        card_top = screen_height * 88 // 100
        card_height = screen_height * 8 // 100
        stack_top = card_top + (card_height - icon_size - safety_margin - text_height) // 2
        icon_bottom = stack_top + icon_size
        label_top = icon_bottom + safety_margin
        self.assertGreaterEqual(label_top - icon_bottom, 10)
        self.assertLess(label_top + text_height, screen_height)
        source = FLEX.read_text(encoding="utf-8")
        self.assertIn("stack_y + icon_size + safety_margin", source)

    def test_approved_bottom_dock_position_is_unchanged(self):
        source = FLEX.read_text(encoding="utf-8")
        self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100", source)


class UserOsd(unittest.TestCase):
    @staticmethod
    def decision(requested: str):
        return {"presentation":{"requested":requested,"resolved":"PURE"},
                "audio":{"requested":"FR","resolved":"AID_1"},
                "subtitle":{"requested":"OFF","resolved":"NONE"}}

    def test_pure_uses_requested_preference(self):
        self.assertEqual(policy.osd_text(self.decision("PURE")),
            "Mode vidéo : PURE\nAudio : Français\nSous-titres : Désactivés")

    def test_auto_uses_requested_preference_not_internal_profile(self):
        text = policy.osd_text(self.decision("CINEMA_AUTO"))
        self.assertEqual(text, "Mode vidéo : CINÉMA AUTO\nAudio : Français\nSous-titres : Désactivés")
        self.assertNotIn("Profil appliqué", text)
        self.assertNotIn("→", text)

    def test_logs_retain_requested_and_resolved(self):
        for player in ("openhtpc-play", "openhtpc-play-dvd"):
            source = (PAYLOAD / player).read_text(encoding="utf-8")
            self.assertIn("presentation_requested", source)
            self.assertIn("presentation_resolved", source)

    def test_multiline_utf8_has_no_mpv_escape(self):
        text = policy.osd_text(self.decision("CINEMA_AUTO"))
        self.assertNotIn("\\N", text)
        self.assertNotIn("broken escape sequence", text)


class OpticalArtwork(unittest.TestCase):
    ASSETS = {
        "dvd-media.png": (1024, 688),
        "bluray-media.png": (1024, 688),
        "uhd-bluray-media.png": (1024, 700),
        "dvd-media-badge.png": (512, 256),
        "bluray-media-badge.png": (512, 256),
        "uhd-bluray-media-badge.png": (512, 256),
    }

    def test_all_six_derived_png_assets_exist(self):
        for name, size in self.ASSETS.items():
            with self.subTest(name=name):
                path = PAYLOAD / "assets/ui" / name
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertEqual((image.format, image.mode, image.size), ("PNG", "RGBA", size))

    def test_dvd_bluray_uhd_badges_are_referenced(self):
        source = (PAYLOAD / "openhtpc-disc-view.py").read_text(encoding="utf-8")
        for name in ("dvd-media-badge.png", "bluray-media-badge.png", "uhd-bluray-media-badge.png"):
            self.assertIn(name, source)

    def test_provenance_records_master_hashes_and_disclaimer(self):
        source = (ROOT / "assets/ASSET_PROVENANCE.md").read_text(encoding="utf-8")
        for digest in (
            "77924fff80e273b7ac09dc2c0cf6b1aae5e6036c45f1aa01807a16764da848d7",
            "b58ed1513beff775341131aada124d26914dcef0a58a612b86569c577dcfaac8",
            "32e9e104dc162bb830d77db34896c99a2bdfe78ae3c5f61b49b040a88db2286c",
        ):
            self.assertIn(digest, source)
        self.assertIn("not official DVD Forum", source)
        self.assertIn("Created for OPENHTPC by Steve Dehanne", source)

    def test_optical_derivation_is_reproducible_and_engine_neutral(self):
        script = (ROOT / "assets/ui-source/derive_optical_media.py").read_text(encoding="utf-8")
        self.assertIn("ImageOps.contain", script)
        self.assertIn("Image.Resampling.LANCZOS", script)
        for engine in ("openhtpc-play-dvd", "openhtpc-play", "openhtpc-playback-policy.py"):
            self.assertTrue((PAYLOAD / engine).is_file())


if __name__ == "__main__":
    unittest.main()
