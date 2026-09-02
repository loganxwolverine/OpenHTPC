import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("audio_rc2_policy", PAYLOAD / "openhtpc-playback-policy.py")
model = load("audio_rc2_model", PAYLOAD / "openhtpc-system-model.py")


class AudioRefresh(unittest.TestCase):
    def test_pcm_and_bitstream_selection_refresh_parent_immediately(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw); install = home / "install"; install.mkdir()
            for name in ("openhtpc-playback-policy.py", "openhtpc-playback-setting"):
                shutil.copy2(PAYLOAD / name, install / name)
            (install / "openhtpc-playback-setting").chmod(0o755)
            config = home / ".config/openhtpc"; config.mkdir(parents=True)
            flex = config / "flex-v1.ini"
            flex.write_text("[SYSTEM_AUDIO]\nEntry1=MODE AUDIO : PCM;i;:submenu AUDIO_OUTPUT_MODE\nEntry2=RETOUR;b;:back\n")
            env = {**os.environ, "HOME":str(home), "OPENHTPC_HOME":str(home), "OPENHTPC_INSTALL_DIR":str(install)}
            env.pop("DISPLAY", None); env.pop("WAYLAND_DISPLAY", None)
            for value in ("BITSTREAM", "PCM"):
                subprocess.run([str(install / "openhtpc-playback-setting"), "audio_output_mode", value], env=env, check=True)
                self.assertEqual(policy.read_preferences(home)["audio_output_mode"], value)
                self.assertIn(f"MODE AUDIO : {value}", flex.read_text())

    def test_audio_refresh_uses_qualified_targeted_renderer(self):
        setting = (PAYLOAD / "openhtpc-playback-setting").read_text()
        action = (PAYLOAD / "openhtpc-system-action").read_text()
        self.assertIn('"audio" if sys.argv[1] == "audio_output_mode" else "playback"', setting)
        self.assertIn('(("system-audio.png","audio"),) if audio_only', action)


class DvdObservation(unittest.TestCase):
    def test_dvd_runtime_emits_requested_and_observed_policy(self):
        source = (PAYLOAD / "openhtpc-play-dvd").read_text()
        self.assertIn("--log-file=\"$dvd_attempt\"", source)
        self.assertIn("record_audio_observation", source)
        self.assertIn("--event AUDIO_POLICY", source)
        self.assertIn("--event AUDIO_POLICY_OBSERVED", source)
        self.assertIn('"$INSTALL/openhtpc-system-action" audio', source)

    def test_real_dvd_dispatch_records_observed_runtime_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw); home = base / "home"; install = base / "install"; fakebin = base / "bin"
            install.mkdir(); fakebin.mkdir(); (home / ".config/openhtpc/runtime/mpv").mkdir(parents=True)
            state_dir = home / ".local/state/openhtpc"; state_dir.mkdir(parents=True)
            runtime = home / ".config/openhtpc/runtime/mpv/pure.conf"; runtime.write_text("# fixture\n")
            (home / ".config/openhtpc/profile.json").write_text(json.dumps({"runtime":{"status":"ready"},"runtime_profiles":{"profiles":{"PURE":{"generation_status":"generated","config_path":str(runtime)}}}}))
            (state_dir / "optical-current.json").write_text(json.dumps({"state":"DVD","device":"/dev/fixture","generation":1,"physical_edition":{"audio":[{"format":"ac3","langcode":"en"}]}}))
            policy.write_preference(home, "audio_output_mode", "BITSTREAM")
            for name in ("openhtpc-play-dvd", "openhtpc-playback-policy.py"):
                shutil.copy2(PAYLOAD / name, install / name); (install / name).chmod(0o755)
            events = base / "events.log"
            helper = install / "openhtpc-runtime.py"; helper.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >>"{events}"\n'); helper.chmod(0o755)
            mpv = fakebin / "mpv"; mpv.write_text('#!/bin/sh\nfor arg in "$@"; do case "$arg" in --log-file=*) printf "AO: [pipewire] 48000Hz stereo 2ch spdif-ac3\\n" >"${arg#--log-file=}";; esac; done\nexit 0\n'); mpv.chmod(0o755)
            env = {**os.environ, "HOME":str(home), "OPENHTPC_HOME":str(home), "OPENHTPC_INSTALL_DIR":str(install), "OPENHTPC_FLEX_RETAINED":"1", "PATH":f"{fakebin}:{os.environ['PATH']}"}
            subprocess.run([str(install / "openhtpc-play-dvd"), "/dev/fixture"], env=env, check=True)
            observed = json.loads((state_dir / "audio-policy-last.json").read_text())
            self.assertEqual((observed["requested"], observed["passthrough"], observed["source_codec"]), ("BITSTREAM", "ACTIVE", "AC3"))
            logged = events.read_text(); self.assertIn("AUDIO_POLICY", logged); self.assertIn("AUDIO_POLICY_OBSERVED", logged)

    def test_dvd_bitstream_proof_writes_active_observation(self):
        decision = {"audio_output":{"requested":"BITSTREAM","source_codec":"AC3","reason":"passthrough_candidate","audio_spdif":"ac3,eac3,dts,dts-hd,truehd"}}
        with tempfile.TemporaryDirectory() as raw:
            observed = policy.record_audio_observation(pathlib.Path(raw), decision, "AO: [pipewire] 48000Hz stereo 2ch spdif-ac3")
            self.assertEqual(observed["passthrough"], "ACTIVE")
            self.assertEqual(json.loads((pathlib.Path(raw)/".local/state/openhtpc/audio-policy-last.json").read_text())["resolved"], "BITSTREAM")

    def test_no_mpv_audio_evidence_stays_unknown(self):
        decision = {"audio_output":{"requested":"BITSTREAM","source_codec":"AC3","reason":"passthrough_candidate","audio_spdif":"qualified"}}
        with tempfile.TemporaryDirectory() as raw:
            observed = policy.record_audio_observation(pathlib.Path(raw), decision, "Video: fixture only")
            self.assertEqual(observed["passthrough"], "UNKNOWN")
            self.assertEqual(observed["resolved"], "UNKNOWN")

    def test_dvd_codec_uses_existing_lsdvd_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw); policy.write_preference(home, "audio_output_mode", "BITSTREAM")
            optical = {"physical_edition":{"audio":[{"format":"ac3","langcode":"en"}]}}
            decision = policy.resolve(home, kind="dvd", optical_state=optical)
            self.assertEqual(decision["audio_output"]["source_codec"], "AC3")


class AudioTruthAndDock(unittest.TestCase):
    @staticmethod
    def build_audio(home, requested):
        policy.write_preference(home, "audio_output_mode", requested)
        health = {"capabilities":{"available":True,"audio":{"default_sink":"HDMI","backend":"PipeWire","connection_class":"HDMI","channels":"8"}}}
        return model.build(home, PAYLOAD, health, {"version":"test","build_id":"test"})["audio_section"]

    def test_active_inactive_and_absent_observation_truth(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            self.assertEqual(self.build_audio(home, "PCM")["passthrough"], "Inactif")
            self.assertEqual(self.build_audio(home, "BITSTREAM")["passthrough"], "Indéterminé")
            decision = {"audio_output":{"requested":"BITSTREAM","source_codec":"AC3","reason":"passthrough_candidate","audio_spdif":"qualified"}}
            policy.record_audio_observation(home, decision, "AO: [pipewire] stereo 2ch spdif-ac3")
            self.assertEqual(self.build_audio(home, "BITSTREAM")["passthrough"], "Actif")
            history = (home / ".local/state/openhtpc/audio-policy-last.json").read_text()
            self.assertEqual(self.build_audio(home, "PCM")["passthrough"], "Inactif")
            self.assertEqual((home / ".local/state/openhtpc/audio-policy-last.json").read_text(), history)
            decision["audio_output"]["requested"] = "PCM"
            policy.record_audio_observation(home, decision, "AO: [pipewire] 48000Hz 5.1 6ch floatp")
            self.assertEqual(self.build_audio(home, "PCM")["passthrough"], "Inactif")

    def test_audio_selector_uses_qualified_bottom_dock_without_overlap(self):
        source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text()
        self.assertIn('strcmp(name, "AUDIO_OUTPUT_MODE") == 0', source)
        self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100", source)
        self.assertIn("int safety_margin = (geo.screen_height * 1) / 100", source)


if __name__ == "__main__": unittest.main()
