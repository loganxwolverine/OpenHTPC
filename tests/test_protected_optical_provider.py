from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module


PROTECTED = load("protected_optical_provider", PAYLOAD / "openhtpc-protected-optical.py")
CORE = load("protected_optical_core", PAYLOAD / "openhtpc-core.py")


def finder(available: set[str]):
    return lambda name: f"lib{name}.so" if name in available else None


class ProtectedOpticalDetection(unittest.TestCase):
    def temporary(self) -> pathlib.Path:
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup); return pathlib.Path(raw.name)

    def detect(self, home: pathlib.Path, libraries: set[str], **kwargs):
        return PROTECTED.detect(home, environment=kwargs.pop("environment", {}),
                                finder=finder(libraries), loader=lambda _name: object(), **kwargs)

    def test_libaacs_absent_is_not_available(self):
        model = self.detect(self.temporary(), {"bluray"})
        self.assertEqual(model["dependencies"]["libaacs"]["status"], "NOT_AVAILABLE")
        self.assertEqual(model["status"], "NOT_AVAILABLE")

    def test_libaacs_present_and_loadable(self):
        model = self.detect(self.temporary(), {"bluray", "aacs"})
        self.assertEqual(model["dependencies"]["libaacs"]["status"], "AVAILABLE")

    def test_key_database_absent_is_not_configured(self):
        model = self.detect(self.temporary(), {"bluray", "aacs"})
        self.assertEqual(model["external_key_database"]["status"], "NOT_CONFIGURED")
        self.assertEqual(model["status"], "NOT_CONFIGURED")

    def test_key_database_regular_and_readable_is_detected(self):
        home = self.temporary(); path = home / ".config/aacs/KEYDB.cfg"
        path.parent.mkdir(parents=True); path.write_text("fixture-never-read", encoding="utf-8")
        model = self.detect(home, {"bluray", "aacs"})
        self.assertEqual(model["external_key_database"]["status"], "DETECTED")
        self.assertTrue(model["can_open_protected_optical_media"])

    def test_key_database_non_regular_is_rejected(self):
        home = self.temporary(); (home / ".config/aacs/KEYDB.cfg").mkdir(parents=True)
        model = self.detect(home, {"bluray", "aacs"})
        self.assertFalse(model["external_key_database"]["regular"])
        self.assertEqual(model["status"], "NOT_CONFIGURED")

    def test_key_database_regular_but_unreadable_is_not_configured(self):
        home = self.temporary(); path = home / ".config/aacs/KEYDB.cfg"
        path.parent.mkdir(parents=True); path.write_text("fixture", encoding="utf-8")
        model = self.detect(home, {"bluray", "aacs"}, readable=lambda _path, _mode: False)
        self.assertTrue(model["external_key_database"]["regular"])
        self.assertFalse(model["external_key_database"]["readable"])
        self.assertEqual(model["status"], "NOT_CONFIGURED")

    def test_custom_xdg_config_home_is_canonical(self):
        home = self.temporary(); xdg = self.temporary(); path = xdg / "aacs/KEYDB.cfg"
        path.parent.mkdir(); path.write_text("fixture", encoding="utf-8")
        model = self.detect(home, {"bluray", "aacs"}, environment={"XDG_CONFIG_HOME": str(xdg)})
        self.assertEqual(model["external_key_database"]["source"], "XDG_CONFIG_HOME")
        self.assertEqual(model["status"], "AVAILABLE")

    def test_home_config_fallback_is_used(self):
        home = self.temporary(); path = home / ".config/aacs/KEYDB.cfg"
        path.parent.mkdir(parents=True); path.write_text("fixture", encoding="utf-8")
        model = self.detect(home, {"bluray", "aacs"})
        self.assertEqual(model["external_key_database"]["source"], "HOME_CONFIG_FALLBACK")

    def test_libbdplus_is_independent_and_not_required(self):
        home = self.temporary(); path = home / ".config/aacs/KEYDB.cfg"
        path.parent.mkdir(parents=True); path.write_text("fixture", encoding="utf-8")
        model = self.detect(home, {"bluray", "aacs"})
        self.assertEqual(model["dependencies"]["libbdplus"]["status"], "NOT_AVAILABLE")
        self.assertEqual(model["status"], "AVAILABLE")

    def test_found_but_unloadable_library_is_not_available(self):
        def unloadable(_name): raise OSError("fixture")
        model = PROTECTED.detect(self.temporary(), environment={}, finder=finder({"bluray", "aacs"}), loader=unloadable)
        self.assertEqual(model["dependencies"]["libaacs"], {"status":"NOT_AVAILABLE", "detected":True, "loadable":False})

    def test_key_database_content_is_never_opened_or_parsed(self):
        home = self.temporary(); path = home / ".config/aacs/KEYDB.cfg"
        path.parent.mkdir(parents=True); path.write_text("sensitive-fixture", encoding="utf-8")
        before = (path.stat().st_mode, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        with mock.patch.object(pathlib.Path, "open", side_effect=AssertionError("KEYDB content access")), \
             mock.patch.object(pathlib.Path, "read_text", side_effect=AssertionError("KEYDB content access")), \
             mock.patch.object(pathlib.Path, "read_bytes", side_effect=AssertionError("KEYDB content access")):
            model = self.detect(home, {"bluray", "aacs"})
        after = (path.stat().st_mode, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(model["status"], "AVAILABLE")
        self.assertEqual(before, after)

    def test_generic_provider_contract_rejects_invalid_status(self):
        self.assertEqual(PROTECTED.status({"status":"INVALID"}), "BLOCKED")
        self.assertFalse(PROTECTED.available({"status":"NOT_CONFIGURED"}))


class ProtectedOpticalDoctor(unittest.TestCase):
    def test_optional_not_configured_remains_overall_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw); install = home / "install"; install.mkdir()
            (install / "version.json").write_text(json.dumps({"version":"test","build_id":"test","build_date":"test"}))
            attempt = home / ".local/state/openhtpc/protected-optical-last-attempt.json"; attempt.parent.mkdir(parents=True)
            attempt.write_text(json.dumps({"schema":1,"status":"OPEN_FAILED","reason":"DISC_OPEN_REFUSED"}))
            (attempt.parent / "optical-current.json").write_text(json.dumps({
                "canonical_state":"UHD_BLURAY_VIDEO", "protection":"PROTECTED",
                "protection_mechanisms":["AACS"], "classification_source":"LIBBLURAY",
            }))
            state = {
                "HARDWARE_PASSPORT_READY":True, "HARDWARE_PASSPORT_PROVENANCE":"CURRENT",
                "VIDEO_RUNTIME_READY":True, "AUDIO_RUNTIME_READY":True, "VIDEO_RUNTIME_PROVENANCE":"CURRENT",
                "FLEX_READY":True, "MEDIA_BROWSER_READY":True, "AUTOSTART_READY":True,
                "PLUGIN_REGISTRY_READY":True, "OPTICAL_STATE_INITIALIZED":False,
                "PLUGIN_REGISTRY":{"plugin_api":2,"errors":[],"plugins":[{"id":"plugin.example","name":"ExamplePlugin","state":"INCOMPATIBLE"}]},
                "OPTICAL_DRIVE_PRESENT":False, "DVD_READY":False, "TMDB_CONFIGURED":False,
                "plugins":[], "PROTECTED_OPTICAL_SUPPORT":{
                    "status":"NOT_CONFIGURED",
                    "dependencies":{"libbluray":{"status":"AVAILABLE"},"libaacs":{"status":"AVAILABLE"},"libbdplus":{"status":"NOT_AVAILABLE"}},
                    "external_key_database":{"status":"NOT_CONFIGURED"},
                },
            }
            lifecycle = {"ui_instances":0,"monitor_instances":0,"runtime_ownership":"PASS",
                         "appliance_state":"STOPPED","crash_loop_state":"PASS","recent_flex_crashes":0}
            with mock.patch.object(CORE, "capability_state", return_value=state), \
                 mock.patch.object(CORE, "_runtime_lifecycle", return_value=lifecycle), \
                 mock.patch.object(CORE, "graphical_runtime", return_value={"status":"NOT_RUNNING","session":"Wayland","desktop":"KDE","pid":""}), \
                 mock.patch.object(CORE, "_dvdcss_status", return_value="NOT_CONFIGURED"), \
                 mock.patch.object(CORE, "_plasma_suppression", return_value="INACTIVE"), \
                 mock.patch.object(CORE, "_plasma_shell_status", return_value="PASS"), \
                 mock.patch.object(CORE.os, "access", return_value=True), \
                 mock.patch.object(CORE.shutil, "which", return_value="/usr/bin/mpv"), \
                 mock.patch.object(CORE.ctypes.util, "find_library", return_value="libSDL2.so"):
                report = CORE.health_report(home, install)
            statuses = {item["label"]:item["status"] for item in report["checks"]}
            self.assertEqual(report["overall"], "READY")
            self.assertEqual(report["protected_optical_doctor_authority"], "PLUGIN_UNAVAILABLE")
            plugin_owned = {
                "Protected optical media", "libbluray", "libaacs", "libbdplus",
                "External key database", "Protected optical playback",
                "Last protected disc attempt", "Optical media family",
                "Optical exact type", "Optical protection", "Protection mechanism",
                "Classification source",
            }
            self.assertTrue(plugin_owned.isdisjoint(statuses))
            self.assertEqual(statuses["Canonical optical state"], "NOT_INITIALIZED")
            self.assertEqual(statuses["Optical Detection"], "NOT_INITIALIZED")
            self.assertEqual(statuses["DVD"], "UNAVAILABLE")
            optional = {item["label"]:item["status"] for item in report["optional"]}
            self.assertEqual(optional["Blu-ray"], "NOT_INSTALLED")
            self.assertEqual(optional["UHD"], "NOT_INSTALLED")
            self.assertEqual(optional["ExamplePlugin"], "INCOMPATIBLE")


class RuntimeNonRegression(unittest.TestCase):
    def test_intel_amd_nvidia_runtime_sources_match_rc2(self):
        expected = {
            "openhtpc-runtime-generator.py":"f40d24200b1a716c1d053d5403969ae1230f52e5a22c3cadb24edc233ddbe8c2",
            "openhtpc-gpu-policy.py":"3dda5810fede4b25e414029dceeb214d0a27b016575cbecbae20f960ca96407b",
            "openhtpc-builder.sh":"076576b513d3578d5961ca9aa5f8b6d1b2076daca10d72814ec16118858a70b8",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((PAYLOAD / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__": unittest.main()
