#!/usr/bin/env python3
"""Tests for PipeWire HDMI HD bitstream passthrough preparation and diagnostics."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load_backend():
    loader = importlib.machinery.SourceFileLoader("rc4_backend", str(PAYLOAD / "openhtpc-protected-optical-backend.py"))
    spec = importlib.util.spec_from_loader("rc4_backend", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BACKEND = load_backend()


def make_inspect_output(
    sink_id: int = 66,
    node_name: str = "alsa_output.pci-0000_04_00.0.hdmi-surround71",
    node_desc: str = "DG2 Audio Controller Digital Surround 7.1 (HDMI)",
    profile_name: str = "hdmi-surround71",
    media_class: str = "Audio/Sink",
    codecs_str: str = '[ "PCM", "DTS", "AC3" ]',
) -> str:
    return f"""id {sink_id}, type PipeWire:Interface:Node
    alsa.card = "1"
    alsa.card_name = "HDA Intel PCH"
    api.alsa.path = "hdmi:1"
    audio.channels = "8"
    device.profile.name = "{profile_name}"
    device.profile.description = "Digital Surround 7.1 (HDMI)"
    iec958.codecs = "{codecs_str}"
    media.class = "{media_class}"
    node.name = "{node_name}"
    node.description = "{node_desc}"
    node.nick = "DENON-AVR"
"""


class PipeWireBitstreamPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.runtime = self.home / "runtime.conf"
        self.runtime.write_text("vo=null\n")
        (self.home / ".config/openhtpc/runtime").mkdir(parents=True)
        (self.home / ".local/state/openhtpc").mkdir(parents=True)
        (self.home / ".config/openhtpc/profile.json").write_text(
            json.dumps({"runtime": {"status": "ready"}, "runtime_profiles": {"profiles": {"PURE": {"generation_status": "generated", "config_path": str(self.runtime)}}}})
        )

    def test_scenario_a_bitstream_hdmi_incomplete_applies_and_verifies_codecs(self):
        """A. Initial [PCM, DTS, AC3] -> pw-cli adds EAC3 TrueHD DTS-HD, verifies final state."""
        state = {"inspect_calls": 0, "pw_cli_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                state["inspect_calls"] += 1
                codecs = '[ "PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD" ]' if state["pw_cli_called"] else '[ "PCM", "DTS", "AC3" ]'
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str=codecs), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli":
                state["pw_cli_called"] = True
                self.assertEqual(cmd[1:4], ["s", "66", "Props"])
                self.assertIn("PCM DTS AC3 EAC3 TrueHD DTS-HD", cmd[4])
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(diag["audio_sink_id"], 66)
        self.assertTrue(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_codecs_before"], ["PCM", "DTS", "AC3"])
        self.assertEqual(diag["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "CODECS_APPLIED")
        self.assertEqual(diag["iec958_prepare_method"], "pw-cli")
        self.assertTrue(state["pw_cli_called"])

    def test_scenario_b_bitstream_hdmi_already_complete_is_idempotent(self):
        """B. Initial [PCM, DTS, AC3, EAC3, TrueHD, DTS-HD] -> idempotent, no pw-cli mutation."""
        state = {"pw_cli_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD" ]'), "stderr": ""})()
            if "pw-cli" in cmd[0]:
                state["pw_cli_called"] = True
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(diag["audio_sink_id"], 66)
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_SATISFIED")
        self.assertFalse(state["pw_cli_called"])

    def test_scenario_c_pcm_mode_does_not_mutate_pipewire(self):
        """C. PCM mode does not attempt mutation and preserves PCM defaults."""
        state = {"pw_cli_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if "pw-cli" in cmd[0]:
                state["pw_cli_called"] = True
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "PCM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "PCM_MODE")
        self.assertEqual(diag["iec958_codecs_requested"], [])
        self.assertFalse(state["pw_cli_called"])

    def test_scenario_d_changing_node_id_is_resolved_dynamically(self):
        """D. Dynamic node resolution handles changing IDs (e.g. 65 -> 66) without hardcoding."""
        for expected_id in (65, 66, 128):
            with self.subTest(expected_id=expected_id):
                def mock_runner(cmd, **_kwargs):
                    if cmd[:2] == ["wpctl", "inspect"]:
                        return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(expected_id, codecs_str='[ "PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD" ]'), "stderr": ""})()
                    return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

                diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner)
                self.assertEqual(diag["audio_sink_id"], expected_id)

    def test_scenario_e_no_sink_resolved_provides_explicit_diagnostic(self):
        """E. Absence of active sink yields diagnostic without crash."""
        def mock_runner(cmd, **_kwargs):
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "Sink not found"})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner)
        self.assertIsNone(diag["audio_sink_id"])
        self.assertFalse(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "SINK_UNRESOLVED")

    def test_scenario_f_non_hdmi_sink_is_not_mutated(self):
        """F. Non-HDMI sink (e.g. analog stereo) is not mutated."""
        non_hdmi = """id 42, type PipeWire:Interface:Node
    device.profile.name = "analog-stereo"
    device.profile.description = "Built-in Audio Analog Stereo"
    iec958.codecs = "[ "PCM" ]"
    media.class = "Audio/Sink"
    node.name = "alsa_output.pci-0000_00_1f.3.analog-stereo"
    node.description = "Built-in Audio Analog Stereo"
"""
        state = {"pw_cli_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": non_hdmi, "stderr": ""})()
            if "pw-cli" in cmd[0]:
                state["pw_cli_called"] = True
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner)
        self.assertEqual(diag["audio_sink_id"], 42)
        self.assertFalse(diag["audio_sink_is_hdmi"])
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "SINK_NOT_HDMI")
        self.assertFalse(state["pw_cli_called"])

    def test_scenario_g1_pw_cli_unavailable_returns_deterministic_failure(self):
        """G1. Missing pw-cli binary records diagnostic failure without crash."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: None if name == "pw-cli" else f"/usr/bin/{name}",
        )
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "FAILED")
        self.assertEqual(diag["iec958_prepare_reason"], "PW_CLI_UNAVAILABLE")

    def test_scenario_g2_pw_cli_command_error_returns_mutation_failure(self):
        """G2. Failed pw-cli invocation records mutation failure without crash."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if "pw-cli" in cmd[0]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "connection error"})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "FAILED")
        self.assertEqual(diag["iec958_prepare_reason"], "PW_CLI_MUTATION_FAILED")

    def test_scenario_h_mutation_not_effective_is_detected_and_reported(self):
        """H. Mutation command succeeds but re-reading iec958.codecs shows codecs missing."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                # Always returns incomplete codecs even after mutation
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if "pw-cli" in cmd[0]:
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "FAILED")
        self.assertEqual(diag["iec958_prepare_reason"], "MUTATION_NOT_EFFECTIVE")

    def test_scenario_i_diagnostic_json_is_complete_and_atomic(self):
        """I. Full open_disc run produces complete atomic diagnostic in protected-optical-last-command.json."""
        config = self.home / ".config/openhtpc/user-config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"audio_output_mode": "BITSTREAM"}))

        state = {"mutated": False}

        def mock_pw(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                codecs = '[ "PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD" ]' if state["mutated"] else '[ "PCM", "DTS", "AC3" ]'
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str=codecs), "stderr": ""})()
            if "pw-cli" in cmd[0]:
                state["mutated"] = True
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        def mock_mpv(cmd, **_kwargs):
            target = pathlib.Path(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("--log-file=")))
            target.write_text("Video: libbluray fixture\nAudio: dts-hd 8ch 48000 Hz\nSelected decoder: spdif_dts_hd\nAO: [pipewire] fixture\n")
            return type("Proc", (), {"returncode": 0})()

        request = {"device": "/dev/sr0", "generation": 10, "media_type": "BLURAY", "protection": "PROTECTED", "provider_status": "AVAILABLE"}
        result = BACKEND.open_disc(
            self.home,
            request,
            runner=mock_mpv,
            pw_runner=mock_pw,
            finder=lambda name: f"/usr/bin/{name}",
            clock=iter((0.0, 1.5)).__next__,
        )
        self.assertEqual(result["status"], "OPEN_SUCCESS")

        target_diag = self.home / ".local/state/openhtpc/protected-optical-last-command.json"
        self.assertTrue(target_diag.is_file())
        data = json.loads(target_diag.read_text(encoding="utf-8"))

        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["requested_audio_mode"], "BITSTREAM")
        self.assertEqual(data["audio_sink_id"], 66)
        self.assertEqual(data["audio_sink_name"], "alsa_output.pci-0000_04_00.0.hdmi-surround71")
        self.assertEqual(data["audio_sink_profile"], "hdmi-surround71")
        self.assertEqual(data["audio_sink_media_class"], "Audio/Sink")
        self.assertTrue(data["audio_sink_is_hdmi"])
        self.assertEqual(data["iec958_codecs_before"], ["PCM", "DTS", "AC3"])
        self.assertEqual(data["iec958_codecs_requested"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertEqual(data["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertTrue(data["iec958_prepare_attempted"])
        self.assertEqual(data["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(data["iec958_prepare_reason"], "CODECS_APPLIED")
        self.assertEqual(data["iec958_prepare_method"], "pw-cli")
        self.assertIn("timestamp", data)


if __name__ == "__main__":
    unittest.main()
