#!/usr/bin/env python3
"""Dev35 final playback UX geometry, refresh, OSD and DVD shortcut tests."""
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
FLEX = ROOT / "vendor/flex-launcher/src"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("dev35_policy", PAYLOAD / "openhtpc-playback-policy.py")
session = load("dev35_session", PAYLOAD / "openhtpc-session-engine.py")


class GeometryAndReturn(unittest.TestCase):
    def test_all_playback_actions_are_below_status_panel_with_margin(self):
        screen_height = 1080
        status_bottom = 170 + 360
        action_top = screen_height * 88 // 100
        safety_margin = 100
        self.assertGreater(action_top, status_bottom + safety_margin)
        source = (FLEX / "launcher.c").read_text(encoding="utf-8")
        for menu in ("SYSTEM_PLAYBACK", "PLAYBACK_VIDEO", "PLAYBACK_AUDIO", "PLAYBACK_SUBTITLES"):
            self.assertIn(f'strcmp(name, "{menu}") == 0', source)
        self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100", source)

    def test_applyback_waits_reloads_parent_and_returns(self):
        launcher = (FLEX / "launcher.c").read_text(encoding="utf-8")
        unix = (FLEX / "platform/unix.c").read_text(encoding="utf-8")
        self.assertIn("SCMD_APPLY_BACK", launcher)
        self.assertIn("run_process_sync(settings_command)", launcher)
        self.assertIn("reload_menu_section(parent)", launcher)
        self.assertIn("load_menu(parent, false, true)", launcher)
        self.assertIn("waitpid(child_pid, &status, 0)", unix)

    def test_all_three_selectors_use_generic_applyback(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value); install = pathlib.Path(value) / "install"; install.mkdir()
            shutil.copy2(PAYLOAD / "openhtpc-playback-policy.py", install / "openhtpc-playback-policy.py")
            sections = session._playback_policy_sections(home, install, pathlib.Path("icon.png"))
            for section in sections[1:]:
                for line in section.splitlines():
                    if "openhtpc-playback-setting" in line:
                        self.assertIn(":applyback", line)
                        self.assertNotIn(":fork", line)


class EffectiveOsd(unittest.TestCase):
    @staticmethod
    def decision(requested: str):
        return {"presentation":{"requested":requested,"resolved":"PURE"},
                "audio":{"requested":"AUTO","resolved":"MPV_AUTO"},
                "subtitle":{"requested":"OFF","resolved":"NONE"}}

    def test_auto_and_pure_show_policy_and_effective_mode(self):
        expected = {
            "CINEMA_AUTO": "Mode vidéo : CINÉMA AUTO\nAudio : Auto\nSous-titres : Désactivés",
            "PURE": "Mode vidéo : PURE\nAudio : Auto\nSous-titres : Désactivés",
        }
        for requested in ("CINEMA_AUTO", "PURE"):
            text = policy.osd_text(self.decision(requested))
            self.assertEqual(text, expected[requested])
            self.assertNotIn("OPENHTPC", text)
            self.assertNotIn("→", text)

    def test_diagnostic_log_keeps_requested_and_resolved(self):
        for player in ("openhtpc-play", "openhtpc-play-dvd"):
            source = (PAYLOAD / player).read_text(encoding="utf-8")
            self.assertIn("PLAYBACK_POLICY", source)
            self.assertIn("presentation_requested", source)
            self.assertIn("presentation_resolved", source)


class DvdGlobalShortcut(unittest.TestCase):
    def test_dvd_reads_current_global_presentation_mode(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value); install = pathlib.Path(value) / "install"
            (install / "assets/ui").mkdir(parents=True)
            for name in ("openhtpc-playback-policy.py",): shutil.copy2(PAYLOAD / name, install / name)
            policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
            optical = {"state":"DVD", "device":"/dev/sr0"}
            icons = tuple(pathlib.Path(f"i{i}.png") for i in range(4))
            menu = session.disc_menu_entries(optical, install, icons, home)
            self.assertIn("LIRE LE DVD", menu)
            self.assertIn("MODE VIDÉO : CINÉMA AUTO", menu)
            self.assertLess(menu.index("LIRE LE DVD"), menu.index("MODE VIDÉO"))
            self.assertIn(":submenu DVD_VIDEO_MODE", menu)

    def test_dvd_change_updates_same_config_and_derived_label(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value); config = home / ".config/openhtpc"; config.mkdir(parents=True)
            flex = config / "flex-v1.ini"
            flex.write_text("[DISQUE]\nEntry1=LIRE LE DVD;i;play\nEntry2=MODE VIDÉO : CINÉMA AUTO;i;:submenu DVD_VIDEO_MODE\nEntry3=RETOUR;i;:back\n", encoding="utf-8")
            env = {**os.environ, "HOME":str(home), "OPENHTPC_HOME":str(home), "OPENHTPC_INSTALL_DIR":str(PAYLOAD)}
            env.pop("DISPLAY", None); env.pop("WAYLAND_DISPLAY", None)
            subprocess.run([str(PAYLOAD / "openhtpc-playback-setting"), "presentation_mode", "PURE"], env=env, check=True)
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "PURE")
            self.assertIn("MODE VIDÉO : PURE", flex.read_text(encoding="utf-8"))
            subprocess.run([str(PAYLOAD / "openhtpc-playback-setting"), "presentation_mode", "CINEMA_AUTO"], env=env, check=True)
            self.assertEqual(policy.read_preferences(home)["presentation_mode"], "CINEMA_AUTO")
            self.assertIn("MODE VIDÉO : CINÉMA AUTO", flex.read_text(encoding="utf-8"))

    def test_audio_and_subtitle_parent_render_refresh_without_display_probe(self):
        with tempfile.TemporaryDirectory() as value:
            home = pathlib.Path(value); env = {**os.environ, "HOME":str(home), "OPENHTPC_HOME":str(home), "OPENHTPC_INSTALL_DIR":str(PAYLOAD)}
            env.pop("DISPLAY", None); env.pop("WAYLAND_DISPLAY", None)
            setting = PAYLOAD / "openhtpc-playback-setting"
            subprocess.run([str(setting), "audio_language_policy", "FR"], env=env, check=True)
            page = home / ".cache/openhtpc/system-playback.png"; first = page.stat().st_ino
            subprocess.run([str(setting), "subtitle_policy", "OFF"], env=env, check=True)
            self.assertNotEqual(first, page.stat().st_ino)
            prefs = policy.read_preferences(home)
            self.assertEqual((prefs["audio_language_policy"], prefs["subtitle_policy"]), ("FR", "OFF"))
            action = (PAYLOAD / "openhtpc-system-action").read_text(encoding="utf-8")
            self.assertIn('model={"available":True,"playback_policy":policy.read_preferences(home)}', action)


if __name__ == "__main__": unittest.main()
