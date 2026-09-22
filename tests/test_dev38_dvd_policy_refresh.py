#!/usr/bin/env python3
"""Dev38 DVD FR_FULL and global DVD-detail refresh corrective tests."""
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
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("dev38_policy", PAYLOAD / "openhtpc-playback-policy.py")

DRIVEN = {
    "state": "DVD",
    "physical_edition": {
        "lsdvd_ok": True,
        "audio": [{"langcode": lang, "channels": 6} for lang in ("en", "fr", "it")],
        "subtitles": [{"langcode": lang} for lang in
                      ("en", "fr", "it", "fi", "nl", "da", "no", "sv", "is", "pt", "en", "it")],
    },
}


class DvdSubtitlePolicy(unittest.TestCase):
    def test_driven_fr_full_uses_dvd_language_selection_not_lsdvd_index(self):
        result = policy.choose_dvd_subtitle("FR_FULL", DRIVEN)
        self.assertEqual(result["resolved"], "MPV_FR_LANGUAGE")
        self.assertEqual(result["reason"], "dvd_french_full_track")
        self.assertEqual(result["mpv_args"], ["--slang=fr,fra,fre"])
        self.assertNotIn("--sid=", " ".join(result["mpv_args"]))

    def test_dvd_fr_full_without_french_is_none(self):
        state = {"state":"DVD", "physical_edition":{"lsdvd_ok":True, "subtitles":[{"langcode":"en"}]}}
        result = policy.choose_dvd_subtitle("FR_FULL", state)
        self.assertEqual((result["resolved"], result["mpv_args"]), ("NONE", ["--sid=no"]))

    def test_local_fr_full_keeps_french_sid(self):
        probe = {"streams":[
            {"codec_type":"subtitle", "tags":{"language":"eng"}},
            {"codec_type":"subtitle", "tags":{"language":"fr"}},
        ]}
        result = policy.choose_subtitle("FR_FULL", probe)
        self.assertEqual((result["resolved"], result["mpv_args"]), ("SID_2", ["--sid=2"]))

    def test_dvd_off_and_auto_are_unchanged(self):
        self.assertEqual(policy.choose_dvd_subtitle("OFF", DRIVEN)["mpv_args"], ["--sid=no"])
        auto = policy.choose_dvd_subtitle("AUTO", DRIVEN)
        self.assertEqual((auto["resolved"], auto["mpv_args"]), ("MPV_AUTO", []))

    def test_dvd_player_passes_inventory_and_logs_reason(self):
        source = (PAYLOAD / "openhtpc-play-dvd").read_text(encoding="utf-8")
        self.assertIn('--dvd-state "$OPTICAL_STATE"', source)
        self.assertIn('subtitle_reason=$subtitle_reason', source)


class GlobalDvdDetailRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.home = pathlib.Path(self.tmp.name)
        self.install = self.home / "install"; self.install.mkdir()
        for name in ("openhtpc-playback-policy.py", "openhtpc-playback-setting"):
            shutil.copy2(PAYLOAD / name, self.install / name)
        (self.install / "openhtpc-playback-setting").chmod(0o755)
        config = self.home / ".config/openhtpc"; config.mkdir(parents=True)
        self.flex = config / "flex-v1.ini"
        self.flex.write_text("[DISQUE]\nEntry1=LIRE LE DVD;i;play\nEntry2=MODE VIDÉO : CINÉMA AUTO;i;:submenu DVD_VIDEO_MODE\n[DVD_VIDEO_MODE]\nEntry1=PURE;i;set\n", encoding="utf-8")
        self.env = {**os.environ, "HOME":str(self.home), "OPENHTPC_HOME":str(self.home), "OPENHTPC_INSTALL_DIR":str(self.install),
                    "OPENHTPC_SESSION_ENGINE":str(PAYLOAD / "openhtpc-session-engine.py")}
        self.env.pop("DISPLAY", None); self.env.pop("WAYLAND_DISPLAY", None)

    def tearDown(self): self.tmp.cleanup()

    def apply(self, value: str):
        subprocess.run([str(self.install / "openhtpc-playback-setting"), "presentation_mode", value], env=self.env, check=True)

    def test_system_update_regenerates_dvd_detail_value(self):
        self.apply("PURE")
        self.assertIn("MODE VIDÉO : PURE", self.flex.read_text(encoding="utf-8"))
        self.assertEqual(policy.read_preferences(self.home)["presentation_mode"], "PURE")

    def test_dvd_shortcut_return_is_immediately_current(self):
        self.apply("PURE"); self.apply("CINEMA_AUTO")
        self.assertIn("MODE VIDÉO : CINÉMA AUTO", self.flex.read_text(encoding="utf-8"))

    def test_flex_applyback_refreshes_cached_disc_from_system_parent(self):
        source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
        block = source[source.index('else if (!strcmp(special_command, SCMD_APPLY_BACK))'):]
        self.assertIn('Menu *disc = get_menu("DISQUE")', block)
        self.assertIn("reload_menu_section(disc)", block)

    def test_no_per_dvd_presentation_override(self):
        combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in PAYLOAD.iterdir() if path.is_file())
        self.assertNotIn("dvd_presentation_mode", combined)
        self.assertNotIn("disc_presentation_mode", combined)


if __name__ == "__main__": unittest.main()
