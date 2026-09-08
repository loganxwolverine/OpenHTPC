# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Tests for RC7 T8.1A Runtime GPU Resolver."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
GPU_RUNTIME_PATH = PAYLOAD / "openhtpc-gpu-runtime.py"

spec = importlib.util.spec_from_file_location("openhtpc_gpu_runtime", GPU_RUNTIME_PATH)
gpu_rt = importlib.util.module_from_spec(spec)
sys.modules["openhtpc_gpu_runtime"] = gpu_rt
spec.loader.exec_module(gpu_rt)


class MockStat:
    """Explicit injected stat object for testing without root mknod."""

    def __init__(self, mode: int, major: int, minor: int):
        self.st_mode = mode
        self.st_rdev = os.makedev(major, minor)


class TestPCIAddressNormalization(unittest.TestCase):
    def test_non_zero_pci_domain_accepted(self):
        self.assertEqual(gpu_rt.normalize_pci_address("0001:03:00.0"), "0001:03:00.0")
        self.assertEqual(gpu_rt.normalize_pci_address("1:3:0.0"), "0001:03:00.0")
        self.assertEqual(gpu_rt.normalize_pci_address("ffff:ff:1f.7"), "ffff:ff:1f.7")

    def test_invalid_pci_device_rejected(self):
        self.assertIsNone(gpu_rt.normalize_pci_address("0000:03:20.0"))  # 0x20 = 32 > 31
        self.assertIsNone(gpu_rt.normalize_pci_address("0000:03:ff.0"))  # 0xff = 255 > 31

    def test_invalid_pci_function_rejected(self):
        self.assertIsNone(gpu_rt.normalize_pci_address("0000:03:00.8"))
        self.assertIsNone(gpu_rt.normalize_pci_address("0000:03:00.9"))
        self.assertIsNone(gpu_rt.normalize_pci_address("0000:03:00.f"))

    def test_canonical_current_host_addresses_unchanged(self):
        self.assertEqual(gpu_rt.normalize_pci_address("0000:00:02.0"), "0000:00:02.0")
        self.assertEqual(gpu_rt.normalize_pci_address("0000:03:00.0"), "0000:03:00.0")
        self.assertEqual(gpu_rt.normalize_pci_address("03:00.0"), "0000:03:00.0")

    def test_malformed_input_rejected(self):
        self.assertIsNone(gpu_rt.normalize_pci_address("zzzz:03:00.0"))
        self.assertIsNone(gpu_rt.normalize_pci_address("card0"))
        self.assertIsNone(gpu_rt.normalize_pci_address(""))
        self.assertIsNone(gpu_rt.normalize_pci_address(1234))
        self.assertIsNone(gpu_rt.normalize_pci_address(None))


class TestPCIGPUClassParsing(unittest.TestCase):
    # Codex 6.I: 0x030000 => accepted
    def test_codex_I_0x030000_accepted(self):
        self.assertTrue(gpu_rt.is_display_pci_class("0x030000"))
        self.assertEqual(gpu_rt.pci_class_description("0x030000"), "VGA compatible controller [0300]")

    # Codex 6.G: PCI class 10300 => rejected
    def test_codex_G_class_10300_rejected(self):
        self.assertIsNone(gpu_rt.parse_pci_class("10300"))
        self.assertFalse(gpu_rt.is_display_pci_class("10300"))
        self.assertEqual(gpu_rt.pci_class_description("10300"), "Unknown class")

    # Codex 6.H: PCI class 03000 => rejected
    def test_codex_H_class_03000_rejected(self):
        self.assertIsNone(gpu_rt.parse_pci_class("03000"))
        self.assertFalse(gpu_rt.is_display_pci_class("03000"))
        self.assertEqual(gpu_rt.pci_class_description("03000"), "Unknown class")

    def test_pci_class_length_strictness(self):
        # Valid 4-digit and 6-digit formats
        for valid_val in ["0300", "030000", "0302", "030200", "0380", "038000", "0x030000", "0x030200"]:
            self.assertTrue(gpu_rt.is_display_pci_class(valid_val), f"Failed for {valid_val}")

        # Invalid lengths: 2, 3, 5, 7 digits
        for invalid_val in ["03", "300", "10300", "00300", "03000", "0300000", "0x10300", "malformed", ""]:
            self.assertFalse(gpu_rt.is_display_pci_class(invalid_val), f"Should fail for {invalid_val}")
            self.assertIsNone(gpu_rt.parse_pci_class(invalid_val), f"Should fail for {invalid_val}")

    def test_audio_and_network_classes_rejected(self):
        self.assertFalse(gpu_rt.is_display_pci_class("0x020000"))  # Network
        self.assertEqual(gpu_rt.pci_class_description("0x020000"), "Non-display device")
        self.assertFalse(gpu_rt.is_display_pci_class("0x040300"))  # Audio
        self.assertEqual(gpu_rt.pci_class_description("0x040300"), "Non-display device")


class TestHermeticGPURuntime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.sys_dir = self.base / "sys"
        self.dev_dir = self.base / "dev"
        (self.sys_dir / "bus/pci/devices").mkdir(parents=True)
        (self.sys_dir / "class/drm").mkdir(parents=True)
        (self.dev_dir / "dri/by-path").mkdir(parents=True)

        self.mock_stats: dict[pathlib.Path, MockStat] = {}
        self.stat_provider = lambda p: self.mock_stats.get(p.resolve(), p.stat())

    def tearDown(self):
        self.tmp.cleanup()

    def add_pci_gpu(
        self,
        pci_slot: str,
        vendor_id: str = "8086",
        device_id: str = "56a6",
        class_hex: str = "0x030000",
        driver_name: str = "i915",
        card_name: str = "card0",
        render_name: str | None = "renderD128",
        major: int = 226,
        minor: int = 128,
        is_char_device: bool = True,
        omit_sysfs_dev: bool = False,
        sysfs_dev_override: str | None = None,
        create_by_path: bool = True,
        broken_by_path: bool = False,
        connectors: list[tuple[str, str, str | None]] | None = None,  # [(suffix, status, enabled)]
        omit_connector_parent: bool = False,
        contradict_render_pci: str | None = None,
        contradict_connector_pci: str | None = None,
    ) -> pathlib.Path:
        pci_dir = self.sys_dir / "bus/pci/devices" / pci_slot
        pci_dir.mkdir(parents=True, exist_ok=True)
        (pci_dir / "vendor").write_text(f"0x{vendor_id}\n")
        (pci_dir / "device").write_text(f"0x{device_id}\n")
        (pci_dir / "class").write_text(f"{class_hex}\n")

        if driver_name:
            driver_dir = self.sys_dir / "bus/pci/drivers" / driver_name
            driver_dir.mkdir(parents=True, exist_ok=True)
            (pci_dir / "driver").symlink_to(driver_dir)

        drm_dir = pci_dir / "drm"
        drm_dir.mkdir(parents=True, exist_ok=True)

        if card_name:
            card_sysfs = self.sys_dir / "class/drm" / card_name
            card_sysfs.mkdir(parents=True, exist_ok=True)
            (card_sysfs / "device").symlink_to(pci_dir)
            (drm_dir / card_name).mkdir(parents=True, exist_ok=True)

        if render_name:
            render_sysfs = self.sys_dir / "class/drm" / render_name
            render_sysfs.mkdir(parents=True, exist_ok=True)

            if contradict_render_pci:
                other_pci_dir = self.sys_dir / "bus/pci/devices" / contradict_render_pci
                other_pci_dir.mkdir(parents=True, exist_ok=True)
                (render_sysfs / "device").symlink_to(other_pci_dir)
            else:
                (render_sysfs / "device").symlink_to(pci_dir)
                (drm_dir / render_name).mkdir(parents=True, exist_ok=True)

            if not omit_sysfs_dev:
                dev_content = sysfs_dev_override if sysfs_dev_override is not None else f"{major}:{minor}"
                (render_sysfs / "dev").write_text(f"{dev_content}\n")

            real_render = self.dev_dir / "dri" / render_name
            real_render.write_text("")  # created as regular file on disk

            if is_char_device:
                # Explicitly register in mock_stats for injected stat_provider
                self.mock_stats[real_render.resolve()] = MockStat(stat.S_IFCHR | 0o660, major, minor)

            if create_by_path:
                by_path_link = self.dev_dir / "dri/by-path" / f"pci-{pci_slot}-render"
                if broken_by_path:
                    by_path_link.symlink_to(self.dev_dir / "dri/renderD999")
                else:
                    by_path_link.symlink_to(real_render)

        if connectors and card_name:
            for item in connectors:
                conn_suffix = item[0]
                status_val = item[1]
                enabled_val = item[2] if len(item) > 2 else None

                conn_dir = self.sys_dir / "class/drm" / f"{card_name}-{conn_suffix}"
                conn_dir.mkdir(parents=True, exist_ok=True)
                (conn_dir / "status").write_text(f"{status_val}\n")
                if enabled_val is not None:
                    (conn_dir / "enabled").write_text(f"{enabled_val}\n")

                if not omit_connector_parent:
                    if contradict_connector_pci:
                        other_pci_dir = self.sys_dir / "bus/pci/devices" / contradict_connector_pci
                        other_pci_dir.mkdir(parents=True, exist_ok=True)
                        (conn_dir / "device").symlink_to(other_pci_dir)
                    else:
                        (conn_dir / "device").symlink_to(pci_dir)

        return pci_dir

    # Codex 6.A: ordinary file renderD128 + companion .renderD128.stat + NO injected stat provider => rejected
    def test_codex_A_ordinary_file_with_stat_companion_and_no_provider_rejected(self):
        pci_dir = self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            is_char_device=False,
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        real_render = self.dev_dir / "dri/renderD128"
        # Create deceptive companion file
        companion = self.dev_dir / "dri/.renderD128.stat"
        companion.write_text(json.dumps({"st_mode": stat.S_IFCHR | 0o660, "major": 226, "minor": 128}))

        # Run WITHOUT injected stat provider
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=None)
        self.assertEqual(len(gpus), 1)
        self.assertFalse(gpus[0]["render_node_valid"])
        self.assertIsNone(gpus[0]["render_node"])
        self.assertFalse(gpu_rt.is_gpu_available(gpus[0]))
        self.assertIsNone(gpus[0]["persistent_render_path"])
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    # Codex 6.B: fake injected character device + missing /sys/class/drm/renderD128/dev => rejected
    def test_codex_B_injected_char_device_missing_sysfs_dev_rejected(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            is_char_device=True,
            omit_sysfs_dev=True,  # missing /sys/class/drm/renderD128/dev
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(len(gpus), 1)
        self.assertFalse(gpus[0]["render_node_valid"])
        self.assertIsNone(gpus[0]["render_node"])
        self.assertFalse(gpu_rt.is_gpu_available(gpus[0]))

    # Codex 6.C: character device 1:3 => rejected
    def test_codex_C_char_device_1_3_rejected(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            major=1,  # mem major
            minor=3,  # /dev/null minor
            is_char_device=True,
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        # Even if sysfs had 1:3, it's not a valid DRM render node (or if sysfs has 226:128, mismatch)
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(len(gpus), 1)
        self.assertFalse(gpus[0]["render_node_valid"])
        self.assertFalse(gpu_rt.is_gpu_available(gpus[0]))

    # Codex 6.D: correct character device + correct DRM major/minor + correct PCI parent => accepted
    def test_codex_D_correct_char_device_correct_drm_dev_correct_pci_accepted(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            major=226,
            minor=128,
            is_char_device=True,
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(len(gpus), 1)
        self.assertTrue(gpus[0]["render_node_valid"])
        self.assertTrue(gpu_rt.is_gpu_available(gpus[0]))
        self.assertEqual(gpus[0]["render_node"], str(self.dev_dir / "dri/renderD128"))
        self.assertEqual(gpus[0]["persistent_render_path"], str(self.dev_dir / "dri/by-path/pci-0000:03:00.0-render"))

    # Codex 6.E: connector called card0-HDMI-A-1 + no parent relation => not attributed
    def test_codex_E_connector_called_card0_no_parent_not_attributed(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            connectors=[("HDMI-A-1", "connected", "enabled")],
            omit_connector_parent=True,  # No device link in connector dir
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0]["connected_connectors"], [])
        self.assertEqual(gpus[0]["enabled_connectors"], [])
        self.assertFalse(gpus[0]["active_display"])

    # Codex 6.F: unknown connector attribution => cannot resolve active display
    def test_codex_F_unknown_connector_attribution_cannot_resolve_active_display(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            connectors=[("HDMI-A-1", "connected", "enabled")],
            omit_connector_parent=True,
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "NO_DISPLAY")
        self.assertIsNone(display_gpu)
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    def test_char_device_major_minor_mismatch_rejected(self):
        # stat is 226:128, sysfs dev is 226:129
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            major=226,
            minor=128,
            is_char_device=True,
            sysfs_dev_override="226:129",
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertFalse(gpus[0]["render_node_valid"])
        self.assertFalse(gpu_rt.is_gpu_available(gpus[0]))

    def test_connected_and_enabled_is_active(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertTrue(gpus[0]["active_display"])
        self.assertEqual(gpus[0]["enabled_connectors"], ["card0-HDMI-A-1"])

        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(display_gpu["pci_address"], "0000:03:00.0")

        effective = gpu_rt.resolve_effective_candidate(gpus)
        self.assertIsNotNone(effective)
        self.assertEqual(effective["pci_address"], "0000:03:00.0")

    def test_connected_and_disabled_is_not_active(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            connectors=[("HDMI-A-1", "connected", "disabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertFalse(gpus[0]["active_display"])
        self.assertEqual(gpus[0]["connected_connectors"], ["card0-HDMI-A-1"])
        self.assertEqual(gpus[0]["enabled_connectors"], [])

        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "NO_ACTIVE_DISPLAY")
        self.assertIsNone(display_gpu)
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    def test_connected_with_enabled_unavailable(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            connectors=[("HDMI-A-1", "connected", None)],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertFalse(gpus[0]["active_display"])

        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(display_gpu)
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    def test_two_gpus_connected_only_one_enabled(self):
        self.add_pci_gpu(
            pci_slot="0000:00:02.0",
            card_name="card0",
            render_name="renderD128",
            minor=128,
            connectors=[("HDMI-A-1", "connected", "disabled")],
        )
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card1",
            render_name="renderD129",
            minor=129,
            connectors=[("HDMI-A-6", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        gpu_a = next(g for g in gpus if g["pci_address"] == "0000:00:02.0")
        gpu_b = next(g for g in gpus if g["pci_address"] == "0000:03:00.0")

        self.assertFalse(gpu_a["active_display"])
        self.assertTrue(gpu_b["active_display"])

        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(display_gpu["pci_address"], "0000:03:00.0")

        effective = gpu_rt.resolve_effective_candidate(gpus)
        self.assertIsNotNone(effective)
        self.assertEqual(effective["pci_address"], "0000:03:00.0")

    def test_enabled_displays_on_two_gpus_is_ambiguous(self):
        self.add_pci_gpu(
            pci_slot="0000:00:02.0",
            card_name="card0",
            render_name="renderD128",
            minor=128,
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card1",
            render_name="renderD129",
            minor=129,
            connectors=[("HDMI-A-6", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "AMBIGUOUS")
        self.assertIsNone(display_gpu)
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    def test_render_node_missing_is_unavailable(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name=None,
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertIsNone(gpus[0]["render_node"])
        self.assertFalse(gpus[0]["render_node_valid"])
        self.assertFalse(gpu_rt.is_gpu_available(gpus[0]))
        self.assertIsNone(gpu_rt.resolve_effective_candidate(gpus))

    def test_contradictory_pci_association_fails_closed(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            contradict_render_pci="0000:00:02.0",
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        gpu = next(g for g in gpus if g["pci_address"] == "0000:03:00.0")
        self.assertFalse(gpu["render_node_valid"])
        self.assertIsNone(gpu["render_node"])
        self.assertIsNone(gpu["persistent_render_path"])
        self.assertFalse(gpu_rt.is_gpu_available(gpu))

    def test_connector_attribution_contradiction_rejected(self):
        self.add_pci_gpu(
            pci_slot="0000:03:00.0",
            card_name="card0",
            render_name="renderD128",
            contradict_connector_pci="0000:00:02.0",
            connectors=[("HDMI-A-1", "connected", "enabled")],
        )
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        gpu = next(g for g in gpus if g["pci_address"] == "0000:03:00.0")
        self.assertEqual(gpu["connected_connectors"], [])
        self.assertEqual(gpu["enabled_connectors"], [])
        self.assertFalse(gpu["active_display"])

    def test_malformed_passport_root_list(self):
        runtime_gpus = [{"pci_address": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6"}]
        comparison = gpu_rt.compare_passport_gpus(runtime_gpus, [])
        self.assertEqual(comparison["status"], "EXTRA")
        self.assertEqual(comparison["extra"], ["0000:03:00.0"])
        self.assertEqual(comparison["matches"], [])

    def test_passport_gpu_details_none(self):
        runtime_gpus = [{"pci_address": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6"}]
        passport = {"detected": {"gpu_details": None}, "gpu_topology": None}
        comparison = gpu_rt.compare_passport_gpus(runtime_gpus, passport)
        self.assertEqual(comparison["status"], "EXTRA")
        self.assertEqual(comparison["extra"], ["0000:03:00.0"])

    def test_numeric_pci_slot_handled_safely(self):
        runtime_gpus = [{"pci_address": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6"}]
        passport = {"detected": {"gpu_details": [{"pci_slot": 12345}]}, "gpu_topology": None}
        comparison = gpu_rt.compare_passport_gpus(runtime_gpus, passport)
        self.assertEqual(comparison["status"], "EXTRA")

    def test_same_pci_slot_different_hardware_detected_as_changed(self):
        runtime_gpus = [{"pci_address": "0000:03:00.0", "vendor_id": "10de", "device_id": "2489"}]
        passport = {
            "detected": {
                "gpu_details": [
                    {"pci_slot": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6"}
                ]
            }
        }
        comparison = gpu_rt.compare_passport_gpus(runtime_gpus, passport)
        self.assertEqual(comparison["status"], "CHANGED")
        self.assertEqual(comparison["matches"], [])
        self.assertEqual(len(comparison["replaced"]), 1)
        self.assertEqual(comparison["replaced"][0]["pci_address"], "0000:03:00.0")

    def test_render_indices_reversed_pci_identity_correct(self):
        self.add_pci_gpu(pci_slot="0000:00:02.0", card_name="card1", render_name="renderD129", minor=129)
        self.add_pci_gpu(pci_slot="0000:03:00.0", card_name="card0", render_name="renderD128", minor=128)
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        gpu_0 = next(g for g in gpus if g["pci_address"] == "0000:00:02.0")
        gpu_3 = next(g for g in gpus if g["pci_address"] == "0000:03:00.0")
        self.assertTrue(gpu_0["render_node"].endswith("renderD129"))
        self.assertTrue(gpu_3["render_node"].endswith("renderD128"))
        self.assertTrue(gpu_0["persistent_render_path"].endswith("pci-0000:00:02.0-render"))
        self.assertTrue(gpu_3["persistent_render_path"].endswith("pci-0000:03:00.0-render"))

    def test_by_path_missing(self):
        self.add_pci_gpu(pci_slot="0000:03:00.0", card_name="card0", render_name="renderD128", create_by_path=False)
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(len(gpus), 1)
        self.assertIsNone(gpus[0]["persistent_render_path"])
        self.assertTrue(gpu_rt.is_gpu_available(gpus[0]))

    def test_broken_by_path_symlink_fails_closed(self):
        self.add_pci_gpu(pci_slot="0000:03:00.0", card_name="card0", render_name="renderD128", broken_by_path=True)
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertIsNone(gpus[0]["persistent_render_path"])

    def test_card_index_changes_identity_remains_pci(self):
        self.add_pci_gpu(pci_slot="0000:03:00.0", card_name="card7", render_name="renderD135", minor=135)
        gpus = gpu_rt.discover_gpus(sys_root=self.sys_dir, dev_root=self.dev_dir, stat_provider=self.stat_provider)
        self.assertEqual(gpus[0]["pci_address"], "0000:03:00.0")
        self.assertEqual(gpus[0]["card_node"], "card7")

    def test_no_fedora_mutations(self):
        passport_file = self.base / "profile.json"
        content = json.dumps({"detected": {"gpu_details": [{"pci_slot": "0000:03:00.0"}]}})
        passport_file.write_text(content)
        self.add_pci_gpu(pci_slot="0000:03:00.0")
        gpu_rt.build_gpu_runtime_summary(
            sys_root=self.sys_dir,
            dev_root=self.dev_dir,
            passport_path=passport_file,
            stat_provider=self.stat_provider,
        )
        self.assertEqual(passport_file.read_text(), content)


class TestRealPhysicalHostPassiveObservation(unittest.TestCase):
    def test_real_physical_host_passive_observation(self):
        sys_root = pathlib.Path("/sys")
        dev_root = pathlib.Path("/dev")
        if not (sys_root / "bus/pci/devices").is_dir() or not (dev_root / "dri").is_dir():
            self.skipTest("Host DRM or sysfs inaccessible in this environment")

        gpus = gpu_rt.discover_gpus(sys_root=sys_root, dev_root=dev_root)
        pci_slots = [g["pci_address"] for g in gpus]

        if "0000:03:00.0" not in pci_slots:
            self.skipTest("Host does not contain expected Arc A310 testbench device")

        arc = next(g for g in gpus if g["pci_address"] == "0000:03:00.0")
        self.assertTrue(gpu_rt.is_gpu_available(arc))
        self.assertTrue(arc["render_node_valid"])
        self.assertEqual(arc["persistent_render_path"], "/dev/dri/by-path/pci-0000:03:00.0-render")

        # Arc connector observation & proven parentage
        self.assertIn("card1-HDMI-A-6", arc["connected_connectors"])
        self.assertIn("card1-HDMI-A-6", arc["enabled_connectors"])
        self.assertTrue(arc["active_display"])

        # HD530 observation
        if "0000:00:02.0" in pci_slots:
            hd530 = next(g for g in gpus if g["pci_address"] == "0000:00:02.0")
            self.assertTrue(gpu_rt.is_gpu_available(hd530))
            self.assertFalse(hd530["active_display"])

        display_gpu, status = gpu_rt.resolve_display_gpu(gpus)
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(display_gpu["pci_address"], "0000:03:00.0")

        effective = gpu_rt.resolve_effective_candidate(gpus)
        self.assertIsNotNone(effective)
        self.assertEqual(effective["pci_address"], "0000:03:00.0")


if __name__ == "__main__":
    unittest.main()
