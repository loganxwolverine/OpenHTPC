# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic tests for RC7 T8.5 Runtime Playback Observation and Qualification."""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
POLICY_PATH = PAYLOAD / "openhtpc-playback-policy.py"
SYSTEM_MODEL_PATH = PAYLOAD / "openhtpc-system-model.py"

spec_policy = importlib.util.spec_from_file_location("openhtpc_playback_policy", POLICY_PATH)
policy_mod = importlib.util.module_from_spec(spec_policy)
spec_policy.loader.exec_module(policy_mod)

spec_model = importlib.util.spec_from_file_location("openhtpc_system_model", SYSTEM_MODEL_PATH)
sys_model = importlib.util.module_from_spec(spec_model)
spec_model.loader.exec_module(sys_model)


SAMPLE_VULKAN_LOG = """\
[   0.251][v][vo/gpu-next/wayland] Obtained preferred fractional scale, 2.000000, from the compositor.
[   0.251][v][vo/gpu-next/libplacebo] Probing for vulkan devices:
[   0.270][v][vo/gpu-next/libplacebo] Spent 19.682 ms enumerating physical devices
[   0.270][v][vo/gpu-next/libplacebo]     GPU 0: Intel(R) Arc(tm) A310 Graphics (DG2) v1.4.354 (discrete)
[   0.270][v][vo/gpu-next/libplacebo]            uuid: 86:80:A6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo]     GPU 1: Intel(R) HD Graphics 530 (SKL GT2) v1.4.354 (integrated)
[   0.270][v][vo/gpu-next/libplacebo]            uuid: 86:80:12:19:06:00:00:00:00:02:00:00:00:00:00:00
[   0.270][d][vo/gpu-next/libplacebo]      -> excluding due to UUID mismatch
[   0.270][v][vo/gpu-next/libplacebo] Vulkan device properties:
[   0.270][v][vo/gpu-next/libplacebo]     Device Name: Intel(R) Arc(tm) A310 Graphics (DG2)
[   0.270][v][vo/gpu-next/libplacebo]     Device ID: 8086:56a6
[   0.270][v][vo/gpu-next/libplacebo]     Device UUID: 86:80:A6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo]     Driver version: 6801006
[   0.270][v][vo/gpu-next/libplacebo] Creating vulkan device with extensions:
[   0.270][v][vo/gpu-next/libplacebo] Spent 12.656 ms creating vulkan device
"""

SAMPLE_DECISION_ARC = {
    "gpu_render_binding": {
        "status": "RENDER_BOUND",
        "pci_address": "0000:03:00.0",
        "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
        "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
    }
}


class TestRc7PlaybackObservation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp_dir.name)
        (self.home / ".local/state/openhtpc").mkdir(parents=True, exist_ok=True)
        (self.home / ".config/openhtpc").mkdir(parents=True, exist_ok=True)

        display_patch = mock.patch.object(sys_model, "_current_display", return_value={})
        display_patch.start()
        self.addCleanup(display_patch.stop)

        self.gpu_runtime = mock.Mock()
        self.gpu_runtime.discover_gpus.return_value = []
        self.gpu_runtime.resolve_display_gpu.return_value = (None, "UNKNOWN")
        self.gpu_runtime.resolve_playback_gpu_binding.return_value = {"status": "AUTO_FALLBACK"}
        patcher = mock.patch.object(sys_model, "_load_gpu_runtime", return_value=self.gpu_runtime)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_vulkan_render_evidence_proven(self):
        """Case 1: Vulkan render evidence in MPV log proves render GPU."""
        log = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n"
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["render"]["status"], "PROVEN")
        self.assertEqual(obs["render"]["pci_address"], "0000:03:00.0")
        self.assertEqual(obs["render"]["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(obs["render"]["device_name"], "Intel(R) Arc(tm) A310 Graphics (DG2)")
        self.assertTrue(obs["media_opened"])
        self.assertEqual(obs["dispatch_status"], "COMPLETED")

        # Mismatched UUID must fail closed to NOT_PROVEN with no PCI address
        mismatched_decision = {
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:00:02.0",
                "vulkan_uuid": "86801219-0600-0000-0002-000000000000",
            }
        }
        obs_mismatch = policy_mod.parse_playback_observation(mismatched_decision, log, exit_code=0)
        self.assertEqual(obs_mismatch["render"]["status"], "NOT_PROVEN")
        self.assertIsNone(obs_mismatch["render"]["pci_address"])

    def test_02_hwdec_vaapi_active_observed(self):
        """Case 2: hwdec=vaapi active in MPV log yields backend OBSERVED."""
        log = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        decode = obs["decode"]
        self.assertEqual(decode["status"], "OBSERVED")
        self.assertEqual(decode["backend"], "vaapi")
        self.assertIs(decode["hardware_active"], True)
        self.assertFalse(decode["fallback"])
        self.assertIsNone(decode["fallback_reason"])

    def test_03_hwdec_nvdec_active_observed(self):
        """Case 3: hwdec=nvdec active in MPV log yields backend OBSERVED."""
        log = (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (nvdec).\n"
        )
        obs = policy_mod.parse_playback_observation({}, log, exit_code=0)
        decode = obs["decode"]
        self.assertEqual(decode["status"], "OBSERVED")
        self.assertEqual(decode["backend"], "nvdec")
        self.assertIs(decode["hardware_active"], True)
        self.assertFalse(decode["fallback"])
        self.assertIsNone(decode["fallback_reason"])

    def test_04_software_decode_hardware_active_false(self):
        """Case 4: software decode in MPV log yields hardware_active False."""
        log = (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.311][v][vd] Using software decoding.\n"
        )
        obs = policy_mod.parse_playback_observation({}, log, exit_code=0)
        decode = obs["decode"]
        self.assertEqual(decode["status"], "OBSERVED")
        self.assertEqual(decode["backend"], "software")
        self.assertIs(decode["hardware_active"], False)
        self.assertFalse(decode["fallback"])
        self.assertIsNone(decode["fallback_reason"])

    def test_05_hwdec_init_failure_then_software_fallback(self):
        """Case 5: hwdec initialization failure then software fallback is observed with reason."""
        # Scenario A: Device creation failed
        log_dev_fail = (
            "[   0.280][v][vd] Looking at hwdec mpeg2video-nvdec...\n"
            "[   0.281][v][vd] Could not create device.\n"
            "[   0.281][v][vd] Using software decoding.\n"
            "[   0.314][v][cplayer] Starting playback...\n"
        )
        obs_dev = policy_mod.parse_playback_observation({}, log_dev_fail, exit_code=0)
        decode_dev = obs_dev["decode"]
        self.assertEqual(decode_dev["status"], "OBSERVED")
        self.assertEqual(decode_dev["backend"], "software")
        self.assertIs(decode_dev["hardware_active"], False)
        self.assertTrue(decode_dev["fallback"])
        self.assertEqual(decode_dev["fallback_reason"], "DEVICE_CREATION_FAILED")

        # Scenario B: Codec not on whitelist
        log_whitelist = (
            "[   0.290][v][vd] Not trying to use hardware decoding: codec mpeg2video is not on whitelist.\n"
            "[   0.290][v][vd] Using software decoding.\n"
            "[   0.314][v][cplayer] Starting playback...\n"
        )
        obs_wl = policy_mod.parse_playback_observation({}, log_whitelist, exit_code=0)
        decode_wl = obs_wl["decode"]
        self.assertEqual(decode_wl["status"], "OBSERVED")
        self.assertEqual(decode_wl["backend"], "software")
        self.assertIs(decode_wl["hardware_active"], False)
        self.assertTrue(decode_wl["fallback"])
        self.assertEqual(decode_wl["fallback_reason"], "CODEC_NOT_WHITELISTED")

    def test_06_no_decode_evidence_unavailable(self):
        """Case 6: Missing decode lines yield decode status UNAVAILABLE / unknown."""
        log_empty = "[   0.001][v][cplayer] MPV launched but file not opened.\n"
        obs = policy_mod.parse_playback_observation({}, log_empty, exit_code=1)
        decode = obs["decode"]
        self.assertEqual(decode["status"], "UNAVAILABLE")
        self.assertIsNone(decode["backend"])
        self.assertIsNone(decode["hardware_active"])
        self.assertEqual(obs["dispatch_status"], "FAILED")
        self.assertFalse(obs["media_opened"])

    def test_07_render_proven_but_decode_gpu_unknown_physical_gpu_not_proven(self):
        """Case 7: Proven render GPU does NOT prove physical decode GPU."""
        log = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        # Render GPU is proven from Vulkan evidence
        self.assertEqual(obs["render"]["status"], "PROVEN")
        self.assertEqual(obs["render"]["pci_address"], "0000:03:00.0")
        # Physical decode GPU must remain NOT_PROVEN
        self.assertEqual(obs["decode"]["physical_gpu_binding"], "NOT_PROVEN")
        self.assertIsNone(obs["decode"]["physical_gpu_pci"])

    def test_08_consecutive_playback_replaces_stale_state(self):
        """Case 8: Consecutive playback atomically replaces prior observation."""
        log_a = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )
        disp_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        rec_a = policy_mod.record_playback_observation(self.home, SAMPLE_DECISION_ARC, log_a, exit_code=0, kind="local", dispatch_id=disp_a["dispatch_id"])
        state_a = policy_mod.read_playback_runtime(self.home)
        self.assertIsNotNone(state_a)
        self.assertEqual(state_a["decode"]["backend"], "vaapi")
        self.assertIs(state_a["decode"]["hardware_active"], True)

        log_b = (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.311][v][vd] Using software decoding.\n"
        )
        disp_b = policy_mod.record_playback_dispatch(self.home, {}, kind="local")
        rec_b = policy_mod.record_playback_observation(self.home, {}, log_b, exit_code=0, kind="local", dispatch_id=disp_b["dispatch_id"])
        state_b = policy_mod.read_playback_runtime(self.home)
        self.assertIsNotNone(state_b)
        self.assertEqual(state_b["decode"]["backend"], "software")
        self.assertIs(state_b["decode"]["hardware_active"], False)
        # No residue of Playback A
        self.assertNotEqual(state_b["decode"]["backend"], "vaapi")

    def test_09_failed_second_playback_clears_invalidates_previous_state(self):
        """Case 9: A failed second playback invalidates previous successful truth."""
        # Playback A succeeds
        log_a = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )
        disp_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        policy_mod.record_playback_observation(self.home, SAMPLE_DECISION_ARC, log_a, exit_code=0, kind="local", dispatch_id=disp_a["dispatch_id"])
        state_a = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(state_a["dispatch_status"], "COMPLETED")
        self.assertTrue(state_a["media_opened"])

        # Playback B starts dispatching: immediately resets previous observation
        disp_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        state_disp = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(state_disp["dispatch_status"], "DISPATCHED")
        self.assertFalse(state_disp["media_opened"])
        self.assertEqual(state_disp["decode"]["status"], "UNAVAILABLE")
        self.assertEqual(state_disp["render"]["status"], "NOT_PROVEN")

        # Playback B fails
        policy_mod.record_playback_failure(self.home, reason="LAUNCH_FAILED", exit_code=1, kind="local", dispatch_id=disp_b["dispatch_id"])
        state_failed = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(state_failed["dispatch_status"], "FAILED")
        self.assertFalse(state_failed["media_opened"])
        self.assertEqual(state_failed["decode"]["status"], "UNAVAILABLE")
        self.assertEqual(state_failed["render"]["status"], "NOT_PROVEN")

    def test_10_local_dvd_bluray_same_semantic_schema(self):
        """Case 10: Local, DVD, and Blu-ray dispatchers emit identical semantic schemas."""
        required_top_keys = {"schema", "timestamp", "kind", "dispatch_status", "media_opened", "exit_code", "render", "decode"}
        required_render_keys = {"status", "pci_address", "vulkan_uuid", "device_name"}
        required_decode_keys = {"status", "backend", "hardware_active", "fallback", "fallback_reason", "physical_gpu_binding", "physical_gpu_pci"}

        log = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )

        for kind in ("local", "dvd", "bluray"):
            disp = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind=kind)
            rec = policy_mod.record_playback_observation(self.home, SAMPLE_DECISION_ARC, log, exit_code=0, kind=kind, dispatch_id=disp["dispatch_id"])
            self.assertEqual(rec["kind"], kind)
            self.assertTrue(required_top_keys.issubset(set(rec.keys())))
            self.assertTrue(required_render_keys.issubset(set(rec["render"].keys())))
            self.assertTrue(required_decode_keys.issubset(set(rec["decode"].keys())))

    def test_11_system_model_playback_runtime_exposure(self):
        """Case 11: openhtpc-system-model exposes playback_runtime in build()."""
        # When no playback runtime exists
        model_empty = sys_model.build(self.home, PAYLOAD, {}, {})
        self.assertIn("playback_runtime", model_empty)
        self.assertIsNone(model_empty["playback_runtime"])

        # When playback runtime is recorded
        log = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        )
        disp = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        policy_mod.record_playback_observation(self.home, SAMPLE_DECISION_ARC, log, exit_code=0, kind="local", dispatch_id=disp["dispatch_id"])
        model_with_obs = sys_model.build(self.home, PAYLOAD, {}, {})
        self.assertIn("playback_runtime", model_with_obs)
        rt = model_with_obs["playback_runtime"]
        self.assertIsNotNone(rt)
        self.assertEqual(rt["render"]["status"], "PROVEN")
        self.assertEqual(rt["render"]["pci_address"], "0000:03:00.0")
        self.assertEqual(rt["decode"]["backend"], "vaapi")
        self.assertEqual(rt["decode"]["physical_gpu_binding"], "NOT_PROVEN")

    # -------------------------------------------------------------------------
    # Codex Adversarial Tests A through M
    # -------------------------------------------------------------------------

    def test_adversarial_a_arc_uuid_block_then_hd530_block_fails_closed(self):
        """Test A: Arc UUID block logged then HD530 block logged before device creation -> NOT_PROVEN for Arc."""
        log = """\
[   0.270][v][vo/gpu-next/libplacebo] Vulkan device properties:
[   0.270][v][vo/gpu-next/libplacebo]     Device Name: Intel(R) Arc(tm) A310 Graphics (DG2)
[   0.270][v][vo/gpu-next/libplacebo]     Device ID: 8086:56a6
[   0.270][v][vo/gpu-next/libplacebo]     Device UUID: 86:80:A6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo] Vulkan device properties:
[   0.270][v][vo/gpu-next/libplacebo]     Device Name: Intel(R) HD Graphics 530 (SKL GT2)
[   0.270][v][vo/gpu-next/libplacebo]     Device ID: 8086:1912
[   0.270][v][vo/gpu-next/libplacebo]     Device UUID: 86:80:12:19:06:00:00:00:00:02:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo] Creating vulkan device with extensions:
[   0.270][v][vo/gpu-next/libplacebo] Spent 12.656 ms creating vulkan device
[   0.314][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["render"]["status"], "NOT_PROVEN")
        self.assertIsNone(obs["render"]["pci_address"])

    def test_adversarial_b_creating_vulkan_device_without_completion_marker_not_proven(self):
        """Test B: 'Creating vulkan device' without completion marker -> NOT_PROVEN."""
        log = """\
[   0.270][v][vo/gpu-next/libplacebo] Vulkan device properties:
[   0.270][v][vo/gpu-next/libplacebo]     Device Name: Intel(R) Arc(tm) A310 Graphics (DG2)
[   0.270][v][vo/gpu-next/libplacebo]     Device ID: 8086:56a6
[   0.270][v][vo/gpu-next/libplacebo]     Device UUID: 86:80:A6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo] Creating vulkan device with extensions:
[   0.275][e][vo/gpu-next/libplacebo] Failed creating vulkan instance: VK_ERROR_INITIALIZATION_FAILED
[   0.314][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["render"]["status"], "NOT_PROVEN")
        self.assertIsNone(obs["render"]["pci_address"])

    def test_adversarial_c_other_component_lines_with_fake_strings_ignored(self):
        """Test C: [other] lines with fake Vulkan/decode strings -> ignored."""
        log = """\
[   0.100][v][cplayer] [vo/gpu-next/libplacebo] Vulkan device properties:
[   0.101][v][cplayer]     Device UUID: 86:80:A6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.102][v][cplayer] Spent 10 ms creating vulkan device
[   0.103][v][cplayer] Using hardware decoding (vaapi).
[   0.104][v][demux] Using software decoding.
[   0.105][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["render"]["status"], "NOT_PROVEN")
        self.assertIsNone(obs["render"]["pci_address"])
        self.assertEqual(obs["decode"]["status"], "UNAVAILABLE")
        self.assertIsNone(obs["decode"]["backend"])

    def test_adversarial_d_ao_failure_never_video_fallback_reason(self):
        """Test D: [ao] failure -> never video fallback reason."""
        log = """\
[   0.200][v][ao] Could not open audio device.
[   0.201][e][ao] Audio device creation failed.
[   0.202][v][ao] Could not create device.
[   0.250][v][vd] Using software decoding.
[   0.300][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["decode"]["status"], "OBSERVED")
        self.assertEqual(obs["decode"]["backend"], "software")
        self.assertIs(obs["decode"]["hardware_active"], False)
        self.assertFalse(obs["decode"]["fallback"])
        self.assertIsNone(obs["decode"]["fallback_reason"])

    def test_adversarial_e_hardware_to_failure_to_software_fallback_true(self):
        """Test E: hardware -> failure -> software => software fallback=true."""
        log = """\
[   0.250][i][vd] Using hardware decoding (vaapi).
[   0.260][e][vd] Failed to allocate texture: out of memory.
[   0.270][v][vd] Falling back to software decoding.
[   0.271][v][vd] Using software decoding.
[   0.300][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["decode"]["status"], "OBSERVED")
        self.assertEqual(obs["decode"]["backend"], "software")
        self.assertIs(obs["decode"]["hardware_active"], False)
        self.assertTrue(obs["decode"]["fallback"])
        self.assertEqual(obs["decode"]["fallback_reason"], "TEXTURE_ALLOCATION_FAILED")

    def test_adversarial_f_failure_to_software_to_hardware_fallback_false(self):
        """Test F: failure -> software -> hardware => hardware fallback=false."""
        log = """\
[   0.200][v][vd] Looking at hwdec nvdec...
[   0.201][e][vd] Could not create device.
[   0.202][v][vd] Using software decoding.
[   0.210][v][vd] Re-probing hwdec vaapi...
[   0.215][i][vd] Using hardware decoding (vaapi).
[   0.300][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["decode"]["status"], "OBSERVED")
        self.assertEqual(obs["decode"]["backend"], "vaapi")
        self.assertIs(obs["decode"]["hardware_active"], True)
        self.assertFalse(obs["decode"]["fallback"])
        self.assertIsNone(obs["decode"]["fallback_reason"])

    def test_adversarial_g_multiple_transitions_last_effective_transition_wins(self):
        """Test G: multiple hwdec reinitializations -> last effective transition wins."""
        log = """\
[   0.100][i][vd] Using hardware decoding (vaapi).
[   0.150][v][vd] Using software decoding.
[   0.200][i][vd] Using hardware decoding (vaapi).
[   0.250][v][vd] Falling back to software decoding.
[   0.251][v][vd] Using software decoding.
[   0.300][v][cplayer] Starting playback...
"""
        obs = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log, exit_code=0)
        self.assertEqual(obs["decode"]["status"], "OBSERVED")
        self.assertEqual(obs["decode"]["backend"], "software")
        self.assertIs(obs["decode"]["hardware_active"], False)
        self.assertTrue(obs["decode"]["fallback"])

    def test_adversarial_h_concurrent_dispatch_stale_completion_ignored(self):
        """Test H: A dispatch, B dispatch, A completion => B survives (STALE_DISPATCH_IGNORED)."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_a = rec_a["dispatch_id"]
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_b = rec_b["dispatch_id"]
        self.assertNotEqual(id_a, id_b)

        # Dispatch A completes late
        res_a = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, SAMPLE_VULKAN_LOG, exit_code=0, kind="local", dispatch_id=id_a
        )
        self.assertEqual(res_a["status"], "STALE_DISPATCH_IGNORED")
        self.assertEqual(res_a["dispatch_id"], id_a)
        self.assertEqual(res_a["current_dispatch_id"], id_b)

        current = policy_mod.read_playback_runtime(self.home)
        self.assertIsNotNone(current)
        self.assertEqual(current["dispatch_id"], id_b)
        self.assertEqual(current["dispatch_status"], "DISPATCHED")

    def test_adversarial_i_concurrent_dispatch_newer_completion_survives_late_completion(self):
        """Test I: A dispatch, B dispatch, B completion, late A completion => B survives."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_a = rec_a["dispatch_id"]
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_b = rec_b["dispatch_id"]

        log_b = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        obs_b = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, log_b, exit_code=0, kind="local", dispatch_id=id_b
        )
        self.assertEqual(obs_b["dispatch_id"], id_b)
        self.assertEqual(obs_b["dispatch_status"], "COMPLETED")

        # Late A completion
        log_a = "[   0.314][v][cplayer] Starting playback...\n[   0.311][v][vd] Using software decoding.\n"
        res_a = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, log_a, exit_code=0, kind="local", dispatch_id=id_a
        )
        self.assertEqual(res_a["status"], "STALE_DISPATCH_IGNORED")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertIsNotNone(current)
        self.assertEqual(current["dispatch_id"], id_b)
        self.assertEqual(current["dispatch_status"], "COMPLETED")
        self.assertEqual(current["decode"]["backend"], "vaapi")

    def test_adversarial_j_successful_dvd_playback_not_overwritten_by_dispatch_refused(self):
        """Test J: successful DVD playback observation is not overwritten by DISPATCH_REFUSED."""
        disp = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="dvd")
        disp_id = disp["dispatch_id"]
        log_dvd = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n[   0.322][i][vd] Using hardware decoding (vaapi).\n"
        obs = policy_mod.record_playback_observation(self.home, SAMPLE_DECISION_ARC, log_dvd, exit_code=0, kind="dvd", dispatch_id=disp_id)
        self.assertEqual(obs["dispatch_status"], "COMPLETED")

        # Simulate stale dispatch failure attempt without dispatch_id or with mismatched dispatch_id
        fail_res = policy_mod.record_playback_failure(self.home, reason="DISPATCH_REFUSED", kind="dvd", dispatch_id="stale-dispatch-id")
        self.assertEqual(fail_res["status"], "STALE_DISPATCH_IGNORED")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(current["dispatch_id"], disp_id)
        self.assertEqual(current["dispatch_status"], "COMPLETED")

    def test_adversarial_k_normal_dvd_user_stop_not_automatically_failure(self):
        """Test K: normal DVD user stop is not automatically failure."""
        log_opened = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n"
        obs_stopped = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log_opened, exit_code=0)
        self.assertEqual(obs_stopped["dispatch_status"], "COMPLETED")
        self.assertTrue(obs_stopped["media_opened"])
        self.assertEqual(obs_stopped["observation_scope"], "LAST_COMPLETED_PLAYBACK")

        # In contrast, exit before opening media is classified as FAILED
        log_not_opened = SAMPLE_VULKAN_LOG
        obs_not_opened = policy_mod.parse_playback_observation(SAMPLE_DECISION_ARC, log_not_opened, exit_code=0)
        self.assertEqual(obs_not_opened["dispatch_status"], "FAILED")
        self.assertFalse(obs_not_opened["media_opened"])
        self.assertEqual(obs_not_opened["failure_reason"], "MEDIA_NOT_OPENED")

    def test_adversarial_l_malformed_state_rejected_by_read_playback_runtime(self):
        """Test L: malformed state like decode='corrupt' is rejected safely by read_playback_runtime()."""
        rt_file = self.home / ".local/state/openhtpc/playback-runtime.json"

        # Case 1: decode is a string instead of dict
        rt_file.write_text(json.dumps({"schema": 1, "dispatch_id": "test-123", "dispatch_status": "COMPLETED", "render": {"status": "PROVEN"}, "decode": "corrupt"}), encoding="utf-8")
        self.assertIsNone(policy_mod.read_playback_runtime(self.home))

        # Case 2: schema != 1
        rt_file.write_text(json.dumps({"schema": 2, "dispatch_id": "test-123", "dispatch_status": "COMPLETED", "render": {"status": "PROVEN"}, "decode": {}}), encoding="utf-8")
        self.assertIsNone(policy_mod.read_playback_runtime(self.home))

        # Case 3: invalid enum in decode status
        rt_file.write_text(json.dumps({
            "schema": 1,
            "dispatch_id": "test-123",
            "dispatch_status": "COMPLETED",
            "render": {"status": "PROVEN", "pci_address": None, "vulkan_uuid": None, "device_name": None},
            "decode": {"status": "INVALID_ENUM", "backend": None, "hardware_active": None, "fallback": False, "fallback_reason": None, "physical_gpu_binding": "NOT_PROVEN", "physical_gpu_pci": None}
        }), encoding="utf-8")
        self.assertIsNone(policy_mod.read_playback_runtime(self.home))

        # Case 4: completely corrupt JSON
        rt_file.write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(policy_mod.read_playback_runtime(self.home))

    def test_adversarial_m_free_marker_cannot_produce_proven_physical_gpu(self):
        """Test M: free marker DECODE_PHYSICAL_GPU_PROVEN cannot produce PROVEN physical GPU."""
        log = SAMPLE_VULKAN_LOG + (
            "[   0.314][v][cplayer] Starting playback...\n"
            "[   0.322][i][vd] Using hardware decoding (vaapi).\n"
            "[   0.323][i][vd] DECODE_PHYSICAL_GPU_PROVEN pci=0000:03:00.0\n"
        )
        fake_decision = {
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
            },
            "decode_physical_gpu": "PROVEN",
            "physical_gpu_pci": "0000:03:00.0",
        }
        obs = policy_mod.parse_playback_observation(fake_decision, log, exit_code=0)
        self.assertEqual(obs["decode"]["physical_gpu_binding"], "NOT_PROVEN")
        self.assertIsNone(obs["decode"]["physical_gpu_pci"])

    # -------------------------------------------------------------------------
    # Deterministic Race Tests A through E
    # -------------------------------------------------------------------------

    def test_race_a_serialization_and_lock_mutual_exclusion(self):
        """Race Test A: Lock mutual exclusion and serialized transactions prevent stale overwrite."""
        # 1. Lock mutual exclusion: While lock is held, non-blocking lock attempt raises BlockingIOError
        lock_file = self.home / policy_mod.PLAYBACK_RUNTIME_LOCK
        with policy_mod.playback_runtime_lock(self.home):
            fd = os.open(str(lock_file), os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)

        # 2. Transaction serialization: A dispatches, B dispatches before A completes -> A rejected, B survives
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_a = rec_a["dispatch_id"]
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        id_b = rec_b["dispatch_id"]

        res_a = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, SAMPLE_VULKAN_LOG, exit_code=0, kind="local", dispatch_id=id_a
        )
        self.assertEqual(res_a["status"], "STALE_DISPATCH_IGNORED")
        self.assertEqual(res_a["current_dispatch_id"], id_b)

        current = policy_mod.read_playback_runtime(self.home)
        self.assertIsNotNone(current)
        self.assertEqual(current["dispatch_id"], id_b)
        self.assertEqual(current["dispatch_status"], "DISPATCHED")

    def test_race_b_dispatch_a_dispatch_b_failure_a_b_survives(self):
        """Race Test B: A dispatch, B dispatch, failure(A) => B survives."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")

        res_fail_a = policy_mod.record_playback_failure(
            self.home, reason="LAUNCH_FAILED", kind="local", dispatch_id=rec_a["dispatch_id"]
        )
        self.assertEqual(res_fail_a["status"], "STALE_DISPATCH_IGNORED")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(current["dispatch_id"], rec_b["dispatch_id"])
        self.assertEqual(current["dispatch_status"], "DISPATCHED")

    def test_race_c_failure_without_dispatch_id_rejected_b_survives(self):
        """Race Test C: A dispatch, B dispatch, failure() with NO dispatch_id => rejected, B survives."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")

        # None dispatch_id
        res_none = policy_mod.record_playback_failure(self.home, reason="LAUNCH_FAILED", kind="local", dispatch_id=None)
        self.assertEqual(res_none["status"], "MISSING_DISPATCH_ID")

        # Empty string dispatch_id
        res_empty = policy_mod.record_playback_failure(self.home, reason="LAUNCH_FAILED", kind="local", dispatch_id="   ")
        self.assertEqual(res_empty["status"], "MISSING_DISPATCH_ID")

        # Observation without dispatch_id
        res_obs = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, SAMPLE_VULKAN_LOG, exit_code=0, kind="local", dispatch_id=None
        )
        self.assertEqual(res_obs["status"], "MISSING_DISPATCH_ID")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(current["dispatch_id"], rec_b["dispatch_id"])
        self.assertEqual(current["dispatch_status"], "DISPATCHED")

    def test_race_d_dispatch_a_dispatch_b_completion_b_late_completion_a_b_survives(self):
        """Race Test D: A dispatch, B dispatch, B completion, late A completion => B survives."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")

        log_complete = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n"
        obs_b = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, log_complete, exit_code=0, kind="local", dispatch_id=rec_b["dispatch_id"]
        )
        self.assertEqual(obs_b["dispatch_status"], "COMPLETED")

        late_obs_a = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, log_complete, exit_code=0, kind="local", dispatch_id=rec_a["dispatch_id"]
        )
        self.assertEqual(late_obs_a["status"], "STALE_DISPATCH_IGNORED")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(current["dispatch_id"], rec_b["dispatch_id"])
        self.assertEqual(current["dispatch_status"], "COMPLETED")

    def test_race_e_dispatch_a_dispatch_b_completion_b_late_failure_a_b_survives(self):
        """Race Test E: A dispatch, B dispatch, B completion, late A failure => B survives."""
        rec_a = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")
        rec_b = policy_mod.record_playback_dispatch(self.home, SAMPLE_DECISION_ARC, kind="local")

        log_complete = SAMPLE_VULKAN_LOG + "[   0.314][v][cplayer] Starting playback...\n"
        obs_b = policy_mod.record_playback_observation(
            self.home, SAMPLE_DECISION_ARC, log_complete, exit_code=0, kind="local", dispatch_id=rec_b["dispatch_id"]
        )
        self.assertEqual(obs_b["dispatch_status"], "COMPLETED")

        late_fail_a = policy_mod.record_playback_failure(
            self.home, reason="LAUNCH_FAILED", kind="local", dispatch_id=rec_a["dispatch_id"]
        )
        self.assertEqual(late_fail_a["status"], "STALE_DISPATCH_IGNORED")

        current = policy_mod.read_playback_runtime(self.home)
        self.assertEqual(current["dispatch_id"], rec_b["dispatch_id"])
        self.assertEqual(current["dispatch_status"], "COMPLETED")

    # -------------------------------------------------------------------------
    # Schema Type Safety and Malformed State Tests
    # -------------------------------------------------------------------------

    def test_malformed_state_type_safety_never_crashes(self):
        """Schema type safety: unhashable lists, empty dicts, and wrong scalars fail closed safely."""
        rt_file = self.home / policy_mod.PLAYBACK_RUNTIME_FILE

        corruptions = [
            [],  # root is a list
            "not a dict",
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": []},  # unhashable list
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "render": {"status": []}},  # unhashable list
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "decode": {"status": []}},  # unhashable list
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "render": {}},  # empty render
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "decode": {}},  # empty decode
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "media_opened": "true"},  # wrong scalar bool
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "media_opened": True, "exit_code": "0"},  # wrong scalar int
            {"schema": 1, "dispatch_id": "d1", "dispatch_status": "COMPLETED", "media_opened": True, "render": {"status": "PROVEN"}, "decode": {"status": "OBSERVED", "fallback": 1}},  # wrong scalar bool
            {"schema": "1", "dispatch_id": "d1"},  # wrong schema type
            {"schema": 1, "dispatch_id": []},  # list dispatch_id
        ]

        for payload in corruptions:
            rt_file.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(policy_mod.read_playback_runtime(self.home), f"Failed to reject: {payload}")

            # System model must not crash on malformed state
            model = sys_model.build(self.home, PAYLOAD, {}, {})
            self.assertIsNone(model.get("playback_runtime"))


if __name__ == "__main__":
    unittest.main()
