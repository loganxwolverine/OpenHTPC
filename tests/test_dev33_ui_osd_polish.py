#!/usr/bin/env python3
"""Dev33 couch playback page and resolved OSD contract tests.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


policy = load("dev33_policy", PAYLOAD / "openhtpc-playback-policy.py")
session = load("dev33_session", PAYLOAD / "openhtpc-session-engine.py")
ui = load("dev33_ui", PAYLOAD / "openhtpc-ui.py")


def decision(presentation="PURE", audio="AUTO", subtitle="AUTO", aid="MPV_AUTO", sid="MPV_AUTO"):
    return {
        "presentation": {"requested": presentation, "resolved": "PURE", "reason": "test"},
        "audio": {"requested": audio, "resolved": aid, "reason": "test", "mpv_args": []},
        "subtitle": {"requested": subtitle, "resolved": sid, "reason": "test", "mpv_args": []},
    }


class PlaybackPage(unittest.TestCase):
    def test_active_state_page_reflects_all_three_preferences(self):
        source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
        for marker in ("LECTURE — PRÉFÉRENCES ACTIVES", "Mode vidéo", "Langue audio", "Sous-titres", "Application", "Persistance", "ACTIONS"):
            self.assertIn(marker, source)
        with tempfile.TemporaryDirectory() as value:
            target = pathlib.Path(value) / "playback.png"
            model = {"available":True, "product":{"overall":"READY", "health":"PRÊT", "version":"1.1.0-dev33"}, "playback_policy":{
                "presentation_mode":"CINEMA_AUTO", "audio_language_policy":"FR", "subtitle_policy":"OFF"}}
            ui.system_page_png(model, target, PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf", "playback")
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 10000)

    def test_bottom_actions_have_order_navigation_and_distinct_icons(self):
        icons = {key:pathlib.Path(f"{key}.png") for key in ("video","audio","subtitles","status","about","back")}
        root, video, audio, subtitles = session._playback_policy_sections(pathlib.Path("/tmp/home"), PAYLOAD, icons)
        labels = ["MODE VIDÉO", "LANGUE AUDIO", "SOUS-TITRES", "ÉTAT AUDIO", "À PROPOS", "RETOUR"]
        self.assertEqual([line.split("=",1)[1].split(";",1)[0] for line in root.splitlines()], labels)
        self.assertEqual(len({line.split(";")[1] for line in root.splitlines()}), 6)
        self.assertIn(":submenu PLAYBACK_VIDEO", root)
        self.assertIn(":back", root)
        self.assertIn("openhtpc-playback-setting", video + audio + subtitles)

    def test_setting_persists_and_requests_immediate_page_refresh(self):
        with tempfile.TemporaryDirectory() as value:
            base = pathlib.Path(value); home = base / "home"; install = base / "install"
            (home / ".config/openhtpc").mkdir(parents=True); install.mkdir()
            shutil.copy2(PAYLOAD / "openhtpc-playback-policy.py", install / "openhtpc-playback-policy.py")
            marker = base / "refreshed"
            action = install / "openhtpc-system-action"
            action.write_text(f"#!/bin/sh\ntest \"$1\" = playback && touch '{marker}'\n", encoding="utf-8"); action.chmod(0o755)
            env = {**os.environ, "OPENHTPC_HOME":str(home), "OPENHTPC_INSTALL_DIR":str(install)}
            subprocess.run([str(PAYLOAD / "openhtpc-playback-setting"), "audio_language_policy", "FR"], env=env, check=True)
            self.assertEqual(policy.read_preferences(home)["audio_language_policy"], "FR")
            self.assertTrue(marker.is_file())

    def test_new_assets_are_distinct_and_documented(self):
        names = ("playback-video.png", "playback-language.png", "playback-subtitles.png", "playback-audio-status.png", "playback-about.png")
        hashes = {__import__("hashlib").sha256((PAYLOAD/"assets/ui"/name).read_bytes()).hexdigest() for name in names}
        self.assertEqual(len(hashes), len(names))
        provenance = (ROOT/"assets/ASSET_PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("Dev33 adds five original playback-control icons", provenance)


class ResolvedOsd(unittest.TestCase):
    def test_pure(self):
        text = policy.osd_text(decision())
        self.assertIn("Mode vidéo : PURE", text)
        self.assertNotIn("→", text)

    def test_cinema_auto_to_pure(self):
        self.assertIn("Mode vidéo : CINÉMA AUTO", policy.osd_text(decision("CINEMA_AUTO")))

    def test_resolved_audio_and_subtitles(self):
        fr_off = policy.osd_text(decision(audio="FR", subtitle="OFF", aid="AID_2", sid="NONE"))
        self.assertIn("Audio : Français", fr_off)
        self.assertIn("Sous-titres : Désactivés", fr_off)
        self.assertIn("Sous-titres : Français forcés", policy.osd_text(decision(subtitle="FR_FORCED", sid="SID_1")))
        self.assertIn("Sous-titres : Aucun", policy.osd_text(decision(subtitle="FR_FORCED", sid="NONE")))

    def test_osd_is_top_left_and_bounded_to_five_seconds(self):
        for name in ("openhtpc-play", "openhtpc-play-dvd"):
            source = (PAYLOAD/name).read_text(encoding="utf-8")
            for marker in ("--osd-playing-msg-duration=5000", "--osd-align-x=left", "--osd-align-y=top", "--osd-font-size=32"):
                self.assertIn(marker, source)
            self.assertNotIn("--osd-playing-msg-duration=0", source)

    def test_policy_decision_logic_remains_qualified(self):
        streams = {"streams":[
            {"codec_type":"audio","tags":{"language":"fr","title":"VFQ"},"disposition":{}},
            {"codec_type":"audio","tags":{"language":"fra","title":"TrueFrench VFF"},"disposition":{}},
            {"codec_type":"subtitle","tags":{"language":"fr","title":"Complet"},"disposition":{"forced":0}},
        ]}
        self.assertEqual(policy.choose_audio("FR", streams)["resolved"], "AID_2")
        forced = policy.choose_subtitle("FR_FORCED", streams)
        self.assertEqual((forced["resolved"], forced["reason"]), ("NONE", "no_qualified_forced_track"))
        self.assertEqual(policy.choose_subtitle("OFF", streams)["mpv_args"], ["--sid=no"])


if __name__ == "__main__":
    unittest.main()
