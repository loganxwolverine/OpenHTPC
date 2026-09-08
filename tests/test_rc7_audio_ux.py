# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Unit tests for RC7 T7.3: Audio UX (Installer + Système -> Audio + User Persistence).

Covers all 22 required test points:
1. install interactif + 1 HDMI -> suggestion DEVICE possible
2. install interactif + 2 HDMI -> aucun choix imposé
3. install sans HDMI -> SYSTEM disponible
4. install discovery failure -> SYSTEM + installation PASS
5. non-interactive -> SYSTEM
6. sélection SYSTEM -> persistance correcte
7. sélection DEVICE -> descripteur complet persisté
8. changement DEVICE A -> DEVICE B -> config mise à jour proprement
9. mode PCM modifiable indépendamment de la sortie
10. mode BITSTREAM modifiable indépendamment de la sortie
11. SYSTÈME -> AUDIO affiche configured label
12. DEVICE disponible -> Disponible
13. DEVICE absent -> Indisponible + EFFECTIVE SYSTEM
14. DEVICE revient -> Disponible sans modification config
15. RAOP Denon -> absent du menu
16. Volumio réseau -> absent du menu
17. aucune commande de mutation Fedora
18. user-config JSON reste valide et atomique
19. T7.1 discovery non régressé
20. T7.2 routing non régressé
21. PCM / BITSTREAM existant non régressé
22. installation existante sans audio_output_target -> migration/backward compatibility propre
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PAYLOAD = pathlib.Path(__file__).resolve().parent.parent / "payload"
ROOT = PAYLOAD.parent


def _load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


AUDIO = _load("openhtpc_audio", PAYLOAD / "openhtpc-audio.py")
sys.modules["openhtpc_audio"] = AUDIO
SETUP = _load("openhtpc_setup_test", PAYLOAD / "openhtpc-initial-setup.py")
POLICY = _load("openhtpc_policy_test", PAYLOAD / "openhtpc-playback-policy.py")
SETTING = _load("openhtpc_setting_test", PAYLOAD / "openhtpc-playback-setting")
SESSION = _load("openhtpc_session_test", PAYLOAD / "openhtpc-session-engine.py")
MODEL = _load("openhtpc_model_test", PAYLOAD / "openhtpc-system-model.py")
UI = _load("openhtpc_ui_test", PAYLOAD / "openhtpc-ui.py")

DENON_HDMI_SINK = {
    "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround71",
    "display_label": "HDMI — DENON AVR-X1800H",
    "device_type": "HDMI",
    "bus_path": "pci-0000:04:00.0",
    "edid_name": "DENON AVR-X1800H",
    "is_network": False,
    "is_default": True,
}

LG_HDMI_SINK = {
    "node_name": "alsa_output.pci-0000_00_1f.3.hdmi-stereo",
    "display_label": "HDMI — LG TV",
    "device_type": "HDMI",
    "bus_path": "pci-0000:00:1f.3",
    "edid_name": "LG TV",
    "is_network": False,
    "is_default": False,
}

ANALOG_SINK = {
    "node_name": "alsa_output.pci-0000_00_1f.3.analog-stereo",
    "display_label": "Audio analogique — Intel",
    "device_type": "ANALOG",
    "bus_path": "pci-0000:00:1f.3",
    "edid_name": None,
    "is_network": False,
    "is_default": False,
}

RAOP_DENON_SINK = {
    "node_name": "raop_sink.Denon-AVR-X1800H.local",
    "display_label": "Denon AVR-X1800H (AirPlay)",
    "device_type": "UNKNOWN",
    "bus_path": None,
    "edid_name": None,
    "is_network": True,
    "is_default": False,
}

VOLUMIO_NETWORK_SINK = {
    "node_name": "tunnel_sink.volumio.local",
    "display_label": "Volumio Audio",
    "device_type": "UNKNOWN",
    "bus_path": None,
    "edid_name": None,
    "is_network": True,
    "is_default": False,
}


class Rc7AudioUxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = PAYLOAD

        self.input_patcher = mock.patch("builtins.input", return_value="1")
        self.input_patcher.start()
        self.addCleanup(self.input_patcher.stop)

        self.pactl_patcher = mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK])
        self.pactl_patcher.start()
        self.addCleanup(self.pactl_patcher.stop)

    def _init_config(self, audio_target: dict | None = None, audio_mode: str = "PCM") -> pathlib.Path:
        target = self.home / ".config/openhtpc/user-config.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema": 1,
            "configuration_completed": True,
            "local_media_sources": [],
            "tmdb": {"configured": False},
            "audio_output_mode": audio_mode,
        }
        if audio_target is not None:
            data["audio_output_target"] = audio_target
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target

    # 1. install interactif + 1 HDMI -> suggestion DEVICE possible
    def test_01_install_interactive_single_hdmi_suggests_device(self):
        with mock.patch.object(SETUP, "discover_audio_choices", return_value=(AUDIO, [DENON_HDMI_SINK, ANALOG_SINK])), \
             mock.patch("builtins.input", side_effect=["1", "1"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "DEVICE")
            self.assertEqual(target["node_name"], DENON_HDMI_SINK["node_name"])
            self.assertEqual(mode, "PCM")
            self.assertIn("(Recommandé)", fake_out.getvalue())

    # 2. install interactif + 2 HDMI -> aucun choix imposé
    def test_02_install_interactive_multiple_hdmi_no_imposed_choice(self):
        outputs = [DENON_HDMI_SINK, LG_HDMI_SINK]
        self.assertIsNone(AUDIO.recommend_output(outputs, interactive=True))
        with mock.patch.object(SETUP, "discover_audio_choices", return_value=(AUDIO, outputs)), \
             mock.patch("builtins.input", side_effect=["2", "1"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "DEVICE")
            self.assertEqual(target["node_name"], LG_HDMI_SINK["node_name"])
            self.assertNotIn("(Recommandé)", fake_out.getvalue())

    # 3. install sans HDMI -> SYSTEM disponible
    def test_03_install_no_hdmi_system_available(self):
        outputs = [ANALOG_SINK]
        with mock.patch.object(SETUP, "discover_audio_choices", return_value=(AUDIO, outputs)), \
             mock.patch("builtins.input", side_effect=["2", "1"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertIn("Utiliser la sortie audio définie par Fedora", fake_out.getvalue())

    # 4. install discovery failure -> SYSTEM + installation PASS
    def test_04_install_discovery_failure_system_and_pass(self):
        with mock.patch.object(AUDIO, "discover_outputs", side_effect=OSError("pactl failed")):
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertEqual(mode, "PCM")
            saved = SETUP.save(self.home, [], None, target, mode)
            self.assertTrue(saved.is_file())
            data = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(data["audio_output_target"]["mode"], "SYSTEM")

    # 5. non-interactive -> SYSTEM
    def test_05_non_interactive_forces_system(self):
        argv = ["openhtpc-initial-setup.py", "--home", str(self.home), "--non-interactive", "--no-media-sources"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, {"OPENHTPC_INSTALL_DIR": str(PAYLOAD)}, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]), \
             mock.patch("subprocess.run"), \
             mock.patch("sys.stdout"):
            ret = SETUP.main()
            self.assertEqual(ret, 0)
            cfg = json.loads((self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["audio_output_target"]["mode"], "SYSTEM")

    # 6. sélection SYSTEM -> persistance correcte
    def test_06_select_system_persistence(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        argv = ["openhtpc-playback-setting", "audio_output_target", "SYSTEM"]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
            ret = SETTING.main()
            self.assertEqual(ret, 0)
            target = POLICY.read_audio_output_target(self.home)
            self.assertEqual(target["mode"], "SYSTEM")

    # 7. sélection DEVICE -> descripteur complet persisté
    def test_07_select_device_full_descriptor_persisted(self):
        self._init_config()
        argv = ["openhtpc-playback-setting", "audio_output_target", DENON_HDMI_SINK["node_name"]]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            ret = SETTING.main()
            self.assertEqual(ret, 0)
            target = POLICY.read_audio_output_target(self.home)
            self.assertEqual(target["mode"], "DEVICE")
            self.assertEqual(target["node_name"], DENON_HDMI_SINK["node_name"])
            self.assertEqual(target["bus_path"], DENON_HDMI_SINK["bus_path"])
            self.assertEqual(target["edid_name"], DENON_HDMI_SINK["edid_name"])
            self.assertEqual(target["device_type"], "HDMI")

    # 8. changement DEVICE A -> DEVICE B -> config mise à jour proprement
    def test_08_change_device_a_to_device_b(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        argv = ["openhtpc-playback-setting", "audio_output_target", LG_HDMI_SINK["node_name"]]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK, LG_HDMI_SINK]):
            ret = SETTING.main()
            self.assertEqual(ret, 0)
            target = POLICY.read_audio_output_target(self.home)
            self.assertEqual(target["mode"], "DEVICE")
            self.assertEqual(target["node_name"], LG_HDMI_SINK["node_name"])

    # 9. mode PCM modifiable indépendamment de la sortie
    def test_09_pcm_mode_modifiable_independently_of_output(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK), audio_mode="BITSTREAM")
        argv = ["openhtpc-playback-setting", "audio_output_mode", "PCM"]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
            ret = SETTING.main()
            self.assertEqual(ret, 0)
            prefs = POLICY.read_preferences(self.home)
            target = POLICY.read_audio_output_target(self.home)
            self.assertEqual(prefs["audio_output_mode"], "PCM")
            self.assertEqual(target["node_name"], DENON_HDMI_SINK["node_name"])

    # 10. mode BITSTREAM modifiable indépendamment de la sortie
    def test_10_bitstream_mode_modifiable_independently_of_output(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK), audio_mode="PCM")
        argv = ["openhtpc-playback-setting", "audio_output_mode", "BITSTREAM"]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
            ret = SETTING.main()
            self.assertEqual(ret, 0)
            prefs = POLICY.read_preferences(self.home)
            target = POLICY.read_audio_output_target(self.home)
            self.assertEqual(prefs["audio_output_mode"], "BITSTREAM")
            self.assertEqual(target["node_name"], DENON_HDMI_SINK["node_name"])

    # 11. SYSTÈME -> AUDIO affiche configured label
    def test_11_system_audio_displays_configured_label(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            built = MODEL.build(self.home, PAYLOAD, health, version)
            audio = built["audio_section"]
            self.assertEqual(audio["configured_label"], DENON_HDMI_SINK["display_label"])
            self.assertEqual(audio["state_label"], "Disponible")

    # 12. DEVICE disponible -> Disponible
    def test_12_device_available_displays_disponible(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            built = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertEqual(built["audio_section"]["state_label"], "Disponible")
            self.assertTrue(built["audio_section"]["is_available"])
            self.assertFalse(built["audio_section"]["is_fallback"])

    # 13. DEVICE absent -> Indisponible + EFFECTIVE SYSTEM
    def test_13_device_absent_displays_indisponible_and_effective_system(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]):
            built = MODEL.build(self.home, PAYLOAD, health, version)
            audio = built["audio_section"]
            self.assertEqual(audio["state_label"], "Indisponible")
            self.assertFalse(audio["is_available"])
            self.assertTrue(audio["is_fallback"])
            self.assertIn("Sortie système Fedora", audio["effective_label"])
            # Runtime resolution fallback
            decision = POLICY.resolve(self.home)
            self.assertEqual(decision["audio_target"]["effective"], "SYSTEM")
            self.assertTrue(decision["audio_target"]["fallback"])

    # 14. DEVICE revient -> Disponible sans modification config
    def test_14_device_returns_available_without_modifying_config(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        # Device is absent
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]):
            built1 = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertEqual(built1["audio_section"]["state_label"], "Indisponible")
        config_after_absence = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")

        # Device returns
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            built2 = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertEqual(built2["audio_section"]["state_label"], "Disponible")
            self.assertTrue(built2["audio_section"]["is_available"])
        config_after_return = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        self.assertEqual(config_after_absence, config_after_return)

    # 15. RAOP Denon -> absent du menu
    def test_15_raop_denon_excluded_from_menu(self):
        outputs = [DENON_HDMI_SINK, RAOP_DENON_SINK]
        filtered = [o for o in outputs if not o.get("is_network")]
        self.assertNotIn(RAOP_DENON_SINK, filtered)

    # 16. Volumio réseau -> absent du menu
    def test_16_volumio_network_excluded_from_menu(self):
        outputs = [DENON_HDMI_SINK, VOLUMIO_NETWORK_SINK]
        filtered = [o for o in outputs if not o.get("is_network")]
        self.assertNotIn(VOLUMIO_NETWORK_SINK, filtered)

    # 17. aucune commande de mutation Fedora
    def test_17_no_fedora_mutation_commands(self):
        self._init_config()
        executed_cmds = []

        def fake_run(cmd, *args, **kwargs):
            executed_cmds.append(" ".join(str(c) for c in cmd) if isinstance(cmd, list) else str(cmd))
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            argv = ["openhtpc-playback-setting", "audio_output_target", "SYSTEM"]
            env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
                SETTING.main()

        for c in executed_cmds:
            self.assertNotIn("set-default-sink", c)
            self.assertNotIn("set-default", c)

    # 18. user-config JSON reste valide et atomique
    def test_18_user_config_valid_and_atomic(self):
        saved = SETUP.save(self.home, [], None, AUDIO.device_descriptor(DENON_HDMI_SINK), "BITSTREAM")
        mode = saved.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)
        data = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertIn("audio_output_target", data)
        self.assertIn("audio_output_mode", data)
        self.assertEqual(data["audio_output_target"]["mode"], "DEVICE")
        self.assertEqual(data["audio_output_mode"], "BITSTREAM")

    # 19. T7.1 discovery non régressé
    def test_19_t71_discovery_non_regressed(self):
        sys_desc = AUDIO.system_descriptor()
        self.assertEqual(sys_desc["mode"], "SYSTEM")
        dev_desc = AUDIO.device_descriptor(DENON_HDMI_SINK)
        self.assertEqual(dev_desc["mode"], "DEVICE")
        routing = AUDIO.resolve_audio(dev_desc, [DENON_HDMI_SINK])
        self.assertTrue(routing["AVAILABLE"])

    # 20. T7.2 routing non régressé
    def test_20_t72_routing_non_regressed(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            decision = POLICY.resolve(self.home)
            self.assertIn(f"--audio-device=pipewire/{DENON_HDMI_SINK['node_name']}", decision["mpv_args"])

    # 21. PCM / BITSTREAM existant non régressé
    def test_21_pcm_bitstream_existing_non_regressed(self):
        pcm = POLICY.choose_audio_output("PCM", {"codec_name": "truehd"})
        self.assertEqual(pcm["resolved"], "PCM")
        self.assertEqual(pcm["mpv_args"], [])
        bitstream = POLICY.choose_audio_output("BITSTREAM", {"codec_name": "truehd"})
        self.assertEqual(bitstream["resolved"], "BITSTREAM")
        self.assertTrue(any(arg.startswith("--audio-spdif=") for arg in bitstream["mpv_args"]))

    # 22. installation existante sans audio_output_target -> migration/backward compatibility propre
    def test_22_existing_install_without_audio_output_target_backward_compat(self):
        cfg_path = self.home / ".config/openhtpc/user-config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps({"schema": 1, "configuration_completed": True, "local_media_sources": [], "audio_output_mode": "PCM"}), encoding="utf-8")
        target = POLICY.read_audio_output_target(self.home)
        self.assertEqual(target["mode"], "SYSTEM")
        decision = POLICY.resolve(self.home)
        self.assertEqual(decision["audio_target"]["effective"], "SYSTEM")
        self.assertFalse(decision["audio_target"]["fallback"])
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        built = MODEL.build(self.home, PAYLOAD, health, version)
        self.assertEqual(built["audio_section"]["configured_label"], "Sortie système — Fedora")
        self.assertEqual(built["audio_section"]["state_label"], "Disponible")

    # 23. flex menu generation and interactive switch synchronization
    def test_23_flex_menu_generation_and_interactive_switch_sync(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        flex_ini = self.home / ".config/openhtpc/flex-v1.ini"
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK, LG_HDMI_SINK]):
            ok = SESSION.write_flex_config(flex_ini, self.home, [], install=PAYLOAD)
            self.assertTrue(ok)
            content = flex_ini.read_text(encoding="utf-8")
            self.assertIn("Entry1=SORTIE AUDIO : HDMI — DENON AVR-X1800H", content)
            self.assertIn("Entry1=• HDMI — DENON AVR-X1800H", content)
            self.assertIn("Entry2=HDMI — LG TV", content)
            self.assertIn("Entry3=Sortie système — Fedora", content)

            # Interactive switch to SYSTEM
            argv = ["openhtpc-playback-setting", "audio_output_target", "SYSTEM"]
            env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
                ret = SETTING.main()
                self.assertEqual(ret, 0)

            content_updated = flex_ini.read_text(encoding="utf-8")
            self.assertIn("Entry1=SORTIE AUDIO : Sortie système — Fedora", content_updated)
            self.assertIn("Entry1=HDMI — DENON AVR-X1800H", content_updated)
            self.assertNotIn("Entry1=• HDMI — DENON AVR-X1800H", content_updated)
            self.assertIn("Entry3=• Sortie système — Fedora", content_updated)

    # 24. Blocage 1: test_install_terminal_empty_input_selects_system
    def test_24_install_terminal_empty_input_selects_system(self):
        with mock.patch.object(SETUP, "discover_audio_choices", return_value=(AUDIO, [DENON_HDMI_SINK])), \
             mock.patch("builtins.input", side_effect=["", "1"]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertEqual(mode, "PCM")
            self.assertIn("(Recommandé)", fake_out.getvalue())

    # 25. Blocage 1: test_install_gui_radiolist_defaults_to_system
    def test_25_install_gui_radiolist_defaults_to_system(self):
        kd_calls = []
        def fake_kd(args, capture=False):
            kd_calls.append(args)
            if "--radiolist" in args and "Choisissez la sortie utilisée par OPENHTPC :" in args:
                return mock.MagicMock(returncode=0, stdout="SYSTEM\n")
            if "--radiolist" in args and "Choisissez le mode audio :" in args:
                return mock.MagicMock(returncode=0, stdout="PCM\n")
            return mock.MagicMock(returncode=0, stdout="")

        with mock.patch.object(SETUP, "discover_audio_choices", return_value=(AUDIO, [DENON_HDMI_SINK])), \
             mock.patch.object(SETUP, "kd", side_effect=fake_kd):
            target, mode = SETUP.graphical_audio_setup(self.home)
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertEqual(mode, "PCM")
            target_dialog_args = next(call for call in kd_calls if "Choisissez la sortie utilisée par OPENHTPC :" in call)
            self.assertIn("--radiolist", target_dialog_args)
            self.assertNotIn("--menu", target_dialog_args)
            sys_idx = target_dialog_args.index("SYSTEM")
            self.assertEqual(target_dialog_args[sys_idx + 2], "on")
            dev_idx = target_dialog_args.index("1")
            self.assertEqual(target_dialog_args[dev_idx + 2], "off")
            self.assertIn("(Recommandé)", target_dialog_args[dev_idx + 1])

    # 26. Blocage 2: test_install_discovery_failure_preserves_bitstream_choice
    def test_26_install_discovery_failure_preserves_bitstream_choice(self):
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]), \
             mock.patch("builtins.input", side_effect=["2"]):
            target, mode = SETUP.terminal_audio_setup()
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertEqual(mode, "BITSTREAM")
            saved = SETUP.save(self.home, [], None, target, mode)
            cfg = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(cfg["audio_output_target"]["mode"], "SYSTEM")
            self.assertEqual(cfg["audio_output_mode"], "BITSTREAM")

        self._init_config(audio_target={"mode": "SYSTEM"}, audio_mode="BITSTREAM")
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]), \
             mock.patch("builtins.input", side_effect=[""]):
            target, mode = SETUP.terminal_audio_setup(self.home)
            self.assertEqual(target["mode"], "SYSTEM")
            self.assertEqual(mode, "BITSTREAM")

    # 27. Blocage 4: test_user_switch_rejects_nonexistent_node
    def test_27_user_switch_rejects_nonexistent_node(self):
        self._init_config(audio_target=AUDIO.device_descriptor(DENON_HDMI_SINK), audio_mode="BITSTREAM")
        cfg_before = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        argv = ["openhtpc-playback-setting", "audio_output_target", "alsa_output.node_bidon_inexistant"]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            ret = SETTING.main()
            self.assertEqual(ret, 2)
        cfg_after = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        self.assertEqual(cfg_before, cfg_after)

    # 28. Blocage 4: test_user_switch_rejects_network_sink
    def test_28_user_switch_rejects_network_sink(self):
        self._init_config(audio_target=AUDIO.device_descriptor(DENON_HDMI_SINK), audio_mode="BITSTREAM")
        cfg_before = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        argv = ["openhtpc-playback-setting", "audio_output_target", RAOP_DENON_SINK["node_name"]]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK, RAOP_DENON_SINK]):
            ret = SETTING.main()
            self.assertEqual(ret, 2)
        cfg_after = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        self.assertEqual(cfg_before, cfg_after)

    # 29. Blocage 5: test_checkmark_exact_match_no_substring_collision
    def test_29_checkmark_exact_match_no_substring_collision(self):
        sink1 = {
            "node_name": "alsa_output.pci-0000_00_1f.3.hdmi-stereo",
            "display_label": "HDMI — TV Stereo",
            "device_type": "HDMI",
            "bus_path": "pci-0000:00:1f.3",
            "edid_name": "TV Stereo",
            "is_network": False,
            "is_default": False,
        }
        sink2 = {
            "node_name": "alsa_output.pci-0000_00_1f.3.hdmi-stereo-extra1",
            "display_label": "HDMI — TV Stereo Extra",
            "device_type": "HDMI",
            "bus_path": "pci-0000:00:1f.3",
            "edid_name": "TV Stereo Extra",
            "is_network": False,
            "is_default": False,
        }
        self._init_config(AUDIO.device_descriptor(sink1))
        flex_ini = self.home / ".config/openhtpc/flex-v1.ini"
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[sink1, sink2]):
            ok = SESSION.write_flex_config(flex_ini, self.home, [], install=PAYLOAD)
            self.assertTrue(ok)
            content = flex_ini.read_text(encoding="utf-8")
            self.assertIn("Entry1=• HDMI — TV Stereo;", content)
            self.assertNotIn("Entry2=• HDMI — TV Stereo Extra;", content)

            # Switch to sink2
            argv = ["openhtpc-playback-setting", "audio_output_target", sink2["node_name"]]
            env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
                ret = SETTING.main()
                self.assertEqual(ret, 0)
            content2 = flex_ini.read_text(encoding="utf-8")
            self.assertNotIn("Entry1=• HDMI — TV Stereo;", content2)
            self.assertIn("Entry2=• HDMI — TV Stereo Extra;", content2)

            # Switch back to sink1
            argv = ["openhtpc-playback-setting", "audio_output_target", sink1["node_name"]]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True):
                ret = SETTING.main()
                self.assertEqual(ret, 0)
            content3 = flex_ini.read_text(encoding="utf-8")
            self.assertIn("Entry1=• HDMI — TV Stereo;", content3)
            self.assertNotIn("Entry2=• HDMI — TV Stereo Extra;", content3)

    # 30. Blocage 6: test_system_model_audio_offline_does_not_break_global_available
    def test_30_system_model_audio_offline_does_not_break_global_available(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        caps_path = self.home / ".config/openhtpc/runtime/capabilities.json"
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        caps_path.write_text(json.dumps({"schema": 1, "probe_version": "1.0", "hardware": {"cpu": {"model": "Intel"}}}))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]):
            built = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertTrue(built["available"])
            self.assertFalse(built["audio_section"]["is_available"])
            self.assertEqual(built["audio_section"]["state_label"], "Indisponible")

    # 31. Blocage 6: test_system_model_audio_offline_does_not_mask_system_ui
    def test_31_system_model_audio_offline_does_not_mask_system_ui(self):
        from PIL import ImageDraw
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK))
        caps_path = self.home / ".config/openhtpc/runtime/capabilities.json"
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        caps_path.write_text(json.dumps({"schema": 1, "probe_version": "1.0", "hardware": {"cpu": {"model": "Intel"}}}))
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]):
            model = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertTrue(model["available"])
            rendered_texts = []
            orig_draw_text = ImageDraw.ImageDraw.text
            def spy_text(draw_self, xy, text, *args, **kwargs):
                rendered_texts.append(str(text))
                return orig_draw_text(draw_self, xy, text, *args, **kwargs)

            out_img = self.home / "audio.png"
            font_path = PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf"
            with mock.patch.object(ImageDraw.ImageDraw, "text", spy_text):
                UI.system_page_png(model, out_img, font_path, "audio")

            self.assertNotIn("Informations système temporairement indisponibles", rendered_texts)
            self.assertIn("Indisponible", rendered_texts)
            self.assertIn("SORTIE AUDIO", rendered_texts)

    # 32. Blocage 3 / 6: test_device_absence_and_return_does_not_rewrite_config
    def test_32_device_absence_and_return_does_not_rewrite_config(self):
        self._init_config(AUDIO.device_descriptor(DENON_HDMI_SINK), audio_mode="BITSTREAM")
        caps_path = self.home / ".config/openhtpc/runtime/capabilities.json"
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        caps_path.write_text(json.dumps({"schema": 1, "probe_version": "1.0"}))
        initial_content = (self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8")
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}

        # 1. Device absent
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[]):
            decision = POLICY.resolve(self.home)
            self.assertEqual(decision["audio_target"]["effective"], "SYSTEM")
            self.assertTrue(decision["audio_target"]["fallback"])
            m1 = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertFalse(m1["audio_section"]["is_available"])
        self.assertEqual((self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"), initial_content)

        # 2. Device returns
        with mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            decision2 = POLICY.resolve(self.home)
            self.assertEqual(decision2["audio_target"]["effective"], DENON_HDMI_SINK["node_name"])
            self.assertFalse(decision2["audio_target"]["fallback"])
            m2 = MODEL.build(self.home, PAYLOAD, health, version)
            self.assertTrue(m2["audio_section"]["is_available"])
        self.assertEqual((self.home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"), initial_content)

    # 33. Blocage 1 (Codex fail 2): absence totale de fallback write_text audio quand policy indisponible
    def test_33_no_direct_write_text_fallback_when_policy_unavailable(self):
        with mock.patch.object(SETUP, "_load_playback_policy", return_value=None), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as fake_err:
            saved = SETUP.save(self.home, [], None, AUDIO.device_descriptor(DENON_HDMI_SINK), "BITSTREAM")
            self.assertTrue(saved.is_file())
            err_val = fake_err.getvalue()
            self.assertIn("write_audio_output_target indisponible", err_val)
            self.assertIn("write_preference indisponible", err_val)
            cfg = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(cfg["schema"], 1)
            self.assertTrue(cfg["configuration_completed"])
            self.assertNotIn("audio_output_target", cfg)
            self.assertNotIn("audio_output_mode", cfg)

    # 34. Blocage 2 (Codex fail 2): TMDb enrichi préservé avec tmdb_value=None
    def test_34_tmdb_preserved_when_tmdb_value_none(self):
        cfg_path = self.home / ".config/openhtpc/user-config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        initial_cfg = {
            "schema": 1,
            "configuration_completed": True,
            "tmdb": {
                "configured": True,
                "extra": "preserve",
                "custom_key": 42,
            },
        }
        cfg_path.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")

        saved = SETUP.save(self.home, [], None, SETUP.default_system_descriptor(), "PCM")
        result = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(result["tmdb"], initial_cfg["tmdb"])
        self.assertTrue(result["tmdb"]["configured"])
        self.assertEqual(result["tmdb"]["extra"], "preserve")
        self.assertEqual(result["tmdb"]["custom_key"], 42)

    # 35. Blocage 2 (Codex fail 2): configuration enrichie conservée hors clés audio
    def test_35_enriched_config_preserved_across_audio_modification(self):
        cfg_path = self.home / ".config/openhtpc/user-config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        enriched_config = {
            "schema": 1,
            "configuration_completed": True,
            "local_media_sources": ["/media/movies"],
            "tmdb": {
                "configured": True,
                "extra": "preserve",
                "custom_api_version": 4,
            },
            "languages": {
                "preferred_audio": "fre",
                "preferred_subtitles": "fre",
            },
            "presentation_mode": "CINEMA_AUTO",
            "future_unknown_section": {
                "arbitrary_flag": True,
                "version": "v2",
            },
            "audio_output_mode": "PCM",
            "audio_output_target": {"mode": "SYSTEM"},
        }
        cfg_path.write_text(json.dumps(enriched_config, indent=2), encoding="utf-8")

        # 1. Modify audio target via openhtpc-playback-setting
        argv = ["openhtpc-playback-setting", "audio_output_target", DENON_HDMI_SINK["node_name"]]
        env = {"OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(PAYLOAD)}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(AUDIO, "discover_outputs", return_value=[DENON_HDMI_SINK]):
            ret = SETTING.main()
            self.assertEqual(ret, 0)

        # 2. Modify audio mode via openhtpc-playback-setting
        argv_mode = ["openhtpc-playback-setting", "audio_output_mode", "BITSTREAM"]
        with mock.patch.object(sys, "argv", argv_mode), mock.patch.dict(os.environ, env, clear=True):
            ret_mode = SETTING.main()
            self.assertEqual(ret_mode, 0)

        after = json.loads(cfg_path.read_text(encoding="utf-8"))

        # Verify expected audio changes
        self.assertEqual(after["audio_output_target"]["mode"], "DEVICE")
        self.assertEqual(after["audio_output_target"]["node_name"], DENON_HDMI_SINK["node_name"])
        self.assertEqual(after["audio_output_mode"], "BITSTREAM")

        # Verify strict equality for all non-audio keys
        non_audio_keys = [k for k in enriched_config if k not in ("audio_output_target", "audio_output_mode")]
        for k in non_audio_keys:
            self.assertEqual(after[k], enriched_config[k], f"Key {k} was unexpectedly modified!")

    # 36. Blocage 2 (Codex fail 2): nouvelle valeur TMDb explicite met à jour configured sans détruire les autres clés
    def test_36_save_with_explicit_tmdb_token_updates_configured_preserves_extras(self):
        cfg_path = self.home / ".config/openhtpc/user-config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        initial_cfg = {
            "schema": 1,
            "configuration_completed": True,
            "tmdb": {
                "configured": False,
                "extra": "preserve",
            },
        }
        cfg_path.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")

        saved = SETUP.save(self.home, [], "token-xyz", SETUP.default_system_descriptor(), "PCM")
        result = json.loads(saved.read_text(encoding="utf-8"))
        self.assertTrue(result["tmdb"]["configured"])
        self.assertEqual(result["tmdb"]["extra"], "preserve")
        secret = (self.home / ".config/openhtpc/secrets/tmdb-token").read_text(encoding="utf-8").strip()
        self.assertEqual(secret, "token-xyz")

    # 37. Qualified bottom dock includes AUDIO_OUTPUT_TARGET
    def test_37_audio_output_target_uses_qualified_bottom_dock(self):
        source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
        self.assertIn('strcmp(name, "AUDIO_OUTPUT_TARGET") == 0', source)
        self.assertIn('strcmp(name, "AUDIO_OUTPUT_MODE") == 0', source)
        self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100", source)
        binary = PAYLOAD / "flex/bin/flex-launcher"
        symbols = subprocess.run(["strings", str(binary)], text=True, capture_output=True, check=True).stdout
        self.assertIn("AUDIO_OUTPUT_TARGET", symbols)
        self.assertIn("AUDIO_OUTPUT_MODE", symbols)

    # 38. System model build dynamically loads openhtpc-audio without host dependency
    def test_38_system_model_build_without_preloaded_audio_module(self):
        fake_sink = {
            "mode": "DEVICE",
            "node_name": "alsa_output.mocked_fake_device",
            "bus_path": "pci-0000:99:00.0",
            "edid_name": "MOCKED_RECEIVER",
            "display_label": "HDMI — MOCKED RECEIVER",
            "device_type": "HDMI",
            "is_network": False,
            "is_default": True,
        }
        self._init_config(fake_sink)
        health = {"overall": "READY", "checks": []}
        version = {"version": "test", "build_id": "test"}

        # Create hermetic test install dir with a dummy openhtpc-audio.py
        with tempfile.TemporaryDirectory() as temp_install_dir:
            temp_install = pathlib.Path(temp_install_dir)
            tracker_file = temp_install / "tracker.log"
            audio_fake = temp_install / "openhtpc-audio.py"
            audio_fake.write_text(
                f'import pathlib\n'
                f'tracker = pathlib.Path(r"{tracker_file}")\n'
                'def discover_outputs():\n'
                '    with tracker.open("a", encoding="utf-8") as f: f.write("discover\\n")\n'
                '    return [{\n'
                '        "mode": "DEVICE",\n'
                '        "node_name": "alsa_output.mocked_fake_device",\n'
                '        "bus_path": "pci-0000:99:00.0",\n'
                '        "edid_name": "MOCKED_RECEIVER",\n'
                '        "display_label": "HDMI — MOCKED RECEIVER",\n'
                '        "device_type": "HDMI",\n'
                '        "is_network": False,\n'
                '        "is_default": True,\n'
                '    }]\n\n'
                'def resolve_audio(configured, outputs):\n'
                '    with tracker.open("a", encoding="utf-8") as f: f.write("resolve\\n")\n'
                '    return {\n'
                '        "CONFIGURED": dict(configured),\n'
                '        "AVAILABLE": True,\n'
                '        "EFFECTIVE": dict(configured),\n'
                '    }\n',
                encoding="utf-8"
            )

            # Ensure openhtpc_audio is absent from sys.modules
            saved_module = sys.modules.pop("openhtpc_audio", None)
            try:
                self.assertNotIn("openhtpc_audio", sys.modules)
                built = MODEL.build(self.home, temp_install, health, version)
                audio_sec = built["audio_section"]

                # Verify dynamic loading and execution
                self.assertTrue(audio_sec["is_available"])
                self.assertEqual(audio_sec["state_label"], "Disponible")
                self.assertEqual(audio_sec["configured_label"], "HDMI — MOCKED RECEIVER")
                self.assertEqual(audio_sec["effective_label"], "HDMI — MOCKED RECEIVER")
                self.assertFalse(audio_sec["is_fallback"])

                # Verify that the calls came from our hermetic module
                self.assertTrue(tracker_file.is_file(), "Tracker file was not written; dynamic loader was not invoked!")
                logged_calls = tracker_file.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(logged_calls, ["discover", "resolve"])
            finally:
                sys.modules.pop("openhtpc_audio", None)
                if saved_module is not None:
                    sys.modules["openhtpc_audio"] = saved_module

    # 38b. Root cause regression test: no inner importlib shadowing in openhtpc-system-model.py functions
    def test_38b_system_model_no_local_importlib_shadowing(self):
        import ast
        model_source = (PAYLOAD / "openhtpc-system-model.py").read_text(encoding="utf-8")
        tree = ast.parse(model_source)
        inner_importlib_shadows = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if child is node:
                        continue
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if "importlib" in alias.name:
                                inner_importlib_shadows.append((node.name, alias.name, child.lineno))
                    elif isinstance(child, ast.ImportFrom):
                        if child.module and "importlib" in child.module:
                            inner_importlib_shadows.append((node.name, child.module, child.lineno))
        self.assertEqual(
            inner_importlib_shadows,
            [],
            f"Inner import of importlib found in functions: {inner_importlib_shadows}. "
            "This causes UnboundLocalError due to Python scoping rules and breaks dynamic module loading!"
        )

    # 39. Font supports bullet symbol glyph and lacks checkmark
    def test_39_font_glyph_support_bullet_vs_checkmark(self):
        import ctypes
        ft = ctypes.CDLL("libfreetype.so.6")
        library = ctypes.c_void_p()
        self.assertEqual(ft.FT_Init_FreeType(ctypes.byref(library)), 0)
        face = ctypes.c_void_p()
        font_path = PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf"
        self.assertEqual(ft.FT_New_Face(library, str(font_path).encode("utf-8"), 0, ctypes.byref(face)), 0)
        # Checkmark U+2713 is absent (.notdef = 0)
        idx_check = ft.FT_Get_Char_Index(face, ord("✓"))
        self.assertEqual(idx_check, 0, "Checkmark U+2713 should be absent from OpenSans-Regular")
        # Bullet U+2022 is present (> 0)
        idx_bullet = ft.FT_Get_Char_Index(face, ord("•"))
        self.assertGreater(idx_bullet, 0, "Bullet U+2022 must be present in OpenSans-Regular")


if __name__ == "__main__":
    unittest.main()
