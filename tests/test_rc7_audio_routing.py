# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Tests for RC7 T7.2: MPV Device Target + Bitstream Targeting."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

PAYLOAD = pathlib.Path(__file__).resolve().parent.parent / "payload"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


POLICY = _load("openhtpc_playback_policy_test", PAYLOAD / "openhtpc-playback-policy.py")
AUDIO = _load("openhtpc_audio_test", PAYLOAD / "openhtpc-audio.py")
BACKEND = _load("openhtpc_backend_test", PAYLOAD / "openhtpc-protected-optical-backend.py")

DENON_HDMI_SINK = {
    "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround71",
    "display_label": "DENON-AVR",
    "device_type": "HDMI",
    "bus_path": "pci-0000:04:00.0",
    "edid_name": "DENON-AVR",
    "is_network": False,
    "is_default": True,
}

ANALOG_SINK = {
    "node_name": "alsa_output.pci-0000_00_1f.3.analog-stereo",
    "display_label": "Audio interne Stéréo analogique",
    "device_type": "ANALOG",
    "bus_path": "pci-0000:00:1f.3",
    "edid_name": None,
    "is_network": False,
    "is_default": False,
}

NETWORK_SINK = {
    "node_name": "raop_sink.Denon-AVR-X1800H.local.192.168.1.58.7000",
    "display_label": "Denon AVR-X1800H",
    "device_type": "UNKNOWN",
    "bus_path": None,
    "edid_name": None,
    "is_network": True,
    "is_default": False,
}


def make_wpctl_inspect(sink_id: int = 80, node_name: str = DENON_HDMI_SINK["node_name"],
                        profile: str = "hdmi-surround71", is_hdmi: bool = True,
                        codecs: str = '[ "PCM", "DTS", "AC3" ]') -> str:
    lines = [
        f"id {sink_id}, type PipeWire:Interface:Node",
        f'  device.profile.name = "{profile}"',
        '  media.class = "Audio/Sink"',
        f'  node.name = "{node_name}"',
        f'  node.description = "{node_name}"',
        f"  iec958.codecs = {codecs}",
    ]
    if is_hdmi:
        lines.append('  api.alsa.path = "hdmi:1"')
    return "\n".join(lines)


def make_pw_cli_props(codecs: list[str]) -> str:
    lines = [
        "Object: size 2048, type Spa:Pod:Object:Struct (262146), id 2 (Props)",
        "  Prop: key Spa:Enum:Prop:params (262147), flags 00000000",
        "    Struct: size 512",
        '      String: "iec958Codecs"',
    ]
    for c in codecs:
        lines.append(f"      Id: Spa:Enum:AudioIEC958Codec:{c}")
    return "\n".join(lines)


def make_pw_cli_node_info(
    sink_id: int = 80,
    node_name: str = DENON_HDMI_SINK["node_name"],
    profile: str = "hdmi-surround71",
    is_hdmi: bool = True,
    codecs: str = '[ "PCM", "DTS", "AC3" ]',
    alsa_path: str = "hdmi:1",
) -> str:
    lines = [
        f"\tid: {sink_id}",
        "\tpermissions: rwxm-",
        "\ttype: PipeWire:Interface:Node/3",
        "*	properties:",
        '*\t\tmedia.class = "Audio/Sink"',
        f'*\t\tnode.name = "{node_name}"',
        f'*\t\tnode.description = "{node_name}"',
        f'*\t\tdevice.profile.name = "{profile}"',
        f'*\t\tiec958.codecs = "{codecs}"',
    ]
    if alsa_path:
        lines.append(f'*\t\tapi.alsa.path = "{alsa_path}"')
    return "\n".join(lines) + "\n"


class AudioRoutingT72Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp_dir.name)
        cfg_dir = self.home / ".config/openhtpc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = cfg_dir / "user-config.json"
        self.config_file.write_text(json.dumps({
            "schema": 1,
            "configuration_completed": True,
            "local_media_sources": [],
            "tmdb": {"configured": False},
        }))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _set_config(self, target: dict | None = None, mode: str = "PCM"):
        data = json.loads(self.config_file.read_text(encoding="utf-8"))
        if target is not None:
            data["audio_output_target"] = target
        elif "audio_output_target" in data:
            del data["audio_output_target"]
        data["audio_output_mode"] = mode
        self.config_file.write_text(json.dumps(data, indent=2))

    # 1. aucune audio_output_target -> comportement historique SYSTEM.
    def test_01_no_audio_output_target_historic_system_behavior(self):
        self._set_config(target=None, mode="PCM")
        decision = POLICY.resolve(self.home)
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "SYSTEM")
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertTrue(target.get("available"))
        self.assertFalse(target.get("fallback"))
        self.assertEqual(target.get("sink_target"), "@DEFAULT_AUDIO_SINK@")
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))

    # 2. target SYSTEM + PCM.
    def test_02_target_system_pcm(self):
        self._set_config(target={"mode": "SYSTEM"}, mode="PCM")
        decision = POLICY.resolve(self.home)
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "SYSTEM")
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertEqual(target.get("audio_mode"), "PCM")
        self.assertFalse(target.get("fallback"))
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))
        self.assertFalse(any(a.startswith("--audio-spdif=") for a in decision.get("mpv_args", [])))

    # 3. target SYSTEM + BITSTREAM.
    def test_03_target_system_bitstream(self):
        self._set_config(target={"mode": "SYSTEM"}, mode="BITSTREAM")
        decision = POLICY.resolve(self.home, probe={"streams": [{"codec_type": "audio", "codec_name": "ac3"}]})
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "SYSTEM")
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertEqual(target.get("audio_mode"), "BITSTREAM")
        self.assertEqual(target.get("sink_target"), "@DEFAULT_AUDIO_SINK@")
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))
        self.assertTrue(any(a.startswith("--audio-spdif=") for a in decision.get("mpv_args", [])))

    # 4. DEVICE HDMI disponible + PCM -> MPV reçoit pipewire/node correct.
    def test_04_device_hdmi_available_pcm_routes_pipewire_node(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="PCM")
        decision = POLICY.resolve(self.home, audio_outputs=[DENON_HDMI_SINK])
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "DEVICE")
        self.assertEqual(target.get("effective"), DENON_HDMI_SINK["node_name"])
        self.assertTrue(target.get("available"))
        self.assertFalse(target.get("fallback"))
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision.get("mpv_args", []))
        self.assertFalse(any(a.startswith("--audio-spdif=") for a in decision.get("mpv_args", [])))

    # 5. DEVICE HDMI disponible + BITSTREAM -> IEC958 préparé sur même sink + MPV reçoit même sink.
    def test_05_device_hdmi_available_bitstream_exact_same_sink(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        decision = POLICY.resolve(
            self.home,
            probe={"streams": [{"codec_type": "audio", "codec_name": "truehd"}]},
            audio_outputs=[DENON_HDMI_SINK],
        )
        target = decision.get("audio_target", {})
        expected_sink = DENON_HDMI_SINK["node_name"]
        self.assertEqual(target.get("sink_target"), expected_sink)
        self.assertIn(f"--audio-device=pipewire/{expected_sink}", decision.get("mpv_args", []))

        # Test PipeWire preparation targeting this exact sink
        mutated = {"target_id": None}

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                # verify inspect receives the exact resolved sink node name
                self.assertEqual(cmd[2], expected_sink)
                return type("Proc", (), {"returncode": 0, "stdout": make_wpctl_inspect(sink_id=80, node_name=expected_sink), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                codecs = ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"] if mutated["target_id"] else ["PCM", "DTS", "AC3"]
                return type("Proc", (), {"returncode": 0, "stdout": make_pw_cli_props(codecs), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                mutated["target_id"] = cmd[2]
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        pw_diag = POLICY.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            sink_target=target.get("sink_target"),
            target_descriptor=target.get("descriptor"),
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(pw_diag.get("audio_sink_id"), 80)
        self.assertEqual(pw_diag.get("audio_sink_name"), expected_sink)
        self.assertEqual(pw_diag.get("iec958_prepare_status"), "SUCCESS")
        self.assertEqual(mutated["target_id"], "80")

    # 6. DEVICE indisponible + PCM -> fallback SYSTEM, aucune modification config.
    def test_06_device_unavailable_pcm_falls_back_to_system_and_config_unchanged(self):
        original_target = dict(AUDIO.device_descriptor(DENON_HDMI_SINK))
        self._set_config(target=original_target, mode="PCM")
        config_before = self.config_file.read_text()

        decision = POLICY.resolve(self.home, audio_outputs=[ANALOG_SINK])  # DENON missing
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "DEVICE")
        self.assertFalse(target.get("available"))
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertTrue(target.get("fallback"))
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))

        # user-config.json must NOT be modified
        config_after = self.config_file.read_text()
        self.assertEqual(config_before, config_after)

    # 7. DEVICE indisponible + BITSTREAM -> fallback politique SYSTEM existante.
    def test_07_device_unavailable_bitstream_falls_back_to_system_policy(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        decision = POLICY.resolve(
            self.home,
            probe={"streams": [{"codec_type": "audio", "codec_name": "dts"}]},
            audio_outputs=[ANALOG_SINK],
        )
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertTrue(target.get("fallback"))
        self.assertEqual(target.get("sink_target"), "@DEFAULT_AUDIO_SINK@")
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))

        # When prepare_pipewire_hdmi_bitstream runs in fallback:
        inspected = []

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                inspected.append(cmd[2])
                return type("Proc", (), {"returncode": 0, "stdout": make_wpctl_inspect(sink_id=66, is_hdmi=True), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "enum-params":
                return type("Proc", (), {"returncode": 0, "stdout": make_pw_cli_props(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        pw_diag = POLICY.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            sink_target=target.get("sink_target"),
            target_descriptor=target.get("descriptor"),
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(inspected, ["@DEFAULT_AUDIO_SINK@"])
        self.assertEqual(pw_diag.get("iec958_prepare_status"), "SUCCESS")

    # 8. DEVICE analogique + PCM -> routage permis.
    def test_08_device_analog_pcm_routing_permitted(self):
        self._set_config(target=dict(AUDIO.device_descriptor(ANALOG_SINK)), mode="PCM")
        decision = POLICY.resolve(self.home, audio_outputs=[ANALOG_SINK])
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("configured"), "DEVICE")
        self.assertEqual(target.get("effective"), ANALOG_SINK["node_name"])
        self.assertTrue(target.get("available"))
        self.assertIn(f"--audio-device=pipewire/{ANALOG_SINK['node_name']}", decision.get("mpv_args", []))
        self.assertFalse(any(a.startswith("--audio-spdif=") for a in decision.get("mpv_args", [])))

    # 9. DEVICE analogique + BITSTREAM -> aucune préparation HDMI artificielle.
    def test_09_device_analog_bitstream_no_artificial_hdmi_preparation(self):
        self._set_config(target=dict(AUDIO.device_descriptor(ANALOG_SINK)), mode="BITSTREAM")
        decision = POLICY.resolve(
            self.home,
            probe={"streams": [{"codec_type": "audio", "codec_name": "ac3"}]},
            audio_outputs=[ANALOG_SINK],
        )
        target = decision.get("audio_target", {})
        self.assertEqual(target.get("effective"), ANALOG_SINK["node_name"])

        mutated = []

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 0, "stdout": make_wpctl_inspect(sink_id=54, node_name=ANALOG_SINK["node_name"], profile="analog-stereo", is_hdmi=False), "stderr": ""})()
            if cmd[0] == "/usr/bin/pw-cli" and cmd[1] == "s":
                mutated.append(cmd)
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        pw_diag = POLICY.prepare_pipewire_hdmi_bitstream(
            "BITSTREAM",
            sink_target=target.get("sink_target"),
            target_descriptor=target.get("descriptor"),
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertEqual(pw_diag.get("iec958_prepare_status"), "SKIPPED")
        self.assertEqual(pw_diag.get("iec958_prepare_reason"), "SINK_NOT_HDMI")
        self.assertFalse(pw_diag.get("iec958_prepare_attempted"))
        self.assertEqual(mutated, [])

    # 10. node_name changé mais résolution composite réussie -> nouveau node_name transmis à MPV.
    def test_10_node_name_changed_composite_resolution_succeeds(self):
        stale_target = {
            "mode": "DEVICE",
            "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround51",  # old name
            "bus_path": "pci-0000:04:00.0",
            "edid_name": "DENON-AVR",
            "display_label": "DENON-AVR",
            "device_type": "HDMI",
        }
        self._set_config(target=stale_target, mode="PCM")
        # Discovered output has new node_name hdmi-surround71
        decision = POLICY.resolve(self.home, audio_outputs=[DENON_HDMI_SINK])
        target = decision.get("audio_target", {})
        self.assertTrue(target.get("available"))
        self.assertEqual(target.get("effective"), DENON_HDMI_SINK["node_name"])
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision.get("mpv_args", []))

    # 11. correspondance ambiguë -> fallback SYSTEM.
    def test_11_ambiguous_composite_match_falls_back_to_system(self):
        target = {
            "mode": "DEVICE",
            "node_name": "alsa_output.pci-0000_04_00.0.old",
            "bus_path": "pci-0000:04:00.0",
            "edid_name": "DENON-AVR",
            "display_label": "DENON-AVR",
            "device_type": "HDMI",
        }
        self._set_config(target=target, mode="PCM")
        # Two outputs share the same bus_path and edid_name
        ambiguous_outputs = [
            DENON_HDMI_SINK,
            {**DENON_HDMI_SINK, "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround51"},
        ]
        decision = POLICY.resolve(self.home, audio_outputs=ambiguous_outputs)
        res_target = decision.get("audio_target", {})
        self.assertFalse(res_target.get("available"))
        self.assertEqual(res_target.get("effective"), "SYSTEM")
        self.assertTrue(res_target.get("fallback"))
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))

    # 12. sink réseau -> jamais utilisé comme DEVICE.
    def test_12_network_sink_never_used_as_device(self):
        network_target = dict(AUDIO.device_descriptor(NETWORK_SINK))
        self._set_config(target=network_target, mode="PCM")
        decision = POLICY.resolve(self.home, audio_outputs=[NETWORK_SINK])
        target = decision.get("audio_target", {})
        self.assertFalse(target.get("available"))
        self.assertEqual(target.get("effective"), "SYSTEM")
        self.assertTrue(target.get("fallback"))
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision.get("mpv_args", [])))

    # 13. DVD non régressé.
    def test_13_dvd_playback_unregressed_and_routes_device(self):
        # DVD with DEVICE
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        optical = {"physical_edition": {"audio": [{"format": "ac3", "langcode": "en"}]}}
        decision = POLICY.resolve(self.home, kind="dvd", optical_state=optical, audio_outputs=[DENON_HDMI_SINK])
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision.get("mpv_args", []))
        self.assertTrue(any(a.startswith("--audio-spdif=") for a in decision.get("mpv_args", [])))

        # DVD with SYSTEM
        self._set_config(target={"mode": "SYSTEM"}, mode="PCM")
        decision_sys = POLICY.resolve(self.home, kind="dvd", optical_state=optical)
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision_sys.get("mpv_args", [])))

    # 14. Blu-ray/protected optical non régressé.
    def test_14_bluray_protected_optical_routes_device_and_records_diagnostic(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        request = {
            "device": "/dev/sr0",
            "media_type": "BLURAY",
            "protection": "UNPROTECTED",
            "provider_status": "NOT_CONFIGURED",
        }
        # Mock profile.json so runtime_config succeeds
        profile_path = self.home / ".config/openhtpc/profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        conf_dummy = self.home / "pure.conf"
        conf_dummy.write_text("# dummy")
        profile_path.write_text(json.dumps({
            "runtime": {"status": "ready"},
            "runtime_profiles": {"profiles": {"PURE": {"generation_status": "generated", "config_path": str(conf_dummy)}}},
        }))

        captured_cmd = []

        def mock_runner(cmd, **_kwargs):
            captured_cmd.append(list(cmd))
            log_arg = next((arg for arg in cmd if arg.startswith("--log-file=")), None)
            if log_arg:
                pathlib.Path(log_arg.split("=", 1)[1]).write_text("Video: libbluray fixture\nVO: null\n")
            return type("Proc", (), {"returncode": 0})()

        with mock.patch.object(BACKEND._POLICY_MODULE, "_load_audio_module", return_value=AUDIO), \
             mock.patch.object(POLICY, "_load_audio_module", return_value=AUDIO), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            result = BACKEND.open_disc(
                self.home,
                request,
                runner=mock_runner,
                finder=lambda _name: "/usr/bin/mpv",
                clock=iter((0.0, 2.0)).__next__,
            )

        self.assertEqual(result["status"], "OPEN_SUCCESS")
        self.assertTrue(len(captured_cmd) > 0)
        mpv_argv = captured_cmd[0]
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", mpv_argv)

        # Check recorded diagnostic
        diag_file = self.home / ".local/state/openhtpc/protected-optical-last-command.json"
        self.assertTrue(diag_file.is_file())
        diag = json.loads(diag_file.read_text(encoding="utf-8"))
        self.assertEqual(diag.get("target_configured"), "DEVICE")
        self.assertEqual(diag.get("target_effective"), DENON_HDMI_SINK["node_name"])
        self.assertTrue(diag.get("target_available"))
        self.assertFalse(diag.get("target_fallback"))

    # 15. fichiers médias non régressés.
    def test_15_media_file_playback_routes_device_and_records_observation(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        decision = POLICY.resolve(
            self.home,
            probe={"streams": [{"codec_type": "audio", "codec_name": "ac3"}]},
            audio_outputs=[DENON_HDMI_SINK],
        )
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision["mpv_args"])

        observed = POLICY.record_audio_observation(
            self.home,
            decision,
            raw_log=f"AO: [pipewire] 48000Hz stereo 2ch spdif-ac3\naudio-device: pipewire/{DENON_HDMI_SINK['node_name']}",
        )
        self.assertEqual(observed["configured"], "DEVICE")
        self.assertEqual(observed["effective"], DENON_HDMI_SINK["node_name"])
        self.assertTrue(observed["available"])
        self.assertFalse(observed["fallback"])
        self.assertEqual(observed["passthrough"], "ACTIVE")

        saved = json.loads((self.home / ".local/state/openhtpc/audio-policy-last.json").read_text())
        self.assertEqual(saved["effective"], DENON_HDMI_SINK["node_name"])
        self.assertEqual(saved["configured"], "DEVICE")

    # 16. audio_output_mode PCM/BITSTREAM existant préservé.
    def test_16_audio_output_mode_pcm_and_bitstream_preserved(self):
        self._set_config(mode="PCM")
        prefs = POLICY.read_preferences(self.home)
        self.assertEqual(prefs["audio_output_mode"], "PCM")

        self._set_config(mode="BITSTREAM")
        prefs = POLICY.read_preferences(self.home)
        self.assertEqual(prefs["audio_output_mode"], "BITSTREAM")

        # choose_audio_output preserves contract
        pcm_out = POLICY.choose_audio_output("PCM", {"codec_name": "ac3"})
        self.assertEqual(pcm_out["requested"], "PCM")
        self.assertEqual(pcm_out["resolved"], "PCM")
        self.assertEqual(pcm_out["mpv_args"], [])

        bit_out = POLICY.choose_audio_output("BITSTREAM", {"codec_name": "ac3"})
        self.assertEqual(bit_out["requested"], "BITSTREAM")
        self.assertEqual(bit_out["resolved"], "BITSTREAM")
        self.assertTrue(any(a.startswith("--audio-spdif=") for a in bit_out["mpv_args"]))

    # 17. Test réel non destructif (read-only) sur l'hôte
    def test_17_real_system_read_only_introspection(self):
        outputs = AUDIO.discover_outputs()
        self.assertIsInstance(outputs, list)
        for out in outputs:
            self.assertFalse(out.get("is_network", False))
            self.assertIn("node_name", out)
            self.assertIn("device_type", out)
            self.assertIn("display_label", out)

        denon = next((o for o in outputs if "denon" in str(o.get("display_label", "")).lower()
                      or "denon" in str(o.get("edid_name", "")).lower()
                      or "denon" in str(o.get("node_name", "")).lower()), None)
        if denon:
            # Confirm resolving this real physical output returns valid DEVICE
            resolved = AUDIO.resolve_audio(AUDIO.device_descriptor(denon), outputs)
            self.assertTrue(resolved["AVAILABLE"])
            self.assertEqual(resolved["EFFECTIVE"]["node_name"], denon["node_name"])
            self.assertEqual(resolved["EFFECTIVE"]["mode"], "DEVICE")

    # 18. DVD + DEVICE + PCM -> MPV reçoit --audio-device=<node_name> et pas d'activation bitstream
    def test_18_dvd_device_pcm_routes_mpv_device_no_bitstream_activation(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="PCM")
        optical_state = {
            "state": "DVD",
            "device": "/dev/sr0",
            "physical_edition": {"audio": [{"format": "ac3", "channels": 6, "langcode": "fra"}]},
        }
        decision = POLICY.resolve(
            self.home,
            kind="dvd",
            optical_state=optical_state,
            audio_outputs=[DENON_HDMI_SINK],
        )
        self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision["mpv_args"])
        self.assertFalse(any(a.startswith("--audio-spdif=") for a in decision["mpv_args"]))

        diag = POLICY.prepare_audio_target_bitstream(decision)
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "PCM_MODE")
        self.assertFalse(diag["iec958_prepare_attempted"])

    # 19. DVD + DEVICE + BITSTREAM -> MPV reçoit --audio-device=<node_name> ET prepare_pipewire_hdmi_bitstream cible exactement le même <node_name>
    def test_19_dvd_device_bitstream_routes_mpv_device_and_prepares_exact_same_device(self):
        self._set_config(target=dict(AUDIO.device_descriptor(DENON_HDMI_SINK)), mode="BITSTREAM")
        optical_state = {
            "state": "DVD",
            "device": "/dev/sr0",
            "physical_edition": {"audio": [{"format": "ac3", "channels": 6, "langcode": "fra"}]},
        }
        decision = POLICY.resolve(
            self.home,
            kind="dvd",
            optical_state=optical_state,
            audio_outputs=[DENON_HDMI_SINK],
        )
        expected_sink = DENON_HDMI_SINK["node_name"]
        self.assertIn(f"--audio-device=pipewire/{expected_sink}", decision["mpv_args"])
        self.assertTrue(any(a.startswith("--audio-spdif=") for a in decision["mpv_args"]))

        inspect_called_with = []
        set_param_called_with = []
        mutated = False

        def mock_runner(cmd, **_kwargs):
            nonlocal mutated
            if "wpctl" in cmd[0] and "inspect" in cmd:
                inspect_called_with.append(cmd[2])
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if "pw-cli" in cmd[0] and "info" in cmd:
                inspect_called_with.append(cmd[2])
                return type("Proc", (), {"returncode": 0, "stdout": make_pw_cli_node_info(80, node_name=expected_sink), "stderr": ""})()
            if "pw-cli" in cmd[0] and "enum-params" in cmd:
                codecs = ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"] if mutated else ["PCM", "DTS", "AC3"]
                return type("Proc", (), {"returncode": 0, "stdout": make_pw_cli_props(codecs), "stderr": ""})()
            if "pw-cli" in cmd[0] and "s" in cmd:
                mutated = True
                set_param_called_with.append((cmd[2], cmd[4]))
                return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = POLICY.prepare_audio_target_bitstream(
            decision,
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertIn(expected_sink, inspect_called_with)
        self.assertEqual(diag["audio_sink_id"], 80)
        self.assertEqual(diag["audio_sink_name"], expected_sink)
        self.assertTrue(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(set_param_called_with[0][0], "80")

    # 20. DVD + SYSTEM + BITSTREAM -> MPV ne force pas audio-device et prepare_pipewire_hdmi_bitstream cible le sink par défaut historique
    def test_20_dvd_system_bitstream_uses_historical_default_sink(self):
        self._set_config(target={"mode": "SYSTEM"}, mode="BITSTREAM")
        optical_state = {
            "state": "DVD",
            "device": "/dev/sr0",
            "physical_edition": {"audio": [{"format": "ac3", "channels": 6, "langcode": "fra"}]},
        }
        decision = POLICY.resolve(
            self.home,
            kind="dvd",
            optical_state=optical_state,
            audio_outputs=[DENON_HDMI_SINK],
        )
        self.assertFalse(any(a.startswith("--audio-device=") for a in decision["mpv_args"]))
        self.assertTrue(any(a.startswith("--audio-spdif=") for a in decision["mpv_args"]))

        inspect_called_with = []

        def mock_runner(cmd, **_kwargs):
            if "wpctl" in cmd[0] and "inspect" in cmd:
                inspect_called_with.append(cmd[2])
                return type("Proc", (), {"returncode": 0, "stdout": make_wpctl_inspect(sink_id=42, node_name="default_sink", is_hdmi=True), "stderr": ""})()
            if "pw-cli" in cmd[0] and "enum-params" in cmd:
                return type("Proc", (), {"returncode": 0, "stdout": make_pw_cli_props(["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"]), "stderr": ""})()
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        diag = POLICY.prepare_audio_target_bitstream(
            decision,
            runner=mock_runner,
            finder=lambda name: f"/usr/bin/{name}",
        )
        self.assertIn("@DEFAULT_AUDIO_SINK@", inspect_called_with)
        self.assertEqual(diag["audio_sink_id"], 42)
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")

    # 21. pw-cli avec correspondance exacte unique -> PASS
    def test_21_pw_cli_exact_unique_match_succeeds(self):
        target = "alsa_output.pci-0000_04_00.0.hdmi-surround71"
        out = make_pw_cli_node_info(80, node_name=target)

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if cmd[:2] == ["pw-cli", "info"]:
                return type("Proc", (), {"returncode": 0, "stdout": out, "stderr": ""})()
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        sink = POLICY.inspect_sink(target, runner=mock_runner)
        self.assertEqual(sink.get("id"), 80)
        self.assertEqual(sink.get("name"), target)
        self.assertTrue(sink.get("is_hdmi"))

    # 22. pw-cli avec zéro correspondance -> fail-closed
    def test_22_pw_cli_zero_match_fails_closed(self):
        target = "alsa_output.pci-0000_04_00.0.hdmi-surround71"
        out = make_pw_cli_node_info(79, node_name="alsa_output.pci-0000_00_1f.3.analog-stereo", is_hdmi=False)

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if cmd[:2] == ["pw-cli", "info"]:
                return type("Proc", (), {"returncode": 0, "stdout": out, "stderr": ""})()
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        sink = POLICY.inspect_sink(target, runner=mock_runner)
        self.assertEqual(sink, {})

    # 23. pw-cli avec deux objets dont un seul correspond au node.name -> sélection de l'objet exact
    def test_23_pw_cli_two_objects_single_match_selects_exact_matching_object(self):
        target = "alsa_output.pci-0000_04_00.0.hdmi-surround71"
        obj1 = make_pw_cli_node_info(79, node_name="alsa_output.pci-0000_00_1f.3.analog-stereo", is_hdmi=False)
        obj2 = make_pw_cli_node_info(80, node_name=target, is_hdmi=True)
        multi_out = f"{obj1}\n{obj2}"

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if cmd[:2] == ["pw-cli", "info"]:
                return type("Proc", (), {"returncode": 0, "stdout": multi_out, "stderr": ""})()
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        sink = POLICY.inspect_sink(target, runner=mock_runner)
        self.assertEqual(sink.get("id"), 80)
        self.assertEqual(sink.get("name"), target)
        self.assertTrue(sink.get("is_hdmi"))

    # 24. pw-cli avec deux objets portant le même node.name -> fail-closed
    def test_24_pw_cli_two_objects_duplicate_node_name_fails_closed(self):
        target = "alsa_output.pci-0000_04_00.0.hdmi-surround71"
        obj1 = make_pw_cli_node_info(79, node_name=target, is_hdmi=True)
        obj2 = make_pw_cli_node_info(80, node_name=target, is_hdmi=True)
        multi_out = f"{obj1}\n{obj2}"

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if cmd[:2] == ["pw-cli", "info"]:
                return type("Proc", (), {"returncode": 0, "stdout": multi_out, "stderr": ""})()
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        sink = POLICY.inspect_sink(target, runner=mock_runner)
        self.assertEqual(sink, {})

    # 25. non-mélange d'id et de nom entre objets
    def test_25_no_mixing_of_id_and_properties_between_objects(self):
        sink1_name = "alsa_output.pci-0000_00_1f.3.analog-stereo"
        sink2_name = "alsa_output.pci-0000_04_00.0.hdmi-surround71"
        obj1 = make_pw_cli_node_info(79, node_name=sink1_name, profile="analog-stereo", is_hdmi=False, alsa_path="hw:0")
        obj2 = make_pw_cli_node_info(80, node_name=sink2_name, profile="hdmi-surround71", is_hdmi=True, alsa_path="hdmi:1")
        multi_out = f"{obj1}\n{obj2}"

        def mock_runner(cmd, **_kwargs):
            if cmd[:2] == ["wpctl", "inspect"]:
                return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
            if cmd[:2] == ["pw-cli", "info"]:
                return type("Proc", (), {"returncode": 0, "stdout": multi_out, "stderr": ""})()
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        sink2 = POLICY.inspect_sink(sink2_name, runner=mock_runner)
        self.assertEqual(sink2.get("id"), 80)
        self.assertEqual(sink2.get("name"), sink2_name)
        self.assertEqual(sink2.get("profile"), "hdmi-surround71")
        self.assertEqual(sink2.get("alsa_path"), "hdmi:1")
        self.assertTrue(sink2.get("is_hdmi"))

        sink1 = POLICY.inspect_sink(sink1_name, runner=mock_runner)
        self.assertEqual(sink1.get("id"), 79)
        self.assertEqual(sink1.get("name"), sink1_name)
        self.assertEqual(sink1.get("profile"), "analog-stereo")
        self.assertEqual(sink1.get("alsa_path"), "hw:0")
        self.assertFalse(sink1.get("is_hdmi"))

    # 26. openhtpc-audio.py est présent dans PRODUCT_FILES et managed-files.txt
    def test_26_openhtpc_audio_module_managed_and_installable(self):
        managed_content = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
        installer_content = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")

        self.assertIn("openhtpc-audio.py", managed_content)
        self.assertTrue((PAYLOAD / "openhtpc-audio.py").is_file())

        import re
        match = re.search(r'readonly PRODUCT_FILES=\(([^)]+)\)', installer_content)
        self.assertIsNotNone(match, "PRODUCT_FILES array must be defined in install-openhtpc-fedora.sh")
        product_files = match.group(1).split()
        self.assertIn("openhtpc-audio.py", product_files)

    # 27. openhtpc-play-dvd script invents bitstream preparation before launching MPV
    def test_27_dvd_dispatcher_script_invokes_bitstream_prep(self):
        script_text = (PAYLOAD / "openhtpc-play-dvd").read_text(encoding="utf-8")
        self.assertIn("prepare-bitstream", script_text)
        self.assertIn("AUDIO_ROUTING", script_text)
        self.assertIn("AUDIO_PIPEWIRE_PREPARATION", script_text)
        prep_pos = script_text.find("prepare-bitstream")
        mpv_pos = script_text.find('"$mpv_bin" --no-config')
        self.assertNotEqual(prep_pos, -1)
        self.assertNotEqual(mpv_pos, -1)
        self.assertLess(prep_pos, mpv_pos, "Bitstream preparation must execute before launching MPV")


if __name__ == "__main__":
    unittest.main()
