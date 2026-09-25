# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic tests for RC7 T8.3 System UI Runtime GPU Truth."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
SYSTEM_MODEL_PATH = PAYLOAD / "openhtpc-system-model.py"
UI_PATH = PAYLOAD / "openhtpc-ui.py"
CAPABILITIES_PATH = PAYLOAD / "openhtpc-capabilities.py"

spec_model = importlib.util.spec_from_file_location("openhtpc_system_model", SYSTEM_MODEL_PATH)
sys_model = importlib.util.module_from_spec(spec_model)
spec_model.loader.exec_module(sys_model)

spec_ui = importlib.util.spec_from_file_location("openhtpc_ui", UI_PATH)
ui_mod = importlib.util.module_from_spec(spec_ui)
spec_ui.loader.exec_module(ui_mod)

spec_cap = importlib.util.spec_from_file_location("openhtpc_capabilities", CAPABILITIES_PATH)
cap_mod = importlib.util.module_from_spec(spec_cap)
spec_cap.loader.exec_module(cap_mod)


class TestRc7SystemModelRuntimeGpu(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp_dir.name)
        self.install = PAYLOAD
        display_patch = mock.patch.object(sys_model, "_current_display", return_value={})
        display_patch.start()
        self.addCleanup(display_patch.stop)
        # Never load a host GPU runtime from a model test. Public API mocks
        # remain independently configurable by each authority test.
        self.gpu_runtime = mock.Mock()
        self.gpu_runtime.discover_gpus.return_value = []
        self.gpu_runtime.resolve_display_gpu.return_value = (None, "UNKNOWN")
        self.gpu_runtime.resolve_playback_gpu_binding.return_value = {"status": "AUTO_FALLBACK"}
        patcher = mock.patch.object(sys_model, "_load_gpu_runtime", return_value=self.gpu_runtime)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.sys_root = self.home / "sys"
        self.dev_root = self.home / "dev"
        self.sys_root.mkdir(parents=True, exist_ok=True)
        self.dev_root.mkdir(parents=True, exist_ok=True)

        # Base mock structures
        self.health = {"overall": "READY", "checks": []}
        self.version = {"version": "1.2.0-rc2", "build_id": "rc7-test"}

        # Salon multi-GPU profile (Passport declares HD530 as display_gpu)
        self.profile = {
            "schema_version": "1.2.0",
            "hardware_passport": {
                "system": {"manufacturer": "Dell", "model": "OptiPlex 7040"},
                "cpu": {"model": "Intel(R) Core(TM) i7-6700 CPU @ 3.40GHz", "architecture": "x86_64", "logical_cores": 8},
                "memory": {"total_bytes": 16 * 1024**3},
            },
            "gpu_topology": {
                "display_gpu": {"pci_slot": "0000:00:02.0", "model": "Intel HD Graphics 530"},
                "processing_gpu": {"pci_slot": "0000:00:02.0", "model": "Intel HD Graphics 530"},
            },
            "runtime_profiles": {
                "profiles": {
                    "PURE": {"config_path": str(self.home / ".config/openhtpc/runtime/mpv/pure.conf")}
                }
            },
        }

        # Multi-GPU capabilities with per-device matrix including VC-1
        self.capabilities = {
            "schema": "1.2.0",
            "probe_version": "1.2.0-rc2",
            "generated_at": "2026-09-08T20:00:00+00:00",
            "hardware": {
                "system": {"manufacturer": "Dell", "model": "OptiPlex 7040"},
                "cpu": {"model": "Intel(R) Core(TM) i7-6700 CPU @ 3.40GHz", "architecture": "x86_64", "logical_cores": 8},
                "memory": {"total_bytes": 16 * 1024**3},
            },
            "graphics": {
                "devices": [
                    {
                        "pci_address": "0000:00:02.0",
                        "model": "Intel Corporation HD Graphics 530",
                        "kernel_driver": "i915",
                        "memory_type": "shared",
                        "render_nodes": ["renderD128"],
                        "video_decode": {
                            "backends": {
                                "vaapi": {
                                    "profiles": {
                                        "mpeg2": True,
                                        "vc1": True,
                                        "h264_8bit": True,
                                        "hevc_main": True,
                                        "hevc_main10": False,
                                        "vp9_profile0": True,
                                        "vp9_10bit": False,
                                        "av1_main": False,
                                    }
                                }
                            }
                        },
                    },
                    {
                        "pci_address": "0000:03:00.0",
                        "model": "Intel Corporation Arc A310 Graphics [DG2]",
                        "kernel_driver": "xe",
                        "memory_type": "dedicated",
                        "render_nodes": ["renderD129"],
                        "video_decode": {
                            "backends": {
                                "vaapi": {
                                    "profiles": {
                                        "mpeg2": True,
                                        "vc1": False,
                                        "h264_8bit": True,
                                        "hevc_main": True,
                                        "hevc_main10": True,
                                        "vp9_profile0": True,
                                        "vp9_10bit": True,
                                        "av1_main": True,
                                    }
                                }
                            }
                        },
                    },
                ],
                "vulkan": {
                    "loader": {"status": "AVAILABLE"},
                    "devices": [
                        {"driver_name": "Intel open-source Mesa driver", "device_name": "Intel(R) Arc(TM) A310 Graphics"}
                    ],
                },
                "vaapi": {
                    "status": {"status": "AVAILABLE"},
                    "drivers": ["Intel iHD driver"],
                },
            },
            "video_decode": {
                "codecs": {
                    "mpeg2": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "vc1": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "h264_8bit": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "hevc_main": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "hevc_main10": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "vp9_profile0": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "vp9_10bit": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                    "av1_main": {"software_decode": {"status": "AVAILABLE"}, "hardware_decode": {"status": "SUPPORTED"}},
                },
                "devices": {
                    "0000:00:02.0": {
                        "mpeg2": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "vc1": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "h264_8bit": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "hevc_main": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "hevc_main10": {"hardware_decode": {"status": "UNSUPPORTED"}, "hardware_backends": []},
                        "vp9_profile0": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "vp9_10bit": {"hardware_decode": {"status": "UNSUPPORTED"}, "hardware_backends": []},
                        "av1_main": {"hardware_decode": {"status": "UNSUPPORTED"}, "hardware_backends": []},
                    },
                    "0000:03:00.0": {
                        "mpeg2": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "vc1": {"hardware_decode": {"status": "UNSUPPORTED"}, "hardware_backends": []},
                        "h264_8bit": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "hevc_main": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "hevc_main10": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "vp9_profile0": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "vp9_10bit": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                        "av1_main": {"hardware_decode": {"status": "SUPPORTED"}, "hardware_backends": ["vaapi"]},
                    },
                },
            },
            "display": {
                "outputs": [{"connector": "DP-1", "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}}],
                "active_output": {"connector": "DP-1", "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}},
            },
            "audio": {"default_sink": "alsa_output.pci-0000_03_00.0.hdmi-stereo", "backend": "pipewire"},
            "optical": {"drives": []},
            "media": {"sources": []},
            "processing": {"active_profile": "PURE"},
        }

        # Write config and runtime files
        cfg_dir = self.home / ".config/openhtpc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "profile.json").write_text(json.dumps(self.profile), encoding="utf-8")

        runtime_dir = self.home / ".config/openhtpc/runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "capabilities.json").write_text(json.dumps(self.capabilities), encoding="utf-8")

        state_dir = self.home / ".local/state/openhtpc"
        state_dir.mkdir(parents=True, exist_ok=True)

        runtime_mpv = self.home / ".config/openhtpc/runtime/mpv"
        runtime_mpv.mkdir(parents=True, exist_ok=True)
        (runtime_mpv / "pure.conf").write_text("hwdec=vaapi\nvo=gpu-next\ngpu-api=vulkan\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_public_topology_survives_vulkan_failure(self):
        self.gpu_runtime.resolve_display_gpu.return_value = ({"pci_address": "0000:03:00.0"}, "RESOLVED")
        self.gpu_runtime.resolve_playback_gpu_binding.side_effect = RuntimeError("Vulkan unavailable")
        model = sys_model.build(self.home, self.install, self.health, self.version)
        self.gpu_runtime.resolve_display_gpu.assert_called_once_with([])
        self.assertIn("Arc A310", model["overview"]["gpu"])
        self.assertEqual([g["pci"] for g in model["hardware"]["gpus"] if g["role"] == "GPU actif"], ["0000:03:00.0"])

    def test_n150_magnificence_profile_is_exposed_for_1080p(self):
        n150 = dict(self.capabilities["graphics"]["devices"][0])
        n150.update({
            "pci_address": "0000:00:02.0",
            "model": "Intel Corporation Alder Lake-N [Intel Graphics]",
            "device_id": "0x46d4",
            "kernel_driver": "i915",
            "memory_type": "shared",
        })
        self.capabilities["graphics"]["devices"] = [n150]
        (self.home / ".config/openhtpc/runtime/capabilities.json").write_text(
            json.dumps(self.capabilities), encoding="utf-8"
        )
        self.gpu_runtime.resolve_display_gpu.return_value = (
            {"pci_address": "0000:00:02.0", "model": n150["model"]},
            "RESOLVED",
        )
        display = {
            "active_output": {
                "connector": "HDMI-A-1",
                "current_mode": {"width": 1920, "height": 1080, "refresh_hz": 60.0},
            }
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_snapshot=display,
        )
        self.assertEqual(model["magnificence"]["profile_id"], "intel_n150_8086_46d4_sd_1080p")
        self.assertEqual(model["magnificence"]["selected_label"], "KrigBilateral")
        self.assertIn("Réserve GPU", model["magnificence"]["reason_fr"])

    def test_validator_exception_and_unavailable_fail_closed(self):
        node = self.dev_root / "dri/renderD129"
        node.parent.mkdir()
        node.touch()
        def runner(argv, timeout):
            output = ""
            if argv[0] == "lspci":
                output = "0000:03:00.0 VGA compatible controller [0300]: Intel Arc [8086:5690]\n"
            elif argv[0] == "vainfo":
                output = "VAProfileAV1Profile0 : VAEntrypointVLD\n"
            return {"status": "OK", "stdout": output, "stderr": "", "returncode": 0}
        throwing = mock.Mock()
        throwing.validate_render_node.side_effect = RuntimeError("invalid sysfs")
        for validator in (None, throwing):
            with self.subTest(validator=validator), mock.patch.object(cap_mod, "_load_gpu_runtime_validator", return_value=validator):
                result = cap_mod.generate(self.home, self.install, runner=runner, sys_root=self.sys_root, dev_root=self.dev_root, proc_root=self.sys_root)
                self.assertEqual(result["video_decode"]["devices"]["0000:03:00.0"]["av1_main"]["hardware_decode"]["status"], "UNKNOWN")

    def test_technical_decoder_row_never_uses_vulkan_drivers(self):
        from PIL import ImageDraw
        drivers = "Intel open-source Mesa driver, Intel open-source Mesa driver, llvmpipe"
        self.capabilities["graphics"]["vulkan"]["devices"] = [
            {"driver_name": name} for name in drivers.split(", ")
        ]
        (self.home / ".config/openhtpc/runtime/capabilities.json").write_text(json.dumps(self.capabilities))
        model = sys_model.build(
            self.home, self.install, self.health, self.version,
            display_resolution=({"pci_address": "0000:03:00.0"}, "RESOLVED"),
            gpu_binding={"status": "RENDER_BOUND", "vulkan_uuid": "8680a656-0500-0000-0300-000000000000"},
            pure_conf_text="hwdec=vaapi\n",
        )
        self.assertEqual(model["technical"]["physical_decode_gpu"], "Non déterminé")
        self.assertEqual(model["technical"]["vulkan_driver"], drivers)
        self.assertEqual(model["technical"]["configured_hwdec"], "VA-API")
        self.assertIn("Arc A310", model["technical"]["render_gpu"])
        # Even stale/mislabelled input cannot turn driver names into decoder identity.
        for value in ("Non déterminé", drivers, "NOT_PROVEN"):
            model["technical"]["physical_decode_gpu"] = value
            with mock.patch.object(ImageDraw.ImageDraw, "text", autospec=True) as draw_text:
                ui_mod.system_page_png(model, self.home / "technical-proof.png",
                                      PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf", "technical")
            texts = [(call.args[1], call.args[2]) for call in draw_text.call_args_list]
            position = next(pos for pos, text in texts if text == "GPU physique de décodage")
            row_values = [text for pos, text in texts if pos[0] > position[0] and abs(pos[1] - position[1]) <= 2]
            self.assertEqual(row_values, ["Non déterminé"])
            driver_position = next(pos for pos, text in texts if text == drivers)
            self.assertGreater(driver_position[1], position[1])
            self.assertNotIn("NOT_PROVEN", [text for pos, text in texts])

    def test_A_arc_resolved_vulkan_unavailable_passport_hd530_overview_arc(self):
        """A. T8.1A Arc resolved + Vulkan unavailable + Passport HD530 => Overview Arc."""
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        gpu_binding = {
            "status": "AUTO_FALLBACK",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": None,
            "reason": "VULKAN_UNAVAILABLE",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=gpu_binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        self.assertIn("Arc A310", model["overview"]["gpu"])
        self.assertNotIn("HD 530", model["overview"]["gpu"])
        self.assertNotIn("(Passeport)", model["overview"]["gpu"])
        self.assertNotIn("Indéterminé", model["overview"]["gpu"])

    def test_B_vulkan_unavailable_arc_display_identity_retained(self):
        """B. Vulkan detail unavailable but Arc display identity retained."""
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        gpu_binding = {
            "status": "AUTO_FALLBACK",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": None,
            "reason": "VULKAN_UNAVAILABLE",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=gpu_binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        self.assertEqual(model["technical"]["vulkan_binding"], "Indisponible")
        self.assertIn("Arc A310", model["technical"]["render_gpu"])
        self.assertIn("0000:03:00.0", model["technical"]["render_gpu"])

    def test_C_runtime_unresolved_passport_hd530_codec_matrix_non_determine(self):
        """C. Runtime unresolved + Passport HD530 => no GPU actif claim, codec matrix Non déterminée."""
        display_res = (None, "UNKNOWN")
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=None,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        self.assertIn("HD Graphics 530 (Passeport)", model["overview"]["gpu"])
        self.assertEqual(model["codecs_subtitle"], "GPU de rendu : Indéterminé")

        for item in model["codecs"]:
            self.assertIn(item["hardware"], {"Non déterminée", "Non déterminé"})

    def test_D_effective_pure_conf_missing_passport_hwdec_shows_non_determine(self):
        """D. Effective pure.conf missing + Passport hwdec=vaapi => Accélération vidéo = Non déterminé."""
        pure_conf = self.home / ".config/openhtpc/runtime/mpv/pure.conf"
        if pure_conf.is_file():
            pure_conf.unlink()

        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )
        self.assertEqual(model["overview"]["video_accel"], "Non déterminé")
        self.assertEqual(model["technical"]["configured_hwdec"], "Non déterminé")

    def test_E_render_node_order_reversed_capability_attribution(self):
        """E. Probing renderD129 (Arc) before renderD128 (HD530) attributes capabilities to correct PCI addresses."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_hd = sys_bus / "0000:00:02.0"
        pci_arc = sys_bus / "0000:03:00.0"
        pci_hd.mkdir(parents=True)
        pci_arc.mkdir(parents=True)

        (pci_hd / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_hd / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_hd / "device").write_text("0x1912\n", encoding="utf-8")

        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")

        node128 = dev_dri / "renderD128"
        node129 = dev_dri / "renderD129"
        node128.touch()
        node129.touch()

        drm128 = sys_drm / "renderD128"
        drm129 = sys_drm / "renderD129"
        drm128.mkdir(parents=True)
        drm129.mkdir(parents=True)
        (drm128 / "dev").write_text("226:128\n", encoding="utf-8")
        (drm129 / "dev").write_text("226:129\n", encoding="utf-8")

        (drm128 / "device").symlink_to(pci_hd)
        (drm129 / "device").symlink_to(pci_arc)

        class MockStat:
            def __init__(self, major, minor):
                self.st_mode = stat.S_IFCHR | 0o660
                self.st_rdev = os.makedev(major, minor)

        def mock_stat_provider(path: pathlib.Path):
            name = path.name
            if name == "renderD128":
                return MockStat(226, 128)
            elif name == "renderD129":
                return MockStat(226, 129)
            return path.stat()

        vainfo_arc = """vainfo: Driver version: Intel iHD driver
    VAProfileMPEG2Main              : VAEntrypointVLD
    VAProfileH264High               : VAEntrypointVLD
    VAProfileHEVCMain               : VAEntrypointVLD
    VAProfileHEVCMain10             : VAEntrypointVLD
    VAProfileAV1Profile0            : VAEntrypointVLD
"""
        vainfo_hd530 = """vainfo: Driver version: Intel iHD driver
    VAProfileMPEG2Main              : VAEntrypointVLD
    VAProfileH264High               : VAEntrypointVLD
    VAProfileVC1Advanced            : VAEntrypointVLD
    VAProfileHEVCMain               : VAEntrypointVLD
"""

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                # Deliberately return Arc first to test reverse order
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n" \
                      "0000:00:02.0 VGA compatible controller [0300]: Intel Corporation HD Graphics 530 [8086:1912]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "renderD129" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": vainfo_arc, "stderr": ""}
            elif "renderD128" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": vainfo_hd530, "stderr": ""}
            elif "ffmpeg -hide_banner -decoders" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": " V..... av1\n V..... vc1\n V..... mpeg2video\n", "stderr": ""}
            elif "ffmpeg" in cmd or "mpv" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "ffmpeg version 7.0\n", "stderr": ""}
            elif "vulkaninfo" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}
            elif "kscreen-doctor" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}
            return {"status": "COMMAND_UNAVAILABLE", "returncode": 127, "stdout": "", "stderr": ""}

        caps = cap_mod.generate(
            self.home,
            self.install,
            runner=mock_runner,
            proc_root=sys_root,
            sys_root=sys_root,
            dev_root=dev_root,
            stat_provider=mock_stat_provider,
        )

        devices = caps.get("video_decode", {}).get("devices", {})
        self.assertIn("0000:03:00.0", devices)
        self.assertIn("0000:00:02.0", devices)

        # Arc (0000:03:00.0): AV1 supported, VC1 unsupported
        self.assertEqual(devices["0000:03:00.0"]["av1_main"]["hardware_decode"]["status"], "SUPPORTED")
        self.assertEqual(devices["0000:03:00.0"]["vc1"]["hardware_decode"]["status"], "UNSUPPORTED")

        # HD530 (0000:00:02.0): AV1 unsupported, VC1 supported
        self.assertEqual(devices["0000:00:02.0"]["av1_main"]["hardware_decode"]["status"], "UNSUPPORTED")
        self.assertEqual(devices["0000:00:02.0"]["vc1"]["hardware_decode"]["status"], "SUPPORTED")

    def test_F_invalid_mismatched_drm_sysfs_render_node_not_attributed(self):
        """F. Render node with mismatched sysfs PCI link is not attributed to PCI device."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_arc = sys_bus / "0000:03:00.0"
        pci_arc.mkdir(parents=True)
        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")

        node129 = dev_dri / "renderD129"
        node129.touch()

        # Corrupted / mismatched sysfs entry: points to non-matching PCI device
        other_pci = sys_bus / "0000:09:00.0"
        other_pci.mkdir(parents=True)
        drm129 = sys_drm / "renderD129"
        drm129.mkdir(parents=True)
        (drm129 / "dev").write_text("226:129\n", encoding="utf-8")
        (drm129 / "device").symlink_to(other_pci)

        class MockStat:
            def __init__(self, major, minor):
                self.st_mode = stat.S_IFCHR | 0o660
                self.st_rdev = os.makedev(major, minor)

        def mock_stat_provider(path: pathlib.Path):
            if path.name == "renderD129":
                return MockStat(226, 129)
            return path.stat()

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "renderD129" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "VAProfileAV1Profile0 : VAEntrypointVLD\n", "stderr": ""}
            return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}

        caps = cap_mod.generate(
            self.home,
            self.install,
            runner=mock_runner,
            proc_root=sys_root,
            sys_root=sys_root,
            dev_root=dev_root,
            stat_provider=mock_stat_provider,
        )

        devices = caps.get("video_decode", {}).get("devices", {})
        # Since renderD129 failed PCI validation, 0000:03:00.0 capabilities are UNKNOWN
        self.assertEqual(devices["0000:03:00.0"]["av1_main"]["hardware_decode"]["status"], "UNKNOWN")

    def test_G_and_H_multi_gpu_codec_matrix_arc_only_and_legacy_union_isolated(self):
        """G & H. UI matrix consumes Arc capabilities only; legacy union is preserved but isolated."""
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        binding = {
            "status": "RENDER_BOUND",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": "8086-a310-0000-0000",
            "vulkan_device_name": "Intel(R) Arc(TM) A310 Graphics",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )
        codecs_by_key = {item["key"]: item for item in model["codecs"]}

        # G. Arc fixture: VC1=false, AV1=true, HEVC10=true => UI shows Arc values only
        self.assertEqual(codecs_by_key["vc1"]["hardware"], "Non signalée")
        self.assertEqual(codecs_by_key["av1_main"]["hardware"], "Signalée")
        self.assertEqual(codecs_by_key["hevc_main10"]["hardware"], "Signalée")

        # H. Legacy union still has VC1=SUPPORTED, AV1=SUPPORTED, HEVC10=SUPPORTED
        legacy_union = self.capabilities["video_decode"]["codecs"]
        self.assertEqual(legacy_union["vc1"]["hardware_decode"]["status"], "SUPPORTED")
        self.assertEqual(legacy_union["av1_main"]["hardware_decode"]["status"], "SUPPORTED")
        self.assertEqual(legacy_union["hevc_main10"]["hardware_decode"]["status"], "SUPPORTED")
        # But UI matrix for Arc does NOT show VC1 as Signalée
        self.assertNotEqual(codecs_by_key["vc1"]["hardware"], "Signalée")

    def test_I_runtime_vs_stale_passport_disagreement_runtime_wins(self):
        """I. Runtime vs stale Passport disagreement => runtime wins."""
        # Passport explicitly states HD 530 (0000:00:02.0)
        # Runtime T8.1A resolution states Arc A310 (0000:03:00.0)
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        self.assertIn("Arc A310", model["overview"]["gpu"])
        self.assertNotIn("HD 530", model["overview"]["gpu"])
        self.assertNotIn("Passeport", model["overview"]["gpu"])

    def test_J_pure_conf_mappings(self):
        """J. VAAPI / NVDEC / no / missing pure.conf mapping."""
        # VA-API
        m_va = sys_model.build(self.home, self.install, self.health, self.version, pure_conf_text="hwdec=vaapi\n", sys_root=self.sys_root, dev_root=self.dev_root)
        self.assertEqual(m_va["overview"]["video_accel"], "VA-API")
        self.assertEqual(m_va["technical"]["configured_hwdec"], "VA-API")

        # NVDEC
        m_nv = sys_model.build(self.home, self.install, self.health, self.version, pure_conf_text="hwdec=nvdec\n", sys_root=self.sys_root, dev_root=self.dev_root)
        self.assertEqual(m_nv["overview"]["video_accel"], "NVDEC")
        self.assertEqual(m_nv["technical"]["configured_hwdec"], "NVDEC")

        # no -> Désactivé
        m_no = sys_model.build(self.home, self.install, self.health, self.version, pure_conf_text="hwdec=no\n", sys_root=self.sys_root, dev_root=self.dev_root)
        self.assertEqual(m_no["overview"]["video_accel"], "Désactivé")
        self.assertEqual(m_no["technical"]["configured_hwdec"], "Désactivé")

        # missing -> Non déterminé
        m_none = sys_model.build(self.home, self.install, self.health, self.version, pure_conf_text="", sys_root=self.sys_root, dev_root=self.dev_root)
        self.assertEqual(m_none["overview"]["video_accel"], "Non déterminé")
        self.assertEqual(m_none["technical"]["configured_hwdec"], "Non déterminé")

    def test_K_no_raw_tokens_in_couch_ui(self):
        """K. No raw NOT_PROVEN or internal diagnostic tokens in user-facing model."""
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        binding = {
            "status": "RENDER_BOUND",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": "8086-a310-0000-0000",
            "vulkan_device_name": "Intel(R) Arc(TM) A310 Graphics",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        forbidden = ("NOT_PROVEN", "COHERENT_RENDER_ALIGNED", "DG2", "INTEL_DG2", "RENDER_BOUND", "AUTO_FALLBACK")

        for k, v in model["overview"].items():
            if isinstance(v, str):
                for f in forbidden:
                    self.assertNotIn(f, v, f"Found raw token {f} in overview[{k}]={v}")

        for item in model["codecs"]:
            for f in forbidden:
                self.assertNotIn(f, item["hardware"], f"Found raw token {f} in codec hardware: {item}")
                self.assertNotIn(f, item["software"], f"Found raw token {f} in codec software: {item}")

        for k, v in model["technical"].items():
            if isinstance(v, str) and k != "vulkan_binding":
                for f in forbidden:
                    self.assertNotIn(f, v, f"Found raw token {f} in technical[{k}]={v}")

    def test_L_no_arbitrary_gpu_active_role_when_runtime_unresolved(self):
        """L. No arbitrary GPU active role when runtime unresolved."""
        display_res = (None, "UNKNOWN")
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=None,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        for gpu in model["hardware"]["gpus"]:
            self.assertNotEqual(gpu["role"], "GPU actif")
            self.assertIn(gpu["role"], {"GPU détecté", "GPU secondaire"})

    def test_M_single_gpu_without_valid_drm_proof_no_av1_ui_non_determine(self):
        """M. Single GPU without valid DRM proof -> devices contains no supported AV1 and UI shows CAPACITÉ GPU = Non déterminée."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_arc = sys_bus / "0000:03:00.0"
        pci_arc.mkdir(parents=True)
        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")

        home_dir = tpath / "home"
        cfg_dir = home_dir / ".config/openhtpc"
        cfg_dir.mkdir(parents=True)
        single_profile = {
            "schema_version": "1.2.0",
            "gpu_topology": {
                "display_gpu": {"pci_slot": "0000:03:00.0", "model": "Intel Arc A310"},
                "processing_gpu": {"pci_slot": "0000:03:00.0", "model": "Intel Arc A310"},
            },
        }
        (cfg_dir / "profile.json").write_text(json.dumps(single_profile), encoding="utf-8")

        # Render node exists in dev_dri, BUT has NO sysfs DRM link (unvalidated DRM proof)
        node129 = dev_dri / "renderD129"
        node129.touch()

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "vainfo" in cmd:
                out = "vainfo: Driver version: Intel iHD driver\nVAProfileAV1Profile0 : VAEntrypointVLD\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "ffmpeg -hide_banner -decoders" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": " V..... av1\n", "stderr": ""}
            return {"status": "COMMAND_UNAVAILABLE", "returncode": 127, "stdout": "", "stderr": ""}

        caps = cap_mod.generate(
            home_dir,
            self.install,
            runner=mock_runner,
            proc_root=sys_root,
            sys_root=sys_root,
            dev_root=dev_root,
        )

        devices = caps.get("video_decode", {}).get("devices", {})
        arc_caps = devices.get("0000:03:00.0", {})
        self.assertNotEqual(arc_caps.get("av1_main", {}).get("hardware_decode", {}).get("status"), "SUPPORTED")

        # Write generated capabilities to runtime directory
        runtime_dir = home_dir / ".config/openhtpc/runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")

        # Build system model with display resolved to Arc
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310"}
        model = sys_model.build(
            home_dir,
            self.install,
            self.health,
            self.version,
            display_resolution=(disp_gpu, "RESOLVED"),
            sys_root=sys_root,
            dev_root=dev_root,
        )

        av1_item = next(item for item in model["codecs"] if item["key"] == "av1_main")
        self.assertEqual(av1_item["hardware"], "Non déterminée")

    def test_N_validator_unavailable_no_per_gpu_capability_attribution(self):
        """N. Validator unavailable -> NO per-GPU capability attribution."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_arc = sys_bus / "0000:03:00.0"
        pci_arc.mkdir(parents=True)
        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")

        node129 = dev_dri / "renderD129"
        node129.touch()

        drm129 = sys_drm / "renderD129"
        drm129.mkdir(parents=True)
        (drm129 / "dev").write_text("226:129\n", encoding="utf-8")
        (drm129 / "device").symlink_to(pci_arc)

        empty_install = tpath / "empty_install"
        empty_install.mkdir(parents=True)

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "vainfo" in cmd:
                out = "vainfo: Driver version: Intel iHD driver\nVAProfileAV1Profile0 : VAEntrypointVLD\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}

        with mock.patch.object(cap_mod, "_load_gpu_runtime_validator", return_value=None):
            caps = cap_mod.generate(
                self.home,
                empty_install,
                runner=mock_runner,
                proc_root=sys_root,
                sys_root=sys_root,
                dev_root=dev_root,
            )

        devices = caps.get("video_decode", {}).get("devices", {})
        arc_caps = devices.get("0000:03:00.0", {})
        self.assertNotEqual(arc_caps.get("av1_main", {}).get("hardware_decode", {}).get("status"), "SUPPORTED")
        self.assertEqual(arc_caps.get("av1_main", {}).get("hardware_decode", {}).get("status"), "UNKNOWN")

    def test_O_metadata_path_membership_is_not_proof_no_attribution(self):
        """O. Path membership in metadata/passport is not proof -> NO per-GPU capability attribution."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_arc = sys_bus / "0000:03:00.0"
        pci_other = sys_bus / "0000:00:02.0"
        pci_arc.mkdir(parents=True)
        pci_other.mkdir(parents=True)
        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")
        (pci_other / "class").write_text("0x030000\n", encoding="utf-8")

        node129 = dev_dri / "renderD129"
        node129.touch()

        # In sysfs, renderD129 belongs to pci_other, NOT pci_arc
        drm129 = sys_drm / "renderD129"
        drm129.mkdir(parents=True)
        (drm129 / "dev").write_text("226:129\n", encoding="utf-8")
        (drm129 / "device").symlink_to(pci_other)

        # Profile claims render_nodes = ["/dev/dri/renderD129"] for Arc
        home_dir = tpath / "home"
        cfg_dir = home_dir / ".config/openhtpc"
        cfg_dir.mkdir(parents=True)
        profile_data = {
            "schema_version": "1.2.0",
            "detected": {
                "gpus": [
                    {
                        "pci_address": "0000:03:00.0",
                        "model": "Intel Arc A310",
                        "render_nodes": ["/dev/dri/renderD129"],
                    }
                ]
            },
        }
        (cfg_dir / "profile.json").write_text(json.dumps(profile_data), encoding="utf-8")

        class MockStat:
            def __init__(self, major, minor):
                self.st_mode = stat.S_IFCHR | 0o660
                self.st_rdev = os.makedev(major, minor)

        def mock_stat_provider(path: pathlib.Path):
            if path.name == "renderD129":
                return MockStat(226, 129)
            return path.stat()

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "renderD129" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "VAProfileAV1Profile0 : VAEntrypointVLD\n", "stderr": ""}
            return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}

        caps = cap_mod.generate(
            home_dir,
            self.install,
            runner=mock_runner,
            proc_root=sys_root,
            sys_root=sys_root,
            dev_root=dev_root,
            stat_provider=mock_stat_provider,
        )

        devices = caps.get("video_decode", {}).get("devices", {})
        arc_caps = devices.get("0000:03:00.0", {})
        self.assertEqual(arc_caps.get("av1_main", {}).get("hardware_decode", {}).get("status"), "UNKNOWN")

    def test_P_valid_drm_proof_capabilities_published(self):
        """P. Valid DRM proof -> capabilities published for that PCI."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tpath = pathlib.Path(temp_dir.name)

        sys_root = tpath / "sys"
        dev_root = tpath / "dev"
        sys_bus = sys_root / "bus/pci/devices"
        sys_drm = sys_root / "class/drm"
        dev_dri = dev_root / "dri"

        sys_bus.mkdir(parents=True)
        sys_drm.mkdir(parents=True)
        dev_dri.mkdir(parents=True)

        pci_arc = sys_bus / "0000:03:00.0"
        pci_arc.mkdir(parents=True)
        (pci_arc / "class").write_text("0x030000\n", encoding="utf-8")
        (pci_arc / "vendor").write_text("0x8086\n", encoding="utf-8")
        (pci_arc / "device").write_text("0x5690\n", encoding="utf-8")

        node129 = dev_dri / "renderD129"
        node129.touch()

        drm129 = sys_drm / "renderD129"
        drm129.mkdir(parents=True)
        (drm129 / "dev").write_text("226:129\n", encoding="utf-8")
        (drm129 / "device").symlink_to(pci_arc)

        class MockStat:
            def __init__(self, major, minor):
                self.st_mode = stat.S_IFCHR | 0o660
                self.st_rdev = os.makedev(major, minor)

        def mock_stat_provider(path: pathlib.Path):
            if path.name == "renderD129":
                return MockStat(226, 129)
            return path.stat()

        def mock_runner(argv, timeout=8):
            cmd = " ".join(str(a) for a in argv)
            if "lspci" in cmd:
                out = "0000:03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 Graphics [8086:5690]\n"
                return {"status": "OK", "returncode": 0, "stdout": out, "stderr": ""}
            elif "renderD129" in cmd:
                return {"status": "OK", "returncode": 0, "stdout": "VAProfileAV1Profile0 : VAEntrypointVLD\n", "stderr": ""}
            return {"status": "OK", "returncode": 0, "stdout": "", "stderr": ""}

        caps = cap_mod.generate(
            self.home,
            self.install,
            runner=mock_runner,
            proc_root=sys_root,
            sys_root=sys_root,
            dev_root=dev_root,
            stat_provider=mock_stat_provider,
        )

        devices = caps.get("video_decode", {}).get("devices", {})
        self.assertIn("0000:03:00.0", devices)
        self.assertEqual(devices["0000:03:00.0"]["av1_main"]["hardware_decode"]["status"], "SUPPORTED")
        self.assertEqual(devices["0000:03:00.0"]["av1_main"]["hardware_backends"], ["vaapi"])

    def test_Q_display_unresolved_with_auto_fallback_binding_no_gpu_actif(self):
        """Q. Display unresolved + gpu_binding status AUTO_FALLBACK -> Arc is NOT GPU actif, no active GPU role."""
        display_res = (None, "UNKNOWN")
        gpu_binding = {
            "status": "AUTO_FALLBACK",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": None,
            "reason": "VULKAN_UNAVAILABLE",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=gpu_binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        for gpu in model["hardware"]["gpus"]:
            self.assertNotEqual(gpu["role"], "GPU actif")
        active_roles = [g for g in model["hardware"]["gpus"] if g["role"] == "GPU actif"]
        self.assertEqual(len(active_roles), 0)
        self.assertEqual(model["codecs_subtitle"], "GPU de rendu : Indéterminé")

    def test_R_display_resolved_with_gpu_binding_unavailable_arc_is_gpu_actif(self):
        """R. Display resolved + gpu_binding unavailable -> Arc IS GPU actif (positive control)."""
        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        gpu_binding = {
            "status": "UNAVAILABLE",
            "reason": "VULKAN_UNAVAILABLE",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=gpu_binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        arc_gpu = next((g for g in model["hardware"]["gpus"] if "0000:03:00.0" in g["pci"]), None)
        self.assertIsNotNone(arc_gpu)
        self.assertEqual(arc_gpu["role"], "GPU actif")

        hd_gpu = next((g for g in model["hardware"]["gpus"] if "0000:00:02.0" in g["pci"]), None)
        self.assertIsNotNone(hd_gpu)
        self.assertEqual(hd_gpu["role"], "GPU secondaire")

        self.assertIn("Arc A310", model["overview"]["gpu"])
        self.assertIn("Arc A310", model["codecs_subtitle"])

    def test_ui_rendering_overview_codecs_technical(self):
        """openhtpc-ui.py renders overview, codecs, and technical pages with new fields."""
        font_path = PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf"
        if not font_path.is_file():
            self.skipTest("No font found for UI rendering test")

        disp_gpu = {"pci_address": "0000:03:00.0", "model": "Intel Corporation Arc A310 Graphics [DG2]"}
        display_res = (disp_gpu, "RESOLVED")
        binding = {
            "status": "RENDER_BOUND",
            "pci_address": "0000:03:00.0",
            "vulkan_uuid": "8086-a310-0000-0000",
            "vulkan_device_name": "Intel(R) Arc(TM) A310 Graphics",
        }
        model = sys_model.build(
            self.home,
            self.install,
            self.health,
            self.version,
            display_resolution=display_res,
            gpu_binding=binding,
            sys_root=self.sys_root,
            dev_root=self.dev_root,
        )

        for page in ("overview", "codecs", "technical", "hardware", "display_video"):
            target = self.home / f"test-{page}.png"
            ui_mod.system_page_png(model, target, font_path, page)
            self.assertTrue(target.is_file(), f"Page {page} failed to render")
            self.assertGreater(target.stat().st_size, 500, f"Page {page} rendered empty file")


if __name__ == "__main__":
    unittest.main()
