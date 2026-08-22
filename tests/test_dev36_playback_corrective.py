#!/usr/bin/env python3
"""Dev36 playback page availability, action artwork and OSD semantics."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import tempfile
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


policy = load("dev36_policy", PAYLOAD / "openhtpc-playback-policy.py")
session = load("dev36_session", PAYLOAD / "openhtpc-session-engine.py")
ui = load("dev36_ui", PAYLOAD / "openhtpc-ui.py")


class PlaybackPageRouting(unittest.TestCase):
    def test_system_playback_route_exists_from_every_generated_context(self):
        source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        self.assertIn("Entry4=LECTURE;{icon_processing};:submenu SYSTEM_PLAYBACK", source)
        self.assertIn("[SYSTEM_PLAYBACK]", source)
        self.assertIn("{playback_root}", source)

    def test_targeted_refresh_is_explicitly_available(self):
        action = (PAYLOAD / "openhtpc-system-action").read_text(encoding="utf-8")
        self.assertIn('model={"available":True,"playback_policy":policy.read_preferences(home)}', action)

    def test_playback_page_survives_unavailable_capabilities(self):
        with tempfile.TemporaryDirectory() as value:
            target = pathlib.Path(value) / "playback.png"
            fallback = pathlib.Path(value) / "fallback.png"
            model = {"available": False, "playback_policy": {
                "presentation_mode": "CINEMA_AUTO",
                "audio_language_policy": "FR",
                "subtitle_policy": "OFF",
            }}
            ui.system_page_png(model, target, PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf", "playback")
            ui.system_page_png(model, fallback, PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf", "root")
            self.assertTrue(target.is_file())
            self.assertNotEqual(target.read_bytes(), fallback.read_bytes())
            with Image.open(target) as rendered:
                self.assertEqual(rendered.size, (1920, 1080))
            source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
            self.assertIn('if not model.get("available") and page != "playback":', source)


class ActionDockArtwork(unittest.TestCase):
    def test_bottom_geometry_is_preserved(self):
        source = FLEX.read_text(encoding="utf-8")
        self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100", source)
        self.assertGreater(1080 * 88 // 100, 530 + 100)

    def test_six_approved_icons_are_referenced_and_rendered(self):
        icons = {
            "playback-video.png", "playback-language.png",
            "playback-subtitles.png", "playback-audio-status.png",
            "playback-about.png", "system-back.png",
        }
        source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        for name in icons:
            self.assertIn(name, source)
            self.assertTrue((PAYLOAD / "assets/ui" / name).is_file())
        flex = FLEX.read_text(encoding="utf-8")
        self.assertNotIn("is_disc_sheet() || is_system_subpage()) {\n                icon = NULL", flex)
        self.assertIn("if (is_system_subpage()) {", flex)
        self.assertIn("SDL_RenderCopy(renderer, icon, NULL, &artwork_rect)", flex)


class OsdAndPreservedPolicy(unittest.TestCase):
    @staticmethod
    def decision(requested: str):
        return {"presentation":{"requested":requested,"resolved":"PURE"},
                "audio":{"requested":"FR","resolved":"AID_1"},
                "subtitle":{"requested":"OFF","resolved":"NONE"}}

    def test_pure_pure_osd(self):
        self.assertEqual(policy.osd_text(self.decision("PURE")),
            "Mode vidéo : PURE\nAudio : Français\nSous-titres : Désactivés")

    def test_auto_pure_osd(self):
        self.assertEqual(policy.osd_text(self.decision("CINEMA_AUTO")),
            "Mode vidéo : CINÉMA AUTO\nAudio : Français\nSous-titres : Désactivés")

    def test_logs_and_dvd_global_shortcut_remain(self):
        for player in ("openhtpc-play", "openhtpc-play-dvd"):
            source = (PAYLOAD / player).read_text(encoding="utf-8")
            self.assertIn("presentation_requested", source)
            self.assertIn("presentation_resolved", source)
        session_source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        self.assertIn(":submenu DVD_VIDEO_MODE", session_source)
        self.assertIn("presentation_mode CINEMA_AUTO", session_source)

    def test_policy_failure_fallback_remains_multiline(self):
        local = (PAYLOAD / "openhtpc-play").read_text(encoding="utf-8")
        dvd = (PAYLOAD / "openhtpc-play-dvd").read_text(encoding="utf-8")
        self.assertIn("Audio : Auto", local)
        self.assertIn("Sous-titres : Auto", dvd)

    def test_audio_fr_and_subtitle_off_are_unchanged(self):
        probe = {"streams":[{"codec_type":"audio","tags":{"language":"fra","title":"TrueFrench VFF"},"disposition":{}}]}
        self.assertEqual(policy.choose_audio("FR", probe)["resolved"], "AID_1")
        self.assertEqual(policy.choose_subtitle("OFF", probe)["mpv_args"], ["--sid=no"])


if __name__ == "__main__":
    unittest.main()
