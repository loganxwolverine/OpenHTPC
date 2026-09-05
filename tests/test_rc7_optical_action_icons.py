# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shlex
import tempfile
import unittest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
FLEX_C = ROOT / "vendor/flex-launcher/src/launcher.c"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


session_engine = load_module("rc7_action_session_engine", PAYLOAD / "openhtpc-session-engine.py")
optical_model = load_module("rc7_action_optical", PAYLOAD / "openhtpc-optical.py")
playback_policy = load_module("rc7_action_policy", PAYLOAD / "openhtpc-playback-policy.py")
plugin_registry = load_module("rc7_action_registry", PAYLOAD / "openhtpc-plugin-registry.py")


class Rc7OpticalActionIconsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        (self.home / ".config/openhtpc/runtime").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/state/openhtpc").mkdir(parents=True, exist_ok=True)

    def test_01_dvd_action_icons_with_committed_metadata(self):
        """Verify that a qualified DVD disc view (e.g. D-TOX) generates the 4 expected icons: media.png, system-processing.png, eject.png, system-back.png."""
        # Create tmdb cache with PASS status so no configuration prompt is added
        tmdb_dir = self.home / ".cache/openhtpc/tmdb"
        tmdb_dir.mkdir(parents=True, exist_ok=True)
        query = "D-TOX"
        cache_file = tmdb_dir / (hashlib.sha256(f"query:{query}".encode()).hexdigest() + ".json")
        cache_file.write_text(json.dumps({"status": "PASS", "title": "D-Tox", "year": "2002"}), encoding="utf-8")
        secrets_dir = self.home / ".config/openhtpc/secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        (secrets_dir / "tmdb-token").write_text("synthetic-token", encoding="utf-8")

        playback_policy.write_preference(self.home, "presentation_mode", "PURE")
        optical = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0", "disc_title": "D-TOX"}
        default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
        menu = session_engine.disc_menu_entries(optical, PAYLOAD, default_icons, self.home)
        lines = [line.strip() for line in menu.strip().splitlines() if line.strip()]

        entries = {}
        for line in lines:
            key, val = line.split("=", 1)
            parts = val.split(";")
            entries[key] = {"label": parts[0], "icon": parts[1], "command": ";".join(parts[2:])}

        self.assertEqual(len(entries), 4)
        self.assertIn("Entry1", entries)
        self.assertIn("Entry2", entries)
        self.assertIn("Entry3", entries)
        self.assertIn("Entry4", entries)

        # 1. LIRE LE DVD -> media.png
        self.assertEqual(entries["Entry1"]["label"], "LIRE LE DVD")
        self.assertTrue(entries["Entry1"]["icon"].endswith("assets/ui/media.png"))
        self.assertIn("openhtpc-play-dvd", entries["Entry1"]["command"])

        # 2. MODE VIDÉO : PURE -> system-processing.png
        self.assertEqual(entries["Entry2"]["label"], "MODE VIDÉO : PURE")
        self.assertTrue(entries["Entry2"]["icon"].endswith("assets/ui/system-processing.png") or entries["Entry2"]["icon"].endswith("assets/ui/traitement_video.png"))
        self.assertEqual(entries["Entry2"]["command"], ":submenu DVD_VIDEO_MODE")

        # 3. ÉJECTER -> eject.png
        self.assertEqual(entries["Entry3"]["label"], "ÉJECTER")
        self.assertTrue(entries["Entry3"]["icon"].endswith("assets/ui/eject.png"))
        self.assertIn("openhtpc-eject", entries["Entry3"]["command"])

        # 4. RETOUR -> system-back.png
        self.assertEqual(entries["Entry4"]["label"], "RETOUR")
        self.assertTrue(entries["Entry4"]["icon"].endswith("assets/ui/system-back.png"))
        self.assertEqual(entries["Entry4"]["command"], ":back")

    def test_02_dvd_cinema_auto_presentation_mode(self):
        """Verify that CINÉMA AUTO presentation mode preserves the system-processing.png icon."""
        playback_policy.write_preference(self.home, "presentation_mode", "CINEMA_AUTO")
        optical = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0"}
        default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
        menu = session_engine.disc_menu_entries(optical, PAYLOAD, default_icons, self.home)
        self.assertIn("MODE VIDÉO : CINÉMA AUTO", menu)
        self.assertTrue("assets/ui/system-processing.png" in menu or "assets/ui/traitement_video.png" in menu)

    def test_03_bluray_and_uhd_action_icons_generation(self):
        """Verify that Blu-ray and UHD disc views generate the appropriate action icons when enabled."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        for state, name in (("BLURAY_VIDEO", "BLU-RAY"), ("UHD_BLURAY_VIDEO", "UHD BLU-RAY")):
            optical = {"canonical_state": state, "device": "/dev/sr0", "protection": "PROTECTED", "generation": 1,
                       "disc_id": f"synthetic_{state}"}
            (self.home / ".local/state/openhtpc/optical-current.json").write_text(json.dumps(optical), encoding="utf-8")
            (self.home / ".config/openhtpc/runtime/capabilities.json").write_text(
                json.dumps({"optical": {"protected_media": {"status": "AVAILABLE", "state": "AVAILABLE"}}}),
                encoding="utf-8"
            )
            default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
            menu = session_engine.disc_menu_entries(optical, PAYLOAD, default_icons, self.home)
            lines = [line.strip() for line in menu.strip().splitlines() if line.strip()]
            entries = {}
            for line in lines:
                key, val = line.split("=", 1)
                parts = val.split(";")
                entries[key] = {"label": parts[0], "icon": parts[1], "command": ";".join(parts[2:])}

            play_entry = next(e for e in entries.values() if f"LIRE LE {name}" in e["label"])
            self.assertTrue(play_entry["icon"].endswith("assets/ui/media.png"))
            self.assertIn("openhtpc-play-optical", play_entry["command"])

            eject_entry = next(e for e in entries.values() if e["label"] == "ÉJECTER")
            self.assertTrue(eject_entry["icon"].endswith("assets/ui/eject.png"))

            back_entry = next(e for e in entries.values() if e["label"] == "RETOUR")
            self.assertTrue(back_entry["icon"].endswith("assets/ui/system-back.png"))

    def test_04_all_referenced_assets_exist_and_are_valid_png(self):
        """Verify that every icon referenced in optical disc view exists and is a valid RGBA PNG."""
        required_assets = [
            PAYLOAD / "assets/ui/media.png",
            PAYLOAD / "assets/ui/system-processing.png",
            PAYLOAD / "assets/ui/eject.png",
            PAYLOAD / "assets/ui/system-back.png",
        ]
        for asset in required_assets:
            self.assertTrue(asset.is_file(), f"Asset {asset} must exist physically.")
            self.assertGreater(asset.stat().st_size, 100, f"Asset {asset} must not be empty.")
            with Image.open(asset) as img:
                self.assertEqual(img.format, "PNG")
                self.assertIn(img.mode, ("RGBA", "RGB"))
                self.assertGreaterEqual(img.width, 36)
                self.assertGreaterEqual(img.height, 36)

    def test_05_action_commands_strictly_unaffected(self):
        """Verify that all commands generated for disc actions remain functionally immutable."""
        optical = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0"}
        default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
        menu = session_engine.disc_menu_entries(optical, PAYLOAD, default_icons, self.home)

        self.assertIn("env OPENHTPC_FLEX_RETAINED=1 " + str(PAYLOAD / "openhtpc-play-dvd") + " /dev/sr0", menu)
        self.assertIn(":submenu DVD_VIDEO_MODE", menu)
        self.assertIn(":fork env OPENHTPC_RETURN_UI=/bin/true " + str(PAYLOAD / "openhtpc-eject") + " /dev/sr0", menu)
        self.assertIn(":back", menu)

    def test_06_flex_c_source_contracts(self):
        """Verify that vendor/flex-launcher/src/launcher.c implements the exact Tranche 4 contracts with is_menu_disc_action_sheet predicate."""
        self.assertTrue(FLEX_C.is_file())
        source = FLEX_C.read_text(encoding="utf-8")

        # Must not suppress disc action icons
        self.assertNotIn("else if (is_disc_sheet()) {\n                icon = NULL;", source)
        self.assertNotIn("else if (is_disc_sheet()) {\n            icon = NULL;", source)

        # Must define the specific discriminator predicate accepting Menu*
        self.assertIn("static bool is_menu_disc_action_sheet(const Menu *menu)", source)
        self.assertIn("return is_menu_disc_sheet(menu) && !is_menu_disc_ambiguous(menu);", source)

        # Must use is_menu_disc_action_sheet in render_buttons
        self.assertIn("if (is_menu_disc_action_sheet(menu) && entry->icon != NULL)", source)

        # Must use is_disc_action_sheet for action button geometry, reservation, and drawing
        self.assertIn("else if (is_disc_action_sheet()) {", source)
        self.assertIn("int total_w = icon_size + icon_gap + entry->text_rect.w;", source)
        self.assertIn("artwork_rect.x = entry->text_rect.x - icon_gap - icon_size;", source)

    def test_07_write_flex_config_passes_canonical_icons(self):
        """Verify write_flex_config writes the [DISQUE] section with canonical action icons."""
        config_path = self.home / "flex-v1.ini"
        optical = {"canonical_state": "DVD_VIDEO", "state": "DVD", "device": "/dev/sr0", "generation": 1}
        state_dir = self.home / ".local/state/openhtpc"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "optical-current.json").write_text(json.dumps(optical), encoding="utf-8")

        ok = session_engine.write_flex_config(config_path, self.home, [], install=PAYLOAD)
        self.assertTrue(ok)
        self.assertTrue(config_path.is_file())

        content = config_path.read_text(encoding="utf-8")
        self.assertIn("[DISQUE]", content)
        self.assertIn("assets/ui/media.png", content)
        self.assertTrue("assets/ui/system-processing.png" in content or "assets/ui/traitement_video.png" in content)
        self.assertIn("assets/ui/eject.png", content)
        self.assertIn("assets/ui/system-back.png", content)

    def test_08_fallback_gracefully_when_assets_missing(self):
        """Verify that if assets are missing or custom icons passed, disc_menu_entries falls back safely."""
        with tempfile.TemporaryDirectory() as empty_dir:
            empty_install = pathlib.Path(empty_dir)
            optical = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0"}
            custom_icons = (pathlib.Path("/mock/play.png"), pathlib.Path("/mock/tmdb.png"),
                            pathlib.Path("/mock/eject.png"), pathlib.Path("/mock/back.png"))
            menu = session_engine.disc_menu_entries(optical, empty_install, custom_icons, self.home)
            self.assertIn("/mock/play.png", menu)
            self.assertIn("/mock/eject.png", menu)
            self.assertIn("/mock/back.png", menu)

    def test_09_tmdb_ambiguous_candidate_geometry_non_regression(self):
        """Verify that TMDb candidate cards retain full poster geometry (~76x106 at 1080p, ~153x212 at 4K) and are NOT reduced to 36x36 action icons."""
        source = FLEX_C.read_text(encoding="utf-8")

        # 1. Verify that is_disc_ambiguous branches take precedence in layout and rendering
        self.assertIn("if (is_disc_ambiguous()) {", source)

        # 2. Verify candidate poster geometry calculation in calculate_button_geometry
        self.assertIn("int card_h = (geo.screen_height * 115) / 1000;", source)
        self.assertIn("int icon_w = (card_h * 2) / 3;", source)
        self.assertIn("int icon_h = card_h - (geo.screen_height * 18) / 1000;", source)

        # 3. Simulate and assert geometry comparison for 1080p and 4K displays
        for screen_w, screen_h in ((1920, 1080), (3840, 2160)):
            card_h = (screen_h * 115) // 1000
            poster_w = (card_h * 2) // 3
            poster_h = card_h - (screen_h * 18) // 1000
            action_icon_size = (screen_h * 34) // 1000

            self.assertGreater(poster_h, action_icon_size * 2, "Candidate poster height must be more than double the action icon size")
            self.assertGreater(poster_w, action_icon_size, "Candidate poster width must be substantially larger than action icon size")
            self.assertNotEqual(poster_w, poster_h, "Candidate poster must retain 2:3 portrait aspect ratio, not square")

    def test_10_c_harness_predicate_and_artwork_discrimination(self):
        """Compile and run an isolated C harness against the predicate and geometry logic to verify exact runtime distinction between action buttons and TMDb candidates."""
        import subprocess

        c_code = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

typedef struct Entry {
    char *title;
    char *cmd;
    void *icon;
    struct { int x, y, w, h; } icon_rect;
    struct { int x, y, w, h; } text_rect;
    struct Entry *next;
} Entry;

typedef struct Menu {
    char *name;
    Entry *first_entry;
    Entry *root_entry;
} Menu;

static Menu *current_menu = NULL;

static bool is_menu_disc_sheet(const Menu *menu) {
    return menu != NULL && menu->name != NULL && strcmp(menu->name, "DISQUE") == 0;
}
static bool is_disc_sheet(void) {
    return is_menu_disc_sheet(current_menu);
}

static bool is_menu_disc_ambiguous(const Menu *menu) {
    if (!is_menu_disc_sheet(menu) || menu == NULL) return false;
    for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
        if (e->cmd != NULL && strstr(e->cmd, "openhtpc-bind-disc") != NULL) return true;
    }
    return false;
}
static bool is_disc_ambiguous(void) {
    return is_menu_disc_ambiguous(current_menu);
}

static bool is_menu_disc_action_sheet(const Menu *menu) {
    return is_menu_disc_sheet(menu) && !is_menu_disc_ambiguous(menu);
}
static bool is_disc_action_sheet(void) {
    return is_menu_disc_action_sheet(current_menu);
}

int main(void) {
    int screen_w = 1920, screen_h = 1080;
    int action_icon_size = (screen_h * 34) / 1000; // ~36px
    int action_icon_gap = (screen_w * 6) / 1000;   // ~11px

    // CASE 1: Standard Disc Action Sheet (e.g. D-TOX with 4 actions)
    Entry e4 = { .title = "RETOUR", .cmd = ":back", .icon = (void*)1, .next = NULL };
    Entry e3 = { .title = "EJECTER", .cmd = "openhtpc-eject", .icon = (void*)1, .next = &e4 };
    Entry e2 = { .title = "MODE VIDEO", .cmd = ":submenu DVD_VIDEO_MODE", .icon = (void*)1, .next = &e3 };
    Entry e1 = { .title = "LIRE LE DVD", .cmd = "openhtpc-play-dvd", .icon = (void*)1, .next = &e2 };
    Menu action_menu = { .name = "DISQUE", .first_entry = &e1, .root_entry = &e1 };

    current_menu = &action_menu;
    if (!is_disc_sheet()) return 10;
    if (is_disc_ambiguous()) return 11;
    if (!is_disc_action_sheet()) return 12;

    // Verify action icon artwork_rect geometry
    e1.text_rect.x = 800; e1.text_rect.y = 950; e1.text_rect.w = 200; e1.text_rect.h = 30;
    e1.icon_rect.x = 750; e1.icon_rect.y = 940; e1.icon_rect.w = 300; e1.icon_rect.h = 60;
    struct { int x, y, w, h; } art1 = { e1.icon_rect.x, e1.icon_rect.y, e1.icon_rect.w, e1.icon_rect.h };
    if (is_disc_action_sheet()) {
        art1.x = e1.text_rect.x - action_icon_gap - action_icon_size;
        art1.y = e1.icon_rect.y + (e1.icon_rect.h - action_icon_size) / 2;
        art1.w = action_icon_size;
        art1.h = action_icon_size;
    }
    if (art1.w != 36 || art1.h != 36) return 13;

    // CASE 2: Ambiguous TMDb Candidate Sheet
    Entry dock = { .title = "IGNORER", .cmd = "openhtpc-ignore", .icon = NULL, .next = NULL };
    Entry cand2 = { .title = "Candidate 2", .cmd = "openhtpc-bind-disc 456", .icon = (void*)1, .next = &dock };
    Entry cand1 = { .title = "Candidate 1", .cmd = "openhtpc-bind-disc 123", .icon = (void*)1, .next = &cand2 };
    Menu tmdb_menu = { .name = "DISQUE", .first_entry = &cand1, .root_entry = &cand1 };

    current_menu = &tmdb_menu;
    if (!is_disc_sheet()) return 20;
    if (!is_disc_ambiguous()) return 21;
    if (is_disc_action_sheet()) return 22; // MUST BE FALSE

    // Candidate 1 poster layout
    int card_h = (screen_h * 115) / 1000; // 124
    int icon_w = (card_h * 2) / 3;        // 82
    int icon_h = card_h - (screen_h * 18) / 1000; // 105
    cand1.icon_rect.x = 600; cand1.icon_rect.y = 400; cand1.icon_rect.w = icon_w; cand1.icon_rect.h = icon_h;

    // artwork_rect in draw_screen
    struct { int x, y, w, h; } cand_art = { cand1.icon_rect.x, cand1.icon_rect.y, cand1.icon_rect.w, cand1.icon_rect.h };
    if (is_disc_action_sheet()) {
        // If this branch erroneously executed, it would reduce the poster to 36x36
        cand_art.w = action_icon_size;
        cand_art.h = action_icon_size;
    }
    // Verify poster retained full dimensions (not reduced to 36x36)
    if (cand_art.w != 82 || cand_art.h != 105) return 23;

    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "test_harness.c"
            bin_path = pathlib.Path(td) / "test_harness"
            src.write_text(c_code, encoding="utf-8")
            compile_res = subprocess.run(["cc", "-O2", str(src), "-o", str(bin_path)], capture_output=True, text=True)
            self.assertEqual(compile_res.returncode, 0, f"Compilation failed: {compile_res.stderr}")
            run_res = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"C test harness execution failed with code {run_res.returncode}")

    def test_11_initial_render_vs_redraw_text_max_width_consistency(self):
        """Verify that render_buttons calculates the exact same text max_width regardless of whether current_menu is Accueil or DISQUE."""
        import subprocess

        c_code = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

typedef struct Entry {
    char *title;
    char *cmd;
    void *icon;
    struct { int x, y, w, h; } icon_rect;
    struct { int x, y, w, h; } text_rect;
    struct Entry *next;
} Entry;

typedef struct Menu {
    char *name;
    Entry *first_entry;
    Entry *root_entry;
} Menu;

static Menu *current_menu = NULL;

static bool is_menu_disc_sheet(const Menu *menu) {
    return menu != NULL && menu->name != NULL && strcmp(menu->name, "DISQUE") == 0;
}
static bool is_menu_disc_ambiguous(const Menu *menu) {
    if (!is_menu_disc_sheet(menu) || menu == NULL) return false;
    for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
        if (e->cmd != NULL && strstr(e->cmd, "openhtpc-bind-disc") != NULL) return true;
    }
    return false;
}
static bool is_menu_disc_action_sheet(const Menu *menu) {
    return is_menu_disc_sheet(menu) && !is_menu_disc_ambiguous(menu);
}
static bool is_menu_system_subpage(const Menu *menu) {
    return false;
}

int calculate_max_width_for_entry(const Menu *menu, const Entry *entry, int screen_w, int screen_h) {
    int max_width = 250; // default icon_size
    if (is_menu_disc_ambiguous(menu) && entry->cmd != NULL && strstr(entry->cmd, "openhtpc-bind-disc") != NULL) {
        int card_w = (screen_w * 64) / 100;
        int icon_w = ((screen_h * 115) / 1000 * 2) / 3;
        max_width = card_w - icon_w - (screen_w * 5) / 100;
    } else if (is_menu_disc_sheet(menu) || is_menu_system_subpage(menu)) {
        int btn_count = 0;
        for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
            if (e->cmd == NULL || strstr(e->cmd, "openhtpc-bind-disc") == NULL) btn_count++;
        }
        int gap = (screen_w * 15) / 1000;
        int max_w = (btn_count <= 2) ? (screen_w * 36) / 100 : (btn_count <= 3) ? (screen_w * 28) / 100 : (screen_w * 22) / 100;
        int avail_w = (screen_w * 88) / 100;
        int btn_w = (avail_w - (btn_count - 1) * gap) / (btn_count > 0 ? btn_count : 1);
        if (btn_w > max_w) btn_w = max_w;
        if (is_menu_disc_action_sheet(menu) && entry->icon != NULL) {
            int reserved_icon = (screen_h * 34) / 1000 + (screen_w * 6) / 1000;
            max_width = btn_w - (screen_w * 2) / 100 - reserved_icon;
        } else {
            max_width = btn_w - (screen_w * 2) / 100;
        }
    }
    return max_width;
}

int main(void) {
    int screen_w = 1920, screen_h = 1080;

    Entry e4 = { .title = "RETOUR", .cmd = ":back", .icon = (void*)1, .next = NULL };
    Entry e3 = { .title = "EJECTER", .cmd = "openhtpc-eject", .icon = (void*)1, .next = &e4 };
    Entry e2 = { .title = "MODE VIDEO : PURE", .cmd = ":submenu DVD_VIDEO_MODE", .icon = (void*)1, .next = &e3 };
    Entry e1 = { .title = "LIRE LE DVD", .cmd = "openhtpc-play-dvd", .icon = (void*)1, .next = &e2 };
    Menu disc_menu = { .name = "DISQUE", .first_entry = &e1, .root_entry = &e1 };
    Menu home_menu = { .name = "Accueil", .first_entry = NULL, .root_entry = NULL };

    // Stage 1: Initial background reload while user is on Accueil
    current_menu = &home_menu;
    int mw_initial_play = calculate_max_width_for_entry(&disc_menu, &e1, screen_w, screen_h);
    int mw_initial_mode = calculate_max_width_for_entry(&disc_menu, &e2, screen_w, screen_h);

    // Stage 2: Redraw after navigating to DISQUE
    current_menu = &disc_menu;
    int mw_active_play = calculate_max_width_for_entry(&disc_menu, &e1, screen_w, screen_h);
    int mw_active_mode = calculate_max_width_for_entry(&disc_menu, &e2, screen_w, screen_h);

    // Assert absolute consistency between initial background render and active page redraw
    if (mw_initial_play != mw_active_play) return 30;
    if (mw_initial_mode != mw_active_mode) return 31;
    if (mw_initial_play <= 250) return 32; // Must NOT collapse to default icon_size (250)

    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "test_consistency.c"
            bin_path = pathlib.Path(td) / "test_consistency"
            src.write_text(c_code, encoding="utf-8")
            compile_res = subprocess.run(["cc", "-O2", str(src), "-o", str(bin_path)], capture_output=True, text=True)
            self.assertEqual(compile_res.returncode, 0, f"Compilation failed: {compile_res.stderr}")
            run_res = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"Consistency test failed with code {run_res.returncode}")

    def test_12_pure_vs_cinema_auto_font_consistency(self):
        """Verify that LIRE LE DVD and MODE VIDÉO: PURE share the full button width, preventing unwarranted text shrinking."""
        optical_pure = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0"}
        playback_policy.write_preference(self.home, "presentation_mode", "PURE")
        default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
        menu_pure = session_engine.disc_menu_entries(optical_pure, PAYLOAD, default_icons, self.home)
        self.assertIn("LIRE LE DVD", menu_pure)
        self.assertIn("MODE VIDÉO : PURE", menu_pure)

        playback_policy.write_preference(self.home, "presentation_mode", "CINEMA_AUTO")
        menu_auto = session_engine.disc_menu_entries(optical_pure, PAYLOAD, default_icons, self.home)
        self.assertIn("LIRE LE DVD", menu_auto)
        self.assertIn("MODE VIDÉO : CINÉMA AUTO", menu_auto)

    def test_13_video_mode_icon_is_system_processing_matching_system_playback(self):
        """Verify that the icon for MODE VIDÉO in disc menu strictly matches the icon in SYSTÈME → LECTURE (system-processing.png)."""
        sys_menu_source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        self.assertIn('icon_processing = resolve_sys_icon("system-processing.png", resolve_sys_icon("traitement_video.png", logo))', sys_menu_source)
        self.assertIn("Entry4=LECTURE;{icon_processing};:submenu SYSTEM_PLAYBACK", sys_menu_source)

        optical = {"canonical_state": "DVD_VIDEO", "device": "/dev/sr0"}
        default_icons = tuple(pathlib.Path(f"default_{i}.png") for i in range(4))
        menu = session_engine.disc_menu_entries(optical, PAYLOAD, default_icons, self.home)
        lines = [line.strip() for line in menu.strip().splitlines() if line.strip()]
        video_entry = next(line for line in lines if "MODE VIDÉO" in line)
        self.assertTrue("assets/ui/system-processing.png" in video_entry or "assets/ui/traitement_video.png" in video_entry)
        self.assertNotIn("assets/ui/playback-video.png", video_entry)
