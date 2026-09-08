#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Runtime GPU resolver for OPENHTPC.

Passively discovers available GPUs from sysfs and devtmpfs, validates runtime
render character device resources and persistent render paths, resolves the active
display GPU using connected and enabled output states, and evaluates coherence
against the Hardware Passport snapshot. Performs no system mutations, package
installations, or MPV playback modifications.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import sys
from typing import Any, Callable

PCI_DISPLAY_CLASSES: dict[int, str] = {
    0x0300: "VGA compatible controller [0300]",
    0x0301: "XGA controller [0301]",
    0x0302: "3D controller [0302]",
    0x0380: "Display controller [0380]",
}

StatProvider = Callable[[pathlib.Path], Any]


def normalize_pci_address(value: Any) -> str | None:
    """Normalize PCI address to standard dddd:bb:dd.f lower-case format.

    Valid ranges per PCI specification:
    - domain: 0000..ffff (0..65535)
    - bus: 00..ff (0..255)
    - device: 00..1f (0..31)
    - function: 0..7 (0..7)
    Rejects malformed, non-hex, out-of-range, and non-string inputs.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    match = re.fullmatch(
        r"(?:([0-9a-fA-F]{1,4}):)?([0-9a-fA-F]{1,2}):([0-9a-fA-F]{1,2})\.([0-7])",
        raw,
    )
    if not match:
        return None
    domain_str, bus_str, dev_str, fn_str = match.groups()
    try:
        domain = int(domain_str, 16) if domain_str else 0
        bus = int(bus_str, 16)
        dev = int(dev_str, 16)
        fn = int(fn_str, 16)
    except ValueError:
        return None

    if not (0 <= domain <= 0xFFFF):
        return None
    if not (0 <= bus <= 0xFF):
        return None
    if not (0 <= dev <= 0x1F):
        return None
    if not (0 <= fn <= 7):
        return None

    return f"{domain:04x}:{bus:02x}:{dev:02x}.{fn:x}"


def parse_pci_class(class_hex: Any) -> tuple[int, int, int] | None:
    """Parse PCI class string into (base_class, subclass, prog_if).

    Accepted textual payload lengths ONLY:
    - 4 hex digits: base_class (byte 1) + subclass (byte 2), prog_if = 0
    - 6 hex digits: base_class (byte 1) + subclass (byte 2) + prog_if (byte 3)

    An optional '0x' or '0X' prefix is supported.
    Any other length (e.g. 2, 3, 5, 7 digits such as '03', '300', '10300', '00300', '03000')
    or non-hex characters is strictly invalid and returns None.
    """
    if not isinstance(class_hex, str):
        return None
    cleaned = class_hex.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]

    if len(cleaned) not in (4, 6):
        return None
    if not re.fullmatch(r"[0-9a-fA-F]+", cleaned):
        return None

    try:
        val = int(cleaned, 16)
    except ValueError:
        return None

    if len(cleaned) == 6:
        base = (val >> 16) & 0xFF
        sub = (val >> 8) & 0xFF
        prog = val & 0xFF
    else:  # exactly 4 hex characters
        base = (val >> 8) & 0xFF
        sub = val & 0xFF
        prog = 0
    return base, sub, prog


def is_display_pci_class(class_hex: Any) -> bool:
    """Determine if a PCI class hex string corresponds to a display controller (base class 0x03)."""
    parsed = parse_pci_class(class_hex)
    if not parsed:
        return False
    base, _, _ = parsed
    return base == 0x03


def pci_class_description(class_hex: Any) -> str:
    """Return a descriptive label for a PCI class code."""
    parsed = parse_pci_class(class_hex)
    if not parsed:
        return "Unknown class"
    base, sub, _ = parsed
    if base != 0x03:
        return "Non-display device"
    class_code = (base << 8) | sub
    if class_code in PCI_DISPLAY_CLASSES:
        return PCI_DISPLAY_CLASSES[class_code]
    return f"Display controller [{class_code:04x}]"


def get_path_stat(path: pathlib.Path, stat_provider: StatProvider | None = None) -> Any:
    """Retrieve file stat result.

    In production, uses path.stat() exclusively.
    stat_provider is used for dependency injection in tests only.
    Never inspects .stat files or synthetic filesystem conventions.
    """
    if stat_provider is not None:
        return stat_provider(path)
    return path.stat()


def validate_render_node(
    node_path: pathlib.Path,
    expected_pci: str,
    sys_root: pathlib.Path,
    stat_provider: StatProvider | None = None,
) -> bool:
    """Validate that node_path is a real DRM render character device belonging to expected_pci.

    Checks:
    1. path exists
    2. target resolves
    3. target is a character device (regular files rejected)
    4. target basename matches renderD[0-9]+
    5. /sys/class/drm/renderDxxx exists and is a directory
    6. /sys/class/drm/renderDxxx/dev exists, is a file, and parses to <major>:<minor>
    7. stat major:minor == sysfs DRM major:minor
    8. PCI parent in sysfs matches expected_pci exactly. Contradiction => fail closed.
    """
    if not node_path.exists():
        return False

    try:
        target = node_path.resolve()
        if not target.exists():
            return False
    except OSError:
        return False

    if not re.fullmatch(r"renderD[0-9]+", target.name):
        return False

    try:
        st = get_path_stat(target, stat_provider=stat_provider)
        if not stat.S_ISCHR(st.st_mode):
            return False
    except OSError:
        return False

    drm_sysfs_dir = sys_root / "class" / "drm" / target.name
    if not drm_sysfs_dir.is_dir():
        return False

    drm_dev_file = drm_sysfs_dir / "dev"
    if not drm_dev_file.is_file():
        return False

    try:
        dev_str = drm_dev_file.read_text(encoding="utf-8").strip()
        m = re.fullmatch(r"(\d+):(\d+)", dev_str)
        if not m:
            return False
        sys_major = int(m.group(1))
        sys_minor = int(m.group(2))
    except (OSError, ValueError):
        return False

    st_major = os.major(st.st_rdev)
    st_minor = os.minor(st.st_rdev)

    DRM_MAJOR = 226
    if (st_major != sys_major) or (st_minor != sys_minor) or (st_major != DRM_MAJOR):
        return False

    # Check sysfs PCI association
    drm_device_link = drm_sysfs_dir / "device"
    if drm_device_link.exists():
        try:
            resolved_pci_dir = drm_device_link.resolve()
            actual_pci = normalize_pci_address(resolved_pci_dir.name)
            if actual_pci is not None:
                if actual_pci != expected_pci:
                    # Contradiction: node belongs to a different PCI device!
                    return False
                return True
        except OSError:
            return False

    expected_pci_drm = sys_root / "bus" / "pci" / "devices" / expected_pci / "drm" / target.name
    if expected_pci_drm.is_dir():
        # Ensure no other PCI device claims this render node
        pci_bus = sys_root / "bus" / "pci" / "devices"
        if pci_bus.is_dir():
            for other_pci_dir in pci_bus.iterdir():
                if normalize_pci_address(other_pci_dir.name) != expected_pci:
                    if (other_pci_dir / "drm" / target.name).is_dir():
                        return False
        return True

    return False


def resolve_persistent_render_path(
    pci_address: str,
    sys_root: pathlib.Path,
    dev_root: pathlib.Path,
    stat_provider: StatProvider | None = None,
) -> str | None:
    """Dynamically resolve and validate persistent render device path.

    Checks:
    - symlink /dev/dri/by-path/pci-<pci_address>-render exists
    - symlink target exists
    - target is a validated render character device belonging to pci_address
    Fails closed (returns None) if any check fails. Missing by-path returns None.
    """
    by_path = dev_root / "dri" / "by-path" / f"pci-{pci_address}-render"
    if not by_path.is_symlink():
        return None

    try:
        target = by_path.resolve()
        if not target.exists():
            return None
    except OSError:
        return None

    if not validate_render_node(
        node_path=target,
        expected_pci=pci_address,
        sys_root=sys_root,
        stat_provider=stat_provider,
    ):
        return None

    return str(by_path)


def parse_connector_state(connector_dir: pathlib.Path) -> dict[str, Any]:
    """Read status and enabled attributes of a DRM connector.

    Tracks:
    - status: "connected", "disconnected", or "unknown"
    - connected: bool (status == "connected")
    - enabled: bool | None (True if "enabled", False if "disabled", None if unknown)
    - activation_known: bool
    - active: bool (connected is True and enabled is True)
    """
    status_str = "unknown"
    status_file = connector_dir / "status"
    if status_file.is_file():
        try:
            status_str = status_file.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            pass

    enabled_str = "unknown"
    enabled_file = connector_dir / "enabled"
    if enabled_file.is_file():
        try:
            enabled_str = enabled_file.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            pass

    connected = (status_str == "connected")
    if enabled_str == "enabled":
        enabled = True
        activation_known = True
    elif enabled_str == "disabled":
        enabled = False
        activation_known = True
    else:
        enabled = None
        activation_known = False

    active = bool(connected and enabled is True)

    return {
        "connector": connector_dir.name,
        "status": status_str,
        "connected": connected,
        "enabled": enabled,
        "activation_known": activation_known,
        "active": active,
    }


def resolve_connector_pci(conn_dir: pathlib.Path) -> str | None:
    """Trace a DRM connector's sysfs hierarchy to its parent PCI device address.

    Returns normalized PCI address if parentage is proven, None if absent or unproven.
    """
    conn_dev = conn_dir / "device"
    if not conn_dev.exists():
        return None
    try:
        resolved = conn_dev.resolve()
        norm = normalize_pci_address(resolved.name)
        if norm:
            return norm
        if (resolved / "device").exists():
            norm = normalize_pci_address((resolved / "device").resolve().name)
            if norm:
                return norm
        if resolved.parent.name == "drm":
            norm = normalize_pci_address(resolved.parent.parent.name)
            if norm:
                return norm
    except OSError:
        pass
    return None


def get_gpu_connectors(
    pci_address: str,
    card_node: str | None,
    sys_root: pathlib.Path,
) -> list[dict[str, Any]]:
    """Attribute DRM connectors strictly to pci_address.

    A connector is attributed to a GPU ONLY if its sysfs parentage is proven
    to belong to pci_address. If parentage is absent, unproven, or contradictory,
    the connector is NOT attributed to this GPU.
    """
    drm_class = sys_root / "class" / "drm"
    if not drm_class.is_dir() or not card_node:
        return []

    card_sysfs = drm_class / card_node
    card_pci = None
    if (card_sysfs / "device").exists():
        try:
            card_pci = normalize_pci_address((card_sysfs / "device").resolve().name)
        except OSError:
            pass
    if card_pci != pci_address:
        return []

    connectors = []
    pattern = f"{card_node}-*"
    for conn in sorted(drm_class.glob(pattern)):
        if not conn.is_dir():
            continue
        conn_pci = resolve_connector_pci(conn)
        # CRITICAL: parentage MUST match pci_address.
        # If conn_pci is None (missing parentage) or != pci_address (contradiction): REJECT!
        if conn_pci != pci_address:
            continue

        state = parse_connector_state(conn)
        connectors.append(state)

    return connectors


def discover_gpus(
    sys_root: pathlib.Path = pathlib.Path("/sys"),
    dev_root: pathlib.Path = pathlib.Path("/dev"),
    stat_provider: StatProvider | None = None,
) -> list[dict[str, Any]]:
    """Discover all GPU devices present in sysfs and devtmpfs.

    Does not modify any system files or configuration.
    """
    pci_devices: dict[str, pathlib.Path] = {}

    pci_bus = sys_root / "bus" / "pci" / "devices"
    if pci_bus.is_dir():
        for item in pci_bus.iterdir():
            class_file = item / "class"
            if class_file.is_file():
                try:
                    cls_str = class_file.read_text(encoding="utf-8", errors="replace").strip()
                    if not is_display_pci_class(cls_str):
                        continue
                except OSError:
                    continue
            else:
                if not (item / "drm").is_dir():
                    continue

            norm_addr = normalize_pci_address(item.name)
            if norm_addr:
                pci_devices[norm_addr] = item

    drm_class = sys_root / "class" / "drm"
    if drm_class.is_dir():
        for card in drm_class.glob("card[0-9]*"):
            device_link = card / "device"
            if device_link.exists():
                try:
                    dev_dir = device_link.resolve()
                    class_file = dev_dir / "class"
                    if class_file.is_file():
                        cls_str = class_file.read_text(encoding="utf-8", errors="replace").strip()
                        if not is_display_pci_class(cls_str):
                            continue
                    norm_addr = normalize_pci_address(dev_dir.name)
                    if norm_addr and norm_addr not in pci_devices:
                        pci_devices[norm_addr] = dev_dir
                except OSError:
                    pass

    gpus: list[dict[str, Any]] = []

    for pci_addr in sorted(pci_devices.keys()):
        pci_dir = pci_devices[pci_addr]

        vendor_id = None
        vendor_file = pci_dir / "vendor"
        if vendor_file.is_file():
            try:
                raw_v = vendor_file.read_text(encoding="utf-8", errors="replace").strip().lower()
                clean_v = raw_v.removeprefix("0x")
                if re.fullmatch(r"[0-9a-f]{1,4}", clean_v):
                    vendor_id = clean_v.zfill(4)
            except OSError:
                pass

        device_id = None
        device_file = pci_dir / "device"
        if device_file.is_file():
            try:
                raw_d = device_file.read_text(encoding="utf-8", errors="replace").strip().lower()
                clean_d = raw_d.removeprefix("0x")
                if re.fullmatch(r"[0-9a-f]{1,4}", clean_d):
                    device_id = clean_d.zfill(4)
            except OSError:
                pass

        device_type = None
        class_file = pci_dir / "class"
        if class_file.is_file():
            try:
                raw_class = class_file.read_text(encoding="utf-8", errors="replace").strip()
                device_type = pci_class_description(raw_class)
            except OSError:
                pass
        if not device_type or device_type == "Unknown class":
            device_type = "Display controller"

        driver = None
        driver_link = pci_dir / "driver"
        if driver_link.exists():
            try:
                driver = driver_link.resolve().name
            except OSError:
                pass

        card_node = None
        pci_drm = pci_dir / "drm"
        if pci_drm.is_dir():
            cards = sorted(c.name for c in pci_drm.glob("card[0-9]*"))
            if cards:
                card_node = cards[0]
        if not card_node and drm_class.is_dir():
            for c in sorted(drm_class.glob("card[0-9]*")):
                try:
                    c_dev = c / "device"
                    if c_dev.exists() and normalize_pci_address(c_dev.resolve().name) == pci_addr:
                        card_node = c.name
                        break
                except OSError:
                    pass

        render_node_name = None
        if pci_drm.is_dir():
            renders = sorted(r.name for r in pci_drm.glob("renderD[0-9]*"))
            if renders:
                render_node_name = renders[0]
        if not render_node_name and drm_class.is_dir():
            for r in sorted(drm_class.glob("renderD[0-9]*")):
                try:
                    r_dev = r / "device"
                    if r_dev.exists() and normalize_pci_address(r_dev.resolve().name) == pci_addr:
                        render_node_name = r.name
                        break
                except OSError:
                    pass

        render_node_path = None
        render_node_valid = False
        if render_node_name:
            cand_path = dev_root / "dri" / render_node_name
            render_node_valid = validate_render_node(
                node_path=cand_path,
                expected_pci=pci_addr,
                sys_root=sys_root,
                stat_provider=stat_provider,
            )
            if render_node_valid:
                render_node_path = f"/dev/dri/{render_node_name}" if dev_root == pathlib.Path("/dev") else str(cand_path)

        persistent_render_path = resolve_persistent_render_path(
            pci_address=pci_addr,
            sys_root=sys_root,
            dev_root=dev_root,
            stat_provider=stat_provider,
        )

        connectors = get_gpu_connectors(pci_addr, card_node, sys_root)
        connected_connectors = [c["connector"] for c in connectors if c["connected"]]
        enabled_connectors = [c["connector"] for c in connectors if c["active"]]

        gpus.append({
            "pci_address": pci_addr,
            "vendor_id": vendor_id,
            "device_id": device_id,
            "driver": driver,
            "card_node": card_node,
            "render_node": render_node_path,
            "render_node_valid": render_node_valid,
            "persistent_render_path": persistent_render_path,
            "connector_details": connectors,
            "connected_connectors": connected_connectors,
            "enabled_connectors": enabled_connectors,
            "active_display": False,
            "device_type": device_type,
        })

    resolve_display_gpu(gpus)
    return gpus


def is_gpu_available(gpu: dict[str, Any]) -> bool:
    """A GPU is AVAILABLE if it has an active driver and a validated DRM render character device."""
    return bool(gpu.get("driver") and gpu.get("render_node") and gpu.get("render_node_valid"))


def resolve_display_gpu(gpus: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Resolve which GPU drives active display output using ENABLED connected outputs.

    Policy:
    1. one GPU has one or more connected+enabled connectors
       => RESOLVED, active_display_gpu = that GPU
    2. two GPUs have connected connectors but only one GPU has enabled connectors
       => RESOLVED to the enabled GPU
    3. enabled connectors exist on multiple GPUs
       => AMBIGUOUS, active_display_gpu = None
    4. connected connectors exist but all are disabled
       => NO_ACTIVE_DISPLAY, active_display_gpu = None
    5. connected connectors exist but enabled state is unknown and no enabled output is provable
       => UNKNOWN, active_display_gpu = None
    6. no connected connector
       => NO_DISPLAY, active_display_gpu = None
    """
    for g in gpus:
        g["active_display"] = False

    gpus_with_enabled = [g for g in gpus if g.get("enabled_connectors")]
    gpus_with_connected = [g for g in gpus if g.get("connected_connectors")]
    gpus_with_unknown = [
        g for g in gpus if any(c.get("connected") and c.get("enabled") is None for c in g.get("connector_details", []))
    ]

    if len(gpus_with_enabled) == 1:
        chosen = gpus_with_enabled[0]
        chosen["active_display"] = True
        return chosen, "RESOLVED"

    if len(gpus_with_enabled) > 1:
        return None, "AMBIGUOUS"

    if not gpus_with_connected:
        return None, "NO_DISPLAY"

    if gpus_with_unknown:
        return None, "UNKNOWN"

    return None, "NO_ACTIVE_DISPLAY"


def resolve_effective_candidate(gpus: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve the effective GPU candidate for future MPV playback binding.

    Requires:
    - Display resolution status == RESOLVED
    - Active display GPU is AVAILABLE (active driver + validated render char device).
    Returns None if display resolution is ambiguous, no display is enabled, or
    the display GPU lacks necessary runtime resources.
    """
    display_gpu, status = resolve_display_gpu(gpus)
    if status == "RESOLVED" and display_gpu and is_gpu_available(display_gpu):
        return display_gpu
    return None


def extract_passport_gpus(passport: Any) -> dict[str, dict[str, str | None]]:
    """Extract known GPU slot identities with vendor/device IDs from Passport data.

    Safely handles malformed input: non-dict root, None, numeric slots, unexpected shapes.
    Returns: dict mapping normalized pci_address to {"vendor_id": ..., "device_id": ...}
    """
    result: dict[str, dict[str, str | None]] = {}
    if not isinstance(passport, dict):
        return result

    def _record_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        slot_raw = item.get("pci_slot") or item.get("pci_address")
        if not isinstance(slot_raw, (str, int)):
            return
        norm_slot = normalize_pci_address(str(slot_raw))
        if not norm_slot:
            return

        vendor = None
        device = None
        if item.get("vendor_id") is not None:
            v_clean = str(item["vendor_id"]).strip().lower().removeprefix("0x")
            if re.fullmatch(r"[0-9a-f]{1,4}", v_clean):
                vendor = v_clean.zfill(4)
        if item.get("device_id") is not None:
            d_clean = str(item["device_id"]).strip().lower().removeprefix("0x")
            if re.fullmatch(r"[0-9a-f]{1,4}", d_clean):
                device = d_clean.zfill(4)

        pci_id = item.get("pci_id")
        if isinstance(pci_id, str) and ":" in pci_id:
            parts = pci_id.split(":")
            if len(parts) == 2:
                if not vendor and re.fullmatch(r"[0-9a-f]{1,4}", parts[0].strip().lower().removeprefix("0x")):
                    vendor = parts[0].strip().lower().removeprefix("0x").zfill(4)
                if not device and re.fullmatch(r"[0-9a-f]{1,4}", parts[1].strip().lower().removeprefix("0x")):
                    device = parts[1].strip().lower().removeprefix("0x").zfill(4)

        if norm_slot not in result or (vendor and device):
            result[norm_slot] = {"vendor_id": vendor, "device_id": device}

    detected = passport.get("detected")
    if isinstance(detected, dict):
        details = detected.get("gpu_details")
        if isinstance(details, list):
            for it in details:
                _record_item(it)

    topology = passport.get("gpu_topology")
    if isinstance(topology, dict):
        gpus_list = topology.get("gpus")
        if isinstance(gpus_list, list):
            for it in gpus_list:
                _record_item(it)
        for k in ("display_gpu", "processing_gpu"):
            _record_item(topology.get(k))

    return result


def compare_passport_gpus(
    runtime_gpus: list[dict[str, Any]],
    passport: Any,
) -> dict[str, Any]:
    """Compare runtime discovered GPUs with Hardware Passport snapshot.

    Detects:
    - missing: slots in passport but absent at runtime
    - extra: slots at runtime but absent in passport
    - replaced: slots present in both but with different vendor_id or device_id
    - matches: slots present in both with matching (or unavailable) vendor/device IDs
    Never raises on malformed input. Does not mutate profile.json.
    """
    if isinstance(passport, (pathlib.Path, str)):
        path = pathlib.Path(passport)
        if not path.is_file():
            return {
                "status": "PASSPORT_MISSING",
                "matches": [],
                "missing": [],
                "extra": [g["pci_address"] for g in runtime_gpus if isinstance(g, dict) and g.get("pci_address")],
                "replaced": [],
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                "status": "PASSPORT_INVALID",
                "matches": [],
                "missing": [],
                "extra": [g["pci_address"] for g in runtime_gpus if isinstance(g, dict) and g.get("pci_address")],
                "replaced": [],
            }
    else:
        data = passport

    passport_by_slot = extract_passport_gpus(data)

    runtime_by_slot: dict[str, dict[str, str | None]] = {}
    if isinstance(runtime_gpus, list):
        for g in runtime_gpus:
            if isinstance(g, dict) and g.get("pci_address"):
                runtime_by_slot[g["pci_address"]] = {
                    "vendor_id": g.get("vendor_id"),
                    "device_id": g.get("device_id"),
                }

    common_slots = sorted(set(runtime_by_slot.keys()) & set(passport_by_slot.keys()))
    missing_slots = sorted(set(passport_by_slot.keys()) - set(runtime_by_slot.keys()))
    extra_slots = sorted(set(runtime_by_slot.keys()) - set(passport_by_slot.keys()))

    matches: list[str] = []
    replaced: list[dict[str, Any]] = []

    for slot in common_slots:
        ps = passport_by_slot[slot]
        rt = runtime_by_slot[slot]
        v_mismatch = (ps["vendor_id"] is not None and rt["vendor_id"] is not None and ps["vendor_id"].lower() != rt["vendor_id"].lower())
        d_mismatch = (ps["device_id"] is not None and rt["device_id"] is not None and ps["device_id"].lower() != rt["device_id"].lower())

        if v_mismatch or d_mismatch:
            replaced.append({
                "pci_address": slot,
                "passport": ps,
                "runtime": rt,
            })
        else:
            matches.append(slot)

    if replaced:
        status = "CHANGED"
    elif missing_slots and extra_slots:
        status = "CHANGED"
    elif missing_slots:
        status = "MISSING"
    elif extra_slots:
        status = "EXTRA"
    else:
        status = "MATCH"

    return {
        "status": status,
        "matches": matches,
        "missing": missing_slots,
        "extra": extra_slots,
        "replaced": replaced,
    }


def build_gpu_runtime_summary(
    sys_root: pathlib.Path = pathlib.Path("/sys"),
    dev_root: pathlib.Path = pathlib.Path("/dev"),
    passport_path: pathlib.Path | None = None,
    stat_provider: StatProvider | None = None,
) -> dict[str, Any]:
    """Build a comprehensive passive runtime GPU summary."""
    detected = discover_gpus(sys_root=sys_root, dev_root=dev_root, stat_provider=stat_provider)
    available = [g for g in detected if is_gpu_available(g)]
    display_gpu, display_status = resolve_display_gpu(detected)
    effective = resolve_effective_candidate(detected)

    passport_coherence = None
    if passport_path and passport_path.is_file():
        passport_coherence = compare_passport_gpus(detected, passport_path)

    return {
        "detected_gpus": detected,
        "available_gpus": available,
        "display_status": display_status,
        "active_display_gpu": display_gpu,
        "effective_candidate": effective,
        "passport_coherence": passport_coherence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OPENHTPC Runtime GPU Resolver")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    parser.add_argument("--sys-root", type=pathlib.Path, default=pathlib.Path("/sys"), help="Path to sysfs root")
    parser.add_argument("--dev-root", type=pathlib.Path, default=pathlib.Path("/dev"), help="Path to devtmpfs root")
    parser.add_argument(
        "--passport",
        type=pathlib.Path,
        default=pathlib.Path("~/.config/openhtpc/profile.json").expanduser(),
        help="Path to profile.json",
    )
    args = parser.parse_args()

    summary = build_gpu_runtime_summary(
        sys_root=args.sys_root,
        dev_root=args.dev_root,
        passport_path=args.passport if args.passport.exists() else None,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print("=== OPENHTPC GPU RUNTIME RESOLVER ===")
    print(f"Display resolution status: {summary['display_status']}")
    print(f"Detected GPUs ({len(summary['detected_gpus'])}):")
    for g in summary["detected_gpus"]:
        connectors = ", ".join(g["connected_connectors"]) if g["connected_connectors"] else "none"
        enabled = ", ".join(g["enabled_connectors"]) if g["enabled_connectors"] else "none"
        print(f"  - PCI: {g['pci_address']} | Driver: {g['driver']} | Card: {g['card_node']} | Render: {g['render_node']}")
        print(f"    Render Valid: {g['render_node_valid']} | Persistent: {g['persistent_render_path']}")
        print(f"    Connected: {connectors} | Enabled: {enabled} | Active display: {g['active_display']}")

    print(f"Available GPUs ({len(summary['available_gpus'])}):")
    for g in summary["available_gpus"]:
        print(f"  - {g['pci_address']} ({g['device_type']})")

    if summary["active_display_gpu"]:
        ad = summary["active_display_gpu"]
        print(f"Active Display GPU: {ad['pci_address']} (enabled: {', '.join(ad['enabled_connectors'])})")
    else:
        print("Active Display GPU: None (unresolved)")

    if summary["effective_candidate"]:
        ec = summary["effective_candidate"]
        print(f"Effective GPU Candidate: {ec['pci_address']} ({ec['persistent_render_path']})")
    else:
        print("Effective GPU Candidate: None")

    if summary["passport_coherence"]:
        pc = summary["passport_coherence"]
        print(f"Passport Coherence: {pc['status']} (matches: {pc['matches']}, missing: {pc['missing']}, extra: {pc['extra']}, replaced: {pc['replaced']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
