"""Unit tests for OPENHTPC RC7 T6 — Protected Blu-ray AACS UX (P2 architecture).

Validates:
1. T6 policy provided by plugin.bluray, not duplicated in Core presentation.
2. disc-view and session-engine consume the exact same policy contribution.
3. TMDb AMBIGUOUS + AACS blocked preserves its candidate entries.
4. DVD video flow unchanged.
5. Unprotected Blu-ray flow unchanged.
6. BD+ alone is never classified as AACS.
7. AVAILABLE capability preserves normal playback flow.
8. Standalone disc-sheet emits no fake DIAGNOSTIC button.
9. Zero forbidden overclaiming strings in code.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

PAYLOAD = pathlib.Path(__file__).resolve().parent.parent / "payload"


def load_module(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


core_mod        = load_module("rc7t6_core",       PAYLOAD / "openhtpc-core.py")
plugin_mod      = load_module("rc7t6_plugin",     PAYLOAD / "plugins/available/plugin.bluray/shadow.py")
optical_model   = load_module("rc7t6_optical",    PAYLOAD / "openhtpc-optical.py")
disc_view       = load_module("rc7t6_disc_view",  PAYLOAD / "openhtpc-disc-view.py")
session_engine  = load_module("rc7t6_session",    PAYLOAD / "openhtpc-session-engine.py")
disc_sheet      = load_module("rc7t6_disc_sheet", PAYLOAD / "openhtpc-disc-sheet.py")
plugin_registry = load_module("rc7t6_registry",   PAYLOAD / "openhtpc-plugin-registry.py")


def _bluray_state(canonical="BLURAY_VIDEO", protection="PROTECTED",
                  aacs_detected=True, bdplus_detected=False,
                  generation=1, device="/dev/sr0"):
    """Build a minimal optical disc state dict mimicking probe facts."""
    return {
        "canonical_state": canonical,
        "state": {"UHD_BLURAY_VIDEO": "UHD", "BLURAY_FAMILY": "BLURAY"}.get(canonical, "BLURAY"),
        "device": device,
        "generation": generation,
        "protection": protection,
        "protection_mechanisms": (
            ["AACS"] if aacs_detected and not bdplus_detected else
            ["BDPLUS"] if bdplus_detected and not aacs_detected else
            ["AACS", "BDPLUS"] if aacs_detected and bdplus_detected else
            ["NONE"]
        ),
        "classification_source": "LIBBLURAY",
        "classification_confidence": "CERTAIN",
        "playable": False,
        "volume_label": "TEST_DISC",
        "libbluray_disc_info": {
            "bluray_detected": True,
            "aacs_detected": aacs_detected,
            "aacs_handled": False,
            "bdplus_detected": bdplus_detected,
            "bdplus_handled": False,
            "probe_open_succeeded": False,
        },
    }


def _capabilities(status="NOT_CONFIGURED", libaacs="AVAILABLE", libbdplus="NOT_AVAILABLE"):
    return {
        "optical": {
            "protected_media": {
                "status": status,
                "dependencies": {
                    "libbluray": {"status": "AVAILABLE"},
                    "libaacs":   {"status": libaacs},
                    "libbdplus": {"status": libbdplus},
                },
                "external_key_database": {
                    "status": "DETECTED" if status == "AVAILABLE" else "NOT_CONFIGURED"
                },
            }
        }
    }


class TestRC7T6AacsPluginArchitecture(unittest.TestCase):
    """Verifies P2 boundary: policy owned by plugin.bluray, consumed by Core."""

    def setUp(self):
        self.tmp  = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.orig = os.environ.get("OPENHTPC_HOME")
        os.environ["OPENHTPC_HOME"] = str(self.home)
        for sub in (".config/openhtpc/runtime", ".config/openhtpc/secrets",
                    ".local/state/openhtpc", ".cache/openhtpc"):
            (self.home / sub).mkdir(parents=True)
        self.icons = tuple(
            PAYLOAD / "assets/ui" / n
            for n in ("media.png", "media.png", "eject.png", "system-back.png")
        )

    def tearDown(self):
        if self.orig is None:
            os.environ.pop("OPENHTPC_HOME", None)
        else:
            os.environ["OPENHTPC_HOME"] = self.orig
        self.tmp.cleanup()

    def _set_caps(self, status="NOT_CONFIGURED", libaacs="AVAILABLE"):
        (self.home / ".config/openhtpc/runtime/capabilities.json").write_text(
            json.dumps(_capabilities(status, libaacs)), encoding="utf-8"
        )

    def _write_optical(self, state: dict):
        (self.home / ".local/state/openhtpc/optical-current.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

    # ── Test 1: Plugin ownership & no Core duplication ─────────────────────────

    def test_01_t6_policy_provided_by_plugin_bluray_not_duplicated_in_core_views(self):
        """Plugin defines protection_policy; disc-view and session-engine do not duplicate logic."""
        # Plugin declares the callable policy entrypoint
        self.assertTrue(callable(getattr(plugin_mod, "protection_policy", None)))
        self.assertTrue(callable(getattr(plugin_mod, "protected_optical_policy", None)))

        # Evaluate directly against plugin
        state = _bluray_state(aacs_detected=True)
        snap = {"status": "NOT_CONFIGURED"}
        plugin_policy = plugin_mod.protection_policy(state, snap)
        core_fallback = core_mod.core_protected_optical_policy(state, snap)

        self.assertEqual(plugin_policy, core_fallback)
        self.assertTrue(plugin_policy["unplayable"])
        self.assertEqual(plugin_policy["case"], "AACS_NOT_CONFIGURED")
        self.assertIn("base de clés AACS", plugin_policy["message"])

        # Verify that disc-view and session-engine do NOT define their own duplicate AACS messages
        disc_view_code = (PAYLOAD / "openhtpc-disc-view.py").read_text(encoding="utf-8")
        session_code   = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        for code, name in ((disc_view_code, "disc-view"), (session_code, "session-engine")):
            self.assertNotIn("La base de clés AACS nécessaire", code,
                             f"{name} must not hardcode AACS message")
            self.assertNotIn("Les bibliothèques nécessaires au déchiffrement", code,
                             f"{name} must not hardcode AACS message")
            self.assertNotIn("_aacs_proven", code,
                             f"{name} must not contain duplicate classification logic")

    # ── Test 2: disc-view and session-engine consume the same contribution ─────

    def test_02_disc_view_and_session_engine_consume_same_contribution(self):
        """disc-view and session-engine consume the same policy from Core."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        self._set_caps("NOT_CONFIGURED")
        state = _bluray_state(aacs_detected=True)
        self._write_optical(state)

        caps = optical_model.protected_capability(self.home)
        policy = core_mod.resolve_protected_optical_policy(self.home, PAYLOAD, state, caps)

        # 1. Disc-view uses title and section from the contribution
        target = self.home / ".cache/openhtpc/disc-sheet-p2.png"
        res = disc_view.render(self.home, PAYLOAD, state, {"status": "NOT_CONFIGURED"}, target)
        self.assertEqual(res["title"], policy["title"])

        # 2. Session-engine uses policy unplayable flag to build early-return menu
        menu = session_engine.disc_menu_entries(state, PAYLOAD, self.icons, self.home)
        self.assertIn("DIAGNOSTIC", menu)
        self.assertIn("ÉJECTER", menu)
        self.assertIn("RETOUR", menu)
        self.assertNotIn("openhtpc-play-optical", menu)

    # ── Test 3: TMDb AMBIGUOUS preserves candidate entries ─────────────────────

    def test_03_tmdb_ambiguous_with_aacs_blocked_preserves_candidates(self):
        """A protected unplayable Blu-ray with TMDb AMBIGUOUS status preserves candidate items."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        self._set_caps("NOT_CONFIGURED")
        state = _bluray_state(aacs_detected=True)
        state["volume_label"] = "DUNE"
        self._write_optical(state)

        # Write cached metadata with AMBIGUOUS status and 2 candidates to the exact tmdb cache path
        tmdb = load_module("rc7_test_tmdb", PAYLOAD / "openhtpc-tmdb.py")
        cache_file = tmdb.cache_path(self.home, state, "Dune")
        self.assertIsNotNone(cache_file)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        ambiguous_meta = {
            "status": "AMBIGUOUS",
            "query": "Dune",
            "candidates": [
                {"tmdb_id": 438631, "title": "Dune", "release_date": "2021-09-15", "runtime": 155},
                {"tmdb_id": 43074,  "title": "Dune", "release_date": "1984-12-14", "runtime": 137},
            ],
        }
        cache_file.write_text(json.dumps(ambiguous_meta), encoding="utf-8")

        menu = session_engine.disc_menu_entries(state, PAYLOAD, self.icons, self.home)

        # 1. Candidates must NOT be masked
        self.assertIn("438631", menu, "Candidate 1 bind argument missing from menu")
        self.assertIn("43074", menu, "Candidate 2 bind argument missing from menu")
        self.assertIn("Dune", menu)

        # 2. Diagnostic & ejection actions must coexist with the candidates
        self.assertIn("DIAGNOSTIC", menu)
        self.assertIn(":submenu SYSTEM_MEDIA_OPTICAL", menu)
        self.assertIn("ÉJECTER", menu)
        self.assertIn("RETOUR", menu)

        # 3. Play action is absent
        self.assertNotIn("openhtpc-play-optical", menu)

        # 4. disc-view renders AMBIGUOUS section rather than overwriting with protected title
        target = self.home / ".cache/openhtpc/disc-sheet-ambig.png"
        res = disc_view.render(self.home, PAYLOAD, state, ambiguous_meta, target)
        self.assertEqual(res["title"], "DUNE", "Title must not be overridden to 'Blu-ray protégé'")

    # ── Test 4: DVD unchanged ──────────────────────────────────────────────────

    def test_04_dvd_flow_untouched(self):
        """DVD-Video menu remains completely untouched."""
        state = {
            "canonical_state": "DVD_VIDEO", "state": "DVD",
            "device": "/dev/sr0", "generation": 4,
            "protection": "UNPROTECTED", "volume_label": "MY_DVD", "playable": True,
        }
        self._write_optical(state)
        menu = session_engine.disc_menu_entries(state, PAYLOAD, self.icons, self.home)
        self.assertIn("LIRE LE DVD", menu)
        self.assertIn("openhtpc-play-dvd", menu)
        self.assertIn("MODE VIDÉO", menu)
        self.assertIn("ÉJECTER", menu)
        self.assertIn("RETOUR", menu)
        self.assertNotIn("BLU-RAY PROTÉGÉ", menu)
        self.assertNotIn("AACS", menu)

    # ── Test 5: Unprotected Blu-ray unchanged ──────────────────────────────────

    def test_05_unprotected_bluray_untouched(self):
        """Unprotected Blu-ray preserves normal playback without protection gate."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        self._set_caps("AVAILABLE")
        state = _bluray_state(protection="UNPROTECTED", aacs_detected=False, generation=5)
        state["playable"] = True
        self._write_optical(state)

        res = disc_view.render(self.home, PAYLOAD, state, {"status": "NOT_CONFIGURED"},
                               self.home / ".cache/openhtpc/sheet-unprot.png")
        self.assertNotEqual(res["title"], "Blu-ray protégé")

        menu = session_engine.disc_menu_entries(state, PAYLOAD, self.icons, self.home)
        self.assertIn("openhtpc-play-optical", menu)
        self.assertNotIn("AACS", menu)

    # ── Test 6: BD+ alone never presented as AACS ─────────────────────────────

    def test_06_bdplus_only_never_presented_as_aacs(self):
        """BD+ alone produces PROTECTED_GENERIC, never an AACS message."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        self._set_caps("NOT_CONFIGURED")
        state = _bluray_state(aacs_detected=False, bdplus_detected=True)
        self._write_optical(state)

        caps = optical_model.protected_capability(self.home)
        policy = core_mod.resolve_protected_optical_policy(self.home, PAYLOAD, state, caps)

        self.assertEqual(policy["case"], "PROTECTED_GENERIC")
        self.assertNotIn("AACS", policy["message"])
        self.assertEqual(policy["message"],
                         "Ce Blu-ray est protégé et OPENHTPC ne peut pas actuellement en autoriser la lecture.")

    # ── Test 7: AVAILABLE preserves normal playback flow ───────────────────────

    def test_07_available_preserves_normal_playback_flow(self):
        """AVAILABLE capability results in unplayable=False and normal play action."""
        plugin_registry.set_enabled(self.home, PAYLOAD, "plugin.bluray", True)
        self._set_caps("AVAILABLE", libaacs="AVAILABLE")
        state = _bluray_state(aacs_detected=True, generation=7)
        self._write_optical(state)

        caps = optical_model.protected_capability(self.home)
        policy = core_mod.resolve_protected_optical_policy(self.home, PAYLOAD, state, caps)
        self.assertFalse(policy["unplayable"])
        self.assertEqual(policy["case"], "NONE")

        menu = session_engine.disc_menu_entries(state, PAYLOAD, self.icons, self.home)
        self.assertIn("openhtpc-play-optical", menu)
        self.assertNotIn("base de clés AACS", menu)

    # ── Test 8: No fake diagnostic in standalone disc-sheet ────────────────────

    def test_08_no_fake_diagnostic_in_disc_sheet_standalone(self):
        """Standalone disc-sheet write_menu emits no fake openhtpc-system-view command."""
        self._set_caps("NOT_CONFIGURED")
        state = _bluray_state(aacs_detected=True)
        self._write_optical(state)

        data = {"state": state, "title": "TEST", "metadata": {"status": "NOT_CONFIGURED"},
                "artwork": self.icons[0], "duration": None}
        content = disc_sheet.write_menu(self.home, PAYLOAD, data).read_text(encoding="utf-8")

        self.assertNotIn("openhtpc-system-view", content)
        self.assertIn("ÉJECTER", content)
        self.assertIn("RETOUR", content)


class TestRC7T6ForbiddenStrings(unittest.TestCase):
    """Verify absence of misleading claims or forbidden mechanisms in all T6 files."""

    FORBIDDEN = (
        "le matériel n'est pas en cause",
        "OPENHTPC NE FOURNIT PAS DE CLÉS AACS",
        "download_keydb",
        "fetch_keys",
        "les clés nécessaires à sa lecture ne sont pas disponibles",
    )

    def test_no_forbidden_strings_in_all_touched_files(self):
        code = "\n".join(
            (PAYLOAD / n).read_text(encoding="utf-8")
            for n in (
                "openhtpc-core.py",
                "openhtpc-disc-view.py",
                "openhtpc-session-engine.py",
                "openhtpc-disc-sheet.py",
                "plugins/available/plugin.bluray/shadow.py",
            )
        )
        for phrase in self.FORBIDDEN:
            self.assertNotIn(phrase, code, f"Forbidden string found: {phrase!r}")


if __name__ == "__main__":
    unittest.main()
