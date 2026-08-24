import importlib.util
import importlib.machinery
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class AudioPassthroughP0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load("audio_policy_p0", ROOT / "payload/openhtpc-playback-policy.py")
        cls.setup = load("audio_setup_p0", ROOT / "payload/openhtpc-initial-setup.py")

    def test_fresh_and_legacy_config_are_safe_pcm(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            self.assertEqual(self.policy.read_preferences(home)["audio_output_mode"], "PCM")
            root = home / ".config/openhtpc"; root.mkdir(parents=True)
            (root / "user-config.json").write_text('{"schema":1,"audio_mode":"Bitstream"}')
            self.assertEqual(self.policy.read_preferences(home)["audio_output_mode"], "PCM")

    def test_pcm_and_bitstream_persist(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            for value in ("PCM", "BITSTREAM", "PCM"):
                self.policy.write_preference(home, "audio_output_mode", value)
                self.assertEqual(self.policy.read_preferences(home)["audio_output_mode"], value)

    def test_pcm_adds_no_passthrough(self):
        value = self.policy.choose_audio_output("PCM", {"codec_name":"truehd"})
        self.assertEqual(value["mpv_args"], [])
        self.assertEqual(value["resolved"], "PCM")

    def test_bitstream_candidates_share_qualified_mpv_policy(self):
        expected = "--audio-spdif=ac3,eac3,dts,dts-hd,truehd"
        for codec in ("ac3", "eac3", "dts", "truehd"):
            with self.subTest(codec=codec):
                value = self.policy.choose_audio_output("BITSTREAM", {"codec_name":codec})
                self.assertEqual(value["mpv_args"], [expected])
                self.assertEqual(value["resolved"], "BITSTREAM")
        self.assertIn("dts-hd", self.policy.PASSTHROUGH_CODECS)

    def test_non_passthrough_codec_decodes_pcm(self):
        for codec in ("aac", "flac", "opus", "pcm_s24le"):
            value = self.policy.choose_audio_output("BITSTREAM", {"codec_name":codec})
            self.assertEqual(value["resolved"], "PCM")
            self.assertEqual(value["reason"], "codec_not_passthrough_candidate")

    def test_initial_setup_writes_pcm_and_preserves_valid_choice(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            self.setup.save(home, [], None)
            target = home / ".config/openhtpc/user-config.json"
            self.assertEqual(json.loads(target.read_text())["audio_output_mode"], "PCM")
            data = json.loads(target.read_text()); data["audio_output_mode"] = "BITSTREAM"; target.write_text(json.dumps(data))
            self.setup.save(home, [], None)
            self.assertEqual(json.loads(target.read_text())["audio_output_mode"], "BITSTREAM")

    def test_observed_state_requires_real_mpv_evidence(self):
        decision = {"audio_output":{"requested":"BITSTREAM","source_codec":"AC3","reason":"passthrough_candidate","audio_spdif":"ac3,eac3,dts,dts-hd,truehd"}}
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            inactive = self.policy.record_audio_observation(home, decision, "AO: [pipewire] 48000Hz 5.1 6ch floatp")
            self.assertEqual(inactive["passthrough"], "INACTIVE")
            active = self.policy.record_audio_observation(home, decision, "AO: [pipewire] 48000Hz stereo 2ch spdif-ac3")
            self.assertEqual(active["passthrough"], "ACTIVE")

    def test_support_bundle_contains_audio_policy_and_pipewire(self):
        text = (ROOT / "payload/openhtpc-support-bundle.py").read_text()
        self.assertIn('audio-policy.json', text)
        self.assertIn('@DEFAULT_AUDIO_SINK@', text)
        self.assertIn('playback-audio-log.txt', text)
        self.assertIn('allowed={"node.description","device.description","media.class","audio.channels","audio.position","audio.format"}', text)

    def test_doctor_config_contract_accepts_both_audio_modes(self):
        session = load("audio_session_contract", ROOT / "payload/openhtpc-session-engine.py")
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            for mode in ("PCM", "BITSTREAM"):
                config = {"configuration_completed":True,"local_media_sources":[],"tmdb":{"configured":False},"audio_output_mode":mode}
                self.assertEqual(session.validate_user_config(config, home / "missing-token"), [])

    def test_installer_no_longer_asks_audio_mode_or_hdr_capability(self):
        text = (ROOT / "payload/openhtpc-builder.sh").read_text()
        self.assertNotIn('ask_choice "Mode audio souhaité :"', text)
        self.assertNotIn('ask_choice "Capacités HDR connues :"', text)
        self.assertIn('audio_mode="PCM"', text)

    def test_about_uses_approved_back_icon(self):
        text = (ROOT / "payload/openhtpc-session-engine.py").read_text()
        section = text.split("[SYSTEM_ABOUT]", 1)[1].split("[DISQUE]", 1)[0]
        self.assertIn("Entry1=RETOUR;{icon_back};:back", section)

    def test_audio_has_direct_system_route_and_binary_selector(self):
        text = (ROOT / "payload/openhtpc-session-engine.py").read_text()
        self.assertIn("Entry5=AUDIO;{icon_audio};:submenu SYSTEM_AUDIO", text)
        self.assertIn("Entry1=PCM;{playback_icons['audio']}", text)
        self.assertIn("Entry2=BITSTREAM;{playback_icons['audio']}", text)


if __name__ == "__main__": unittest.main()
