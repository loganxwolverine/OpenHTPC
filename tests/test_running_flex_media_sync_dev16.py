#!/usr/bin/env python3
from __future__ import annotations
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
LAUNCHER = ROOT / "vendor/flex-launcher/src/launcher.c"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


session = load("dev16_session", PAYLOAD / "openhtpc-session-engine.py")
play = load("dev16_play", PAYLOAD / "openhtpc-play")


class RunningFlexCache:
    """Lifecycle model of Flex's lazy section cache using its shipped INI format."""
    def __init__(self, path):
        self.path = path
        self.cached = {}
        self.generation = self._generation()

    def _generation(self):
        first = self.path.read_text().splitlines()[0]
        return re.search(r"\bmedia_generation=(\S+)", first).group(1)

    def load(self, section):
        text = self.path.read_text()
        match = re.search(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)", text)
        tokens = set(re.findall(r"mact_[0-9a-f]{32}", match.group(1))) if match else set()
        self.cached[section] = tokens
        return tokens

    def poll_like_shipped_flex(self):
        generation = self._generation()
        if generation != self.generation:
            for section in tuple(self.cached):
                if section == "MEDIA_ROOT" or section.startswith("MEDIA_"):
                    self.load(section)
            self.generation = generation


class RunningFlexMediaSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        self.config = self.home / ".config/openhtpc/flex-v1.ini"
        self.config.parent.mkdir(parents=True)
        self.media = self.home / "media"
        (self.media / "Dvd").mkdir(parents=True)
        (self.media / "Dvd/Alerte.mkv").write_bytes(b"x")

    def publish(self, sources, generation):
        session.write_flex_config(
            self.config, self.home, sources, PAYLOAD, media_generation=generation
        )
        session.activate_media_manifest(self.config, self.home)

    def alerte(self):
        model = json.loads(session.current_media_manifest(self.home).read_text())
        token, item = next(
            (token, item) for token, item in model["items"].items()
            if item["relative_path"] == "Dvd/Alerte.mkv"
        )
        return model, token, item

    def test_cached_dvd_submenu_a_to_b_uses_b_token(self):
        self.publish([self.media], "generation-A")
        model_a, token_a, _ = self.alerte()
        ui = RunningFlexCache(self.config)
        self.assertEqual(ui.load(model_a["items"][token_a]["page_id"]), {token_a})
        self.publish([self.media], "generation-B")
        model_b, token_b, item_b = self.alerte()
        self.assertNotEqual(token_a, token_b)
        ui.poll_like_shipped_flex()
        self.assertEqual(ui.cached[item_b["page_id"]], {token_b})
        page = self.home / ".local/state/openhtpc/media-actions/current-page"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(item_b["page_id"] + "\n")
        self.assertEqual(play.load_media_action(self.home, token_b), item_b)
        self.assertRaisesRegex(ValueError, "TOKEN_NOT_FOUND", play.load_media_action, self.home, token_a)

    def test_zero_one_remove_readd_and_successive_generations(self):
        self.publish([], "generation-A")
        ui = RunningFlexCache(self.config)
        ui.load("MEDIA_ROOT")
        seen = []
        for generation, sources in (("generation-B", [self.media]), ("generation-C", []), ("generation-D", [self.media])):
            self.publish(sources, generation)
            ui.poll_like_shipped_flex()
            self.assertEqual(ui.generation, generation)
            if sources:
                model, token, item = self.alerte()
                seen.append(token)
                self.assertEqual(ui.load(item["page_id"]), {token})
                self.assertIn(token, model["items"])
        self.assertEqual(len(set(seen)), 2)
        self.assertRaisesRegex(ValueError, "TOKEN_NOT_FOUND", play.load_media_action, self.home, seen[0])

    def test_launcher_invalidates_all_cached_media_descendants_on_generation_change(self):
        source = LAUNCHER.read_text()
        block = source[source.index("static void reload_media_menu_sections(void)\n{"):source.index("static void refresh_current_menu_background_and_entries", source.index("static void reload_media_menu_sections(void)\n{"))]
        self.assertIn('!strcmp(name, "MEDIA_ROOT") || !strncmp(name, "MEDIA_", 6)', source)
        self.assertIn("for (Menu *menu = config.first_menu; menu != NULL; menu = menu->next)", block)
        self.assertIn("free_menu_entries(menu)", block)
        self.assertIn('load_menu_by_name("MEDIA_ROOT", false, true)', block)
        watcher = source[source.index("static void refresh_current_menu_background_and_entries(void)\n{"):source.index("static void refresh_live_optical_state", source.index("static void refresh_current_menu_background_and_entries(void)\n{"))]
        self.assertIn("media_generation_changed", watcher)
        self.assertIn("reload_media_menu_sections();", watcher)

    def test_launcher_defers_offscreen_render_and_keeps_navigation_lazy(self):
        source = LAUNCHER.read_text()
        reload_start = source.index("static void reload_menu_section(Menu *menu)\n{")
        reload = source[reload_start:source.index("static bool is_media_menu_name", reload_start)]
        load_start = source.index("static int load_menu(Menu *menu, bool set_back_menu, bool reset_position)\n{")
        load_menu = source[load_start:source.index("static void publish_media_page", load_start)]
        submenu_start = source.index("static void load_submenu(const char *submenu)\n{")
        navigation = source[submenu_start:source.index("static void draw_screen", submenu_start)]

        # Replacing entries destroys their old textures and leaves rendered=false.
        self.assertLess(reload.index("free_menu_entries(menu)"), reload.index("menu->first_entry = new_first"))
        self.assertNotIn("render_buttons(menu);", reload)

        # The visible menu still traverses the existing lazy-render path now.
        self.assertIn("if (current_menu == menu) {\n            load_menu(menu, false, false);", reload)
        self.assertIn("if (current_menu->rendered == false)\n        render_buttons(current_menu);", load_menu)

        # Both forward and back navigation retain the same lazy load authority.
        self.assertIn("load_menu_by_name(submenu, true, true);", navigation)
        self.assertIn("load_menu(menu->back, false, config.reset_on_back);", navigation)


if __name__ == "__main__":
    unittest.main()
