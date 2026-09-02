#!/usr/bin/env python3
"""Dev34 playback refresh, persistence and argument-safe OSD regressions."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("dev34_policy", PAYLOAD / "openhtpc-playback-policy.py")


class PresentationTruth(unittest.TestCase):
    def test_status_card_ends_before_action_zone(self):
        source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
        self.assertIn('card((70, 170, 1780, 360), "LECTURE — PRÉFÉRENCES ACTIVES"', source)
        self.assertIn('txt((90, 590), "ACTIONS"', source)
        for label in ("Mode vidéo", "Langue audio", "Sous-titres", "Application", "Persistance"):
            self.assertIn(label, source)

    def test_pure_auto_parent_reopen_and_session_persistence(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value)
            legacy = home / ".config/openhtpc/video-profile.json"
            policy.write_preference(home, "presentation_mode", "PURE")
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "PURE")
            legacy.write_text(json.dumps({"active_profile": "CINEMA_AUTO"}), encoding="utf-8")
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "PURE")
            reloaded = load("dev34_policy_reloaded", PAYLOAD / "openhtpc-playback-policy.py")
            self.assertEqual(reloaded.read_preferences(home)["presentation_mode"], "PURE")
            reloaded.write_preference(home, "presentation_mode", "CINEMA_AUTO")
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "CINEMA_AUTO")
            self.assertEqual(json.loads(legacy.read_text())["active_profile"], "CINEMA_AUTO")

    def test_setting_atomically_replaces_parent_background(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value)
            env = {**os.environ, "HOME": str(home), "OPENHTPC_HOME": str(home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
            env.pop("DISPLAY", None); env.pop("WAYLAND_DISPLAY", None)
            setting = PAYLOAD / "openhtpc-playback-setting"
            subprocess.run([str(setting), "presentation_mode", "PURE"], env=env, check=True)
            page = home / ".cache/openhtpc/system-playback.png"
            pure_inode = page.stat().st_ino
            subprocess.run([str(setting), "presentation_mode", "CINEMA_AUTO"], env=env, check=True)
            self.assertNotEqual(page.stat().st_ino, pure_inode)
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "CINEMA_AUTO")


class OsdTransport(unittest.TestCase):
    def decision(self, requested="CINEMA_AUTO"):
        return {"presentation":{"requested":requested,"resolved":"PURE","reason":"test"},
                "audio":{"requested":"FR","resolved":"AID_1","reason":"test"},
                "subtitle":{"requested":"OFF","resolved":"NONE","reason":"test"}}

    def test_multiline_utf8_arrow_and_no_broken_escape(self):
        text = policy.osd_text(self.decision())
        self.assertEqual(text, "Mode vidéo : CINÉMA AUTO\nAudio : Français\nSous-titres : Désactivés")
        self.assertNotIn("\\N", text)
        self.assertNotIn("broken escape sequence", text)

    def test_apostrophe_and_all_required_labels_remain_plain_utf8(self):
        samples = ("l'audio Français", "CINÉMA AUTO", "Français", "Désactivés", "Aucun", "Français forcés", "→")
        for sample in samples:
            self.assertEqual(sample.encode("utf-8").decode("utf-8"), sample)

    def test_requested_resolved_match_log_and_osd_contract(self):
        auto = self.decision("CINEMA_AUTO")
        pure = self.decision("PURE")
        self.assertIn("Mode vidéo : CINÉMA AUTO", policy.osd_text(auto))
        self.assertIn("Mode vidéo : PURE", policy.osd_text(pure))
        source = (PAYLOAD / "openhtpc-play").read_text(encoding="utf-8")
        self.assertIn('presentation_requested=decision["presentation"]["requested"]', source)
        self.assertIn('presentation_resolved=decision["presentation"]["resolved"]', source)

    def test_audio_fr_and_subtitle_off_unchanged(self):
        probe = {"streams":[{"codec_type":"audio","tags":{"language":"fra","title":"TrueFrench VFF"},"disposition":{}}]}
        self.assertEqual(policy.choose_audio("FR", probe)["resolved"], "AID_1")
        self.assertEqual(policy.choose_subtitle("OFF", probe)["mpv_args"], ["--sid=no"])


if __name__ == "__main__":
    unittest.main()
