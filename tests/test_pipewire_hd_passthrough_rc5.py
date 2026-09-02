#!/usr/bin/env python3
"""Tests for PipeWire HDMI HD bitstream passthrough preparation, effective SPA state verification, and diagnostics."""
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load_backend():
    loader = importlib.machinery.SourceFileLoader("rc5_backend", str(PAYLOAD / "openhtpc-protected-optical-backend.py"))
    spec = importlib.util.spec_from_loader("rc5_backend", loader)
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


def make_enum_params_output(codecs: list[str]) -> str:
    lines = [
        "Object: size 2048, type Spa:Pod:Object:Struct (262146), id 2 (Props)",
        "  Prop: key Spa:Enum:Prop:params (262147), flags 00000000",
        "    Struct: size 512",
        "      String: \"iec958Codecs\"",
    ]
    for c in codecs:
        lines.append(f"      Id: Spa:Enum:AudioIEC958Codec:{c}")
    return "\n".join(lines) + "\n"


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

    def test_scenario_a_property_stale_and_spa_complete_requires_no_mutation(self):
        """A. Property has 3 codecs, SPA Props has all 6 codecs -> ALREADY_COMPATIBLE, no pw-cli set-param."""
        state = {"pw_cli_mutated": False, "enum_params_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                state["enum_params_called"] = True
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                state["pw_cli_mutated"] = True
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(diag["audio_sink_id"], 66)
        self.assertTrue(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_property_codecs"], ["PCM", "DTS", "AC3"])
        self.assertEqual(diag["iec958_codecs_before"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertEqual(diag["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_COMPATIBLE")
        self.assertTrue(state["enum_params_called"])
        self.assertFalse(state["pw_cli_mutated"])

    def test_scenario_b_spa_incomplete_before_mutates_and_verifies_effective_state(self):
        """B. Initial SPA [PCM, DTS, AC3] -> pw-cli adds EAC3 TrueHD DTS-HD, verifies final SPA state."""
        state = {"pw_cli_mutated": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                codecs = ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"] if state["pw_cli_mutated"] else ["PCM", "DTS", "AC3"]
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(codecs), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                state["pw_cli_mutated"] = True
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
        self.assertTrue(state["pw_cli_mutated"])

    def test_scenario_c_spa_already_complete_is_idempotent(self):
        """C. Initial SPA [PCM, DTS, AC3, EAC3, TrueHD, DTS-HD] -> idempotent, no set-param."""
        state = {"pw_cli_mutated": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                state["pw_cli_mutated"] = True
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
        self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_COMPATIBLE")
        self.assertFalse(state["pw_cli_mutated"])

    def test_scenario_d_set_param_succeeds_but_spa_remains_incomplete(self):
        """D. Mutation command succeeds but enum-params Props still returns incomplete codecs -> MUTATION_NOT_EFFECTIVE."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                # Stays incomplete even after mutation
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3"]), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
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
        self.assertEqual(diag["iec958_codecs_after"], ["PCM", "DTS", "AC3"])

    def test_scenario_e_malformed_enum_params_output_handles_gracefully(self):
        """E. Malformed or empty output from enum-params is parsed safely without crash."""
        self.assertEqual(BACKEND.parse_spa_codecs(""), [])
        self.assertEqual(BACKEND.parse_spa_codecs("random text with no codecs"), [])
        raw_garbage = "Object: corrupted struct 12345 { ?? }"
        self.assertEqual(BACKEND.parse_spa_codecs(raw_garbage), [])

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                return type("Proc", (), {"returncode": 0, "stdout": "invalid enum params format", "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
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

    def test_scenario_f_dynamic_node_id_resolution_without_hardcoding(self):
        """F. Dynamic node resolution handles changing IDs (62, 66, 128) without hardcoding."""
        for expected_id in (62, 66, 128):
            with self.subTest(expected_id=expected_id):
                def mock_runner(cmd, **_kwargs):
                    if cmd[:2] == ["wpctl", "inspect"]:
                        return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(expected_id), "stderr": ""})()
                    if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                        self.assertEqual(cmd[2], str(expected_id))
                        return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
                    return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

                diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner, finder=lambda name: f"/usr/bin/{name}")
                self.assertEqual(diag["audio_sink_id"], expected_id)
                self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_COMPATIBLE")

    def test_scenario_g_non_hdmi_sink_is_not_mutated(self):
        """G. Non-HDMI sink (e.g. analog stereo) is not mutated."""
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

        diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner, finder=lambda name: f"/usr/bin/{name}")
        self.assertEqual(diag["audio_sink_id"], 42)
        self.assertFalse(diag["audio_sink_is_hdmi"])
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "SINK_NOT_HDMI")
        self.assertFalse(state["pw_cli_called"])

    def test_scenario_h_absence_of_sink_provides_explicit_diagnostic(self):
        """H. Absence of active sink yields diagnostic without crash."""
        def mock_runner(cmd, **_kwargs):
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "Sink not found"})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream("BITSTREAM", runner=mock_runner, finder=lambda name: f"/usr/bin/{name}")
        self.assertIsNone(diag["audio_sink_id"])
        self.assertFalse(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "SINK_UNRESOLVED")

    def test_scenario_i1_pw_cli_unavailable_returns_deterministic_failure(self):
        """I1. Missing pw-cli binary records diagnostic failure without crash."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: None if name == "pw-cli" else f"/usr/bin/{name}",
        )
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "FAILED")
        self.assertEqual(diag["iec958_prepare_reason"], "PW_CLI_UNAVAILABLE")

    def test_scenario_i2_pw_cli_command_error_returns_mutation_failure(self):
        """I2. Failed pw-cli set-param invocation records mutation failure without crash."""
        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3"]), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
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

    def test_scenario_j_pcm_mode_does_not_mutate_pipewire(self):
        """J. PCM mode does not attempt mutation and preserves PCM defaults."""
        state = {"pw_cli_called": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66), "stderr": ""})()
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

        pcm_args = BACKEND.effective_policy_args({"audio_output": {"requested": "PCM"}})
        self.assertEqual(pcm_args, ["--aid=auto", "--audio-spdif="])

    def test_scenario_k_bitstream_contract_rc4_preserved(self):
        """K. BITSTREAM mode preserves the exact audio arguments validated on Denon AVR."""
        args = BACKEND.effective_policy_args({"audio_output": {"requested": "BITSTREAM"}})
        self.assertEqual(args, ["--aid=auto", "--audio-channels=auto", "--audio-spdif=ac3,eac3,dts,dts-hd,truehd"])

    def test_scenario_l_diagnostic_json_is_complete_and_atomic(self):
        """L. Full open_disc run produces complete atomic diagnostic with SPA effective representations."""
        config = self.home / ".config/openhtpc/user-config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"audio_output_mode": "BITSTREAM"}))

        state = {"mutated": False}

        def mock_pw(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(66, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                codecs = ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"] if state["mutated"] else ["PCM", "DTS", "AC3"]
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(codecs), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
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
        self.assertEqual(data["iec958_property_codecs"], ["PCM", "DTS", "AC3"])
        self.assertEqual(data["iec958_codecs_before"], ["PCM", "DTS", "AC3"])
        self.assertEqual(data["iec958_codecs_requested"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertEqual(data["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertTrue(data["iec958_prepare_attempted"])
        self.assertEqual(data["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(data["iec958_prepare_reason"], "CODECS_APPLIED")
        self.assertEqual(data["iec958_prepare_method"], "pw-cli")
        self.assertIn("timestamp", data)

    def test_scenario_m_post_reboot_physical_state_reproduced(self):
        """M. Exact post-reboot physical case: Node 62, wpctl inspect property [PCM, DTS, AC3], SPA Props 6 codecs -> ALREADY_COMPATIBLE."""
        state = {"pw_cli_mutated": False}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_inspect_output(62, codecs_str='[ "PCM", "DTS", "AC3" ]'), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                self.assertEqual(cmd[2], "62")
                return type("Proc", (), {"returncode": 0, "stdout": make_enum_params_output(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                state["pw_cli_mutated"] = True
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = BACKEND.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(diag["audio_sink_id"], 62)
        self.assertEqual(diag["iec958_property_codecs"], ["PCM", "DTS", "AC3"])
        self.assertEqual(diag["iec958_codecs_before"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertEqual(diag["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_COMPATIBLE")
        self.assertFalse(state["pw_cli_mutated"])


if __name__ == "__main__":
    unittest.main()
