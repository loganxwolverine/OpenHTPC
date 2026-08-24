from __future__ import annotations

import pathlib
import subprocess
import importlib.util
import json
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "tools/openhtpc-amd-codec-forensic.sh"
CAPABILITIES = ROOT / "payload/openhtpc-capabilities.py"


def load_capabilities():
    spec = importlib.util.spec_from_file_location("openhtpc_capabilities", CAPABILITIES)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AmdCodecPhase2ACollector(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(COLLECTOR)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_collector_is_explicitly_read_only(self):
        source = COLLECTOR.read_text(encoding="utf-8")
        forbidden = ("sudo ", " dnf install", " dnf5 install", "rpm-ostree", "kscreen-doctor",
                     "openhtpc start", "openhtpc update", "chmod ", "chown ", "setfacl ")
        for marker in forbidden:
            self.assertNotIn(marker, source)
        self.assertIn("configuration_mutations=NONE", source)
        self.assertIn("media_playback=NO", source)

    def test_passport_render_node_is_used_without_model_hardcoding(self):
        source = COLLECTOR.read_text(encoding="utf-8")
        self.assertIn('(\"video_backend\", \"render_node\")', source)
        self.assertIn('vainfo --display drm --device "$render_node"', source)
        for marker in ("Vega", "Picasso", "Raven", "Ryzen", "1002:15d8", "renderD128"):
            self.assertNotIn(marker, source)

    def test_required_forensic_sections_are_present(self):
        source = COLLECTOR.read_text(encoding="utf-8")
        for heading in ("GPU AND DRM", "INSTALLED MEDIA PACKAGES AND PROVENANCE", "LIBVA AND VAAPI",
                        "FFMPEG", "MPV", "OPENHTPC HARDWARE PASSPORT", "OPENHTPC PURE RUNTIME"):
            self.assertIn(heading, source)

    def test_existing_vaapi_parser_accepts_libva_vld_syntax(self):
        capabilities = load_capabilities()
        sample = """vainfo: Driver version: Mesa Gallium driver 26.1.7 for AMD Radeon
    VAProfileMPEG2Main              : VAEntrypointVLD
    VAProfileH264High               : VAEntrypointVLD
    VAProfileH264High               : VAEntrypointEncSlice
    VAProfileHEVCMain               : VAEntrypointVLD
    VAProfileHEVCMain10             : VAEntrypointVLD
    VAProfileVP9Profile0            : VAEntrypointVLD
"""
        driver, codecs = capabilities.parse_vaapi(sample)
        self.assertIn("Mesa Gallium", driver)
        for codec in ("mpeg2", "h264_8bit", "hevc_main", "hevc_main10", "vp9_profile0"):
            self.assertTrue(codecs[codec], codec)

    def test_existing_vaapi_parser_rejects_encode_only_profiles(self):
        capabilities = load_capabilities()
        sample = """VAProfileH264High : VAEntrypointEncSlice
VAProfileHEVCMain : VAEntrypointEncSlice
VAProfileHEVCMain10 : VAEntrypointEncSliceLP
"""
        _, codecs = capabilities.parse_vaapi(sample)
        self.assertFalse(codecs["h264_8bit"])
        self.assertFalse(codecs["hevc_main"])
        self.assertFalse(codecs["hevc_main10"])


class CanonicalCapabilityRefreshConsistency(unittest.TestCase):
    CURRENT = {"mpeg2": False, "h264": True, "hevc": True, "hevc_main10": True, "vp9": True, "av1": False}
    STALE = {"mpeg2": True, "h264": False, "hevc": False, "hevc_main10": False, "vp9": True, "av1": False}

    def setUp(self):
        self.capabilities = load_capabilities()

    def snapshot(self, observed=None):
        observed = observed or self.CURRENT
        canonical = {"mpeg2": observed["mpeg2"], "h264_8bit": observed["h264"],
                     "hevc_main": observed["hevc"], "hevc_main10": observed["hevc_main10"],
                     "vp9_profile0": observed["vp9"], "vp9_10bit": observed["vp9"],
                     "av1_main": observed["av1"]}
        codecs = {key: {"hardware_decode": {"status": "SUPPORTED" if value else "UNSUPPORTED"}}
                  for key, value in canonical.items()}
        return {"schema": self.capabilities.SCHEMA, "probe_version": "fixture", "generated_at": "2026-08-24T15:00:00+00:00",
                "hardware_fingerprint": "hardware", "runtime_fingerprint": "runtime", "hardware": {},
                "graphics": {"devices": []}, "display": {"outputs": []}, "video_decode": {"codecs": codecs},
                "audio": {}, "optical": {}, "media": {}, "video_processing": {}, "validation": {}, "confidence": {}}

    def physical_dev3_profile(self):
        return {"media_stack": {"observed_capabilities": {"vaapi_decode": self.CURRENT.copy()}},
                "gpu_topology": {"display_gpu": {"identity": "display", "vaapi_decode": self.STALE.copy()},
                                 "processing_gpu": {"identity": "processing", "vaapi_decode": self.STALE.copy()},
                                 "gpus": [{"pci_slot": "fixture", "vaapi_decode": self.STALE.copy()}]},
                "runtime": {"status": "ready", "sentinel": "unchanged"}}

    def run_refresh(self, profile, snapshot=None):
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup)
        home = pathlib.Path(raw.name); config = home / ".config/openhtpc"; config.mkdir(parents=True)
        path = config / "profile.json"; path.write_text(json.dumps(profile), encoding="utf-8")
        with mock.patch.object(self.capabilities, "generate", return_value=snapshot or self.snapshot()):
            value = self.capabilities.refresh(home, home / "install")
        return home, path, json.loads(path.read_text(encoding="utf-8")), value

    def test_canonical_refresh_reproduces_and_closes_physical_dev3_contradiction(self):
        _, _, profile, _ = self.run_refresh(self.physical_dev3_profile())
        current = profile["media_stack"]["observed_capabilities"]["vaapi_decode"]
        self.assertEqual(current, self.CURRENT)
        self.assertEqual(profile["gpu_topology"]["display_gpu"]["vaapi_decode"], current)
        self.assertEqual(profile["gpu_topology"]["processing_gpu"]["vaapi_decode"], current)
        self.assertEqual(profile["gpu_topology"]["gpus"][0]["vaapi_decode"], current)

    def test_gpu_identity_and_runtime_are_unchanged(self):
        original = self.physical_dev3_profile()
        _, _, profile, _ = self.run_refresh(original)
        self.assertEqual(profile["gpu_topology"]["display_gpu"]["identity"], "display")
        self.assertEqual(profile["gpu_topology"]["processing_gpu"]["identity"], "processing")
        self.assertEqual(profile["gpu_topology"]["gpus"][0]["pci_slot"], "fixture")
        self.assertEqual(profile["runtime"], {"status": "ready", "sentinel": "unchanged"})

    def test_real_transition_is_recorded_once_and_second_refresh_is_idempotent(self):
        initial = self.physical_dev3_profile()
        initial["media_stack"]["observed_capabilities"]["vaapi_decode"] = self.STALE.copy()
        home, path, first, value = self.run_refresh(initial)
        history = first["media_stack"]["capability_change_history"]
        self.assertEqual(len(history), 1)
        self.assertIn("LOSS", {item["change"] for item in history[0]["changes"]})
        self.assertIn("GAIN", {item["change"] for item in history[0]["changes"]})
        self.assertTrue(value["confidence"]["capability_changes"])
        with mock.patch.object(self.capabilities, "generate", return_value=self.snapshot()):
            second_value = self.capabilities.refresh(home, home / "install")
        second = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(second["media_stack"]["capability_change_history"], history)
        self.assertEqual(second_value["confidence"]["capability_changes"], [])

    def test_failed_probe_preserves_previous_profile(self):
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup)
        home = pathlib.Path(raw.name); config = home / ".config/openhtpc"; config.mkdir(parents=True)
        path = config / "profile.json"; before = json.dumps(self.physical_dev3_profile(), sort_keys=True)
        path.write_text(before, encoding="utf-8")
        with mock.patch.object(self.capabilities, "generate", side_effect=RuntimeError("probe failed")):
            with self.assertRaises(RuntimeError): self.capabilities.refresh(home, home / "install")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_incomplete_codec_observation_preserves_previous_profile_and_snapshot(self):
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup)
        home = pathlib.Path(raw.name); config = home / ".config/openhtpc"; config.mkdir(parents=True)
        path = config / "profile.json"; before = json.dumps(self.physical_dev3_profile(), sort_keys=True)
        path.write_text(before, encoding="utf-8")
        snapshot_path = self.capabilities.snapshot_path(home); snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text("previous snapshot\n", encoding="utf-8")
        incomplete = self.snapshot()
        incomplete["video_decode"]["codecs"]["h264_8bit"]["hardware_decode"]["status"] = "UNKNOWN"
        with mock.patch.object(self.capabilities, "generate", return_value=incomplete):
            with self.assertRaisesRegex(ValueError, "CAPABILITY_CODEC_OBSERVATION_INCOMPLETE"):
                self.capabilities.refresh(home, home / "install")
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual(snapshot_path.read_text(encoding="utf-8"), "previous snapshot\n")

    def test_staging_failure_writes_neither_snapshot_nor_profile(self):
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup)
        home = pathlib.Path(raw.name); config = home / ".config/openhtpc"; config.mkdir(parents=True)
        profile_path = config / "profile.json"; before_profile = json.dumps(self.physical_dev3_profile(), sort_keys=True)
        profile_path.write_text(before_profile, encoding="utf-8")
        snapshot_path = self.capabilities.snapshot_path(home); snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text("previous snapshot\n", encoding="utf-8")
        original_stage = self.capabilities.stage_json; calls = 0
        def fail_second(path, value, mode):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError("profile staging failed")
            return original_stage(path, value, mode)
        with mock.patch.object(self.capabilities, "generate", return_value=self.snapshot()), \
             mock.patch.object(self.capabilities, "stage_json", side_effect=fail_second):
            with self.assertRaises(OSError): self.capabilities.refresh(home, home / "install")
        self.assertEqual(profile_path.read_text(encoding="utf-8"), before_profile)
        self.assertEqual(snapshot_path.read_text(encoding="utf-8"), "previous snapshot\n")


if __name__ == "__main__":
    unittest.main()
