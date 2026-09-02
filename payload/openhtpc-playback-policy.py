#!/usr/bin/env python3
"""Persistent playback preferences and deterministic MPV track policy.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import datetime
import time
from typing import Any, Callable

DEFAULTS = {
    "presentation_mode": "PURE",
    "audio_language_policy": "AUTO",
    "audio_output_mode": "PCM",
    "subtitle_policy": "AUTO",
}
VALID = {
    "presentation_mode": {"PURE", "CINEMA_AUTO"},
    "audio_language_policy": {"AUTO", "FR", "DEFAULT"},
    "audio_output_mode": {"PCM", "BITSTREAM"},
    "subtitle_policy": {"AUTO", "OFF", "FR_FORCED", "FR_FULL"},
}
FR_LANGS = {"fr", "fra", "fre"}


def config_path(home: pathlib.Path) -> pathlib.Path:
    return home / ".config/openhtpc/user-config.json"


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
    requested = output.get("requested", "PCM")
    spdif_active = bool(re.search(r"AO:\s*\[[^]]+\].*\bspdif[-:]|\baudio format:\s*spdif", raw_log, re.I))
    unavailable = bool(re.search(r"(?:spdif|passthrough).*(?:not supported|unsupported|failed|unavailable)", raw_log, re.I))
    ao_match = re.search(r"AO:\s*\[([^]]+)\]", raw_log)
    passthrough = "ACTIVE" if spdif_active else "UNAVAILABLE" if requested == "BITSTREAM" and unavailable else "INACTIVE" if ao_match else "UNKNOWN"
    device_match = re.search(r"(?:audio-device|device)\s*[=:]\s*([^\s,]+)", raw_log, re.I)
    value = {"schema": 1, "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "requested": requested, "source_codec": output.get("source_codec", "UNKNOWN"),
             "resolved": "BITSTREAM" if spdif_active else "PCM" if ao_match else "UNKNOWN", "reason": output.get("reason"),
             "passthrough": passthrough, "audio_spdif": output.get("audio_spdif", "none"),
             "ao": ao_match.group(1) if ao_match else "UNKNOWN",
             "audio_device": device_match.group(1) if device_match else "DEFAULT"}
    _atomic_json(home / ".local/state/openhtpc/audio-policy-last.json", value)
    return value


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


def parse_wpctl_sink(inspect_text: str) -> dict[str, Any]:
    """Parse output from `wpctl inspect <target>` dynamically."""
    if not inspect_text:
        return {}
    id_match = re.search(r"\bid\s+(\d+)", inspect_text, re.I)
    sink_id = int(id_match.group(1)) if id_match else None
    props: dict[str, str] = {}
    for line in inspect_text.splitlines():
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


def inspect_sink(target: str = "@DEFAULT_AUDIO_SINK@", *, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    try:
        proc = runner(["wpctl", "inspect", target], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if getattr(proc, "returncode", 1) != 0:
            return {}
        stdout = getattr(proc, "stdout", "") or ""
        return parse_wpctl_sink(stdout)
    except (OSError, ValueError, TypeError):
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
    runner: Callable[..., Any] = subprocess.run,
    finder: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Inspect and prepare PipeWire HDMI sink for bitstream HD passthrough if required."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sink = inspect_sink(sink_target, runner=runner)
    sink_id = sink.get("id")
    sink_name = sink.get("name")
    sink_desc = sink.get("description")
    sink_profile = sink.get("profile")
    sink_media_class = sink.get("media_class")
    is_hdmi = bool(sink.get("is_hdmi", False))
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
            optical_state: dict | None = None) -> dict:
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
    return {"presentation": presentation, "audio": audio, "audio_output": audio_output, "subtitle": subtitle,
            "mpv_args": [*audio["mpv_args"], *audio_output["mpv_args"], *subtitle["mpv_args"]], "kind": kind}


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
    args = parser.parse_args()
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
