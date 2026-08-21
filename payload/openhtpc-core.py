#!/usr/bin/env python3
"""Read-only OPENHTPC Basic capability and plugin registry model."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import ctypes.util
from typing import Any

PLUGIN_FIELDS = {
    "plugin_id", "plugin_version", "capability", "dependencies",
    "hardware_requirements", "menu_entries", "install", "verify", "remove", "doctor",
}


def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def plugin_roots(home: pathlib.Path, install: pathlib.Path) -> list[pathlib.Path]:
    return [install / "plugins", home / ".local/share/openhtpc/plugins"]


def validate_plugin(value: dict[str, Any]) -> tuple[bool, str]:
    if set(value) != PLUGIN_FIELDS:
        return False, "PLUGIN_SCHEMA_INVALID"
    if not all(isinstance(value[key], str) and value[key] for key in ("plugin_id", "plugin_version", "capability")):
        return False, "PLUGIN_IDENTITY_INVALID"
    if not value["plugin_id"].startswith("plugin."):
        return False, "PLUGIN_ID_INVALID"
    for key in ("dependencies", "hardware_requirements", "menu_entries"):
        if not isinstance(value[key], list):
            return False, "PLUGIN_SCHEMA_INVALID"
    for key in ("install", "verify", "remove", "doctor"):
        if not isinstance(value[key], str) or not value[key]:
            return False, "PLUGIN_LIFECYCLE_INVALID"
    return True, "PASS"


def installed_plugins(home: pathlib.Path, install: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
    plugins, errors, seen = [], [], set()
    for root in plugin_roots(home, install):
        if not root.is_dir():
            continue
        for manifest in sorted(root.glob("*.json")):
            value = read_json(manifest)
            valid, reason = validate_plugin(value or {})
            if not valid:
                errors.append(f"{manifest.name}:{reason}")
                continue
            if value["plugin_id"] in seen:
                errors.append(f"{manifest.name}:PLUGIN_DUPLICATE")
                continue
            seen.add(value["plugin_id"])
            plugins.append(value)
    return plugins, errors


def capability_state(home: pathlib.Path, install: pathlib.Path) -> dict[str, Any]:
    profile = read_json(home / ".config/openhtpc/profile.json") or {}
    user = read_json(home / ".config/openhtpc/user-config.json") or {}
    optical = read_json(home / ".local/state/openhtpc/optical-current.json") or {}
    runtime = profile.get("runtime") if isinstance(profile.get("runtime"), dict) else {}
    profiles = profile.get("runtime_profiles") if isinstance(profile.get("runtime_profiles"), dict) else {}
    pure = profiles.get("profiles", {}).get("PURE", {}) if isinstance(profiles.get("profiles"), dict) else {}
    pure_path = pure.get("config_path")
    sources = user.get("local_media_sources") if isinstance(user.get("local_media_sources"), list) else []
    plugins, plugin_errors = installed_plugins(home, install)
    optical_initialized = (home / ".local/state/openhtpc/optical-current.json").is_file()
    optical_state = optical.get("state", "NOT_INITIALIZED" if not optical_initialized else "NO_DRIVE")
    detected = profile.get("detected") if isinstance(profile.get("detected"), dict) else {}
    passport_optical = detected.get("optical_drives") if isinstance(detected.get("optical_drives"), list) else []
    optical_present = optical_state not in {"NO_DRIVE", "NOT_INITIALIZED"} or bool(passport_optical)
    return {
        "LOCAL_MEDIA_READY": bool(user.get("configuration_completed")) and any(pathlib.Path(p).is_dir() for p in sources if isinstance(p, str)),
        "DVD_READY": _dvd_runtime_ready(),
        "OPTICAL_DRIVE_PRESENT": optical_present,
        "OPTICAL_STATE_INITIALIZED": optical_initialized,
        "TMDB_CONFIGURED": bool((user.get("tmdb") or {}).get("configured")),
        "VIDEO_RUNTIME_READY": runtime.get("status") == "ready" and isinstance(pure_path, str) and pathlib.Path(pure_path).is_file(),
        "AUDIO_RUNTIME_READY": runtime.get("status") == "ready",
        "HARDWARE_PASSPORT_READY": profile.get("generator", {}).get("name") == "OPENHTPC Builder",
        "FLEX_READY": (install / "flex/bin/flex-launcher").is_file(),
        "MEDIA_BROWSER_READY": (install / "openhtpc-media-browser.py").is_file(),
        "AUTOSTART_READY": (home / ".config/autostart/openhtpc.desktop").is_file(),
        "PLUGIN_REGISTRY_READY": not plugin_errors,
        "DISC_MONITOR_ACTIVE": _process_active("openhtpc-optical-monitor"),
        "optical_state": optical_state,
        "plugins": plugins,
        "plugin_errors": plugin_errors,
    }


def doctor(home: pathlib.Path, install: pathlib.Path) -> tuple[str, list[str]]:
    report = health_report(home, install); checks = report["checks"]
    lines = [f"{item['label']:<25} {item['status']}" for item in checks]
    lines.extend(["", "Optional plugins:"])
    for item in report["optional"]: lines.append(f"{item['label']:<25} {item['status']}")
    lines.extend(["", f"Overall: {report['overall']}"])
    return report["overall"], lines


def _process_environment(pid: int) -> dict[str,str]:
    try:
        proc=pathlib.Path(f"/proc/{pid}"); status=(proc/"status").read_text(errors="replace")
        uid_line=next(line for line in status.splitlines() if line.startswith("Uid:"))
        if int(uid_line.split()[1]) != os.getuid(): return {}
        command=(proc/"comm").read_text().strip()
        if command != "flex-launcher": return {}
        allowed={"XDG_SESSION_TYPE","WAYLAND_DISPLAY","DISPLAY","XDG_CURRENT_DESKTOP","KDE_FULL_SESSION"}
        return {key:value for key,value in (entry.split("=",1) for entry in (proc/"environ").read_bytes().decode(errors="replace").split("\0") if "=" in entry) if key in allowed}
    except (OSError,StopIteration,ValueError): return {}


def graphical_runtime() -> dict[str,str]:
    pids=[]
    try:
        result=subprocess.run(["pgrep","-x","flex-launcher"],text=True,capture_output=True,timeout=2)
        pids=[int(value) for value in result.stdout.split()]
    except (OSError,ValueError,subprocess.TimeoutExpired): pass
    for pid in pids:
        env=_process_environment(pid)
        if env:
            kind=env.get("XDG_SESSION_TYPE") or ("wayland" if env.get("WAYLAND_DISPLAY") else "x11" if env.get("DISPLAY") else "unknown")
            desktop="KDE Plasma" if env.get("KDE_FULL_SESSION") or "KDE" in env.get("XDG_CURRENT_DESKTOP","").upper() else env.get("XDG_CURRENT_DESKTOP","Unknown")
            return {"status":"RUNNING","session":kind.capitalize(),"desktop":desktop,"pid":str(pid)}
    return {"status":"NOT_RUNNING","session":"UI runtime unavailable","desktop":"Unknown","pid":""}


def health_report(home: pathlib.Path, install: pathlib.Path) -> dict[str,Any]:
    state = capability_state(home, install)
    state_root = home / ".local/state/openhtpc"
    first_run = not any((state_root / filename).exists() for filename in ("runtime-session.json", "runtime.log", "desktop-restore.json"))
    optical_initialized = state.get("OPTICAL_STATE_INITIALIZED", (state_root / "optical-current.json").is_file())
    optical_status = "PASS" if optical_initialized else ("NOT_INITIALIZED" if first_run or not state.get("OPTICAL_DRIVE_PRESENT") else "INITIALIZING")
    checks_raw = [
        ("OPENHTPC Core", install.is_dir()),
        ("Hardware Passport", state["HARDWARE_PASSPORT_READY"]),
        ("Generated Runtime", state["VIDEO_RUNTIME_READY"] and state["AUDIO_RUNTIME_READY"]),
        ("Flex Launcher", state["FLEX_READY"]),
        ("Media Browser", state["MEDIA_BROWSER_READY"]),
        ("MPV executable", bool(shutil.which("mpv"))),
        ("DVD dispatcher", os.access(install / "openhtpc-play-dvd", os.X_OK)),
        ("File dispatcher component", os.access(install / "openhtpc-play", os.X_OK)),
        ("Canonical optical state", optical_status),
        ("Plasma optical suppression", _plasma_suppression(home)),
        ("Optical Detection", "NOT_INITIALIZED" if first_run and not optical_initialized else ("UNAVAILABLE" if not state["OPTICAL_DRIVE_PRESENT"] else "PASS")),
        ("DVD", "PASS" if state["DVD_READY"] and state["OPTICAL_DRIVE_PRESENT"] else "UNAVAILABLE"),
        ("DVD CSS", _dvdcss_status(install)),
        ("TMDb", "PASS" if state["TMDB_CONFIGURED"] else "NOT_CONFIGURED"),
        ("Autostart", state["AUTOSTART_READY"]),
        ("Plugin Registry", state["PLUGIN_REGISTRY_READY"]),
        ("Capability snapshot", "AVAILABLE" if read_json(home / ".config/openhtpc/runtime/capabilities.json") else "NOT_GENERATED"),
    ]
    runtime_lifecycle = _runtime_lifecycle(home, install)
    version=read_json(install/"version.json") or {"product":"OPENHTPC Basic V1","version":(install/"VERSION").read_text().strip() if (install/"VERSION").is_file() else "UNKNOWN","build_id":"UNKNOWN","build_date":"UNKNOWN"}
    flex_metadata = read_json(install / "flex/BUILD-METADATA.json") or {}
    sdl_runtime = ctypes.util.find_library("SDL2-2.0")
    graphics=graphical_runtime()
    checks_raw.extend([
        ("Version",version.get("version","UNKNOWN")),
        ("Build",version.get("build_id","UNKNOWN")),
        ("Build date",version.get("build_date","UNKNOWN")),
        ("Flex provenance", "PASS" if flex_metadata.get("source_revision") else "NOT_AVAILABLE"),
        ("SDL runtime", sdl_runtime or "FAIL"),
        ("Graphics session", graphics["session"]),
        ("Desktop", graphics["desktop"]),
        ("UI crash-loop", runtime_lifecycle.get("crash_loop_state", "PASS")),
        ("Recent Flex crashes", str(runtime_lifecycle.get("recent_flex_crashes", 0))),
        ("UI instances", str(runtime_lifecycle["ui_instances"])),
        ("Authoritative Flex PID",str(runtime_lifecycle.get("authoritative_flex_pid") or "NOT_RUNNING")),
        ("Unexpected Flex PIDs",",".join(str(pid) for pid in runtime_lifecycle.get("unexpected_flex_pids",[])) or "NONE"),
        ("Optical monitor instances", str(runtime_lifecycle["monitor_instances"])),
        ("Runtime ownership", runtime_lifecycle["runtime_ownership"]),
        ("Appliance state", runtime_lifecycle["appliance_state"]),
        ("Plasma Shell",_plasma_shell_status()),
        ("Desktop restore","NOT_TESTED" if first_run else runtime_lifecycle.get("desktop_restore","NOT_TESTED")),
        ("Last OPENHTPC exit","FIRST_RUN" if first_run else runtime_lifecycle.get("last_exit","UNKNOWN")),
    ])
    checks_raw.extend([
        ("Calibration map", _calibration_map_status(home, install)),
        ("Calibration current", _calibration_staleness_status(home, install)),
    ])
    checks_raw.append(
        ("Video profile", _video_profile_status(home, install)),
    )
    checks=[]; blocking=False
    for label,value in checks_raw:
        status = value if isinstance(value, str) else ("PASS" if value else "FAIL")
        checks.append({"label":label,"status":status})
        blocking |= status == "FAIL" and label != "Plasma optical suppression"
        blocking |= label == "Desktop restore" and status.startswith("FAILED")
    installed = {item["plugin_id"] for item in state["plugins"]}
    optional=[]
    for name, label in (("bluray", "Blu-ray"), ("uhd", "UHD"), ("jellyfin", "Jellyfin"), ("plex", "Plex"), ("streaming", "Streaming")):
        optional.append({"label":label,"status":"PASS" if 'plugin.'+name in installed else "NOT_INSTALLED"})
    overall = "BLOCKED" if blocking else ("READY" if state["VIDEO_RUNTIME_READY"] else "DEGRADED")
    lifecycle=_runtime_lifecycle(home,install)
    if state["OPTICAL_DRIVE_PRESENT"] and lifecycle.get("appliance_state")=="RUNNING" and lifecycle.get("monitor_instances",0)!=1: overall="DEGRADED"
    return {"schema":1,"overall":overall,"checks":checks,"optional":optional,"capabilities":state,"runtime":lifecycle,"graphics":graphics,"first_run":first_run}


def _dvdcss_status(install: pathlib.Path) -> str:
    helper = install / "openhtpc-dvd-dependencies.py"
    if not helper.is_file():
        return "NOT_CONFIGURED"
    import ctypes
    import ctypes.util
    library = ctypes.util.find_library("dvdcss")
    if not library:
        return "NOT_CONFIGURED"
    try:
        ctypes.CDLL(library)
    except OSError:
        return "FAIL"
    return "PASS"


def _dvd_runtime_ready() -> bool:
    import ctypes
    import ctypes.util
    return all(shutil.which(name) for name in ("lsdvd", "eject", "udisksctl")) and bool(ctypes.util.find_library("dvdnav"))


def _process_active(name: str) -> bool:
    try:
        return subprocess.run(["pgrep", "-x", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _runtime_lifecycle(home: pathlib.Path, install: pathlib.Path) -> dict:
    helper = install / "openhtpc-runtime.py"
    if not helper.is_file():
        return {"ui_instances": 0, "monitor_instances": 0, "runtime_ownership": "PASS", "appliance_state": "STOPPED"}
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("openhtpc_runtime_status", helper)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module.status(home, install)
    except (OSError, AttributeError, TypeError):
        return {"ui_instances": 0, "monitor_instances": 0, "runtime_ownership": "FAIL", "appliance_state": "UNKNOWN"}


def _plasma_suppression(home: pathlib.Path) -> str:
    value = read_json(home / ".local/state/openhtpc/kde-device-popup.json") or {}
    appliance = read_json(home / ".local/state/openhtpc/appliance-mode.json") or {}
    if not appliance.get("active"): return "INACTIVE"
    return "PASS" if value.get("component") == "org.kde.plasma.devicenotifier" and value.get("applied") else "FAIL"

def _plasma_shell_status()->str:
    try:
        service=subprocess.run(["systemctl","--user","is-active","plasma-plasmashell.service"],text=True,capture_output=True,timeout=3)
        process=subprocess.run(["pgrep","-x","plasmashell"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        return "PASS" if service.returncode==0 and service.stdout.strip()=="active" and process.returncode==0 else "NOT_AVAILABLE"
    except (OSError,subprocess.TimeoutExpired):return "NOT_AVAILABLE"


def default_paths() -> tuple[pathlib.Path, pathlib.Path]:
    home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    return home, pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))


# ---------------------------------------------------------------------------
# C3 Auto Calibration doctor helpers (read-only — never trigger calibration)
# ---------------------------------------------------------------------------

_CAL_MAP_SCHEMA_VERSION = 2
_CAL_METHOD_VERSION = 1


def _calibration_map_status(home: pathlib.Path, install: pathlib.Path) -> str:
    """Return CALIBRATION_OK, CALIBRATION_ABSENT, or CALIBRATION_MAP_CORRUPT."""
    map_path = home / ".local/state/openhtpc/performance_map.json"
    if not map_path.exists():
        return "CALIBRATION_ABSENT"
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != _CAL_MAP_SCHEMA_VERSION:
            return "CALIBRATION_MAP_CORRUPT"
        return "CALIBRATION_OK"
    except Exception:
        return "CALIBRATION_MAP_CORRUPT"


def _calibration_staleness_status(home: pathlib.Path, install: pathlib.Path) -> str:
    """Return CALIBRATION_CURRENT, CALIBRATION_STALE, or CALIBRATION_ABSENT."""
    map_path = home / ".local/state/openhtpc/performance_map.json"
    if not map_path.exists():
        return "CALIBRATION_ABSENT"
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != _CAL_MAP_SCHEMA_VERSION:
            return "CALIBRATION_ABSENT"
        saved_sigs = data.get("calibration_metadata", {}).get("signatures", {})
        # Check benchmark_method_version
        if saved_sigs.get("benchmark_method_version") != _CAL_METHOD_VERSION:
            return "CALIBRATION_STALE"
        # Check recipe_catalog_version against installed catalog
        catalog_path = install / "assets" / "c3_calibration_catalog.json"
        if catalog_path.exists():
            try:
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                if saved_sigs.get("recipe_catalog_version") != catalog.get("recipe_catalog_version"):
                    return "CALIBRATION_STALE"
            except Exception:
                pass
        # Check asset hashes for installed assets
        asset_dir = install / "assets" / "benchmark"
        saved_asset_versions = saved_sigs.get("benchmark_asset_version", {})
        for scope_id, saved_hash in saved_asset_versions.items():
            # Determine asset filename from catalog
            try:
                if catalog_path.exists():
                    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                    scope_def = catalog.get("scopes", {}).get(scope_id, {})
                    filename = scope_def.get("benchmark_asset_filename", "")
                    if filename:
                        asset_path_check = asset_dir / filename
                        if asset_path_check.exists():
                            import hashlib as _hl
                            current_hash = _hl.sha256(asset_path_check.read_bytes()).hexdigest()
                            if current_hash != saved_hash:
                                return "CALIBRATION_STALE"
            except Exception:
                pass
        return "CALIBRATION_CURRENT"
    except Exception:
        return "CALIBRATION_ABSENT"


def _video_profile_status(home: pathlib.Path, install: pathlib.Path) -> str:
    """Return video profile status for Doctor. Never triggers calibration."""
    profile_path = home / ".config/openhtpc/video-profile.json"
    if not profile_path.exists():
        # Fresh install — PURE is the implicit default, this is healthy
        return "PURE_DEFAULT"
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        active = data.get("active_profile", "PURE")
        if active not in {"PURE", "CINEMA_AUTO"}:
            return "PROFILE_INVALID"
        if active == "CINEMA_AUTO":
            # Check that a performance map exists
            map_path = home / ".local/state/openhtpc/performance_map.json"
            if not map_path.exists():
                return "CINEMA_AUTO_NO_MAP"
            return "CINEMA_AUTO"
        return "PURE"
    except Exception:
        return "PROFILE_UNREADABLE"


