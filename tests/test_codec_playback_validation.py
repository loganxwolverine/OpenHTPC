from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/openhtpc-amd-codec-playback-validation.sh"
REPORTER = ROOT / "tools/openhtpc-codec-playback-report.py"
SPEC = importlib.util.spec_from_file_location("codec_report", REPORTER)
MODULE = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(MODULE)


class CodecPlaybackValidationTests(unittest.TestCase):
    def test_helper_syntax_and_explicit_source_policy(self):
        result = subprocess.run(["bash", "-n", str(HELPER)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('usage: $0 LABEL -- MPV_SOURCE_OR_OPTIONS...', source)
        self.assertNotIn("LIBVA_DRIVERS_PATH", source)

    def test_mpeg2_software_fallback_remains_pending_review(self):
        result = MODULE.summarize("MPEG2_DVD", "VO: [gpu-next] 720x576\n", {"streams": [{
            "codec_type": "video", "codec_name": "mpeg2video", "profile": "Main", "pix_fmt": "yuv420p"}]},
            0, "vaapi", "/dev/dri/renderD-test", True)
        self.assertEqual(result["decode"]["observed"], "software")
        self.assertTrue(result["decode"]["software_fallback"])
        self.assertEqual(result["playback"]["physical_qualification"], "PENDING_REVIEW")

    def test_hevc_main10_requires_observed_vaapi_and_10bit_source_evidence(self):
        log = "Using hardware decoding (vaapi).\nVO: [gpu-next] 3840x2160\nOPENHTPC_METRICS vo_drop=0 decoder_drop=0\n"
        result = MODULE.summarize("HEVC_MAIN10", log, {"streams": [{"codec_type": "video",
            "codec_name": "hevc", "profile": "Main 10", "pix_fmt": "yuv420p10le"}]},
            0, "vaapi", "/dev/dri/renderD-test", True)
        self.assertEqual(result["source"]["bit_depth"], 10)
        self.assertEqual(result["decode"]["observed"], "vaapi")
        self.assertEqual(result["playback"]["vo_dropped_frames"], 0)
        self.assertEqual(result["playback"]["physical_qualification"], "PENDING_REVIEW")


if __name__ == "__main__":
    unittest.main()
