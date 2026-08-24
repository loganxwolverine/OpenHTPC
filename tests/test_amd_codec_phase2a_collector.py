from __future__ import annotations

import pathlib
import subprocess
import importlib.util
import unittest

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


if __name__ == "__main__":
    unittest.main()
