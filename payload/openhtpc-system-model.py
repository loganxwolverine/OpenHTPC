#!/usr/bin/env python3
"""Normalized SYSTÈME presenter; consumes canonical state and never probes hardware."""
from __future__ import annotations
import datetime, json, pathlib

CODEC_ORDER = ("mpeg2", "h264_8bit", "hevc_main", "hevc_main10", "vp9_profile0", "vp9_10bit", "av1_main")
CODEC_NAMES = {
    "mpeg2": "MPEG-2",
    "h264_8bit": "H.264 / AVC",
    "hevc_main": "HEVC / H.265",
    "hevc_main10": "HEVC / H.265 10 bits",
    "vp9_profile0": "VP9",
    "vp9_10bit": "VP9 10 bits",
    "av1_main": "AV1",
}
STATUS_FR = {
    "AVAILABLE": "Disponible",
    "SUPPORTED": "Pris en charge",
    "VALIDATED": "Validé",
    "UNVALIDATED": "Non encore testé",
    "UNKNOWN": "Indéterminé",
    "UNAVAILABLE": "Indisponible",
    "UNSUPPORTED": "Non pris en charge",
    "DETECTED": "Détecté",
    "ACTIVE": "Actif",
    "INACTIVE": "Inactif",
    "NOT_RUN": "Non effectué",
    "NOT_EVALUATED": "Non évalué",
    "NOT_APPLICABLE": "Sans objet",
    "PASS": "OK",
    "FAIL": "Échec",
    "READY": "Prêt",
    "RUNNING": "En cours",
    "STOPPED": "Arrêté",
    "NOT_CONFIGURED": "Non configuré",
    "NOT_INSTALLED": "Non installé",
    "NOT_GENERATED": "Non généré",
    "SKIPPED_UNSUPPORTED_ENVIRONMENT": "Non applicable",
    "unknown": "Indéterminé",
}

CHECK_LABELS_FR = {
    "OPENHTPC Core": "Cœur système OPENHTPC",
    "Hardware Passport": "Passeport matériel",
    "Generated Runtime": "Environnement généré",
    "Flex Launcher": "Lanceur d'interface",
    "Media Browser": "Explorateur de médias",
    "DVD": "Prise en charge DVD",
    "Capability snapshot": "Instantané des capacités",
}


def read_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def clean(value, default="Indéterminé"):
    if value in (None, "", [], {}):
        return default
    s = str(value).replace("\n", " ").replace("\r", " ").replace(";", " — ").strip()
    if s.lower() in {"unknown", "none", "null", "not_applicable"}:
        return default
    return s


def state(value):
    raw = value.get("status") if isinstance(value, dict) else value
    if isinstance(raw, str) and raw.lower() in STATUS_FR:
        return STATUS_FR[raw.lower()]
    return STATUS_FR.get(str(raw), clean(raw))


def short_device(value):
    raw = clean(value)
    lower = raw.lower()
    if "hdmi" in lower:
        return "HDMI"
    if "displayport" in lower or "display port" in lower:
        return "DisplayPort"
    return raw if len(raw) <= 54 else raw[:53].rstrip() + "…"


def health_label(overall):
    return {"READY": "PRÊT", "PASS": "PRÊT", "DEGRADED": "ATTENTION", "BLOCKED": "PROBLÈME"}.get(str(overall).upper(), "ATTENTION")


def _display_summary(mode: dict | None, active: dict | None = None) -> str:
    if not isinstance(mode, dict) or not mode.get("width") or not mode.get("height"):
        return "Indéterminé"
    w = mode.get("width")
    h = mode.get("height")
    hz = mode.get("refresh_hz")
    parts = [f"{w} × {h}"]
    if isinstance(hz, (int, float)):
        if abs(hz - round(hz)) < 0.05:
            parts.append(f"{int(round(hz))} Hz")
        else:
            parts.append(f"{hz:.2f} Hz")
    if isinstance(active, dict):
        hdr_mode = active.get("current_hdr_mode", {})
        hdr_status = hdr_mode.get("status") if isinstance(hdr_mode, dict) else hdr_mode
        if hdr_status == "ACTIVE":
            parts.append("HDR")
        elif hdr_status == "INACTIVE":
            parts.append("SDR")
    return " • ".join(parts)


def _mode(mode, active=None):
    return _display_summary(mode, active)


def _matches(record, key):
    codec = str(record.get("codec", "")).lower()
    profile = str(record.get("profile", "")).lower()
    bits = record.get("bit_depth")
    return (
        (key == "mpeg2" and codec in {"mpeg2video", "mpeg2"})
        or (key == "h264_8bit" and codec in {"h264", "avc"} and bits in {None, 8})
        or (key == "hevc_main" and codec in {"hevc", "h265"} and bits in {None, 8} and "10" not in profile)
        or (key == "hevc_main10" and codec in {"hevc", "h265"} and (bits == 10 or "10" in profile))
        or (key == "vp9_profile0" and codec == "vp9" and bits in {None, 8})
        or (key == "vp9_10bit" and codec == "vp9" and bits == 10)
        or (key == "av1_main" and codec == "av1")
    )


def build(home: pathlib.Path, install: pathlib.Path, health: dict, version: dict) -> dict:
    caps = read_json(home / ".config/openhtpc/runtime/capabilities.json")
    profile = read_json(home / ".config/openhtpc/profile.json")
    detected = profile.get("detected", {}) if isinstance(profile.get("detected"), dict) else {}
    topology = profile.get("gpu_topology", {}) if isinstance(profile.get("gpu_topology"), dict) else {}
    legacy_gpu = topology.get("processing_gpu", {}) if isinstance(topology.get("processing_gpu"), dict) else {}
    available = bool(caps)
    hardware = caps.get("hardware", {})
    graphics = caps.get("graphics", {})
    display = caps.get("display", {})
    decode = caps.get("video_decode", {})
    audio = caps.get("audio", {})
    media = caps.get("media", {})
    optical = caps.get("optical", {})
    processing = caps.get("video_processing", {})
    cpu = hardware.get("cpu", {})
    memory = hardware.get("memory", {})
    system = hardware.get("system", {})
    ram = memory.get("total_bytes")
    ram = f"{ram/1024**3:.1f} Gio" if isinstance(ram, (int, float)) else clean(detected.get("memory"), "Indéterminée")

    gpus = []
    for index, item in enumerate(graphics.get("devices", []) if isinstance(graphics.get("devices"), list) else []):
        gpus.append({
            "role": "GPU actif" if item.get("active") is True else "GPU secondaire" if item.get("active") is False else f"GPU {index+1}",
            "name": clean(item.get("model")),
            "driver": clean(item.get("kernel_driver")),
            "memory": "Partagée" if item.get("memory_type") == "shared" else "Dédiée" if item.get("memory_type") == "dedicated" else "Indéterminée",
            "pci": clean(item.get("pci_address")),
            "device_id": clean(item.get("device_id")),
            "render_nodes": ", ".join(item.get("render_nodes", [])) or "Indéterminé",
        })

    active = display.get("active_output") if isinstance(display.get("active_output"), dict) else {}
    mode = active.get("current_mode") if isinstance(active.get("current_mode"), dict) else {}
    if not mode and isinstance(display.get("outputs"), list):
        for out in display.get("outputs"):
            if isinstance(out, dict) and out.get("active") and isinstance(out.get("current_mode"), dict):
                active = out
                mode = out.get("current_mode")
                break
    if not mode and isinstance(active.get("available_modes"), list) and active.get("available_modes"):
        first_mode = active.get("available_modes")[0]
        if isinstance(first_mode, dict) and first_mode.get("width") and first_mode.get("height"):
            mode = first_mode

    display_summary_str = _display_summary(mode, active)
    res_str = f"{mode.get('width')} × {mode.get('height')}" if mode.get("width") and mode.get("height") else "Indéterminée"
    if isinstance(mode.get("refresh_hz"), (int, float)):
        hz = mode.get("refresh_hz")
        ref_str = f"{int(round(hz))} Hz" if abs(hz - round(hz)) < 0.05 else f"{hz:.2f} Hz"
    else:
        ref_str = "Indéterminée"

    codecs = []
    matrix = decode.get("codecs", {}) if isinstance(decode.get("codecs"), dict) else {}
    records = caps.get("validation", {}).get("records", []) if isinstance(caps.get("validation"), dict) else []
    for key in CODEC_ORDER:
        item = matrix.get(key, {})
        detail = next((r for r in reversed(records) if isinstance(r, dict) and _matches(r, key)), {})
        signature = ""
        if detail:
            wh = f"{detail.get('width')}×{detail.get('height')}" if detail.get("width") and detail.get("height") else ""
            bits = f"{detail.get('bit_depth')} bits" if detail.get("bit_depth") else ""
            fps = f"{detail.get('fps'):.2f} fps" if isinstance(detail.get("fps"), (int, float)) else ""
        codecs.append({
            "key": key,
            "name": CODEC_NAMES[key],
            "software": state(item.get("software_decode", {})),
            "hardware": state(item.get("hardware_decode", {})),
            "validated": state(item.get("validated_playback", {})),
            "backend": ", ".join(item.get("hardware_backends", [])).upper() or "Indéterminé",
            "detail": signature,
        })

    sources = media.get("sources", []) if isinstance(media.get("sources"), list) else []
    raw_source_types = {clean(item.get("filesystem_type") or item.get("filesystem_class")) for item in sources if isinstance(item, dict)}
    source_types = sorted({STATUS_FR.get(s, clean(s)) for s in raw_source_types if s})
    drives = optical.get("drives", []) if isinstance(optical.get("drives"), list) else []
    generated = caps.get("generated_at")
    stale = False
    try:
        stale = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(generated)).total_seconds() > 604800
    except (TypeError, ValueError):
        stale = not available

    checks = health.get("checks", []) if isinstance(health.get("checks"), list) else []
    action = read_json(home / ".local/state/openhtpc/system-action.json")

    display_dict = {
        "connector": clean(active.get("connector")),
        "resolution": res_str,
        "refresh": ref_str,
        "summary": display_summary_str,
        "scale": f"{active.get('scale'):.2f}" if isinstance(active.get("scale"), (int, float)) else "Indéterminée",
        "depth": f"{active.get('color_depth', {}).get('current_bits')} bits" if isinstance(active.get("color_depth"), dict) and active.get("color_depth", {}).get("current_bits") else "Indéterminée",
        "hdr_current": state(active.get("current_hdr_mode", {})),
        "hdr_capable": state(active.get("hdr_capable", {})),
        "hdr_pipeline": state(display.get("hdr_pipeline_validated", {})),
        "codecs": codecs,
    }

    audio_dict = {
        "audio_output": short_device(audio.get("default_sink")),
        "audio_backend": clean(audio.get("backend")),
        "connection": clean(audio.get("connection_class")),
        "channels": f"{audio.get('channels')} canaux" if audio.get("channels") else "Indéterminés",
        "passthrough": state(audio.get("passthrough", {})),
    }

    media_optical_dict = {
        "configured": media.get("configured_sources", 0),
        "accessible": media.get("accessible_sources", 0),
        "source_types": ", ".join(source_types) or "Aucune",
        "playback": clean(media.get("playback_backend", "mpv")).upper(),
        "drives": len(drives),
        "dvd": state(optical.get("dvd", {}).get("physical_support", {})),
        "css": state(optical.get("dvd", {}).get("css_support", {})),
        "bluray": state(optical.get("bluray_plugin", {})),
        "uhd": state(optical.get("uhd_plugin", {})),
    }

    audio_media_dict = {**audio_dict, **media_optical_dict}

    gpu_ev = processing.get("gpu_backend", {}).get("evidence", []) if isinstance(processing.get("gpu_backend"), dict) else []
    render_ev = processing.get("render_backend", {}).get("evidence", []) if isinstance(processing.get("render_backend"), dict) else []
    gpu_backend_str = "Vulkan" if "VULKAN" in gpu_ev and processing.get("gpu_backend", {}).get("status") == "AVAILABLE" else state(processing.get("gpu_backend", {}))
    render_backend_str = "gpu-next" if "MPV" in render_ev and processing.get("render_backend", {}).get("status") == "AVAILABLE" else state(processing.get("render_backend", {}))

    result = {
        "available": available,
        "stale": stale,
        "generated_at": clean(generated, "Jamais"),
        "schema": caps.get("schema"),
        "probe_version": caps.get("probe_version"),
        "product": {
            "version": clean(version.get("version")),
            "build": clean(version.get("build_id")),
            "health": health_label(health.get("overall")),
            "overall": health.get("overall", "UNKNOWN"),
        },
        "overview": {
            "machine": " ".join(v for v in (clean(system.get("manufacturer"), ""), clean(system.get("model"), "")) if v) or "Machine non identifiée",
            "cpu": clean(cpu.get("model")),
            "ram": ram,
            "gpu": gpus[0]["name"] if gpus else "Indéterminé",
            "display": display_summary_str,
            "graphics": "Vulkan • VA-API" if state(graphics.get("vulkan", {}).get("loader", {})) == "Disponible" and state(graphics.get("vaapi", {}).get("status", {})) == "Disponible" else "Capacités graphiques partielles",
        },
        "codecs": codecs,
        "hardware": {
            "machine": clean(system.get("model")),
            "manufacturer": clean(system.get("manufacturer")),
            "cpu": clean(cpu.get("model")),
            "architecture": clean(cpu.get("architecture")),
            "logical_cores": clean(cpu.get("logical_cores")),
            "ram": ram,
            "gpus": gpus,
            "vulkan": state(graphics.get("vulkan", {}).get("loader", {})),
            "vaapi": state(graphics.get("vaapi", {}).get("status", {})),
            "vulkan_driver": ", ".join(clean(x.get("driver_name")) for x in graphics.get("vulkan", {}).get("devices", []) if isinstance(x, dict)) or "Indéterminé",
            "vaapi_driver": ", ".join(graphics.get("vaapi", {}).get("drivers", [])) or "Indéterminé",
        },
        "display": display_dict,
        "audio": clean(audio.get("default_sink") or ((detected.get("audio_devices") or [None])[0]), "N/A"),
        "audio_section": audio_dict,
        "media_optical": media_optical_dict,
        "audio_media": audio_media_dict,
        "processing": {
            "profile": clean(processing.get("active_profile")),
            "gpu_backend": gpu_backend_str,
            "render_backend": render_backend_str,
            "output": _display_summary(processing.get("output_mode", {})),
            "benchmark": state(processing.get("benchmark", {}).get("status")),
            "recommendation": state(processing.get("recommendation_status")),
            "active_video_profile": "PURE",
            "map_present": False,
        },
        "diagnostics": {
            "checks": [{"label": CHECK_LABELS_FR.get(item.get("label"), clean(item.get("label"))), "status": state(item.get("status"))} for item in checks],
            "overall": health_label(health.get("overall")),
            "snapshot": "Disponible" if available else "Indisponible",
            "last_action": clean(action.get("message"), "Aucune action récente"),
            "privacy": "Le rapport contient des informations techniques sur cette machine. Vérifiez-le avant de le partager.",
        },
        "technical": {
            "version": clean(version.get("version")),
            "build": clean(version.get("build_id")),
            "schema": clean(caps.get("schema")),
            "probe": clean(caps.get("probe_version")),
            "generated": clean(generated),
            "mpv": clean(decode.get("mpv", {}).get("version")),
            "ffmpeg": clean(decode.get("ffmpeg", {}).get("version")),
            "connector": clean(active.get("connector")),
            "vulkan_driver": ", ".join(clean(x.get("driver_name")) for x in graphics.get("vulkan", {}).get("devices", []) if isinstance(x, dict)) or "Indéterminé",
            "vaapi_driver": ", ".join(graphics.get("vaapi", {}).get("drivers", [])) or "Indéterminé",
        },
    }
    state_caps = health.get("capabilities", {}) if isinstance(health.get("capabilities"), dict) else {}
    result.update({
        "overall": health.get("overall", "UNKNOWN"),
        "product_version": clean(version.get("version")),
        "build_id": clean(version.get("build_id")),
        "model": clean(system.get("model")),
        "manufacturer": clean(system.get("manufacturer")),
        "cpu": clean(cpu.get("model")),
        "gpu": clean((gpus[0]["name"] if gpus else None) or legacy_gpu.get("model") or detected.get("gpu"), "N/A"),
        "ram": ram,
        "audio_sink": clean(audio.get("default_sink") or ((detected.get("audio_devices") or [None])[0]), "N/A"),
        "optical": clean(((detected.get("optical_drives") or [None])[0]), "Non détecté"),
        "media_state": "Aucun disque",
        "profile": clean(processing.get("active_profile") or ("PURE" if "PURE" in profile.get("runtime_profiles", {}).get("profiles", {}) else None), "N/A"),
        "vulkan": state(graphics.get("vulkan", {}).get("loader", {})) if available else clean((detected.get("vulkan") or {}).get("status"), "N/A"),
        "vaapi": state(graphics.get("vaapi", {}).get("status", {})) if available else clean((detected.get("vaapi") or {}).get("status"), "N/A"),
        "runtime": clean(profile.get("runtime", {}).get("status"), "N/A"),
        "tmdb": "Configuré" if state_caps.get("TMDB_CONFIGURED") else "Non configuré",
        "disc_monitor": "Actif" if health.get("runtime", {}).get("monitor_instances") == 1 else "Indisponible",
        "media_module": "Actif" if state_caps.get("MEDIA_BROWSER_READY") else "Indisponible",
        "dvd": "Actif" if state_caps.get("DVD_READY") else "Indisponible",
        "optional": {name: "Non installé" for name in ("bluray", "uhd", "jellyfin", "plex", "streaming")},
        "services": "Actif" if health.get("overall") in {"READY", "PASS"} else "Attention",
        "uptime": "N/A",
        "memory_usage": "N/A",
        "temperature": "N/A",
        "gpu_usage": "N/A",
    })
    # C4 video profile state
    try:
        vp_path = home / ".config/openhtpc/video-profile.json"
        vp_data = read_json(vp_path)
        active_profile = vp_data.get("active_profile", "PURE") if vp_data else "PURE"
        if active_profile not in {"PURE", "CINEMA_AUTO"}:
            active_profile = "PURE"
    except Exception:
        active_profile = "PURE"

    perf_map_path = home / ".local/state/openhtpc/performance_map.json"
    perf_map_present = perf_map_path.exists()
    map_stale = False
    decision_human = "PURE"
    if perf_map_present:
        try:
            import importlib.util
            ca_path = install / "openhtpc-cinema-auto.py"
            if ca_path.exists():
                spec = importlib.util.spec_from_file_location("ca", ca_path)
                if spec and spec.loader:
                    ca = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(ca)
                    pmap = json.loads(perf_map_path.read_text(encoding="utf-8"))
                    if pmap:
                        stale, _ = ca.is_map_stale(pmap)
                        map_stale = stale
                        rec, _ = ca.select_recipe("DVD_PAL_FILM", pmap, ca._load_catalog())
                        RECIPE_NAMES = {
                            "RECIPE_0_PURE": "PURE",
                            "RECIPE_C2_DVD_KRIG_BILATERAL": "KrigBilateral",
                            "RECIPE_C2_DVD_FSRCNNX_8": "FSRCNNX 8",
                            "RECIPE_C2_DVD_RAVU_LITE": "RAVU Lite",
                            "RECIPE_C2_DVD_CFL_LITE": "CfL Lite",
                        }
                        decision_human = RECIPE_NAMES.get(rec, rec)
        except Exception:
            pass

    cal_ui_status = None
    cal_status_file = home / ".local/state/openhtpc/calibration-ui-status.json"
    if cal_status_file.exists():
        try:
            cst = read_json(cal_status_file)
            cal_ui_status = cst.get("status")
        except Exception:
            pass

    result["video_profile"] = {
        "active": active_profile,
        "map_present": perf_map_present,
        "map_stale": map_stale,
        "decision": decision_human,
        "cal_ui_status": cal_ui_status,
    }
    # Also update top-level profile key to reflect actual active C4 profile
    result["profile"] = active_profile
    # Update processing section
    result.setdefault("processing", {})
    result["processing"]["active_video_profile"] = active_profile
    result["processing"]["map_present"] = perf_map_present
    result["processing"]["map_stale"] = map_stale
    result["processing"]["decision"] = decision_human
    result["processing"]["cal_ui_status"] = cal_ui_status
    if available:
        result["vulkan"] = clean(graphics.get("vulkan", {}).get("loader", {}).get("status"), "N/A")
        result["vaapi"] = clean(graphics.get("vaapi", {}).get("status", {}).get("status"), "N/A")
    return result
