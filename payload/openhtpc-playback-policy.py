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

DEFAULTS = {
    "presentation_mode": "PURE",
    "audio_language_policy": "AUTO",
    "subtitle_policy": "AUTO",
}
VALID = {
    "presentation_mode": {"PURE", "CINEMA_AUTO"},
    "audio_language_policy": {"AUTO", "FR", "DEFAULT"},
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


def probe_media(path: pathlib.Path, ffprobe: str | None = None) -> dict | None:
    binary = ffprobe or shutil.which("ffprobe")
    if not binary: return None
    try:
        result = subprocess.run([binary, "-v", "error", "-show_streams", "-of", "json", "--", str(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False)
        value = json.loads(result.stdout) if result.returncode == 0 else None
        return value if isinstance(value, dict) and isinstance(value.get("streams"), list) else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def resolve(home: pathlib.Path, media: pathlib.Path | None = None, kind: str = "local", probe: dict | None = None) -> dict:
    prefs = read_preferences(home)
    if probe is None and media is not None: probe = probe_media(media)
    requested = prefs["presentation_mode"]
    presentation = {"requested": requested, "resolved": "PURE", "reason": "requested_pure" if requested == "PURE" else "no_qualified_local_auto_scope"}
    audio = choose_audio(prefs["audio_language_policy"], probe)
    subtitle = choose_subtitle(prefs["subtitle_policy"], probe)
    return {"presentation": presentation, "audio": audio, "subtitle": subtitle, "mpv_args": [*audio["mpv_args"], *subtitle["mpv_args"]], "kind": kind}


def osd_text(decision: dict) -> str:
    p = decision["presentation"]; a = decision["audio"]; s = decision["subtitle"]
    mode = "CINÉMA AUTO → " + p["resolved"] if p["requested"] == "CINEMA_AUTO" else p["resolved"]
    audio = "Français" if a["resolved"].startswith("AID_") and a["requested"] == "FR" else "Piste par défaut" if a["requested"] == "DEFAULT" else "Auto"
    if s["requested"] == "OFF": subtitles = "Désactivés"
    elif s["resolved"] == "NONE": subtitles = "Aucun"
    elif s["requested"] == "FR_FORCED": subtitles = "Français forcés"
    elif s["requested"] == "FR_FULL": subtitles = "Français"
    else: subtitles = "Auto"
    # Pass literal newlines as one argv value.  MPV's osd-playing-msg parser
    # treats a literal ``\N`` as an invalid property-expansion escape.
    return f"OPENHTPC\nMode vidéo : {mode}\nAudio : {audio}\nSous-titres : {subtitles}"


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--home", type=pathlib.Path, default=pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("get")
    setter = sub.add_parser("set"); setter.add_argument("key", choices=sorted(VALID)); setter.add_argument("value")
    resolver = sub.add_parser("resolve"); resolver.add_argument("--media", type=pathlib.Path); resolver.add_argument("--kind", choices=("local", "dvd"), default="local")
    args = parser.parse_args()
    if args.command == "get": print(json.dumps(read_preferences(args.home), ensure_ascii=False, sort_keys=True)); return 0
    if args.command == "set":
        try: result = write_preference(args.home, args.key, args.value.upper())
        except ValueError: return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0
    result = resolve(args.home, args.media, args.kind); result["osd"] = osd_text(result); print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
