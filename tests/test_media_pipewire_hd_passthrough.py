#!/usr/bin/env python3
"""Hermetic tests for MEDIA PipeWire IEC958 dynamic preparation and bitstream playback."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


POLICY = load("media_pw_policy", PAYLOAD / "openhtpc-playback-policy.py")
PLAY = load("media_pw_play", PAYLOAD / "openhtpc-play")


def make_inspect_output(
    sink_id: int = 65,
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


class MediaPipeWirePassthroughTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.install = self.home / "install"
        self.install.mkdir(parents=True)
        for name in (
            "openhtpc-play",
            "openhtpc-playback-policy.py",
            "openhtpc-capabilities.py",
            "openhtpc-runtime.py",
        ):
            src = PAYLOAD / name
            if src.is_file():
                dest = self.install / name
                dest.write_bytes(src.read_bytes())
                dest.chmod(0o755)

        self.source = self.home / "Movies"
        self.source.mkdir(parents=True)
        self.movie = self.source / "Pacific Rim Uprising.mkv"
        self.movie.write_bytes(b"dummy mkv video content")

        config_dir = self.home / ".config/openhtpc"
        config_dir.mkdir(parents=True)
        (config_dir / "user-config.json").write_text(
            json.dumps({
                "configuration_completed": True,
                "local_media_sources": [str(self.source)],
                "audio_output_mode": "BITSTREAM",
            })
        )

        self.runtime = config_dir / "pure.conf"
        self.runtime.write_text("vo=null\n")
        (config_dir / "profile.json").write_text(
            json.dumps({
                "runtime": {"status": "ready"},
                "runtime_profiles": {"profiles": {"PURE": {"generation_status": "generated", "config_path": str(self.runtime)}}},
            })
        )

        self.fakebin = self.home / "fakebin"
        self.fakebin.mkdir()
        self.log_dir = self.home / ".local/state/openhtpc"
        self.log_dir.mkdir(parents=True)

    def _setup_mock_tools(self, sink_id: int = 65, initial_codecs: list[str] | None = None):
        if initial_codecs is None:
            initial_codecs = ["PCM", "DTS", "AC3"]

        state_file = self.home / "pw_state.json"
        state_file.write_text(json.dumps({"mutated": False, "sink_id": sink_id, "initial_codecs": initial_codecs, "mutations": [], "fail_mutation": False}))

        wpctl = self.fakebin / "wpctl"
        wpctl.write_text(f"""#!/usr/bin/env python3
import sys, json, pathlib
state = json.loads(pathlib.Path({repr(str(state_file))}).read_text())
print({repr(make_inspect_output(sink_id=sink_id))})
""")
        wpctl.chmod(0o755)

        pw_cli = self.fakebin / "pw-cli"
        pw_cli.write_text(f"""#!/usr/bin/env python3
import sys, json, pathlib

state_p = pathlib.Path({repr(str(state_file))})
state = json.loads(state_p.read_text())

if len(sys.argv) >= 4 and sys.argv[1] == "enum-params" and sys.argv[3] == "Props":
    codecs = ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"] if state["mutated"] else state["initial_codecs"]
    lines = [
        "Object: size 2048, type Spa:Pod:Object:Struct (262146), id 2 (Props)",
        "  Prop: key Spa:Enum:Prop:params (262147), flags 00000000",
        "    Struct: size 512",
        "      String: \\"iec958Codecs\\"",
    ]
    for c in codecs:
        lines.append(f"      Id: Spa:Enum:AudioIEC958Codec:{{c}}")
    print("\\n".join(lines))
    sys.exit(0)

if len(sys.argv) >= 5 and sys.argv[1] == "s" and sys.argv[3] == "Props":
    if state.get("fail_mutation"):
        sys.stderr.write("Simulated pw-cli mutation failure\\n")
        sys.exit(1)
    state["mutated"] = True
    state["mutations"].append(sys.argv[4])
    state_p.write_text(json.dumps(state))
    sys.exit(0)

sys.exit(0)
""")
        pw_cli.chmod(0o755)

        mpv = self.fakebin / "mpv"
        mpv.write_text("""#!/usr/bin/env python3
import sys, pathlib, os
log_arg = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--log-file=")), None)
if log_arg:
    pathlib.Path(log_arg).write_text("VO: [gpu] 3840x2160\\nAO: [pipewire] 48000Hz 8ch spdif-eac3\\nStarting playback...\\n")
argv_log = os.environ.get("OPENHTPC_TEST_ARGV")
if argv_log:
    pathlib.Path(argv_log).write_text("\\n".join(sys.argv))
sys.exit(0)
""")
        mpv.chmod(0o755)

        ffprobe = self.fakebin / "ffprobe"
        ffprobe.write_text("""#!/usr/bin/env python3
import sys, json
print(json.dumps({
    "streams": [
        {"codec_type": "video", "codec_name": "hevc"},
        {"codec_type": "audio", "codec_name": "eac3", "tags": {"language": "fre", "title": "French EAC3 7.1"}, "disposition": {"default": 1}}
    ]
}))
sys.exit(0)
""")
        ffprobe.chmod(0o755)

        return state_file

    def _run_play(self, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        argv_log = self.home / "mpv.argv"
        env = {
            **os.environ,
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(self.install),
            "OPENHTPC_TEST_ARGV": str(argv_log),
            "OPENHTPC_FLEX_RETAINED": "1",
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_RUNTIME_DIR": str(self.home / ".runtime"),
            "PATH": f"{self.fakebin}:{os.environ['PATH']}",
            "OPENHTPC_TEST_ENVIRONMENT": "1",
        }
        if extra_env:
            env.update(extra_env)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        return subprocess.run(
            [str(self.install / "openhtpc-play"), str(self.movie)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_case_a_bitstream_incomplete_sink_mutates_and_verifies_effective_codecs(self):
        """Cas A: MEDIA BITSTREAM with incomplete SPA [PCM, DTS, AC3] triggers dynamic PipeWire preparation."""
        state_file = self._setup_mock_tools(sink_id=65, initial_codecs=["PCM", "DTS", "AC3"])

        result = self._run_play()
        self.assertEqual(result.returncode, 0, result.stderr)

        state = json.loads(state_file.read_text())
        self.assertTrue(state["mutated"], "pw-cli mutation should have been executed")
        self.assertEqual(len(state["mutations"]), 1)
        self.assertIn("PCM DTS AC3 EAC3 TrueHD DTS-HD", state["mutations"][0])

        diag_path = self.home / ".local/state/openhtpc/playback-last-private.json"
        self.assertTrue(diag_path.is_file())
        diag = json.loads(diag_path.read_text())
        self.assertEqual(diag["requested_audio_mode"], "BITSTREAM")
        self.assertEqual(diag["audio_sink_id"], 65)
        self.assertEqual(diag["active_sink_id"], 65)
        self.assertTrue(diag["audio_sink_is_hdmi"])
        self.assertEqual(diag["iec958_codecs_before"], ["PCM", "DTS", "AC3"])
        self.assertEqual(diag["iec958_codecs_after"], ["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "CODECS_APPLIED")
        self.assertEqual(diag["iec958_prepare_method"], "pw-cli")

        argv = (self.home / "mpv.argv").read_text().splitlines()
        self.assertIn("--audio-spdif=ac3,eac3,dts,dts-hd,truehd", argv)

    def test_case_b_bitstream_already_compatible_sink_is_idempotent(self):
        """Cas B: MEDIA BITSTREAM with already complete SPA codecs makes no mutation."""
        state_file = self._setup_mock_tools(sink_id=65, initial_codecs=["PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"])

        result = self._run_play()
        self.assertEqual(result.returncode, 0, result.stderr)

        state = json.loads(state_file.read_text())
        self.assertFalse(state["mutated"], "pw-cli should NOT have mutated already compatible sink")

        diag = json.loads((self.home / ".local/state/openhtpc/playback-last-private.json").read_text())
        self.assertEqual(diag["requested_audio_mode"], "BITSTREAM")
        self.assertEqual(diag["audio_sink_id"], 65)
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")
        self.assertEqual(diag["iec958_prepare_reason"], "ALREADY_COMPATIBLE")

    def test_case_c_pcm_mode_does_not_mutate_pipewire(self):
        """Cas C: MEDIA PCM mode never mutates PipeWire and records SKIPPED / PCM_MODE."""
        (self.home / ".config/openhtpc/user-config.json").write_text(
            json.dumps({
                "configuration_completed": True,
                "local_media_sources": [str(self.source)],
                "audio_output_mode": "PCM",
            })
        )
        state_file = self._setup_mock_tools(sink_id=65, initial_codecs=["PCM", "DTS", "AC3"])

        result = self._run_play()
        self.assertEqual(result.returncode, 0, result.stderr)

        state = json.loads(state_file.read_text())
        self.assertFalse(state["mutated"], "pw-cli must never mutate in PCM mode")

        diag = json.loads((self.home / ".local/state/openhtpc/playback-last-private.json").read_text())
        self.assertEqual(diag["requested_audio_mode"], "PCM")
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "PCM_MODE")

        argv = (self.home / "mpv.argv").read_text().splitlines()
        self.assertNotIn("--audio-spdif=ac3,eac3,dts,dts-hd,truehd", argv)

    def test_case_d_preparation_failure_is_non_blocking_and_diagnosed(self):
        """Cas D: PipeWire tool failure (mutation error or missing tool) is non-blocking."""
        state_file = self._setup_mock_tools(sink_id=65)
        state = json.loads(state_file.read_text())
        state["fail_mutation"] = True
        state_file.write_text(json.dumps(state))

        result = self._run_play()
        self.assertEqual(result.returncode, 0, "Playback must not crash when pw-cli mutation fails")

        diag = json.loads((self.home / ".local/state/openhtpc/playback-last-private.json").read_text())
        self.assertEqual(diag["requested_audio_mode"], "BITSTREAM")
        self.assertTrue(diag["iec958_prepare_attempted"])
        self.assertEqual(diag["iec958_prepare_status"], "FAILED")
        self.assertEqual(diag["iec958_prepare_reason"], "PW_CLI_MUTATION_FAILED")

    def test_case_e_dynamic_sink_id_resolution(self):
        """Cas E: Dynamic resolution handles sink ID transitions (e.g. 60 -> 65) without hardcoding."""
        for expected_id in (60, 65, 128):
            with self.subTest(sink_id=expected_id):
                state_file = self._setup_mock_tools(sink_id=expected_id, initial_codecs=["PCM", "DTS", "AC3"])
                result = self._run_play()
                self.assertEqual(result.returncode, 0)
                diag = json.loads((self.home / ".local/state/openhtpc/playback-last-private.json").read_text())
                self.assertEqual(diag["audio_sink_id"], expected_id)
                self.assertEqual(diag["active_sink_id"], expected_id)
                self.assertEqual(diag["iec958_prepare_status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
