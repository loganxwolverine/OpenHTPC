from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile
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

    def test_mpeg2_hardware_absence_does_not_fabricate_playback_validation(self):
        value = profile(POST)
        value["playback_validation"] = {"last_test": {"video": {"status": "pending"}}}
        observed = MODULE.codec_views(value)["media_stack.observed_capabilities.vaapi_decode"]
        self.assertFalse(observed["mpeg2"])
        self.assertEqual(value["playback_validation"]["last_test"]["video"]["status"], "pending")

    def test_multi_gpu_machine_union_allows_distinct_per_gpu_truth(self):
        intel = {"mpeg2": True, "h264": True, "hevc": True, "hevc_main10": True, "vp9": True, "av1": False}
        amd = {"mpeg2": True, "h264": False, "hevc": False, "hevc_main10": False, "vp9": True, "av1": False}
        value = {
            "media_stack": {"observed_capabilities": {"vaapi_decode": intel}},
            "detected": {"gpu_details": [
                {"pci_slot": "0000:00:02.0", "vaapi_decode": intel},
                {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
            ]},
            "gpu_topology": {
                "display_gpu": {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
                "processing_gpu": {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
                "gpus": [
                    {"pci_slot": "0000:00:02.0", "vaapi_decode": intel},
                    {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
                ],
            },
        }
        result = MODULE.consistency(value)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["contradictions"], [])

    def test_multi_gpu_role_must_match_its_exact_pci_entry(self):
        intel = {"mpeg2": True, "h264": True, "hevc": True, "hevc_main10": True, "vp9": True, "av1": False}
        amd = {"mpeg2": True, "h264": False, "hevc": False, "hevc_main10": False, "vp9": True, "av1": False}
        value = {
            "media_stack": {"observed_capabilities": {"vaapi_decode": intel}},
            "detected": {"gpu_details": [
                {"pci_slot": "0000:00:02.0", "vaapi_decode": intel},
                {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
            ]},
            "gpu_topology": {
                "display_gpu": {"pci_slot": "0000:03:00.0", "vaapi_decode": intel},
                "processing_gpu": {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
                "gpus": [
                    {"pci_slot": "0000:00:02.0", "vaapi_decode": intel},
                    {"pci_slot": "0000:03:00.0", "vaapi_decode": amd},
                ],
            },
        }
        result = MODULE.consistency(value)
        self.assertEqual(result["status"], "CONTRADICTION")
        self.assertIn("display_gpu", result["contradictions"])

    def test_boolean_cli_reports_consistent_true(self):
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "profile.json"
            path.write_text(json.dumps(profile(POST)), encoding="utf-8")
            result = subprocess.run(["python3", str(PATH), str(path), "--boolean"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "CONSISTENT = True")


if __name__ == "__main__":
    unittest.main()
