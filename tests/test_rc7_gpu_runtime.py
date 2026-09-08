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
import shutil
import socket
import stat
import subprocess
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


class TestHermeticVulkanDeviceResolution(unittest.TestCase):
    ARC_VULKAN_TEXT = """
GPU0:
VkPhysicalDeviceProperties:
---------------------------
\tapiVersion        = 1.4.354 (4211042)
\tdriverVersion     = 26.1.6 (109056006)
\tvendorID          = 0x8086
\tdeviceID          = 0x56a6
\tdeviceType        = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tdeviceName        = Intel(R) Arc(tm) A310 Graphics (DG2)

VkPhysicalDevicePCIBusInfoPropertiesEXT:
----------------------------------------
\tpciDomain   = 0
\tpciBus      = 3
\tpciDevice   = 0
\tpciFunction = 0

VkPhysicalDeviceDrmPropertiesEXT:
---------------------------------
\thasPrimary   = true
\thasRender    = true
\tprimaryMajor = 226
\tprimaryMinor = 1
\trenderMajor  = 226
\trenderMinor  = 129

VkPhysicalDeviceVulkan11Properties:
-----------------------------------
\tdeviceUUID                        = 8680a656-0500-0000-0300-000000000000
"""

    DUAL_GPU_TEXT = """
GPU0:
VkPhysicalDeviceProperties:
---------------------------
\tapiVersion        = 1.4.354 (4211042)
\tdriverVersion     = 26.1.6 (109056006)
\tvendorID          = 0x8086
\tdeviceID          = 0x1912
\tdeviceType        = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
\tdeviceName        = Intel(R) HD Graphics 530 (SKL GT2)

VkPhysicalDevicePCIBusInfoPropertiesEXT:
----------------------------------------
\tpciDomain   = 0
\tpciBus      = 0
\tpciDevice   = 2
\tpciFunction = 0

VkPhysicalDeviceDrmPropertiesEXT:
---------------------------------
\thasPrimary   = true
\thasRender    = true
\tprimaryMajor = 226
\tprimaryMinor = 0
\trenderMajor  = 226
\trenderMinor  = 128

VkPhysicalDeviceVulkan11Properties:
-----------------------------------
\tdeviceUUID                        = 86801219-0600-0000-0002-000000000000

GPU1:
VkPhysicalDeviceProperties:
---------------------------
\tapiVersion        = 1.4.354 (4211042)
\tdriverVersion     = 26.1.6 (109056006)
\tvendorID          = 0x8086
\tdeviceID          = 0x56a6
\tdeviceType        = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tdeviceName        = Intel(R) Arc(tm) A310 Graphics (DG2)

VkPhysicalDevicePCIBusInfoPropertiesEXT:
----------------------------------------
\tpciDomain   = 0
\tpciBus      = 3
\tpciDevice   = 0
\tpciFunction = 0

VkPhysicalDeviceDrmPropertiesEXT:
---------------------------------
\thasPrimary   = true
\thasRender    = true
\tprimaryMajor = 226
\tprimaryMinor = 1
\trenderMajor  = 226
\trenderMinor  = 129

VkPhysicalDeviceVulkan11Properties:
-----------------------------------
\tdeviceUUID                        = 8680a656-0500-0000-0300-000000000000

GPU2:
VkPhysicalDeviceProperties:
---------------------------
\tapiVersion        = 1.4.354 (4211042)
\tdriverVersion     = 26.1.6 (109056006)
\tvendorID          = 0x10005
\tdeviceID          = 0x0000
\tdeviceType        = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName        = llvmpipe (LLVM 22.1.8, 256 bits)

VkPhysicalDeviceVulkan11Properties:
-----------------------------------
\tdeviceUUID                        = 6d657361-3236-2e31-2e36-000000000000
"""

    def test_01_single_vulkan_device_matching_pci_resolves(self):
        devices = gpu_rt.parse_vulkaninfo_text(self.ARC_VULKAN_TEXT)
        self.assertEqual(len(devices), 1)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["pci_address"], "0000:03:00.0")
        self.assertEqual(res["vulkan_device_name"], "Intel(R) Arc(tm) A310 Graphics (DG2)")
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(res["vendor_id"], "8086")
        self.assertEqual(res["device_id"], "56a6")
        self.assertEqual(res["drm_render_major"], 226)
        self.assertEqual(res["drm_render_minor"], 129)
        self.assertIn("pci_bus_info_match", res["evidence"])

    def test_02_two_vulkan_devices_one_pci_match(self):
        devices = gpu_rt.parse_vulkaninfo_text(self.DUAL_GPU_TEXT)
        res_arc = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res_arc["status"], "RESOLVED")
        self.assertEqual(res_arc["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")

        res_hd = gpu_rt.resolve_vulkan_device_for_pci("0000:00:02.0", vulkan_devices=devices)
        self.assertEqual(res_hd["status"], "RESOLVED")
        self.assertEqual(res_hd["vulkan_device_uuid"], "86801219-0600-0000-0002-000000000000")

    def test_03_no_pci_match_returns_not_found(self):
        devices = gpu_rt.parse_vulkaninfo_text(self.DUAL_GPU_TEXT)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:07:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "NOT_FOUND")
        self.assertEqual(res["pci_address"], "0000:07:00.0")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("no_matching_vulkan_physical_device", res["evidence"])

    def test_04_duplicate_pci_evidence_returns_ambiguous(self):
        dup_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = GPU A
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 11111111-1111-1111-1111-111111111111

GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = GPU B
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 22222222-2222-2222-2222-222222222222
"""
        devices = gpu_rt.parse_vulkaninfo_text(dup_text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "AMBIGUOUS")
        self.assertIn("multiple_vulkan_devices_matching_pci", res["evidence"])

    def test_05_vulkan_unavailable(self):
        def failing_runner():
            return -1, "", "vulkaninfo: command not found"

        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", runner=failing_runner)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("vulkan_query_unavailable", res["evidence"])

    def test_06_llvmpipe_software_device_not_mapped_to_pci(self):
        llvm_only = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = llvmpipe (LLVM 22.1.8)
\tdeviceType = PHYSICAL_DEVICE_TYPE_CPU
\tvendorID = 0x10005
\tdeviceID = 0x0000
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 6d657361-3236-2e31-2e36-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(llvm_only)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "NOT_FOUND")

    def test_07_gpu_ordering_reversed_yields_same_result(self):
        reversed_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000

GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) HD Graphics 530 (SKL GT2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 0
\tpciDevice = 2
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 86801219-0600-0000-0002-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(reversed_text)
        res_arc = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        res_hd = gpu_rt.resolve_vulkan_device_for_pci("0000:00:02.0", vulkan_devices=devices)
        self.assertEqual(res_arc["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(res_hd["vulkan_device_uuid"], "86801219-0600-0000-0002-000000000000")

    def test_08_identical_marketing_names_pci_determines_identity(self):
        dual_identical_names = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = SuperGPU 9000
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 1
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa

GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = SuperGPU 9000
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 2
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
"""
        devices = gpu_rt.parse_vulkaninfo_text(dual_identical_names)
        res_1 = gpu_rt.resolve_vulkan_device_for_pci("0000:01:00.0", vulkan_devices=devices)
        res_2 = gpu_rt.resolve_vulkan_device_for_pci("0000:02:00.0", vulkan_devices=devices)
        self.assertEqual(res_1["vulkan_device_uuid"], "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(res_2["vulkan_device_uuid"], "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    def test_09_uuid_remains_opaque_no_pci_derivation_from_uuid(self):
        opaque_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = deadbeef-cafe-babe-0123-456789abcdef
"""
        devices = gpu_rt.parse_vulkaninfo_text(opaque_text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["vulkan_device_uuid"], "deadbeef-cafe-babe-0123-456789abcdef")
        res_none = gpu_rt.resolve_vulkan_device_for_pci("0000:00:01.0", vulkan_devices=devices)
        self.assertEqual(res_none["status"], "NOT_FOUND")

    def test_10_vendor_device_alone_insufficient(self):
        no_pci_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Duplicate Card
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tvendorID = 0x8086
\tdeviceID = 0x56a6
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 11111111-1111-1111-1111-111111111111

GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Duplicate Card
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tvendorID = 0x8086
\tdeviceID = 0x56a6
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 22222222-2222-2222-2222-222222222222
"""
        devices = gpu_rt.parse_vulkaninfo_text(no_pci_text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("LOCAL_DRM_IDENTITY_UNAVAILABLE", res["evidence"])

    def test_11_drm_major_minor_corroboration_when_available(self):
        devices = gpu_rt.parse_vulkaninfo_text(self.ARC_VULKAN_TEXT)
        arc_record = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(arc_record, vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertIn("drm_render_node_corroborated", res["evidence"])

    def test_12_conflicting_pci_vs_drm_evidence_fails_closed(self):
        conflict_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Conflicting GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 128
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(conflict_text)
        arc_record = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(arc_record, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("IDENTITY_CONFLICT", res["evidence"])
        self.assertIsNone(res["vulkan_device_uuid"])

    def test_13_non_zero_pci_domain_supported(self):
        non_zero_domain_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Enterprise GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 1
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 12345678-1234-1234-1234-123456789abc
"""
        devices = gpu_rt.parse_vulkaninfo_text(non_zero_domain_text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0001:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["pci_address"], "0001:03:00.0")

    def test_14_malformed_vulkan_properties_no_crash(self):
        garbage = "not a valid vulkaninfo output\nrandom garbage = 1234\nGPU:\n===\n"
        devices = gpu_rt.parse_vulkaninfo_text(garbage)
        self.assertEqual(devices, [])
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "NOT_FOUND")

    def test_resolve_vulkan_device_for_gpu_helper(self):
        devices = gpu_rt.parse_vulkaninfo_text(self.ARC_VULKAN_TEXT)
        gpu_dict = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(gpu_dict, vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertIn("drm_render_node_corroborated", res["evidence"])

    def test_supplementary_foreign_section_device_uuid_ignored(self):
        foreign_uuid_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test Real GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
VkPhysicalDeviceUnapprovedForeignProperties:
\tdeviceUUID = bad00000-0000-0000-0000-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(foreign_uuid_text)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["device_uuid"], "8680a656-0500-0000-0300-000000000000")
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")

    def test_supplementary_indented_gpu_headers_remain_separated(self):
        indented_text = """
  GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = GPU Zero
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 1
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 11111111-1111-1111-1111-111111111111

    GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = GPU One
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 2
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 22222222-2222-2222-2222-222222222222
"""
        devices = gpu_rt.parse_vulkaninfo_text(indented_text)
        self.assertEqual(len(devices), 2)
        res0 = gpu_rt.resolve_vulkan_device_for_pci("0000:01:00.0", vulkan_devices=devices)
        res1 = gpu_rt.resolve_vulkan_device_for_pci("0000:02:00.0", vulkan_devices=devices)
        self.assertEqual(res0["vulkan_device_uuid"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(res1["vulkan_device_uuid"], "22222222-2222-2222-2222-222222222222")

    def test_supplementary_strict_uuid_validation_rejects_garbage(self):
        bad_uuids = [
            "prefix8680a656-0500-0000-0300-000000000000",
            "8680a656-0500-0000-0300-000000000000suffix",
            "[8680a656-0500-0000-0300-000000000000]",
            "8680a656-0500-0000-0300-00000000000",
            "8680a656-0500-0000-0300-0000000000000",
            "8680a656-0500-0000-0300-00000000000g",
        ]
        for bad_uuid in bad_uuids:
            text = f"""
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Bad UUID GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = {bad_uuid}
"""
            devices = gpu_rt.parse_vulkaninfo_text(text)
            self.assertEqual(len(devices), 1)
            self.assertIsNone(devices[0]["device_uuid"])
            res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
            self.assertEqual(res["status"], "UNAVAILABLE")
            self.assertIsNone(res["vulkan_device_uuid"])
            self.assertIn("missing_device_uuid", res["evidence"])

    # --- Section 13: 13 Required Reproductions (A through M) ---

    def test_reproduction_A_two_contradictory_pci_structures(self):
        # Two contradictory complete PCI structures
        # => PCI state CONFLICT => UNAVAILABLE => DRM fallback forbidden
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 4
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["pci_state"], gpu_rt.EvidenceState.CONFLICT)
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("INVALID_OR_CONFLICTING_PCI_EVIDENCE", res["evidence"])
        self.assertIn("IDENTITY_EVIDENCE_CONFLICT", res["evidence"])

    def test_reproduction_B_valid_pci_structure_then_incomplete_pci_structure(self):
        # Valid PCI structure then incomplete PCI structure
        # => evidence no longer usable => UNAVAILABLE
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["pci_state"], gpu_rt.EvidenceState.INVALID)
        self.assertIsNone(devices[0]["pci_address"])
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("INVALID_OR_CONFLICTING_PCI_EVIDENCE", res["evidence"])

    def test_reproduction_C_two_contradictory_drm_structures(self):
        # Two contradictory DRM structures
        # => DRM CONFLICT => UNAVAILABLE => PCI-only bypass forbidden
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 128
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["drm_state"], gpu_rt.EvidenceState.CONFLICT)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("IDENTITY_EVIDENCE_CONFLICT", res["evidence"])

    def test_reproduction_D_valid_drm_structure_then_has_render_false(self):
        # Valid DRM structure then hasRender=false in SAME GPU block
        # => DRM CONFLICT => UNAVAILABLE => no UUID
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = false
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["drm_state"], gpu_rt.EvidenceState.CONFLICT)
        self.assertIsNone(devices[0]["drm_render_major"])
        self.assertIsNone(devices[0]["drm_render_minor"])
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("IDENTITY_EVIDENCE_CONFLICT", res["evidence"])
        self.assertIsNone(res["vulkan_device_uuid"])

    def test_reproduction_D_reverse_order_has_render_false_then_valid_drm_is_conflict(self):
        # hasRender=false then valid DRM structure in SAME GPU block
        # => DRM CONFLICT => UNAVAILABLE => no UUID
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = false
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["drm_state"], gpu_rt.EvidenceState.CONFLICT)
        self.assertIsNone(devices[0]["drm_render_major"])
        self.assertIsNone(devices[0]["drm_render_minor"])
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("IDENTITY_EVIDENCE_CONFLICT", res["evidence"])
        self.assertIsNone(res["vulkan_device_uuid"])

    def test_single_has_render_false_occurrence_is_absent(self):
        # A single occurrence: hasRender=false with no previous valid DRM
        # => drm_state = ABSENT => allows PCI-only resolution
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = false
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["drm_state"], gpu_rt.EvidenceState.ABSENT)
        self.assertIsNone(devices[0]["drm_render_major"])
        self.assertIsNone(devices[0]["drm_render_minor"])
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertIn("pci_bus_info_match", res["evidence"])
        self.assertIn("drm_corroboration_unavailable", res["evidence"])
        self.assertNotIn("drm_render_node_corroborated", res["evidence"])

    def test_reproduction_E_valid_drm_structure_then_incomplete_drm_structure(self):
        # Valid DRM structure then incomplete DRM structure
        # => stale render values cleared => UNAVAILABLE if target depends on it
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["drm_state"], gpu_rt.EvidenceState.INVALID)
        self.assertIsNone(devices[0]["drm_render_major"])
        self.assertIsNone(devices[0]["drm_render_minor"])
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("INVALID_DRM_EVIDENCE", res["evidence"])

    def test_reproduction_F_gpu0_with_device_name_only(self):
        # GPU0 with deviceName only => incomplete enumeration => UNAVAILABLE
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test Incomplete GPU
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertFalse(devices.enumeration_reliable)
        self.assertEqual(devices.unreliable_reason, "INCOMPLETE_VULKAN_ENUMERATION")
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertNotEqual(res["status"], "NOT_FOUND")
        self.assertIn("INCOMPLETE_VULKAN_ENUMERATION", res["evidence"])

    def test_reproduction_G_malformed_pci_structure_with_matching_validated_drm(self):
        # Malformed PCI structure + matching validated DRM => UNAVAILABLE => fallback forbidden
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["pci_state"], gpu_rt.EvidenceState.INVALID)
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("INVALID_OR_CONFLICTING_PCI_EVIDENCE", res["evidence"])

    def test_reproduction_H_pci_structure_genuinely_absent_with_validated_drm_match(self):
        # PCI structure genuinely absent + validated DRM match => RESOLVED via validated fallback
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["pci_state"], gpu_rt.EvidenceState.ABSENT)
        valid_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(valid_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertIn("validated_t8_1a_drm_fallback_match", res["evidence"])

    def test_reproduction_I_pci_absent_with_render_node_valid_false(self):
        # PCI absent + render_node_valid=False => UNAVAILABLE => NOT NOT_FOUND
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        unvalidated_gpu = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": False,
        }
        res = gpu_rt.resolve_vulkan_device_for_gpu(unvalidated_gpu, vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertNotEqual(res["status"], "NOT_FOUND")
        self.assertIn("LOCAL_DRM_IDENTITY_UNAVAILABLE", res["evidence"])

        res_pci = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res_pci["status"], "UNAVAILABLE")
        self.assertNotEqual(res_pci["status"], "NOT_FOUND")
        self.assertIn("LOCAL_DRM_IDENTITY_UNAVAILABLE", res_pci["evidence"])

    def test_reproduction_J_leading_single_quote_before_uuid(self):
        # Leading single quote before otherwise valid UUID => INVALID UUID
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = '8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["uuid_state"], gpu_rt.EvidenceState.INVALID)
        self.assertIsNone(devices[0]["device_uuid"])
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("missing_device_uuid", res["evidence"])

    def test_reproduction_K_uuid_with_unmatched_double_quote(self):
        # UUID with unmatched double quote => INVALID UUID
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Test GPU
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = "8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        self.assertEqual(devices[0]["uuid_state"], gpu_rt.EvidenceState.INVALID)
        self.assertIsNone(devices[0]["device_uuid"])
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("missing_device_uuid", res["evidence"])

    def test_reproduction_L_multiple_trustworthy_matching_candidates(self):
        # Multiple trustworthy matching candidates => AMBIGUOUS
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Candidate A
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 11111111-1111-1111-1111-111111111111

GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Candidate B
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 22222222-2222-2222-2222-222222222222
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "AMBIGUOUS")
        self.assertIn("multiple_vulkan_devices_matching_pci", res["evidence"])
        self.assertIsNone(res["vulkan_device_uuid"])

    def test_reproduction_M_trustworthy_enumeration_with_zero_match(self):
        # Trustworthy enumeration + zero match => NOT_FOUND
        text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text)
        res = gpu_rt.resolve_vulkan_device_for_pci("0000:07:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "NOT_FOUND")
        self.assertEqual(res["pci_address"], "0000:07:00.0")
        self.assertIsNone(res["vulkan_device_uuid"])
        self.assertIn("no_matching_vulkan_physical_device", res["evidence"])


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

    def test_real_physical_host_arc_vulkan_resolution(self):
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo binary not found on host")
        if not pathlib.Path("/sys/bus/pci/devices/0000:03:00.0").is_dir():
            self.skipTest("Host does not contain Arc A310 testbench device")

        status, devices = gpu_rt.query_vulkan_devices()
        if status != "AVAILABLE" or not devices:
            self.skipTest("Vulkan physical device enumeration unavailable in this environment")

        if "0000:03:00.0" not in [d.get("pci_address") for d in devices]:
            self.skipTest("Arc A310 physical device not accessible in Vulkan enumeration")

        res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["pci_address"], "0000:03:00.0")
        self.assertEqual(res["vulkan_device_name"], "Intel(R) Arc(tm) A310 Graphics (DG2)")
        self.assertEqual(res["vulkan_device_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(res["drm_render_major"], 226)
        self.assertEqual(res["drm_render_minor"], 129)
        self.assertIn("pci_bus_info_match", res["evidence"])

        arc_record = {
            "pci_address": "0000:03:00.0",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
        }
        res_corroborated = gpu_rt.resolve_vulkan_device_for_gpu(arc_record, vulkan_devices=devices)
        self.assertEqual(res_corroborated["status"], "RESOLVED")
        self.assertIn("drm_render_node_corroborated", res_corroborated["evidence"])

    def test_real_physical_host_hd530_vulkan_resolution(self):
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo binary not found on host")
        if not pathlib.Path("/sys/bus/pci/devices/0000:00:02.0").is_dir():
            self.skipTest("Host does not contain HD530 testbench device")

        status, devices = gpu_rt.query_vulkan_devices()
        if status != "AVAILABLE" or not devices:
            self.skipTest("Vulkan physical device enumeration unavailable in this environment")

        if "0000:00:02.0" not in [d.get("pci_address") for d in devices]:
            self.skipTest("HD530 physical device not accessible in Vulkan enumeration")

        res = gpu_rt.resolve_vulkan_device_for_pci("0000:00:02.0", vulkan_devices=devices)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["pci_address"], "0000:00:02.0")
        self.assertEqual(res["vulkan_device_name"], "Intel(R) HD Graphics 530 (SKL GT2)")
        self.assertEqual(res["vulkan_device_uuid"], "86801219-0600-0000-0002-000000000000")
        self.assertEqual(res["drm_render_major"], 226)
        self.assertEqual(res["drm_render_minor"], 128)
        self.assertIn("pci_bus_info_match", res["evidence"])

        hd530_record = {
            "pci_address": "0000:00:02.0",
            "render_node": "/dev/dri/renderD128",
            "render_node_valid": True,
        }
        res_corroborated = gpu_rt.resolve_vulkan_device_for_gpu(hd530_record, vulkan_devices=devices)
        self.assertEqual(res_corroborated["status"], "RESOLVED")
        self.assertIn("drm_render_node_corroborated", res_corroborated["evidence"])

    def test_real_physical_host_llvmpipe_excluded(self):
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo binary not found on host")
        status, devices = gpu_rt.query_vulkan_devices()
        if status != "AVAILABLE" or not devices:
            self.skipTest("Vulkan query unavailable in this environment")

        llvm_devices = [d for d in devices if d.get("device_name") and "llvmpipe" in d["device_name"]]
        if not llvm_devices:
            self.skipTest("No llvmpipe software device present in Vulkan enumeration")
        for d in llvm_devices:
            self.assertEqual(d.get("device_type"), "PHYSICAL_DEVICE_TYPE_CPU")
            self.assertIsNone(d.get("pci_address"))

    def test_real_physical_host_mpv_uuid_acceptance(self):
        if not shutil.which("mpv"):
            self.skipTest("mpv binary not found")
        if not shutil.which("vulkaninfo"):
            self.skipTest("vulkaninfo binary not found")

        wayland_display = os.environ.get("WAYLAND_DISPLAY")
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not wayland_display:
            uid = os.getuid()
            cand_xdg = xdg_runtime_dir or f"/run/user/{uid}"
            if (pathlib.Path(cand_xdg) / "wayland-0").exists():
                wayland_display = "wayland-0"
                xdg_runtime_dir = cand_xdg

        if not wayland_display or not xdg_runtime_dir:
            self.skipTest("WAYLAND_DISPLAY or XDG_RUNTIME_DIR not available in environment")

        sock_path = pathlib.Path(xdg_runtime_dir) / wayland_display
        if not sock_path.exists():
            self.skipTest(f"Wayland socket {sock_path} does not exist")

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(sock_path))
            sock.close()
        except Exception as exc:
            self.skipTest(f"Wayland socket {sock_path} not accessible: {exc}")

        status, devices = gpu_rt.query_vulkan_devices()
        if status != "AVAILABLE" or not devices or not getattr(devices, "enumeration_reliable", True):
            self.skipTest("Vulkan physical device enumeration unavailable in this environment")

        arc_res = gpu_rt.resolve_vulkan_device_for_pci("0000:03:00.0", vulkan_devices=devices)
        if arc_res["status"] != "RESOLVED" or not arc_res.get("vulkan_device_uuid"):
            self.skipTest("Arc A310 testbench device not resolved in Vulkan enumeration")
        arc_uuid = arc_res["vulkan_device_uuid"]

        env = os.environ.copy()
        env["WAYLAND_DISPLAY"] = wayland_display
        env["XDG_RUNTIME_DIR"] = xdg_runtime_dir

        probe_cmd = [
            "mpv",
            "--no-config",
            "--vo=gpu-next",
            "--gpu-api=vulkan",
            f"--vulkan-device={arc_uuid}",
            "--msg-level=gpu_next=trace,vo=trace,libplacebo=trace",
            "--ao=null",
            "--frames=1",
            "avdevice://lavfi:color=c=black:s=64x64:d=0.04",
        ]
        try:
            probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=12, env=env)
        except Exception as e:
            self.skipTest(f"MPV execution failed: {e}")

        if probe.returncode != 0:
            combined = probe.stdout + probe.stderr
            if any(err in combined for err in [
                "Failed initializing any suitable GPU context",
                "couldn't open the Wayland display",
                "couldn't open the X11 display",
                "Cannot open display",
                "Failed to connect to wayland",
                "wl_display_connect",
            ]):
                self.skipTest(f"Display/Wayland context inaccessible for MPV Vulkan init: {combined.strip().splitlines()[-1] if combined.strip() else 'context failed'}")
            self.fail(f"mpv failed with unexpected error: {probe.stderr}")

        self.assertEqual(probe.returncode, 0)
        self.assertIn("Intel(R) Arc(tm) A310 Graphics", probe.stdout + probe.stderr)

        hd_res = gpu_rt.resolve_vulkan_device_for_pci("0000:00:02.0", vulkan_devices=devices)
        if hd_res["status"] == "RESOLVED" and hd_res.get("vulkan_device_uuid"):
            hd_uuid = hd_res["vulkan_device_uuid"]
            hd_cmd = [
                "mpv",
                "--no-config",
                "--vo=gpu-next",
                "--gpu-api=vulkan",
                f"--vulkan-device={hd_uuid}",
                "--msg-level=gpu_next=trace,vo=trace,libplacebo=trace",
                "--ao=null",
                "--frames=1",
                "avdevice://lavfi:color=c=black:s=64x64:d=0.04",
            ]
            hd_proc = subprocess.run(hd_cmd, capture_output=True, text=True, timeout=12, env=env)
            self.assertEqual(hd_proc.returncode, 0)
            self.assertIn("Intel(R) HD Graphics 530", hd_proc.stdout + hd_proc.stderr)

        bad_cmd = [
            "mpv",
            "--no-config",
            "--vo=gpu-next",
            "--gpu-api=vulkan",
            "--vulkan-device=invalid-uuid",
            "--ao=null",
            "--frames=1",
            "avdevice://lavfi:color=c=black:s=64x64:d=0.04",
        ]
        bad_proc = subprocess.run(bad_cmd, capture_output=True, text=True, timeout=12, env=env)
        combined_bad = bad_proc.stdout + bad_proc.stderr
        self.assertEqual(bad_proc.returncode, 1)
        self.assertIn("No device with name 'invalid-uuid'", combined_bad)


class TestDynamicPlaybackGPUBinding(unittest.TestCase):
    """Hermetic tests for dynamic MPV GPU binding (T8.1B2).

    Covers all 14 scenarios from Section L.
    """

    def setUp(self):
        self.valid_arc_gpu = {
            "pci_address": "0000:03:00.0",
            "driver": "i915",
            "card_node": "/dev/dri/card1",
            "render_node": "/dev/dri/renderD129",
            "render_node_valid": True,
            "persistent_render_path": "/dev/dri/by-path/pci-0000:03:00.0-render",
            "connected_connectors": ["HDMI-A-1"],
            "enabled_connectors": ["HDMI-A-1"],
            "active_display": True,
            "device_type": "PHYSICAL_DEVICE_TYPE_DISCRETE_GPU",
        }
        self.valid_vulkan_text = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 129
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""

    def test_01_unique_active_gpu_all_evidence_valid_binds(self):
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["pci_address"], "0000:03:00.0")
        self.assertEqual(binding["drm_render_path"], "/dev/dri/by-path/pci-0000:03:00.0-render")
        self.assertEqual(binding["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(
            binding["mpv_args"],
            [
                "--vulkan-device=8680a656-0500-0000-0300-000000000000",
            ],
        )
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

    def test_02_display_ambiguous_auto_fallback(self):
        gpu1 = dict(self.valid_arc_gpu, pci_address="0000:03:00.0", active_display=True)
        gpu2 = dict(self.valid_arc_gpu, pci_address="0000:00:02.0", active_display=True, connected_connectors=["DP-1"], enabled_connectors=["DP-1"])
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[gpu1, gpu2],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "DISPLAY_AMBIGUOUS")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_03_no_active_display_auto_fallback(self):
        gpu1 = dict(self.valid_arc_gpu, active_display=False, enabled_connectors=[])
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[gpu1],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "DISPLAY_NOT_FOUND")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_04_gpu_unavailable_auto_fallback(self):
        gpu1 = dict(self.valid_arc_gpu, render_node_valid=False)
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[gpu1],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "GPU_UNAVAILABLE")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_05_persistent_render_path_missing_auto_fallback(self):
        gpu1 = dict(self.valid_arc_gpu, persistent_render_path=None)
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[gpu1],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "PERSISTENT_RENDER_PATH_MISSING")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_06_vulkan_not_found_auto_fallback(self):
        other_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) HD Graphics 530 (SKL GT2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 0
\tpciDevice = 2
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 128
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 86801219-0600-0000-0002-000000000000
"""
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(other_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "VULKAN_NOT_FOUND")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_07_vulkan_unavailable_auto_fallback(self):
        incomplete_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Incomplete GPU
"""
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(incomplete_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "VULKAN_UNAVAILABLE")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_08_vulkan_ambiguous_auto_fallback(self):
        ambiguous_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000001
"""
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(ambiguous_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "VULKAN_AMBIGUOUS")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_09_pci_drm_identity_conflict_auto_fallback(self):
        conflict_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 128
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(conflict_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "AUTO_FALLBACK")
        self.assertEqual(binding["reason"], "PCI_DRM_CONFLICT")
        self.assertEqual(binding["mpv_args"], [])
        self.assertIsNone(binding["drm_render_path"])
        self.assertIsNone(binding["vulkan_uuid"])

    def test_10_render_node_card_index_changes_persistent_pci_path_used(self):
        gpu_changed_index = dict(
            self.valid_arc_gpu,
            render_node="/dev/dri/renderD135",
            persistent_render_path="/dev/dri/by-path/pci-0000:03:00.0-render",
        )
        vulkan_135 = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceDrmPropertiesEXT:
\thasRender = true
\trenderMajor = 226
\trenderMinor = 135
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        vulkan_devices = gpu_rt.parse_vulkaninfo_text(vulkan_135)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[gpu_changed_index],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["drm_render_path"], "/dev/dri/by-path/pci-0000:03:00.0-render")
        self.assertNotIn("renderD135", binding["drm_render_path"])
        self.assertEqual(binding["mpv_args"], ["--vulkan-device=8680a656-0500-0000-0300-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

    def test_11_vulkan_enumeration_order_reversed_same_uuid(self):
        text_a = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) HD Graphics 530 (SKL GT2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 0
\tpciDevice = 2
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 86801219-0600-0000-0002-000000000000
GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
"""
        text_b = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) HD Graphics 530 (SKL GT2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 0
\tpciDevice = 2
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 86801219-0600-0000-0002-000000000000
"""
        devices_a = gpu_rt.parse_vulkaninfo_text(text_a)
        devices_b = gpu_rt.parse_vulkaninfo_text(text_b)
        binding_a = gpu_rt.resolve_playback_gpu_binding(detected_gpus=[self.valid_arc_gpu], vulkan_devices=devices_a)
        binding_b = gpu_rt.resolve_playback_gpu_binding(detected_gpus=[self.valid_arc_gpu], vulkan_devices=devices_b)
        self.assertEqual(binding_a["status"], "RENDER_BOUND")
        self.assertEqual(binding_b["status"], "RENDER_BOUND")
        self.assertEqual(binding_a["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(binding_b["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(binding_a["mpv_args"], ["--vulkan-device=8680a656-0500-0000-0300-000000000000"])
        self.assertEqual(binding_b["mpv_args"], ["--vulkan-device=8680a656-0500-0000-0300-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding_a["mpv_args"]))
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding_b["mpv_args"]))

    def test_12_two_identical_gpu_names_pci_identity_determines_mapping(self):
        text_two_arcs = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 3
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0300-000000000000
GPU1:
VkPhysicalDeviceProperties:
\tdeviceName = Intel(R) Arc(tm) A310 Graphics (DG2)
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 4
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 8680a656-0500-0000-0400-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(text_two_arcs)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["pci_address"], "0000:03:00.0")
        self.assertEqual(binding["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(binding["mpv_args"], ["--vulkan-device=8680a656-0500-0000-0300-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

    def test_13_no_stale_render_nodes_emitted_by_generator(self):
        generator_path = PAYLOAD / "openhtpc-runtime-generator.py"
        spec = importlib.util.spec_from_file_location("generator_test_13", generator_path)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            profile_path = base / "profile.json"
            pure_path = base / "pure.conf"
            ref_path = base / "reference.conf"
            options_path = base / "options.txt"
            values_path = base / "values.txt"
            version_path = base / "version.json"

            passport = {
                "schema": 1,
                "generator": {"name": "OPENHTPC Builder", "version": "1.2.0"},
                "gpu_topology": {
                    "display_gpu": {"pci_slot": "0000:03:00.0", "render_node": "/dev/dri/renderD129"},
                    "processing_gpu": {"pci_slot": "0000:03:00.0", "render_node": "/dev/dri/renderD129"},
                    "offload_required": False,
                },
                "video_backend": {"status": "observed", "decode_api": "vaapi", "render_api": "vulkan"},
                "runtime": {"status": "pending"},
                "runtime_profiles": {"profiles": {}},
            }
            profile_path.write_text(json.dumps(passport), encoding="utf-8")
            options = (
                "vo", "gpu-api", "hwdec", "vaapi-device", "include", "scale", "dscale",
                "cscale", "dither", "dither-depth", "scaler-resizes-only",
                "correct-downscaling", "linear-downscaling", "sigmoid-upscaling",
                "target-colorspace-hint", "gamut-mapping-mode",
            )
            reference = {
                "scale": "spline36", "dscale": "mitchell", "cscale": "spline36",
                "dither": "fruit", "dither-depth": "auto", "target-colorspace-hint": "auto",
                "gamut-mapping-mode": "auto",
            }
            options_path.write_text("".join(f" --{name} String {reference.get(name, 'available')}\n" for name in options), encoding="utf-8")
            values_path.write_text("gpu-next vulkan vaapi\n", encoding="utf-8")
            version_path.write_text(json.dumps({"version": "1.2.0", "build_id": "test"}), encoding="utf-8")

            gen.generate(profile_path, pure_path, ref_path, options_path, values_path, version_path)

            pure_content = pure_path.read_text(encoding="utf-8")
            ref_content = ref_path.read_text(encoding="utf-8")

            self.assertIn("vo=gpu-next", pure_content)
            self.assertIn("gpu-api=vulkan", pure_content)
            self.assertIn("hwdec=vaapi", pure_content)
            self.assertNotIn("renderD128", pure_content)
            self.assertNotIn("renderD129", pure_content)
            self.assertNotIn("vaapi-device", pure_content)

            self.assertNotIn("renderD128", ref_content)
            self.assertNotIn("renderD129", ref_content)
            self.assertNotIn("vaapi-device", ref_content)

    def test_14_all_three_playback_paths_receive_same_binding_semantics(self):
        policy_path = PAYLOAD / "openhtpc-playback-policy.py"
        spec = importlib.util.spec_from_file_location("policy_test_14", policy_path)
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)

        bound_decision = {
            "status": "RENDER_BOUND",
            "pci_address": "0000:03:00.0",
            "drm_render_path": "/dev/dri/by-path/pci-0000:03:00.0-render",
            "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
            "vulkan_device_name": "Intel Arc A310",
            "reason": "COHERENT_RENDER_ALIGNED",
            "evidence": [],
            "mpv_args": [
                "--vulkan-device=8680a656-0500-0000-0300-000000000000",
            ],
        }
        fallback_decision = {
            "status": "AUTO_FALLBACK",
            "pci_address": None,
            "drm_render_path": None,
            "vulkan_uuid": None,
            "vulkan_device_name": None,
            "reason": "GPU_UNAVAILABLE",
            "evidence": [],
            "mpv_args": [],
        }

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            (home / ".config/openhtpc").mkdir(parents=True)
            (home / ".config/openhtpc/user-config.json").write_text(json.dumps({"presentation_mode": "PURE"}), encoding="utf-8")
            rt_dir = home / ".config/openhtpc/runtime/mpv"
            rt_dir.mkdir(parents=True)
            (rt_dir / "pure.conf").write_text("vo=gpu-next\ngpu-api=vulkan\nhwdec=vaapi\n", encoding="utf-8")

            # Local path
            local_bound = pol.resolve(home, None, "local", gpu_binding=bound_decision)
            self.assertIn("--vulkan-device=8680a656-0500-0000-0300-000000000000", local_bound["mpv_args"])
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in local_bound["mpv_args"]))
            self.assertEqual(local_bound["gpu_render_binding"]["status"], "RENDER_BOUND")
            self.assertEqual(local_bound["decode_policy"]["status"], "OBSERVED")
            self.assertEqual(local_bound["decode_policy"]["hwdec"], "vaapi")
            self.assertEqual(local_bound["decode_policy"]["physical_gpu_binding"], "NOT_PROVEN")

            local_fallback = pol.resolve(home, None, "local", gpu_binding=fallback_decision)
            self.assertFalse(any(a.startswith(("--vaapi-device=", "--vulkan-device=")) for a in local_fallback["mpv_args"]))
            self.assertEqual(local_fallback["gpu_render_binding"]["status"], "AUTO_FALLBACK")

            # DVD path
            dvd_bound = pol.resolve(home, None, "dvd", gpu_binding=bound_decision)
            self.assertIn("--vulkan-device=8680a656-0500-0000-0300-000000000000", dvd_bound["mpv_args"])
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in dvd_bound["mpv_args"]))
            self.assertEqual(dvd_bound["gpu_render_binding"]["status"], "RENDER_BOUND")

            dvd_fallback = pol.resolve(home, None, "dvd", gpu_binding=fallback_decision)
            self.assertFalse(any(a.startswith(("--vaapi-device=", "--vulkan-device=")) for a in dvd_fallback["mpv_args"]))

            # Blu-ray path (via effective_policy_args)
            optical_backend_path = PAYLOAD / "openhtpc-protected-optical-backend.py"
            spec_opt = importlib.util.spec_from_file_location("opt_backend_14", optical_backend_path)
            opt_mod = importlib.util.module_from_spec(spec_opt)
            spec_opt.loader.exec_module(opt_mod)

            bluray_bound_decision = pol.resolve(home, None, "bluray", gpu_binding=bound_decision)
            bluray_bound_args = opt_mod.effective_policy_args(bluray_bound_decision)
            self.assertIn("--vulkan-device=8680a656-0500-0000-0300-000000000000", bluray_bound_args)
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in bluray_bound_args))

            bluray_fallback_decision = pol.resolve(home, None, "bluray", gpu_binding=fallback_decision)
            bluray_fallback_args = opt_mod.effective_policy_args(bluray_fallback_decision)
            self.assertFalse(any(a.startswith(("--vaapi-device=", "--vulkan-device=")) for a in bluray_fallback_args))

    def test_15_live_salon_host_synthetic_playback_binding(self):
        if not pathlib.Path("/dev/dri/by-path/pci-0000:03:00.0-render").exists():
            self.skipTest("Host does not contain Arc persistent render path")
        binding = gpu_rt.resolve_playback_gpu_binding()
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["pci_address"], "0000:03:00.0")
        self.assertEqual(binding["drm_render_path"], "/dev/dri/by-path/pci-0000:03:00.0-render")
        self.assertEqual(binding["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
        self.assertEqual(
            binding["mpv_args"],
            [
                "--vulkan-device=8680a656-0500-0000-0300-000000000000",
            ],
        )
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

        wayland_display = os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/1000"
        env = os.environ.copy()
        env["WAYLAND_DISPLAY"] = wayland_display
        env["XDG_RUNTIME_DIR"] = xdg_runtime_dir

        probe_cmd = [
            "mpv",
            "--no-config",
            "--vo=gpu-next",
            "--gpu-api=vulkan",
            "--hwdec=vaapi",
            *binding["mpv_args"],
            "--msg-level=all=v",
            "--ao=null",
            "--frames=1",
            "avdevice://lavfi:color=c=black:s=64x64:d=0.04",
        ]
        try:
            probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=12, env=env)
        except Exception as e:
            self.skipTest(f"MPV execution failed: {e}")

        if probe.returncode != 0:
            combined = probe.stdout + probe.stderr
            if any(err in combined for err in [
                "Failed initializing any suitable GPU context",
                "couldn't open the Wayland display",
                "couldn't open the X11 display",
                "Cannot open display",
                "Failed to connect to wayland",
                "wl_display_connect",
            ]):
                self.skipTest("Display/Wayland context inaccessible")
            self.fail(f"mpv failed with unexpected error: {probe.stderr}")

        self.assertEqual(probe.returncode, 0)
        combined_out = probe.stdout + probe.stderr
        self.assertIn("Intel(R) Arc(tm) A310 Graphics", combined_out)
        self.assertIn("Setting option 'vulkan-device' = '8680a656-0500-0000-0300-000000000000'", combined_out)
        self.assertNotIn("Setting option 'vaapi-device'", combined_out)

    def test_16_openhtpc_gpu_runtime_module_managed_and_installable(self):
        script_path = PAYLOAD / "openhtpc-gpu-runtime.py"
        self.assertTrue(script_path.is_file(), "payload/openhtpc-gpu-runtime.py must exist")

        installer_text = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
        self.assertIn("openhtpc-gpu-runtime.py", installer_text, "openhtpc-gpu-runtime.py must be in installer")

        managed_files = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("openhtpc-gpu-runtime.py", managed_files, "openhtpc-gpu-runtime.py must be in managed-files.txt")

    def test_17_nvidia_runtime_render_binding_preserves_nvdec_no_vaapi(self):
        policy_path = PAYLOAD / "openhtpc-playback-policy.py"
        spec = importlib.util.spec_from_file_location("policy_test_17", policy_path)
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)

        nvidia_gpu = {
            "pci_address": "0000:01:00.0",
            "driver": "nvidia",
            "card_node": "/dev/dri/card0",
            "render_node": "/dev/dri/renderD128",
            "render_node_valid": True,
            "persistent_render_path": "/dev/dri/by-path/pci-0000:01:00.0-render",
            "connected_connectors": ["HDMI-A-1"],
            "enabled_connectors": ["HDMI-A-1"],
            "active_display": True,
            "device_type": "PHYSICAL_DEVICE_TYPE_DISCRETE_GPU",
        }
        nvidia_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = NVIDIA GeForce RTX 3060
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 1
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 10de2503-0000-0000-0000-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(nvidia_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[nvidia_gpu],
            vulkan_devices=devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["pci_address"], "0000:01:00.0")
        self.assertEqual(binding["vulkan_uuid"], "10de2503-0000-0000-0000-000000000000")
        self.assertEqual(binding["mpv_args"], ["--vulkan-device=10de2503-0000-0000-0000-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            rt_dir = home / ".config/openhtpc/runtime/mpv"
            rt_dir.mkdir(parents=True)
            (rt_dir / "pure.conf").write_text("vo=gpu-next\ngpu-api=vulkan\nhwdec=nvdec\n", encoding="utf-8")
            (home / ".config/openhtpc/user-config.json").write_text(json.dumps({"presentation_mode": "PURE"}), encoding="utf-8")

            res = pol.resolve(home, None, "local", gpu_binding=binding)
            self.assertIn("--vulkan-device=10de2503-0000-0000-0000-000000000000", res["mpv_args"])
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in res["mpv_args"]))
            self.assertEqual(res["decode_policy"]["hwdec"], "nvdec")
            self.assertEqual(res["decode_policy"]["status"], "OBSERVED")
            self.assertEqual(res["decode_policy"]["physical_gpu_binding"], "NOT_PROVEN")

    def test_18_amd_runtime_render_binding_emits_vulkan_no_vaapi(self):
        policy_path = PAYLOAD / "openhtpc-playback-policy.py"
        spec = importlib.util.spec_from_file_location("policy_test_18", policy_path)
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)

        amd_gpu = {
            "pci_address": "0000:0a:00.0",
            "driver": "amdgpu",
            "card_node": "/dev/dri/card0",
            "render_node": "/dev/dri/renderD128",
            "render_node_valid": True,
            "persistent_render_path": "/dev/dri/by-path/pci-0000:0a:00.0-render",
            "connected_connectors": ["DisplayPort-0"],
            "enabled_connectors": ["DisplayPort-0"],
            "active_display": True,
            "device_type": "PHYSICAL_DEVICE_TYPE_DISCRETE_GPU",
        }
        amd_vulkan = """
GPU0:
VkPhysicalDeviceProperties:
\tdeviceName = AMD Radeon RX 6600
\tdeviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
VkPhysicalDevicePCIBusInfoPropertiesEXT:
\tpciDomain = 0
\tpciBus = 10
\tpciDevice = 0
\tpciFunction = 0
VkPhysicalDeviceVulkan11Properties:
\tdeviceUUID = 100273ff-0000-0000-0000-000000000000
"""
        devices = gpu_rt.parse_vulkaninfo_text(amd_vulkan)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[amd_gpu],
            vulkan_devices=devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["pci_address"], "0000:0a:00.0")
        self.assertEqual(binding["vulkan_uuid"], "100273ff-0000-0000-0000-000000000000")
        self.assertEqual(binding["mpv_args"], ["--vulkan-device=100273ff-0000-0000-0000-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            rt_dir = home / ".config/openhtpc/runtime/mpv"
            rt_dir.mkdir(parents=True)
            (rt_dir / "pure.conf").write_text("vo=gpu-next\ngpu-api=vulkan\nhwdec=vaapi\n", encoding="utf-8")
            (home / ".config/openhtpc/user-config.json").write_text(json.dumps({"presentation_mode": "PURE"}), encoding="utf-8")

            res = pol.resolve(home, None, "local", gpu_binding=binding)
            self.assertIn("--vulkan-device=100273ff-0000-0000-0000-000000000000", res["mpv_args"])
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in res["mpv_args"]))
            self.assertEqual(res["decode_policy"]["hwdec"], "vaapi")
            self.assertEqual(res["decode_policy"]["status"], "OBSERVED")
            self.assertEqual(res["decode_policy"]["physical_gpu_binding"], "NOT_PROVEN")

    def test_19_intel_runtime_render_binding_emits_vulkan_no_vaapi(self):
        policy_path = PAYLOAD / "openhtpc-playback-policy.py"
        spec = importlib.util.spec_from_file_location("policy_test_19", policy_path)
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)

        vulkan_devices = gpu_rt.parse_vulkaninfo_text(self.valid_vulkan_text)
        binding = gpu_rt.resolve_playback_gpu_binding(
            detected_gpus=[self.valid_arc_gpu],
            vulkan_devices=vulkan_devices,
        )
        self.assertEqual(binding["status"], "RENDER_BOUND")
        self.assertEqual(binding["mpv_args"], ["--vulkan-device=8680a656-0500-0000-0300-000000000000"])
        self.assertFalse(any(a.startswith("--vaapi-device=") for a in binding["mpv_args"]))

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            rt_dir = home / ".config/openhtpc/runtime/mpv"
            rt_dir.mkdir(parents=True)
            (rt_dir / "pure.conf").write_text("vo=gpu-next\ngpu-api=vulkan\nhwdec=vaapi\n", encoding="utf-8")
            (home / ".config/openhtpc/user-config.json").write_text(json.dumps({"presentation_mode": "PURE"}), encoding="utf-8")

            res = pol.resolve(home, None, "local", gpu_binding=binding)
            self.assertIn("--vulkan-device=8680a656-0500-0000-0300-000000000000", res["mpv_args"])
            self.assertFalse(any(a.startswith("--vaapi-device=") for a in res["mpv_args"]))
            self.assertEqual(res["decode_policy"]["hwdec"], "vaapi")
            self.assertEqual(res["decode_policy"]["status"], "OBSERVED")
            self.assertEqual(res["decode_policy"]["physical_gpu_binding"], "NOT_PROVEN")

    def test_20_sequential_playback_replaces_diagnostic_state(self):
        play_path = PAYLOAD / "openhtpc-play"
        loader = importlib.machinery.SourceFileLoader("play_test_20", str(play_path))
        spec = importlib.util.spec_from_loader("play_test_20", loader)
        play_mod = importlib.util.module_from_spec(spec)
        loader.exec_module(play_mod)

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            media = home / "media.mkv"
            source = home / "source"
            diag_file = home / ".local/state/openhtpc/playback-last-private.json"

            # Run Playback A (RENDER_BOUND)
            bound_binding = {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "drm_render_path": "/dev/dri/by-path/pci-0000:03:00.0-render",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel Arc A310",
                "reason": "COHERENT_RENDER_ALIGNED",
                "evidence": ["test_bound"],
                "mpv_args": ["--vulkan-device=8680a656-0500-0000-0300-000000000000"],
            }
            play_mod.private_state(home, media, source, {
                "kind": "local",
                "gpu_render_binding_details": bound_binding,
                "gpu_binding_details": bound_binding,
            })

            data_a = json.loads(diag_file.read_text(encoding="utf-8"))
            self.assertEqual(data_a["gpu_render_binding_details"]["status"], "RENDER_BOUND")
            self.assertEqual(data_a["gpu_render_binding_details"]["vulkan_uuid"], "8680a656-0500-0000-0300-000000000000")
            self.assertEqual(data_a["gpu_render_binding_details"]["drm_render_path"], "/dev/dri/by-path/pci-0000:03:00.0-render")

            # Run Playback B (AUTO_FALLBACK)
            fallback_binding = {
                "status": "AUTO_FALLBACK",
                "pci_address": None,
                "drm_render_path": None,
                "vulkan_uuid": None,
                "vulkan_device_name": None,
                "reason": "GPU_UNAVAILABLE",
                "evidence": ["test_fallback"],
                "mpv_args": [],
            }
            play_mod.private_state(home, media, source, {
                "kind": "local",
                "gpu_render_binding_details": fallback_binding,
                "gpu_binding_details": fallback_binding,
            })

            data_b = json.loads(diag_file.read_text(encoding="utf-8"))
            self.assertEqual(data_b["gpu_render_binding_details"]["status"], "AUTO_FALLBACK")
            self.assertIsNone(data_b["gpu_render_binding_details"]["vulkan_uuid"])
            self.assertIsNone(data_b["gpu_render_binding_details"]["drm_render_path"])
            raw_b = diag_file.read_text(encoding="utf-8")
            self.assertNotIn("8680a656-0500-0000-0300-000000000000", raw_b)
            self.assertNotIn("0000:03:00.0", raw_b)

    def test_21_decode_policy_unavailable_when_runtime_config_missing(self):
        policy_path = PAYLOAD / "openhtpc-playback-policy.py"
        spec = importlib.util.spec_from_file_location("policy_test_21", policy_path)
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)

        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            (home / ".config/openhtpc").mkdir(parents=True)
            (home / ".config/openhtpc/user-config.json").write_text(json.dumps({"presentation_mode": "PURE"}), encoding="utf-8")

            res = pol.resolve(home, None, "local")
            self.assertEqual(res["decode_policy"]["status"], "UNAVAILABLE")
            self.assertIsNone(res["decode_policy"]["hwdec"])
            self.assertEqual(res["decode_policy"]["physical_gpu_binding"], "NOT_PROVEN")

if __name__ == "__main__":
    unittest.main()
