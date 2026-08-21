#!/usr/bin/env python3
"""Analyse un journal MPV OPENHTPC sans confondre demande et observation."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys


def first_match(patterns: tuple[str, ...], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: analyzer PROFILE LOG MPV_RC SUMMARY_BASE RUNTIME_PROFILE", file=sys.stderr)
        return 2

    profile_path = pathlib.Path(sys.argv[1])
    log_path = pathlib.Path(sys.argv[2])
    mpv_rc = int(sys.argv[3])
    summary_base = pathlib.Path(sys.argv[4])
    runtime_profile = sys.argv[5].upper()
    if runtime_profile not in {"PURE", "REFERENCE"}:
        print("invalid runtime profile", file=sys.stderr)
        return 2
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    log = log_path.read_text(encoding="utf-8", errors="replace")
    lines = log.splitlines()

    runtime_backend = profile.get("runtime", {}).get("backend", {})
    blueprint = profile.get("mpv_blueprint", {})
    hwdec_requested = runtime_backend.get("decode_api") or blueprint.get("hwdec")
    renderer_requested = runtime_backend.get("render_api") or blueprint.get("gpu_api")
    requested_from_log = first_match((r"Setting option ['\"]hwdec['\"]\s*=\s*['\"]([^'\"]+)",), log)
    if requested_from_log:
        hwdec_requested = requested_from_log

    vo_match = re.search(r"\bVO:\s*\[([^]]+)]\s+(\d{2,5}x\d{2,5})(?:\s+(\S+))?", log, re.IGNORECASE)
    vo_observed = vo_match.group(1) if vo_match else None
    resolution = vo_match.group(2) if vo_match else None
    output_format = vo_match.group(3) if vo_match else None

    codec = first_match(
        (
            r"\bVideo\s+--vid=\d+\s+\(([^,\s)]+)",
            r"\bcodec\s*[=:]\s*['\"]?([a-z0-9_.-]+)",
            r"Looking at hwdec\s+([a-z0-9_.-]+?)-(?:vaapi|nvdec|vdpau|vulkan)",
        ),
        log,
    )
    if not resolution:
        resolution = first_match((r"\b(\d{2,5}x\d{2,5})\b",), log)
    source_category = None
    if resolution:
        width, height = (int(value) for value in resolution.split("x", 1))
        if width >= 3840 or height >= 2160:
            source_category = "UHD/4K"
        elif width >= 1920 or height >= 1080:
            source_category = "1080p"
        elif width >= 1280 or height >= 720:
            source_category = "720p"
        else:
            source_category = "SD"

    hwdec_observed = first_match((r"Using hardware decoding\s*\(([^)]+)\)",), log)
    not_attempted = bool(re.search(r"Not trying to use hardware decoding", log, re.IGNORECASE))
    software_evidence = bool(
        re.search(r"software decoding|fall(?:ing)? back to software|Not trying to use hardware decoding", log, re.IGNORECASE)
    )
    if not hwdec_observed and (not_attempted or software_evidence or vo_observed):
        hwdec_observed = "software"

    renderer_observed = None
    for line in lines:
        lower = line.lower()
        if "vulkan" not in lower or "setting option" in lower:
            continue
        if re.search(r"created|initialized|instance|device|driver|renderer|context|using vulkan", lower):
            renderer_observed = "vulkan"
            break

    gpu_observed = first_match((r"Device Name\s*:\s*(.+)$", r"Vulkan device[^:]*:\s*(.+)$"), log, re.MULTILINE)
    if gpu_observed == "":
        gpu_observed = None

    fallback_reason = None
    if re.search(r"codec\s+mpeg2video\s+is not on (?:the )?whitelist", log, re.IGNORECASE):
        fallback_reason = "MPV did not attempt hardware decoding for this codec"
    elif not_attempted:
        fallback_reason = "MPV did not attempt hardware decoding for this codec"
    elif hwdec_observed == "software" and hwdec_requested:
        failure = first_match(
            (
                r"((?:Failed|Could not|Unable) to (?:initialize|open|use)[^\n]*(?:hwdec|hardware|VA-API|NVDEC)[^\n]*)",
                r"(Hardware decoding[^\n]*(?:failed|unavailable)[^\n]*)",
            ),
            log,
        )
        fallback_reason = failure or "Hardware decoding was requested but software decoding was observed"

    ignored_probe = re.compile(r"Failed to create mapper", re.IGNORECASE)
    important_error = re.compile(
        r"Error decoding|Could not open codec|Failed to initialize video|No video streams|Exiting.*(?:error|fatal)",
        re.IGNORECASE,
    )
    errors: list[str] = []
    for line in lines:
        clean = line.strip()
        if ignored_probe.search(clean) and hwdec_observed not in (None, "software"):
            continue
        if important_error.search(clean) and clean not in errors:
            errors.append(clean[:500])

    if vo_observed and hwdec_observed not in (None, "software"):
        video_status = "validated"
    elif vo_observed and hwdec_observed == "software":
        video_status = "software_fallback"
    elif mpv_rc != 0 or errors:
        video_status = "failed"
    else:
        video_status = "pending"

    pipewire_observed = bool(re.search(r"\bpipewire\b|\[ao/pipewire]|AO:\s*\[pipewire]", log, re.IGNORECASE))
    pipewire_streaming = bool(re.search(r"state\s*=\s*streaming", log, re.IGNORECASE))
    audio_backend = "pipewire" if pipewire_observed else None
    audio_status = "backend_observed" if pipewire_observed else "pending"

    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()
    last_test = {
        "timestamp": timestamp,
        "profile": runtime_profile,
        "mpv_exit_code": mpv_rc,
        "video": {
            "status": video_status,
            "codec": codec,
            "resolution": resolution,
            "source_category": source_category,
            "hwdec_requested": hwdec_requested,
            "hwdec_observed": hwdec_observed,
            "renderer_requested": renderer_requested,
            "renderer_observed": renderer_observed,
            "vo_observed": vo_observed,
            "video_output_format": output_format,
            "gpu_observed": gpu_observed,
            "software_fallback_reason": fallback_reason,
            "visual_smoothness_confirmed": None,
            "errors": errors,
        },
        "audio": {
            "status": audio_status,
            "backend_observed": audio_backend,
            "streaming_state_observed": pipewire_streaming,
            "audible_output_confirmed": False,
        },
    }
    profile["playback_validation"] = {"last_test": last_test}
    profile.setdefault("runtime", {})["playback_validated"] = False

    profile_tmp = profile_path.with_suffix(".json.tmp")
    profile_tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(profile_tmp, profile_path)

    json_path = summary_base.with_suffix(".summary.json")
    text_path = summary_base.with_suffix(".summary.txt")
    json_path.write_text(json.dumps(last_test, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    video_label = {
        "validated": "réussie avec décodage matériel observé",
        "software_fallback": "réussie avec décodage logiciel",
        "failed": "échec",
        "pending": "non déterminée",
    }[video_status]
    summary = [
        "------------------------------------------------------------",
        "OPENHTPC — Résultat du test",
        "------------------------------------------------------------",
        f"Lecture vidéo : {video_label}",
        f"Profil : {runtime_profile}",
        f"Codec : {codec or 'non observé'}",
        f"Résolution : {resolution or 'non observée'}",
        f"Catégorie source : {source_category or 'non observée'}",
        f"Décodage demandé : {hwdec_requested or 'pending'}",
        f"Décodage observé : {hwdec_observed or 'pending'}",
        f"Renderer demandé : {renderer_requested or 'pending'}",
        f"Renderer observé : {renderer_observed or 'pending'}",
        f"VO : {vo_observed or 'non observé'}",
        f"Format vidéo : {output_format or 'non observé'}",
        f"GPU : {gpu_observed or 'non observé'}",
    ]
    if fallback_reason:
        summary.append(f"Fallback : {fallback_reason}")
    summary.extend(
        (
            f"Erreurs importantes : {len(errors)}",
            f"Audio backend : {audio_backend or 'non observé'}",
            "Audio audible : non confirmé",
            "Fluidité visuelle : non confirmée automatiquement",
            "------------------------------------------------------------",
        )
    )
    text_path.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(text_path.read_text(encoding="utf-8"), end="")
    print(f"Résumé JSON : {json_path}")
    print(f"Résumé texte : {text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
