from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/openhtpc-codec-capability-audit.py"
SPEC = importlib.util.spec_from_file_location("codec_audit", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def profile(media, display=None, processing=None):
    result = {"media_stack": {"observed_capabilities": {"vaapi_decode": media}}}
    result["gpu_topology"] = {
        "display_gpu": {"vaapi_decode": display if display is not None else media},
        "processing_gpu": {"vaapi_decode": processing if processing is not None else media},
    }
    return result


PRE = {"mpeg2": True, "h264": False, "hevc": False, "hevc_main10": False, "vp9": True, "av1": False}
POST = {"mpeg2": False, "h264": True, "hevc": True, "hevc_main10": True, "vp9": True, "av1": False}


class CodecCapabilityAuditTests(unittest.TestCase):
    def test_pre_remediation_consistent(self):
        self.assertEqual(MODULE.consistency(profile(PRE))["status"], "PASS")

    def test_post_remediation_stale_topology_is_contradiction(self):
        self.assertEqual(MODULE.consistency(profile(POST, PRE, PRE))["status"], "CONTRADICTION")

    def test_second_identical_refresh_is_idempotent(self):
        first = MODULE.consistency(profile(POST))
        second = MODULE.consistency(profile(POST))
        self.assertEqual(first, second)
        self.assertEqual(second["status"], "PASS")

    def test_failed_remediation_leaves_consistent_previous_observation(self):
        self.assertEqual(MODULE.consistency(profile(PRE))["status"], "PASS")
        self.assertEqual(MODULE.transition(PRE, PRE)["classification"], "NO_CHANGE")

    def test_noop_already_installed_is_no_change(self):
        self.assertEqual(MODULE.transition(POST, POST)["classification"], "NO_CHANGE")

    def test_mpeg2_loss_is_never_classified_as_universal_improvement(self):
        result = MODULE.transition(PRE, POST)
        self.assertEqual(result["classification"], "CAPABILITY_REGRESSION")
        self.assertEqual(result["lost"], ["mpeg2"])
        self.assertEqual(result["gained"], ["h264", "hevc", "hevc_main10"])


if __name__ == "__main__":
    unittest.main()
