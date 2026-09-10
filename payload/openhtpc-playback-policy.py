#!/usr/bin/env python3
"""Persistent playback preferences and deterministic MPV track policy.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

DEFAULTS = {
    "refresh_matching": "OFF",
    "presentation_mode": "PURE",
    "audio_language_policy": "AUTO",
    "audio_output_mode": "PCM",
    "subtitle_policy": "AUTO",
}
VALID = {
    "refresh_matching": {"AUTO", "OFF"},
    "presentation_mode": {"PURE", "CINEMA_AUTO"},
    "audio_language_policy": {"AUTO", "FR", "DEFAULT"},
    "audio_output_mode": {"PCM", "BITSTREAM"},
    "subtitle_policy": {"AUTO", "OFF", "FR_FORCED", "FR_FULL"},
}
FR_LANGS = {"fr", "fra", "fre"}
MPV_DEFAULT_HWDEC_CODEC_WHITELIST = "h264,vc1,hevc,vp8,vp9,av1,prores,prores_raw,ffv1,dpx"


def config_path(home: pathlib.Path) -> pathlib.Path:
    return home / ".config/openhtpc/user-config.json"


def _load_audio_module():
    try:
        import openhtpc_audio
        return openhtpc_audio
    except ImportError:
        pass
    for loc in (
        pathlib.Path(__file__).resolve().parent / "openhtpc-audio.py",
        pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", "")) / "openhtpc-audio.py",
        pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-audio.py",
    ):
        if loc.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_audio", loc)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception:
                pass
    return None


def _load_gpu_runtime_module():
    try:
        import openhtpc_gpu_runtime
        return openhtpc_gpu_runtime
    except ImportError:
        pass
    for loc in (
        pathlib.Path(__file__).resolve().parent / "openhtpc-gpu-runtime.py",
        pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", "")) / "openhtpc-gpu-runtime.py",
        pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-gpu-runtime.py",
    ):
        if loc.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_gpu_runtime", loc)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception:
                pass
    return None


def read_audio_output_target(home: pathlib.Path) -> dict:
    try:
        data = json.loads(config_path(home).read_text(encoding="utf-8"))
        target = data.get("audio_output_target")
        if isinstance(target, dict):
            return dict(target)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    mod = _load_audio_module()
    if mod and hasattr(mod, "system_descriptor"):
        return mod.system_descriptor()
    return dict(mode="SYSTEM", node_name=None, bus_path=None, edid_name=None,
                display_label="SYSTEM", device_type="UNKNOWN")


def write_audio_output_target(home: pathlib.Path, target: dict) -> dict:
    if not isinstance(target, dict) or target.get("mode") not in ("SYSTEM", "DEVICE"):
        raise ValueError("INVALID_AUDIO_TARGET")
    target_path = config_path(home)
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, json.JSONDecodeError, ValueError):
        data = {"schema": 1, "configuration_completed": True, "local_media_sources": [], "tmdb": {"configured": False}}
    data["audio_output_target"] = dict(target)
    _atomic_json(target_path, data)
    return read_audio_output_target(home)


def read_preferences(home: pathlib.Path) -> dict[str, str]:
    try:
        data = json.loads(config_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        data = {}
    result = dict(DEFAULTS)
    for key, choices in VALID.items():
        value = data.get(key)
        if isinstance(value, str) and value in choices:
            result[key] = value
    # Preserve the qualified C4 selection when upgrading from RC2.
    if "presentation_mode" not in data:
        try:
            legacy = json.loads((home / ".config/openhtpc/video-profile.json").read_text(encoding="utf-8"))
            value = legacy.get("active_profile")
            if value in VALID["presentation_mode"]:
                result["presentation_mode"] = value
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return result


def _atomic_json(target: pathlib.Path, data: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_preference(home: pathlib.Path, key: str, value: str) -> dict[str, str]:
    if key not in VALID or value not in VALID[key]:
        raise ValueError("INVALID_PLAYBACK_PREFERENCE")
    target = config_path(home)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict): raise ValueError
    except (OSError, json.JSONDecodeError, ValueError):
        data = {"schema": 1, "configuration_completed": True, "local_media_sources": [], "tmdb": {"configured": False}}
    data[key] = value
    _atomic_json(target, data)
    if key == "presentation_mode":
        _atomic_json(home / ".config/openhtpc/video-profile.json", {"schema": 1, "active_profile": value})
    return read_preferences(home)


def _lang(stream: dict) -> str:
    return str(stream.get("tags", {}).get("language", "")).casefold().strip()


def _title(stream: dict) -> str:
    return str(stream.get("tags", {}).get("title", "")).casefold()


def _flag(stream: dict, name: str) -> bool:
    return bool(stream.get("disposition", {}).get(name, 0))


def _is_french(stream: dict, secondary: bool = True) -> bool:
    if _lang(stream) in FR_LANGS: return True
    return secondary and bool(re.search(r"\b(?:français|francais|french|truefrench|vff|vfq)\b", _title(stream)))


def _typed_streams(probe: dict, codec_type: str) -> list[dict]:
    result = []
    for stream in probe.get("streams", []) if isinstance(probe, dict) else []:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            item = dict(stream); item["mpv_id"] = len(result) + 1; result.append(item)
    return result


def choose_audio(policy: str, probe: dict | None) -> dict:
    tracks = _typed_streams(probe or {}, "audio")
    if policy == "AUTO":
        return {"requested": policy, "resolved": "MPV_AUTO", "track": None, "reason": "qualified_default", "mpv_args": []}
    if policy == "DEFAULT":
        chosen = next((track for track in tracks if _flag(track, "default")), None)
        return {"requested": policy, "resolved": f"AID_{chosen['mpv_id']}" if chosen else "MPV_DEFAULT", "track": chosen, "reason": "container_default" if chosen else "no_explicit_default", "mpv_args": [f"--aid={chosen['mpv_id']}"] if chosen else []}
    candidates = [track for track in tracks if _is_french(track)]
    def score(track: dict) -> tuple[int, int]:
        title = _title(track); structured = _lang(track) in FR_LANGS
        if re.search(r"\b(?:vff|truefrench|true french)\b", title): rank = 0
        elif structured and not re.search(r"\b(?:vfq|québec|quebec)\b", title): rank = 1
        elif structured: rank = 2
        else: rank = 3
        return rank, int(track["mpv_id"])
    chosen = min(candidates, key=score) if candidates else None
    if chosen:
        return {"requested": policy, "resolved": f"AID_{chosen['mpv_id']}", "track": chosen, "reason": "french_track_selected", "mpv_args": [f"--aid={chosen['mpv_id']}"]}
    if probe is None:
        return {"requested": policy, "resolved": "MPV_FR_LANGUAGE", "track": None, "reason": "probe_unavailable_language_fallback", "mpv_args": ["--alang=fr,fra,fre"]}
    return {"requested": policy, "resolved": "MPV_DEFAULT", "track": None, "reason": "no_french_track", "mpv_args": []}


PASSTHROUGH_CODECS = ("ac3", "eac3", "dts", "dts-hd", "truehd")
PASSTHROUGH_SOURCE_CODECS = {"ac3", "eac3", "dts", "truehd"}


def choose_audio_output(mode: str, audio_track: dict | None) -> dict:
    codec = str((audio_track or {}).get("codec_name") or "UNKNOWN").casefold()
    source_codec = codec.upper() if codec != "unknown" else "UNKNOWN"
    if mode == "PCM":
        return {"requested": "PCM", "source_codec": source_codec, "resolved": "PCM",
                "reason": "user_requested_pcm", "mpv_args": [], "audio_spdif": "none"}
    candidate = codec in PASSTHROUGH_SOURCE_CODECS
    return {
        "requested": "BITSTREAM", "source_codec": source_codec,
        "resolved": "BITSTREAM" if candidate else "PCM" if codec != "unknown" else "BITSTREAM_REQUESTED",
        "reason": "passthrough_candidate" if candidate else "codec_not_passthrough_candidate" if codec != "unknown" else "source_codec_unknown",
        "mpv_args": ["--audio-spdif=" + ",".join(PASSTHROUGH_CODECS)],
        "audio_spdif": ",".join(PASSTHROUGH_CODECS),
    }


def record_audio_observation(home: pathlib.Path, decision: dict, raw_log: str = "") -> dict:
    output = decision.get("audio_output", {})
    target = decision.get("audio_target", {})
    requested = output.get("requested", "PCM")
    spdif_active = bool(re.search(r"AO:\s*\[[^]]+\].*\bspdif[-:]|\baudio format:\s*spdif", raw_log, re.I))
    unavailable = bool(re.search(r"(?:spdif|passthrough).*(?:not supported|unsupported|failed|unavailable)", raw_log, re.I))
    ao_match = re.search(r"AO:\s*\[([^]]+)\]", raw_log)
    passthrough = "ACTIVE" if spdif_active else "UNAVAILABLE" if requested == "BITSTREAM" and unavailable else "INACTIVE" if ao_match else "UNKNOWN"
    device_match = re.search(r"(?:audio-device|device)\s*[=:]\s*([^\s,]+)", raw_log, re.I)
    effective_target = target.get("effective", "SYSTEM")
    device_val = device_match.group(1) if device_match else (effective_target if effective_target != "SYSTEM" else "DEFAULT")
    value = {
        "schema": 1,
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested": requested,
        "source_codec": output.get("source_codec", "UNKNOWN"),
        "resolved": "BITSTREAM" if spdif_active else "PCM" if ao_match else "UNKNOWN",
        "reason": output.get("reason"),
        "passthrough": passthrough,
        "audio_spdif": output.get("audio_spdif", "none"),
        "ao": ao_match.group(1) if ao_match else "UNKNOWN",
        "audio_device": device_val,
        "configured": target.get("configured", "SYSTEM"),
        "configured_label": target.get("configured_label", "SYSTEM"),
        "available": target.get("available", True),
        "effective": effective_target,
        "audio_mode": target.get("audio_mode", requested),
        "fallback": target.get("fallback", False),
    }
    _atomic_json(home / ".local/state/openhtpc/audio-policy-last.json", value)
    return value


OPEN_MARKERS = ("Starting playback...", "AO: [", "VO: [", "[vo/gpu-next]", "Using hardware decoding", "Using software decoding")
PLAYBACK_RUNTIME_FILE = ".local/state/openhtpc/playback-runtime-last.json"
PLAYBACK_RUNTIME_LOCK = ".local/state/openhtpc/playback-runtime-last.lock"
VALID_DISPATCH_STATUSES = {"DISPATCHED", "COMPLETED", "FAILED"}
VALID_PROVEN_STATUSES = {"PROVEN", "NOT_PROVEN"}
VALID_DECODE_STATUSES = {"OBSERVED", "UNAVAILABLE"}
VALID_OBSERVATION_SCOPES = {"ACTIVE_DISPATCH", "LAST_COMPLETED_PLAYBACK", "FAILED_PLAYBACK"}


@contextlib.contextmanager
def playback_runtime_lock(home: pathlib.Path):
    """Exclusive inter-process lock around playback runtime state mutations."""
    lock_path = home / PLAYBACK_RUNTIME_LOCK
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def generate_dispatch_id() -> str:
    """Generate an opaque unique identifier for a playback dispatch."""
    import uuid
    return uuid.uuid4().hex


def normalize_vulkan_uuid_from_log(raw_uuid: str) -> str:
    """Normalize Vulkan UUID by removing hyphens and colons and lowercasing."""
    if not raw_uuid:
        return ""
    return re.sub(r"[-:]", "", str(raw_uuid).strip()).lower()


def parse_vulkan_render_observation(raw_log: str, decision: dict) -> dict:
    """Parse Vulkan render evidence line-by-line strictly from [vo/gpu-next/libplacebo]."""
    binding = decision.get("gpu_render_binding") or decision.get("gpu_binding") or {}
    expected_uuid_norm = normalize_vulkan_uuid_from_log(binding.get("vulkan_uuid") or "")
    expected_pci = binding.get("pci_address")
    expected_status = binding.get("status")

    enumerated_devices: list[dict[str, str]] = []
    current_properties_candidate: dict[str, str | None] | None = None
    device_under_creation: dict[str, str | None] | None = None
    created_device: dict[str, str | None] | None = None

    current_enum_name: str | None = None
    in_properties_block = False

    for line in raw_log.splitlines():
        # Match standard MPV log line: [ timestamp][level][component] message
        m = re.match(r"^(?:\[[\s\d.]+\])?\[[a-z]\]\[([^\]]+)\][ \t]?(.*)", line)
        if not m:
            continue
        component = m.group(1).strip()
        msg = m.group(2)

        # Accept render evidence ONLY from vo/gpu-next/libplacebo
        if component != "vo/gpu-next/libplacebo":
            continue

        # 1. Device enumeration lines
        gpu_match = re.match(r"^GPU\s+\d+:\s*(.*?)(?:\s+v\d+\.\d+.*|\s*\([^)]+\))?$", msg.strip())
        if gpu_match:
            current_enum_name = gpu_match.group(1).strip()
            continue

        uuid_enum_match = re.match(r"^uuid:\s*([0-9a-fA-F:-]+)", msg.strip())
        if uuid_enum_match and current_enum_name:
            enum_uuid = normalize_vulkan_uuid_from_log(uuid_enum_match.group(1))
            enumerated_devices.append({"name": current_enum_name, "uuid": enum_uuid})
            current_enum_name = None
            continue

        # 2. Selection / Properties block
        if "Vulkan device properties:" in msg:
            in_properties_block = True
            current_properties_candidate = {"name": None, "uuid": None}
            continue

        if in_properties_block:
            name_match = re.match(r"^Device Name:\s*(.+)", msg.strip())
            if name_match:
                current_properties_candidate["name"] = name_match.group(1).strip()
                continue

            uuid_prop_match = re.match(r"^Device UUID:\s*([0-9a-fA-F:-]+)", msg.strip())
            if uuid_prop_match:
                current_properties_candidate["uuid"] = normalize_vulkan_uuid_from_log(uuid_prop_match.group(1))
                continue

            if not msg.startswith(" ") and not msg.startswith("\t"):
                in_properties_block = False

        # 3. Device creation sequence
        if "Creating vulkan device" in msg:
            in_properties_block = False
            device_under_creation = current_properties_candidate
            created_device = None
            continue

        if "Spent" in msg and "creating vulkan device" in msg:
            # Positive initialization completion marker
            if device_under_creation is not None:
                created_device = device_under_creation
            device_under_creation = None
            continue

        if "failed creating vulkan device" in msg.lower() or "failed to initialize vulkan" in msg.lower():
            device_under_creation = None
            created_device = None
            continue

    # Resolution of Render GPU:
    if not expected_uuid_norm or expected_status != "RENDER_BOUND" or not expected_pci:
        return {
            "status": "NOT_PROVEN",
            "pci_address": None,
            "vulkan_uuid": created_device.get("uuid") if created_device else None,
            "device_name": created_device.get("name") if created_device else None,
        }

    if not created_device:
        return {
            "status": "NOT_PROVEN",
            "pci_address": None,
            "vulkan_uuid": None,
            "device_name": None,
        }

    created_uuid = created_device.get("uuid")
    if created_uuid != expected_uuid_norm:
        return {
            "status": "NOT_PROVEN",
            "pci_address": None,
            "vulkan_uuid": created_uuid,
            "device_name": created_device.get("name"),
        }

    matching_enum = [d for d in enumerated_devices if d.get("uuid") == expected_uuid_norm]
    if len(matching_enum) > 1:
        return {
            "status": "NOT_PROVEN",
            "pci_address": None,
            "vulkan_uuid": created_uuid,
            "device_name": created_device.get("name"),
        }

    return {
        "status": "PROVEN",
        "pci_address": expected_pci,
        "vulkan_uuid": binding.get("vulkan_uuid"),
        "device_name": created_device.get("name") or binding.get("vulkan_device_name"),
    }


def parse_decode_observation(raw_log: str) -> dict:
    """Parse decode transitions chronologically strictly from [vd]."""
    current_decode: dict[str, Any] | None = None
    pending_hwdec_failure: str | None = None

    for line in raw_log.splitlines():
        m = re.match(r"^(?:\[[\s\d.]+\])?\[[a-z]\]\[([^\]]+)\][ \t]?(.*)", line)
        if not m:
            continue
        component = m.group(1).strip()
        msg = m.group(2)

        # Accept decode evidence ONLY from [vd]
        if component != "vd":
            continue

        # 1. Successful hardware decoding transition
        hw_match = re.search(r"Using hardware decoding\s*\(([^)]+)\)", msg, re.I)
        if hw_match:
            backend = hw_match.group(1).strip().lower()
            current_decode = {
                "status": "OBSERVED",
                "backend": backend,
                "hardware_active": True,
                "fallback": False,
                "fallback_reason": None,
                "physical_gpu_binding": "NOT_PROVEN",
                "physical_gpu_pci": None,
            }
            pending_hwdec_failure = None
            continue

        # 2. Hardware decode failure indication
        tex_fail = re.search(r"Failed to allocate texture", msg, re.I)
        dev_fail = re.search(r"Could not create device|Failed to initialize hwdec|hwdec.*failed", msg, re.I)
        wl_fail = re.search(r"codec\s+.*?\s+is not on whitelist", msg, re.I)
        fallback_msg = re.search(r"Falling back to software decoding", msg, re.I)
        hw_look = re.search(r"Looking at hwdec", msg, re.I)
        if tex_fail:
            pending_hwdec_failure = "TEXTURE_ALLOCATION_FAILED"
        elif dev_fail:
            pending_hwdec_failure = "DEVICE_CREATION_FAILED"
        elif wl_fail:
            pending_hwdec_failure = "CODEC_NOT_WHITELISTED"
        elif fallback_msg:
            if pending_hwdec_failure is None:
                pending_hwdec_failure = "FALLBACK_TO_SOFTWARE"
        elif hw_look and pending_hwdec_failure is None:
            pending_hwdec_failure = "HARDWARE_DECODE_UNAVAILABLE"

        # 3. Software decoding transition
        sw_match = re.search(r"Using software decoding", msg, re.I)
        if sw_match:
            prior_was_hardware = current_decode is not None and current_decode.get("hardware_active") is True
            fallback = prior_was_hardware or (pending_hwdec_failure is not None)
            fallback_reason = pending_hwdec_failure
            if fallback and not fallback_reason:
                fallback_reason = "RUNTIME_FALLBACK"
            current_decode = {
                "status": "OBSERVED",
                "backend": "software",
                "hardware_active": False,
                "fallback": fallback,
                "fallback_reason": fallback_reason,
                "physical_gpu_binding": "NOT_PROVEN",
                "physical_gpu_pci": None,
            }
            pending_hwdec_failure = None
            continue

    if current_decode is not None:
        return current_decode

    return {
        "status": "UNAVAILABLE",
        "backend": None,
        "hardware_active": None,
        "fallback": False,
        "fallback_reason": None,
        "physical_gpu_binding": "NOT_PROVEN",
        "physical_gpu_pci": None,
    }


def parse_playback_observation(
    decision: dict,
    raw_log: str = "",
    *,
    exit_code: int | None = None,
) -> dict:
    """Parse MPV runtime log and resolve render, decode, and fallback evidence."""
    render = parse_vulkan_render_observation(raw_log, decision)
    decode = parse_decode_observation(raw_log)

    media_opened = any(marker in raw_log for marker in OPEN_MARKERS)
    failure_reason = None
    if exit_code is None:
        dispatch_status = "COMPLETED" if media_opened else "DISPATCHED"
        observation_scope = "LAST_COMPLETED_PLAYBACK" if media_opened else "ACTIVE_DISPATCH"
    elif exit_code == 0:
        dispatch_status = "COMPLETED" if media_opened else "FAILED"
        observation_scope = "LAST_COMPLETED_PLAYBACK" if media_opened else "FAILED_PLAYBACK"
        if not media_opened:
            failure_reason = "MEDIA_NOT_OPENED"
    else:
        dispatch_status = "FAILED"
        observation_scope = "FAILED_PLAYBACK"
        failure_reason = "MPV_EXIT_ERROR" if media_opened else "MEDIA_NOT_OPENED"

    res = {
        "media_opened": media_opened,
        "exit_code": exit_code,
        "dispatch_status": dispatch_status,
        "observation_scope": observation_scope,
        "render": render,
        "decode": decode,
    }
    if failure_reason is not None:
        res["failure_reason"] = failure_reason
    return res


def record_playback_dispatch(
    home: pathlib.Path,
    decision: dict,
    *,
    kind: str = "local",
    dispatch_id: str | None = None,
) -> dict:
    """Record initial dispatch state immediately clearing any previous playback state."""
    with playback_runtime_lock(home):
        target = home / PLAYBACK_RUNTIME_FILE
        now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        disp_id = dispatch_id or generate_dispatch_id()
        record = {
            "schema": 1,
            "dispatch_id": disp_id,
            "timestamp": now_iso,
            "kind": kind,
            "dispatch_status": "DISPATCHED",
            "media_opened": False,
            "exit_code": None,
            "observation_scope": "ACTIVE_DISPATCH",
            "render": {
                "status": "NOT_PROVEN",
                "pci_address": None,
                "vulkan_uuid": None,
                "device_name": None,
            },
            "decode": {
                "status": "UNAVAILABLE",
                "backend": None,
                "hardware_active": None,
                "fallback": False,
                "fallback_reason": None,
                "physical_gpu_binding": "NOT_PROVEN",
                "physical_gpu_pci": None,
            },
        }
        _atomic_json(target, record)
        return record


def record_playback_failure(
    home: pathlib.Path,
    decision: dict | None = None,
    *,
    kind: str = "local",
    reason: str = "LAUNCH_FAILED",
    exit_code: int | None = None,
    dispatch_id: str | None = None,
) -> dict:
    """Record failed playback launch, ensuring stale successful state is cleared."""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        return {
            "status": "MISSING_DISPATCH_ID",
            "dispatch_id": dispatch_id,
        }

    with playback_runtime_lock(home):
        target = home / PLAYBACK_RUNTIME_FILE
        current = read_playback_runtime(home)
        if current is not None:
            current_id = current.get("dispatch_id")
            if current_id and current_id != dispatch_id:
                return {
                    "status": "STALE_DISPATCH_IGNORED",
                    "dispatch_id": dispatch_id,
                    "current_dispatch_id": current_id,
                }

        now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            "schema": 1,
            "dispatch_id": dispatch_id,
            "timestamp": now_iso,
            "kind": kind,
            "dispatch_status": "FAILED",
            "media_opened": False,
            "exit_code": exit_code,
            "failure_reason": reason,
            "observation_scope": "FAILED_PLAYBACK",
            "render": {
                "status": "NOT_PROVEN",
                "pci_address": None,
                "vulkan_uuid": None,
                "device_name": None,
            },
            "decode": {
                "status": "UNAVAILABLE",
                "backend": None,
                "hardware_active": False,
                "fallback": False,
                "fallback_reason": reason,
                "physical_gpu_binding": "NOT_PROVEN",
                "physical_gpu_pci": None,
            },
        }
        _atomic_json(target, record)
        return record


def record_playback_observation(
    home: pathlib.Path,
    decision: dict,
    raw_log: str = "",
    *,
    exit_code: int | None = None,
    kind: str = "local",
    dispatch_id: str | None = None,
) -> dict:
    """Record completed MPV playback observation atomically, rejecting stale dispatch IDs."""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        return {
            "status": "MISSING_DISPATCH_ID",
            "dispatch_id": dispatch_id,
        }

    with playback_runtime_lock(home):
        target = home / PLAYBACK_RUNTIME_FILE
        current = read_playback_runtime(home)
        if current is not None:
            current_id = current.get("dispatch_id")
            if current_id and current_id != dispatch_id:
                return {
                    "status": "STALE_DISPATCH_IGNORED",
                    "dispatch_id": dispatch_id,
                    "current_dispatch_id": current_id,
                }

        parsed = parse_playback_observation(decision, raw_log, exit_code=exit_code)
        now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            "schema": 1,
            "dispatch_id": dispatch_id,
            "timestamp": now_iso,
            "kind": kind,
            **parsed,
        }
        _atomic_json(target, record)
        return record


def read_playback_runtime(home: pathlib.Path) -> dict | None:
    """Read and strictly validate the latest playback runtime observation."""
    target = home / PLAYBACK_RUNTIME_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    schema = data.get("schema")
    if type(schema) is not int or schema != 1:
        return None

    dispatch_id = data.get("dispatch_id")
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        return None

    dispatch_status = data.get("dispatch_status")
    if not isinstance(dispatch_status, str) or dispatch_status not in VALID_DISPATCH_STATUSES:
        return None

    media_opened = data.get("media_opened")
    if type(media_opened) is not bool:
        return None

    exit_code = data.get("exit_code")
    if exit_code is not None and (type(exit_code) is not int or type(exit_code) is bool):
        return None

    obs_scope = data.get("observation_scope")
    if obs_scope is not None and (not isinstance(obs_scope, str) or obs_scope not in VALID_OBSERVATION_SCOPES):
        return None

    fail_reason = data.get("failure_reason")
    if fail_reason is not None and not isinstance(fail_reason, str):
        return None

    # Render
    render = data.get("render")
    if not isinstance(render, dict):
        return None
    render_status = render.get("status")
    if not isinstance(render_status, str) or render_status not in VALID_PROVEN_STATUSES:
        return None
    for field in ("pci_address", "vulkan_uuid", "device_name"):
        val = render.get(field)
        if val is not None and not isinstance(val, str):
            return None

    # Decode
    decode = data.get("decode")
    if not isinstance(decode, dict):
        return None
    decode_status = decode.get("status")
    if not isinstance(decode_status, str) or decode_status not in VALID_DECODE_STATUSES:
        return None
    backend = decode.get("backend")
    if backend is not None and not isinstance(backend, str):
        return None
    hw_active = decode.get("hardware_active")
    if hw_active is not None and type(hw_active) is not bool:
        return None
    fallback = decode.get("fallback")
    if type(fallback) is not bool:
        return None
    fallback_reason = decode.get("fallback_reason")
    if fallback_reason is not None and not isinstance(fallback_reason, str):
        return None
    phys_binding = decode.get("physical_gpu_binding")
    if not isinstance(phys_binding, str) or phys_binding not in VALID_PROVEN_STATUSES:
        return None
    phys_pci = decode.get("physical_gpu_pci")
    if phys_pci is not None and not isinstance(phys_pci, str):
        return None

    return data


REQUIRED_BITSTREAM_CODECS = ("PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD")
CANONICAL_CODECS_MAP = {
    "pcm": "PCM",
    "dts": "DTS",
    "ac3": "AC3",
    "eac3": "EAC3",
    "truehd": "TrueHD",
    "dts-hd": "DTS-HD",
    "dtshd": "DTS-HD",
}


def split_pipewire_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Split multi-object PipeWire text (pw-cli or wpctl) into discrete (id, lines) blocks."""
    if not text:
        return []
    blocks: list[tuple[int, list[str]]] = []
    current_id: int | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        m = re.match(r"^\s*id(?::\s*|\s+)(\d+)(?:\b|,|$)", line)
        if m:
            if current_id is not None and current_lines:
                blocks.append((current_id, current_lines))
                current_lines = []
            current_id = int(m.group(1))
        if current_id is not None:
            current_lines.append(line)

    if current_id is not None and current_lines:
        blocks.append((current_id, current_lines))

    if not blocks:
        id_m = re.search(r"(?:^|\n)\s*id[:\s]+(\d+)", text, re.I) or re.search(r"\bid\s+(\d+)", text, re.I)
        if id_m:
            blocks.append((int(id_m.group(1)), text.splitlines()))

    return blocks


def parse_pipewire_object_block(sink_id: int, lines: list[str]) -> dict[str, Any]:
    """Parse key-value properties within a single isolated PipeWire block."""
    props: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^\s*\*?\s*([\w.]+)\s*=\s*(.+)$", line)
        if match:
            props[match.group(1).strip()] = match.group(2).strip()

    media_class = props.get("media.class", "").strip('"')
    node_name = props.get("node.name", "").strip('"')
    node_desc = props.get("node.description", "").strip('"')
    node_nick = props.get("node.nick", "").strip('"')
    profile_name = props.get("device.profile.name", "").strip('"')
    profile_desc = props.get("device.profile.description", "").strip('"')
    alsa_path = props.get("api.alsa.path", "").strip('"')
    raw_codecs = props.get("iec958.codecs", "")
    codecs_tokens = [c for c in re.findall(r"[A-Za-z0-9_-]+", raw_codecs) if c.lower() not in {"iec958", "codecs"}]
    codecs = [CANONICAL_CODECS_MAP.get(c.lower(), c) for c in codecs_tokens]

    combined = f"{profile_name} {node_name} {node_desc} {node_nick} {profile_desc} {alsa_path}".lower()
    is_hdmi = media_class == "Audio/Sink" and bool(re.search(r"\bhdmi\b|hdmi-|\.hdmi|digital surround|displayport", combined))

    return {
        "id": sink_id,
        "name": node_name or None,
        "description": node_desc or node_nick or None,
        "profile": profile_name or None,
        "media_class": media_class or None,
        "alsa_path": alsa_path or None,
        "is_hdmi": is_hdmi,
        "codecs": codecs,
    }


def parse_wpctl_sink(inspect_text: str, expected_node_name: str | None = None) -> dict[str, Any]:
    """Parse output from `wpctl inspect <target>` or `pw-cli info <target>` dynamically.

    Fail-closed: requires exact node.name match when expected_node_name is given,
    and returns empty dict on 0 or >1 matches.
    """
    blocks = split_pipewire_blocks(inspect_text)
    if not blocks:
        return {}

    parsed_objects = [parse_pipewire_object_block(b_id, b_lines) for b_id, b_lines in blocks]

    if expected_node_name is not None:
        matching = [obj for obj in parsed_objects if obj.get("name") == expected_node_name]
        if len(matching) == 1:
            return matching[0]
        return {}

    if len(parsed_objects) == 1:
        return parsed_objects[0]

    return {}


def inspect_sink(target: str = "@DEFAULT_AUDIO_SINK@", *, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    target_str = str(target).strip()
    if not target_str:
        return {}
    if target_str.startswith("pipewire/"):
        target_str = target_str[len("pipewire/"):]

    is_default = (target_str == "@DEFAULT_AUDIO_SINK@")
    is_numeric = target_str.isdigit()
    expected_node_name = None if (is_default or is_numeric) else target_str
    expected_id = int(target_str) if is_numeric else None

    # Step 1: try wpctl inspect
    try:
        proc = runner(["wpctl", "inspect", target_str], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if getattr(proc, "returncode", 1) == 0 and getattr(proc, "stdout", ""):
            parsed = parse_wpctl_sink(proc.stdout, expected_node_name=expected_node_name)
            if parsed.get("id") is not None:
                if expected_id is not None and parsed.get("id") != expected_id:
                    pass
                else:
                    return parsed
    except (OSError, ValueError, TypeError):
        pass

    # Step 2: for explicit targets, try pw-cli info
    if not is_default:
        try:
            pw_proc = runner(["pw-cli", "info", target_str], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if getattr(pw_proc, "returncode", 1) == 0 and getattr(pw_proc, "stdout", ""):
                parsed = parse_wpctl_sink(pw_proc.stdout, expected_node_name=expected_node_name)
                if parsed.get("id") is not None:
                    if expected_id is not None and parsed.get("id") != expected_id:
                        pass
                    else:
                        return parsed
        except (OSError, ValueError, TypeError):
            pass

    return {}


def parse_spa_codecs(enum_params_text: str) -> list[str]:
    """Parse effective IEC958 codecs from `pw-cli enum-params <id> Props` output."""
    if not enum_params_text:
        return []
    matches = re.findall(r"(?:Spa:Enum:)?AudioIEC958Codec:([A-Za-z0-9_-]+)", enum_params_text, re.I)
    if not matches:
        raw_matches = re.findall(r"\biec958Codecs\s*[:=]\s*\[([^\]]+)\]", enum_params_text, re.I)
        if raw_matches:
            matches = [c for c in re.findall(r"[A-Za-z0-9_-]+", raw_matches[0]) if c.lower() not in {"iec958codecs", "codecs"}]
    codecs: list[str] = []
    seen: set[str] = set()
    for raw in matches:
        canon = CANONICAL_CODECS_MAP.get(raw.lower(), raw)
        if canon.upper() not in seen:
            seen.add(canon.upper())
            codecs.append(canon)
    return codecs


def get_effective_spa_codecs(
    sink_id: int | str | None,
    *,
    runner: Callable[..., Any] = subprocess.run,
    finder: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """Query active node Props from PipeWire via `pw-cli enum-params <id> Props`."""
    if sink_id is None:
        return []
    pw_cli = finder("pw-cli")
    if not pw_cli:
        return []
    try:
        proc = runner(
            [pw_cli, "enum-params", str(sink_id), "Props"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if getattr(proc, "returncode", 1) != 0:
            return []
        stdout = getattr(proc, "stdout", "") or ""
        return parse_spa_codecs(stdout)
    except (OSError, ValueError, TypeError):
        return []


def prepare_pipewire_hdmi_bitstream(
    requested_mode: str,
    *,
    sink_target: str = "@DEFAULT_AUDIO_SINK@",
    target_descriptor: dict[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    finder: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Inspect and prepare PipeWire HDMI sink for bitstream HD passthrough if required."""
    if isinstance(sink_target, dict):
        target_descriptor = target_descriptor or sink_target
        sink_target = target_descriptor.get("node_name") or "@DEFAULT_AUDIO_SINK@"
    if isinstance(sink_target, str) and sink_target.startswith("pipewire/"):
        sink_target = sink_target[len("pipewire/"):]
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sink = inspect_sink(sink_target, runner=runner)
    sink_id = sink.get("id")
    sink_name = sink.get("name")
    sink_desc = sink.get("description")
    sink_profile = sink.get("profile")
    sink_media_class = sink.get("media_class")
    is_hdmi = bool(sink.get("is_hdmi", False))
    if target_descriptor and isinstance(target_descriptor, dict):
        device_type = target_descriptor.get("device_type")
        if device_type and device_type != "HDMI" and device_type != "UNKNOWN":
            is_hdmi = False
    property_codecs = list(sink.get("codecs", []))
    req_codecs = list(REQUIRED_BITSTREAM_CODECS)

    base_diag = {
        "audio_sink_id": sink_id,
        "audio_sink_name": sink_name,
        "audio_sink_description": sink_desc,
        "audio_sink_profile": sink_profile,
        "audio_sink_media_class": sink_media_class,
        "audio_sink_is_hdmi": is_hdmi,
        "iec958_property_codecs": property_codecs,
        "iec958_codecs_before": [],
        "iec958_codecs_requested": req_codecs if requested_mode == "BITSTREAM" else [],
        "iec958_codecs_after": [],
        "iec958_prepare_attempted": False,
        "iec958_prepare_status": "SKIPPED",
        "iec958_prepare_reason": "PCM_MODE",
        "iec958_prepare_method": None,
        "timestamp": timestamp,
    }

    if requested_mode != "BITSTREAM":
        return base_diag

    if not sink or sink_id is None:
        base_diag.update({
            "iec958_prepare_status": "SKIPPED",
            "iec958_prepare_reason": "SINK_UNRESOLVED",
        })
        return base_diag

    if not is_hdmi:
        base_diag.update({
            "iec958_prepare_status": "SKIPPED",
            "iec958_prepare_reason": "SINK_NOT_HDMI",
        })
        return base_diag

    pw_cli = finder("pw-cli")
    if not pw_cli:
        base_diag.update({
            "iec958_prepare_attempted": True,
            "iec958_prepare_status": "FAILED",
            "iec958_prepare_reason": "PW_CLI_UNAVAILABLE",
            "iec958_prepare_method": "pw-cli",
        })
        return base_diag

    codecs_before = get_effective_spa_codecs(sink_id, runner=runner, finder=finder)
    base_diag["iec958_codecs_before"] = codecs_before
    base_diag["iec958_codecs_after"] = codecs_before

    if all(codec in codecs_before for codec in req_codecs):
        base_diag.update({
            "iec958_prepare_attempted": False,
            "iec958_prepare_status": "SUCCESS",
            "iec958_prepare_reason": "ALREADY_COMPATIBLE",
            "iec958_prepare_method": "pw-cli",
        })
        return base_diag

    target_codecs: list[str] = []
    seen: set[str] = set()
    for c in codecs_before + req_codecs:
        c_norm = CANONICAL_CODECS_MAP.get(c.lower(), c)
        if c_norm.upper() not in seen:
            seen.add(c_norm.upper())
            target_codecs.append(c_norm)

    codecs_payload = " ".join(target_codecs)
    cmd = [pw_cli, "s", str(sink_id), "Props", f"{{ iec958Codecs : [ {codecs_payload} ] }}"]

    try:
        proc = runner(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        returncode = getattr(proc, "returncode", 1)
    except (OSError, ValueError, TypeError):
        returncode = 1

    if returncode != 0:
        base_diag.update({
            "iec958_prepare_attempted": True,
            "iec958_prepare_status": "FAILED",
            "iec958_prepare_reason": "PW_CLI_MUTATION_FAILED",
            "iec958_prepare_method": "pw-cli",
        })
        return base_diag

    codecs_after = get_effective_spa_codecs(sink_id, runner=runner, finder=finder)
    base_diag["iec958_codecs_after"] = codecs_after
    base_diag["iec958_prepare_attempted"] = True
    base_diag["iec958_prepare_method"] = "pw-cli"

    if all(codec in codecs_after for codec in req_codecs):
        base_diag["iec958_prepare_status"] = "SUCCESS"
        base_diag["iec958_prepare_reason"] = "CODECS_APPLIED"
    else:
        base_diag["iec958_prepare_status"] = "FAILED"
        base_diag["iec958_prepare_reason"] = "MUTATION_NOT_EFFECTIVE"

    return base_diag


def prepare_audio_target_bitstream(
    decision: dict[str, Any],
    *,
    runner: Callable[..., Any] = subprocess.run,
    finder: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Prepare PipeWire HDMI bitstream according to resolved decision and audio target."""
    audio_output = decision.get("audio_output") or {}
    requested_mode = audio_output.get("requested", "PCM")
    audio_target = decision.get("audio_target") or {}
    sink_target = audio_target.get("sink_target") or "@DEFAULT_AUDIO_SINK@"
    target_desc = audio_target.get("descriptor")
    try:
        return prepare_pipewire_hdmi_bitstream(
            requested_mode,
            sink_target=sink_target,
            target_descriptor=target_desc,
            runner=runner,
            finder=finder,
        )
    except Exception:
        return {
            "audio_sink_id": None,
            "audio_sink_is_hdmi": False,
            "iec958_prepare_attempted": False,
            "iec958_prepare_status": "FAILED",
            "iec958_prepare_reason": "PREPARATION_EXCEPTION",
        }


def choose_subtitle(policy: str, probe: dict | None) -> dict:
    tracks = _typed_streams(probe or {}, "subtitle")
    if policy == "AUTO":
        return {"requested": policy, "resolved": "MPV_AUTO", "track": None, "reason": "qualified_default", "mpv_args": []}
    if policy == "OFF":
        return {"requested": policy, "resolved": "NONE", "track": None, "reason": "user_disabled", "mpv_args": ["--sid=no"]}
    french = [track for track in tracks if _is_french(track)]
    if policy == "FR_FORCED":
        structured = [track for track in french if _flag(track, "forced")]
        secondary = [track for track in french if re.search(r"\b(?:forced|forcé|force)\b", _title(track))]
        chosen = (structured or secondary or [None])[0]
        reason = "structured_forced_track" if structured else "title_forced_track" if secondary else "no_qualified_forced_track"
    else:
        full = [track for track in french if not _flag(track, "forced") and not re.search(r"\b(?:forced|forcé|force)\b", _title(track))]
        chosen = full[0] if full else None
        reason = "french_full_track" if chosen else "no_qualified_full_track"
    return {"requested": policy, "resolved": f"SID_{chosen['mpv_id']}" if chosen else "NONE", "track": chosen, "reason": reason, "mpv_args": [f"--sid={chosen['mpv_id']}"] if chosen else ["--sid=no"]}


def choose_dvd_subtitle(policy: str, optical_state: dict | None) -> dict:
    """Resolve DVD subtitles without treating lsdvd order as an MPV track ID."""
    if policy in {"AUTO", "OFF", "FR_FORCED"}:
        return choose_subtitle(policy, None)
    physical = optical_state.get("physical_edition", {}) if isinstance(optical_state, dict) else {}
    subtitles = physical.get("subtitles", []) if isinstance(physical, dict) and physical.get("lsdvd_ok") is True else []
    french = next((track for track in subtitles
                   if isinstance(track, dict) and str(track.get("langcode", "")).casefold().strip() in FR_LANGS), None)
    if french is None:
        return {"requested": policy, "resolved": "NONE", "track": None,
                "reason": "dvd_no_qualified_full_track", "mpv_args": ["--sid=no"]}
    # lsdvd subpicture order is not MPV's track-list ID.  MPV documents --slang
    # for dvd:// playback and resolves the usable track for the selected title.
    return {"requested": policy, "resolved": "MPV_FR_LANGUAGE", "track": french,
            "reason": "dvd_french_full_track", "mpv_args": ["--slang=fr,fra,fre"]}


def play_mpv(home, command, *, media=None, runner=subprocess.run, refresh_dispatch_id=None, **kwargs):
    """Shared T8.6 lifecycle; refresh helper failure never prevents MPV launch."""
    try:
        spec = importlib.util.spec_from_file_location("openhtpc_refresh_match", pathlib.Path(__file__).with_name("openhtpc-refresh-match.py"))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
    except (OSError, ImportError, AttributeError):
        return runner(command, **kwargs)
    return helper.run_playback(home, command, media=media, runner=runner, dispatch_id=refresh_dispatch_id, **kwargs)


def probe_media(path: pathlib.Path, ffprobe: str | None = None) -> dict | None:
    binary = ffprobe or shutil.which("ffprobe")
    if not binary: return None
    try:
        result = subprocess.run([binary, "-v", "error", "-show_streams", "-of", "json", "--", str(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False)
        value = json.loads(result.stdout) if result.returncode == 0 else None
        return value if isinstance(value, dict) and isinstance(value.get("streams"), list) else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def resolve(home: pathlib.Path, media: pathlib.Path | None = None, kind: str = "local", probe: dict | None = None,
            optical_state: dict | None = None, *, audio_outputs: list[dict] | None = None,
            gpu_binding: dict[str, Any] | None = None) -> dict:
    prefs = read_preferences(home)
    if probe is None and media is not None: probe = probe_media(media)
    requested = prefs["presentation_mode"]
    presentation = {"requested": requested, "resolved": "PURE", "reason": "requested_pure" if requested == "PURE" else "no_qualified_local_auto_scope"}
    audio = choose_audio(prefs["audio_language_policy"], probe)
    source_audio_tracks = _typed_streams(probe or {}, "audio")
    if not source_audio_tracks and kind == "dvd" and isinstance(optical_state, dict):
        physical = optical_state.get("physical_edition", {})
        dvd_tracks = physical.get("audio", []) if isinstance(physical, dict) else []
        for index, track in enumerate(dvd_tracks if isinstance(dvd_tracks, list) else [], 1):
            if isinstance(track, dict) and track.get("format"):
                source_audio_tracks.append({**track, "codec_name": str(track["format"]).casefold(), "mpv_id": index})
    dvd_language_track = next((track for track in source_audio_tracks if audio.get("requested") == "FR" and str(track.get("langcode", "")).casefold() in FR_LANGS), None)
    effective_audio_track = audio.get("track") or dvd_language_track or next((track for track in source_audio_tracks if _flag(track, "default")), None) or (source_audio_tracks[0] if source_audio_tracks else None)
    audio_output = choose_audio_output(prefs["audio_output_mode"], effective_audio_track)
    subtitle = (choose_dvd_subtitle(prefs["subtitle_policy"], optical_state)
                if kind == "dvd" else choose_subtitle(prefs["subtitle_policy"], probe))

    # Dynamic GPU binding resolution (RC7 T8.1B2)
    if gpu_binding is None:
        gpu_mod = _load_gpu_runtime_module()
        if gpu_mod and hasattr(gpu_mod, "resolve_playback_gpu_binding"):
            try:
                gpu_binding = gpu_mod.resolve_playback_gpu_binding()
            except Exception:
                gpu_binding = {
                    "status": "AUTO_FALLBACK",
                    "pci_address": None,
                    "drm_render_path": None,
                    "vulkan_uuid": None,
                    "vulkan_device_name": None,
                    "reason": "RESOLVER_EXCEPTION",
                    "evidence": [],
                    "mpv_args": [],
                }
        else:
            gpu_binding = {
                "status": "AUTO_FALLBACK",
                "pci_address": None,
                "drm_render_path": None,
                "vulkan_uuid": None,
                "vulkan_device_name": None,
                "reason": "RESOLVER_UNAVAILABLE",
                "evidence": [],
                "mpv_args": [],
            }

    # Audio output target resolution (RC7 T7.2)
    target_config = read_audio_output_target(home)
    audio_mod = _load_audio_module()
    target_mode = target_config.get("mode") if isinstance(target_config, dict) else "SYSTEM"

    if target_mode == "DEVICE":
        if audio_outputs is not None:
            outputs = audio_outputs
        elif audio_mod and hasattr(audio_mod, "discover_outputs"):
            outputs = audio_mod.discover_outputs()
        else:
            outputs = []
        if audio_mod and hasattr(audio_mod, "resolve_audio"):
            routing = audio_mod.resolve_audio(target_config, outputs)
        else:
            routing = {
                "CONFIGURED": target_config,
                "AVAILABLE": False,
                "EFFECTIVE": {"mode": "SYSTEM", "node_name": None, "bus_path": None, "edid_name": None, "display_label": "SYSTEM", "device_type": "UNKNOWN"},
            }
    else:
        sys_desc = (
            audio_mod.system_descriptor()
            if audio_mod and hasattr(audio_mod, "system_descriptor")
            else {"mode": "SYSTEM", "node_name": None, "bus_path": None, "edid_name": None, "display_label": "SYSTEM", "device_type": "UNKNOWN"}
        )
        routing = {
            "CONFIGURED": target_config if isinstance(target_config, dict) and target_config.get("mode") == "SYSTEM" else sys_desc,
            "AVAILABLE": True,
            "EFFECTIVE": sys_desc,
        }

    configured_target = routing["CONFIGURED"]
    available = bool(routing["AVAILABLE"])
    effective_target = routing["EFFECTIVE"]
    is_fallback = bool(configured_target.get("mode") == "DEVICE" and not available)

    mpv_device_args: list[str] = []
    if effective_target.get("mode") == "DEVICE" and effective_target.get("node_name"):
        mpv_device_args = [f"--audio-device=pipewire/{effective_target['node_name']}"]
        bitstream_sink_target = effective_target["node_name"]
    else:
        mpv_device_args = []
        bitstream_sink_target = "@DEFAULT_AUDIO_SINK@"

    audio_target_diag = {
        "configured": configured_target.get("mode", "SYSTEM"),
        "configured_label": configured_target.get("display_label") or configured_target.get("edid_name") or configured_target.get("node_name") or "SYSTEM",
        "available": available,
        "effective": effective_target.get("node_name") if effective_target.get("mode") == "DEVICE" else "SYSTEM",
        "audio_mode": prefs["audio_output_mode"],
        "fallback": is_fallback,
        "sink_target": bitstream_sink_target,
        "descriptor": effective_target,
    }

    hwdec = None
    hwdec_status = "UNAVAILABLE"
    hwdec_codecs = None
    pure_conf_path = home / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf_path.is_file():
        try:
            profile_path = home / ".config/openhtpc/profile.json"
            if profile_path.is_file():
                prof = json.loads(profile_path.read_text(encoding="utf-8"))
                cand = prof.get("runtime_profiles", {}).get("profiles", {}).get("PURE", {}).get("config_path")
                if cand and pathlib.Path(cand).is_file():
                    pure_conf_path = pathlib.Path(cand)
        except (OSError, ValueError, KeyError):
            pass

    if pure_conf_path.is_file():
        try:
            for conf_line in pure_conf_path.read_text(encoding="utf-8").splitlines():
                line = conf_line.strip()
                if line.startswith("hwdec=") and not line.startswith("#"):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        hwdec = val
                        hwdec_status = "OBSERVED"
                elif line.startswith("hwdec-codecs=") and not line.startswith("#"):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        hwdec_codecs = val
        except OSError:
            pass

    profile_data = None
    try:
        prof_path = home / ".config/openhtpc/profile.json"
        if prof_path.is_file():
            profile_data = json.loads(prof_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        pass

    processing_gpu = {}
    if isinstance(profile_data, dict):
        processing_gpu = profile_data.get("gpu_topology", {}).get("processing_gpu", {})
        if not processing_gpu and isinstance(profile_data.get("gpu_selection", {}).get("gpu"), dict):
            processing_gpu = profile_data["gpu_selection"]["gpu"]

    vaapi_decode = processing_gpu.get("vaapi_decode", {}) if isinstance(processing_gpu, dict) else {}
    nvdec_decode = processing_gpu.get("nvdec_decode", {}) if isinstance(processing_gpu, dict) else {}
    gpu_model = str(processing_gpu.get("model", "")).casefold()
    gpu_vendor = str(processing_gpu.get("vendor", "")).casefold()
    gpu_device_id = str(processing_gpu.get("device_id", "")).casefold()
    vulkan_name = str((gpu_binding or {}).get("vulkan_device_name", "")).casefold()

    media_codec = None
    if kind == "dvd":
        media_codec = "mpeg2video"
    elif kind == "local":
        video_streams = _typed_streams(probe or {}, "video")
        if video_streams and isinstance(video_streams[0], dict):
            media_codec = str(video_streams[0].get("codec_name", "")).casefold() or None

    mpv_decode_args: list[str] = []
    physical_gpu_binding = "NOT_PROVEN"
    effective_hwdec = hwdec

    # Diagnostic capability assessment (non-authoritative for negative decisions when physical binding is NOT_PROVEN)
    is_intel_dg2 = bool(
        "dg2" in gpu_model
        or "arc" in gpu_model
        or "dg2" in vulkan_name
        or "arc" in vulkan_name
        or gpu_device_id.startswith("56")
    )
    diagnostic_limits: list[str] = []
    if hwdec == "vaapi" and is_intel_dg2:
        diagnostic_limits.append("INTEL_DG2_NO_HARDWARE_VC1")
    elif (hwdec == "vaapi" and vaapi_decode.get("vc1") is False) or (hwdec == "nvdec" and nvdec_decode.get("vc1") is False):
        diagnostic_limits.append("PASSPORT_NO_HARDWARE_VC1")
    if (hwdec == "vaapi" and vaapi_decode.get("mpeg2") is False) or (hwdec == "nvdec" and nvdec_decode.get("mpeg2") is False):
        diagnostic_limits.append("PASSPORT_NO_HARDWARE_MPEG2")

    # NEGATIVE HWDEC POLICY — FROZEN RULE:
    # A per-GPU negative decoding decision such as:
    # --hwdec=no, codec exclusion, forced software decoding
    # requires PROVEN physical decode-GPU identity. RENDER GPU identity is insufficient.
    # If physical_gpu_binding == "NOT_PROVEN", then GPU-specific capability information
    # may be diagnostic, but MUST NOT be used to disable hardware decoding.
    # Hardware Passport codec capabilities are not runtime authority unless identity and freshness
    # have independently been proven.
    # Positive MPV capability enablement is permitted when MPV provides safe software fallback.
    if hwdec in {"vaapi", "nvdec"}:
        needs_mpeg2 = (
            kind == "dvd"
            or kind == "bluray"
            or media_codec in {"mpeg2video", "mpegvideo", "mpeg1video"}
        )
        if needs_mpeg2:
            existing_codecs = {c.strip() for c in hwdec_codecs.split(",")} if hwdec_codecs else set()
            if "mpeg2video" not in existing_codecs and "all" not in existing_codecs:
                base_codecs = hwdec_codecs if hwdec_codecs else MPV_DEFAULT_HWDEC_CODEC_WHITELIST
                mpv_decode_args.append(f"--hwdec-codecs={base_codecs},mpeg2video")

    decode_policy = {
        "status": hwdec_status,
        "hwdec": hwdec,
        "physical_gpu_binding": physical_gpu_binding,
    }
    if media_codec is not None:
        decode_policy["media_codec"] = media_codec
        decode_policy["effective_hwdec"] = effective_hwdec
    if diagnostic_limits:
        decode_policy["diagnostic_limits"] = diagnostic_limits

    mpv_gpu_args = list((gpu_binding or {}).get("mpv_args", []))
    mpv_args = [*mpv_gpu_args, *mpv_decode_args, *audio["mpv_args"], *audio_output["mpv_args"], *mpv_device_args, *subtitle["mpv_args"]]
    return {
        "presentation": presentation,
        "audio": audio,
        "audio_output": audio_output,
        "subtitle": subtitle,
        "audio_target": audio_target_diag,
        "gpu_binding": gpu_binding,
        "gpu_render_binding": gpu_binding,
        "decode_policy": decode_policy,
        "mpv_args": mpv_args,
        "kind": kind,
    }


def osd_text(decision: dict) -> str:
    p = decision["presentation"]; a = decision["audio"]; s = decision["subtitle"]
    requested = "CINÉMA AUTO" if p["requested"] == "CINEMA_AUTO" else "PURE"
    audio = "Français" if a["resolved"].startswith("AID_") and a["requested"] == "FR" else "Piste par défaut" if a["requested"] == "DEFAULT" else "Auto"
    if s["requested"] == "OFF": subtitles = "Désactivés"
    elif s["resolved"] == "NONE": subtitles = "Aucun"
    elif s["requested"] == "FR_FORCED": subtitles = "Français forcés"
    elif s["requested"] == "FR_FULL": subtitles = "Français"
    else: subtitles = "Auto"
    # Pass literal newlines as one argv value.  MPV's osd-playing-msg parser
    # treats a literal ``\N`` as an invalid property-expansion escape.
    return f"Mode vidéo : {requested}\nAudio : {audio}\nSous-titres : {subtitles}"


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--home", type=pathlib.Path, default=pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("get")
    setter = sub.add_parser("set"); setter.add_argument("key", choices=sorted(VALID)); setter.add_argument("value")
    resolver = sub.add_parser("resolve"); resolver.add_argument("--media", type=pathlib.Path); resolver.add_argument("--kind", choices=("local", "dvd"), default="local"); resolver.add_argument("--dvd-state", type=pathlib.Path)
    prep = sub.add_parser("prepare-bitstream"); prep.add_argument("--decision", type=str, required=True)
    rec_obs = sub.add_parser("record-observation")
    rec_obs.add_argument("--decision", type=str, required=True)
    rec_obs.add_argument("--log-file", type=pathlib.Path, required=True)
    rec_obs.add_argument("--exit-code", type=int, default=0)
    rec_obs.add_argument("--kind", type=str, default="local")
    rec_obs.add_argument("--dispatch-id", type=str, default=None)
    rec_disp = sub.add_parser("record-dispatch")
    rec_disp.add_argument("--decision", type=str, required=True)
    rec_disp.add_argument("--kind", type=str, default="local")
    rec_disp.add_argument("--dispatch-id", type=str, default=None)
    rec_fail = sub.add_parser("record-failure")
    rec_fail.add_argument("--reason", type=str, default="LAUNCH_FAILED")
    rec_fail.add_argument("--exit-code", type=int, default=None)
    rec_fail.add_argument("--kind", type=str, default="local")
    rec_fail.add_argument("--dispatch-id", type=str, default=None)
    sub.add_parser("get-runtime")
    args = parser.parse_args()
    if args.command == "record-observation":
        try:
            decision = json.loads(args.decision) if args.decision else {}
        except Exception:
            decision = {}
        raw = args.log_file.read_text(encoding="utf-8", errors="replace") if args.log_file.is_file() else ""
        res = record_playback_observation(args.home, decision, raw, exit_code=args.exit_code, kind=args.kind, dispatch_id=args.dispatch_id)
        print(json.dumps(res, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "record-dispatch":
        try:
            decision = json.loads(args.decision) if args.decision else {}
        except Exception:
            decision = {}
        res = record_playback_dispatch(args.home, decision, kind=args.kind, dispatch_id=args.dispatch_id)
        print(json.dumps(res, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "record-failure":
        res = record_playback_failure(args.home, reason=args.reason, exit_code=args.exit_code, kind=args.kind, dispatch_id=args.dispatch_id)
        print(json.dumps(res, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "get-runtime":
        rt = read_playback_runtime(args.home)
        print(json.dumps(rt, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "prepare-bitstream":
        try:
            decision = json.loads(args.decision)
        except Exception:
            decision = {}
        diag = prepare_audio_target_bitstream(decision)
        print(json.dumps(diag, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "get": print(json.dumps(read_preferences(args.home), ensure_ascii=False, sort_keys=True)); return 0
    if args.command == "set":
        try: result = write_preference(args.home, args.key, args.value.upper())
        except ValueError: return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0
    optical_state = None
    if args.dvd_state is not None:
        try:
            candidate = json.loads(args.dvd_state.read_text(encoding="utf-8"))
            if isinstance(candidate, dict): optical_state = candidate
        except (OSError, json.JSONDecodeError):
            pass
    result = resolve(args.home, args.media, args.kind, optical_state=optical_state); result["osd"] = osd_text(result); print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
