#!/usr/bin/env python3
"""Read-only OPENHTPC Basic capability and plugin registry model."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import ctypes.util
from typing import Any

def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def capability_provenance_state(profile: dict[str, Any], snapshot: dict[str, Any] | None) -> str:
    """Compare decision provenance without treating legacy passports as current."""
    if not snapshot:
        return "SNAPSHOT_MISSING"
    source = profile.get("capability_source")
    if not isinstance(source, dict):
        return "REBUILD_REQUIRED"
    keys = ("hardware_fingerprint", "runtime_fingerprint")
    if not all(isinstance(source.get(key), str) and source.get(key) for key in keys):
        return "REBUILD_REQUIRED"
    return "CURRENT" if all(source[key] == snapshot.get(key) for key in keys) else "STALE"


def runtime_provenance_state(profile: dict[str, Any], passport_state: str) -> str:
    if passport_state != "CURRENT":
        return passport_state
    source = profile.get("runtime", {}).get("generation_provenance", {}).get("capability_source")
    return "CURRENT" if source == profile.get("capability_source") else "STALE"


def plugin_registry(install: pathlib.Path):
    path=install/"openhtpc-plugin-registry.py"
    spec=importlib.util.spec_from_file_location("openhtpc_plugin_registry",path)
    if spec is None or spec.loader is None:raise ImportError("PLUGIN_REGISTRY_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def plugin_status(home:pathlib.Path,install:pathlib.Path)->dict[str,Any]:
    try:return plugin_registry(install).registry(home,install)
    except (OSError,ImportError,AttributeError,TypeError,ValueError):
        return {"schema":2,"plugin_api":2,"plugins":[],"errors":[{"id":"core.registry","state":"BROKEN","reason":"PLUGIN_REGISTRY_UNAVAILABLE"}],"providers":{},"core_integrity":"BROKEN"}


def installed_plugins(home:pathlib.Path,install:pathlib.Path)->tuple[list[dict[str,Any]],list[str]]:
    """Compatibility view for existing Core consumers; V2 manifests contain no commands."""
    value=plugin_status(home,install)
    plugins=[{"plugin_id":item["id"],"plugin_version":item["version"],"capability":item["capabilities"],"menu_entries":[]}
             for item in value["plugins"] if item["state"]=="AVAILABLE"]
    errors=[f"{item.get('id','plugin')}:{item['reason']}" for item in value["errors"]]
    return plugins,errors


def optional_plugin_states(registry:dict[str,Any])->list[dict[str,str]]:
    plugins={item["id"]:item for item in registry.get("plugins",[]) if isinstance(item,dict) and isinstance(item.get("id"),str)}
    result=[];known=set()
    if "plugin.bluray" in plugins:
        item=plugins["plugin.bluray"];result.append({"label":"Blu-ray/UHD","status":item["state"]});known.update({"plugin.bluray","plugin.uhd"})
        optional=(("jellyfin","Jellyfin"),("plex","Plex"),("streaming","Streaming"))
    else:optional=(("bluray","Blu-ray"),("uhd","UHD"),("jellyfin","Jellyfin"),("plex","Plex"),("streaming","Streaming"))
    for name,label in optional:
        plugin_id="plugin."+name;known.add(plugin_id);item=plugins.get(plugin_id)
        result.append({"label":label,"status":item.get("state","NOT_INSTALLED") if item else "NOT_INSTALLED"})
    result.extend({"label":item["name"],"status":item["state"]} for item in sorted(plugins.values(),key=lambda value:value["id"]) if item["id"] not in known)
    return result


def capability_state(home: pathlib.Path, install: pathlib.Path) -> dict[str, Any]:
    profile = read_json(home / ".config/openhtpc/profile.json") or {}
    user = read_json(home / ".config/openhtpc/user-config.json") or {}
    optical = read_json(home / ".local/state/openhtpc/optical-current.json") or {}
    runtime = profile.get("runtime") if isinstance(profile.get("runtime"), dict) else {}
    snapshot = read_json(home / ".config/openhtpc/runtime/capabilities.json")
    protected = (snapshot or {}).get("optical", {}).get("protected_media", {})
    passport_provenance = capability_provenance_state(profile, snapshot)
    runtime_provenance = runtime_provenance_state(profile, passport_provenance)
    profiles = profile.get("runtime_profiles") if isinstance(profile.get("runtime_profiles"), dict) else {}
    pure = profiles.get("profiles", {}).get("PURE", {}) if isinstance(profiles.get("profiles"), dict) else {}
    pure_path = pure.get("config_path")
    sources = user.get("local_media_sources") if isinstance(user.get("local_media_sources"), list) else []
    registry=plugin_status(home,install);plugins,plugin_errors=installed_plugins(home,install)
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
        "HARDWARE_PASSPORT_PROVENANCE": passport_provenance,
        "VIDEO_RUNTIME_PROVENANCE": runtime_provenance,
        "FLEX_READY": (install / "flex/bin/flex-launcher").is_file(),
        "MEDIA_BROWSER_READY": (install / "openhtpc-media-browser.py").is_file(),
        "AUTOSTART_READY": (home / ".config/autostart/openhtpc.desktop").is_file(),
        "PLUGIN_REGISTRY_READY": registry.get("core_integrity")!="BROKEN",
        "PLUGIN_REGISTRY": registry,
        "DISC_MONITOR_ACTIVE": _process_active("openhtpc-optical-monitor"),
        "PROTECTED_OPTICAL_SUPPORT": protected,
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

PROTECTED_OPTICAL_DOCTOR_LABELS=("Protected optical media","libbluray","libaacs","libbdplus",
 "External key database","Protected optical playback","Optical media family","Optical exact type",
 "Optical protection","Protection mechanism","Classification source","Last protected disc attempt")
OPTICAL_PRESENTATION_KEYS={"NONE","BLURAY","BLURAY_FAMILY","UHD_BLURAY"}
OPTICAL_BADGE_KEYS={"NONE","BLURAY","UHD_BLURAY"}

def core_optical_presentation_descriptor(optical:dict[str,Any]|None)->dict[str,Any]:
    """Temporary Core fallback for Blu-ray/UHD presentation selection."""
    optical=optical if isinstance(optical,dict) else {};canonical=optical.get("canonical_state","UNKNOWN")
    if canonical=="BLURAY_VIDEO":return {"owned":True,"presentation_key":"BLURAY","badge_key":"BLURAY","display_label":"BLU-RAY","media_kind":"BLURAY"}
    if canonical=="BLURAY_FAMILY":return {"owned":True,"presentation_key":"BLURAY_FAMILY","badge_key":"BLURAY","display_label":"BLU-RAY / UHD","media_kind":"BLURAY"}
    if canonical=="UHD_BLURAY_VIDEO":return {"owned":True,"presentation_key":"UHD_BLURAY","badge_key":"UHD_BLURAY","display_label":"ULTRA HD BLU-RAY 4K","media_kind":"BLURAY"}
    return {"owned":False,"presentation_key":"NONE","badge_key":"NONE","display_label":"","media_kind":"NONE"}

def _valid_optical_presentation_descriptor(value:Any)->bool:
    return (isinstance(value,dict) and set(value)=={"owned","presentation_key","badge_key","display_label","media_kind"} and
            isinstance(value.get("owned"),bool) and value.get("presentation_key") in OPTICAL_PRESENTATION_KEYS and
            value.get("badge_key") in OPTICAL_BADGE_KEYS and isinstance(value.get("display_label"),str) and
            value.get("media_kind") in {"NONE","BLURAY"} and
            ((value["owned"] and value["badge_key"]!="NONE" and value["media_kind"]=="BLURAY" and bool(value["display_label"])) or
             (not value["owned"] and value==core_optical_presentation_descriptor({}))))

def optical_presentation_descriptor(home:pathlib.Path,install:pathlib.Path,registry:dict[str,Any],optical:dict[str,Any]|None)->tuple[str,dict[str,Any]]:
    """Select one declarative presentation authority with exact Core fallback."""
    fallback=core_optical_presentation_descriptor(optical)
    plugin=next((item for item in registry.get("plugins",[]) if item.get("id")=="plugin.bluray"),None)
    if not plugin or plugin.get("state")!="AVAILABLE":return "CORE_FALLBACK",fallback
    loaded=plugin_registry(install).load_entrypoint(home,install,"plugin.bluray")
    try:value=loaded["module"].presentation_descriptor(optical or {}) if loaded.get("state")=="AVAILABLE" else None
    except (Exception,SystemExit):value=None
    if _valid_optical_presentation_descriptor(value) and value==fallback:return "PLUGIN_P2",value
    plugin["state"]="BROKEN";registry.setdefault("errors",[]).append({"id":"plugin.bluray","state":"BROKEN","reason":"PLUGIN_PRESENTATION_BROKEN"})
    return "CORE_FALLBACK",fallback

def core_protected_optical_doctor_rows(inputs:dict[str,Any])->list[dict[str,Any]]:
    """Temporary Core fallback for the media-specific Doctor presentation."""
    protected=inputs.get("protected") if isinstance(inputs.get("protected"),dict) else {}
    dependencies=protected.get("dependencies") if isinstance(protected.get("dependencies"),dict) else {}
    key_database=protected.get("external_key_database") if isinstance(protected.get("external_key_database"),dict) else {}
    rows=[
        {"label":"Protected optical media","status":protected.get("status","NOT_CONFIGURED"),"blocking":protected.get("status")=="BLOCKED"},
        {"label":"libbluray","status":(dependencies.get("libbluray") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
        {"label":"libaacs","status":(dependencies.get("libaacs") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
        {"label":"libbdplus","status":(dependencies.get("libbdplus") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
        {"label":"External key database","status":key_database.get("status","NOT_CONFIGURED"),"blocking":False},
        {"label":"Protected optical playback","status":"ENABLED" if protected.get("status")=="AVAILABLE" else "DISABLED","blocking":False},
    ]
    optical=inputs.get("optical") if isinstance(inputs.get("optical"),dict) else {};canonical=optical.get("canonical_state","UNKNOWN")
    if canonical in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
        rows.extend([
            {"label":"Optical media family","status":"BLURAY","blocking":False},
            {"label":"Optical exact type","status":{"BLURAY_VIDEO":"BLURAY","UHD_BLURAY_VIDEO":"UHD_BLURAY"}.get(canonical,"UNKNOWN"),"blocking":False},
            {"label":"Optical protection","status":optical.get("protection","UNKNOWN"),"blocking":False},
            {"label":"Protection mechanism","status":"+".join(optical.get("protection_mechanisms") or ["UNKNOWN"]),"blocking":False},
            {"label":"Classification source","status":optical.get("classification_source","UNKNOWN"),"blocking":False},
        ])
    attempt=inputs.get("last_attempt")
    if isinstance(attempt,dict):rows.append({"label":"Last protected disc attempt","status":attempt.get("status","UNKNOWN"),"blocking":False})
    return rows

def _valid_protected_optical_doctor_rows(rows:Any)->bool:
    if not isinstance(rows,list) or len(rows)!=len({row.get("label") for row in rows if isinstance(row,dict)}):return False
    allowed=set(PROTECTED_OPTICAL_DOCTOR_LABELS)
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"label","status","blocking"} or row.get("label") not in allowed or not isinstance(row.get("status"),str):return False
        expected=row["label"]=="Protected optical media" and row["status"]=="BLOCKED"
        if row.get("blocking") is not expected:return False
    return True

def protected_optical_doctor_projection(home:pathlib.Path,install:pathlib.Path,registry:dict[str,Any],inputs:dict[str,Any])->tuple[str,list[dict[str,Any]]]:
    """Select one Doctor authority; optional plugin failures always fall back."""
    plugin=next((item for item in registry.get("plugins",[]) if item.get("id")=="plugin.bluray"),None)
    if not plugin or plugin.get("state")!="AVAILABLE":return "CORE_FALLBACK",core_protected_optical_doctor_rows(inputs)
    loaded=plugin_registry(install).load_entrypoint(home,install,"plugin.bluray")
    try:rows=loaded["module"].doctor_rows(inputs) if loaded.get("state")=="AVAILABLE" else None
    except (Exception,SystemExit):rows=None
    fallback=core_protected_optical_doctor_rows(inputs)
    if _valid_protected_optical_doctor_rows(rows) and rows==fallback:return "PLUGIN_P2",rows
    plugin["state"]="BROKEN";registry.setdefault("errors",[]).append({"id":"plugin.bluray","state":"BROKEN","reason":"PLUGIN_DOCTOR_BROKEN"})
    return "CORE_FALLBACK",fallback


def health_report(home: pathlib.Path, install: pathlib.Path) -> dict[str,Any]:
    state = capability_state(home, install)
    state_root = home / ".local/state/openhtpc"
    first_run = not any((state_root / filename).exists() for filename in ("runtime-session.json", "runtime.log", "desktop-restore.json"))
    optical_initialized = state.get("OPTICAL_STATE_INITIALIZED", (state_root / "optical-current.json").is_file())
    optical_status = "PASS" if optical_initialized else ("NOT_INITIALIZED" if first_run or not state.get("OPTICAL_DRIVE_PRESENT") else "INITIALIZING")
    checks_raw = [
        ("OPENHTPC Core", install.is_dir()),
        ("Hardware Passport", state["HARDWARE_PASSPORT_PROVENANCE"] if state["HARDWARE_PASSPORT_READY"] and state["HARDWARE_PASSPORT_PROVENANCE"] != "CURRENT" else state["HARDWARE_PASSPORT_READY"]),
        ("Generated Runtime", state["VIDEO_RUNTIME_PROVENANCE"] if state["VIDEO_RUNTIME_READY"] and state["VIDEO_RUNTIME_PROVENANCE"] != "CURRENT" else state["VIDEO_RUNTIME_READY"] and state["AUDIO_RUNTIME_READY"]),
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
        ("Plugin API", str(state.get("PLUGIN_REGISTRY",{}).get("plugin_api",2))),
        ("Plugin diagnostics", (state.get("PLUGIN_REGISTRY",{}).get("errors") or [{"reason":"PASS"}])[0]["reason"]),
        ("Capability snapshot", "AVAILABLE" if read_json(home / ".config/openhtpc/runtime/capabilities.json") else "NOT_GENERATED"),
    ]
    protected = state.get("PROTECTED_OPTICAL_SUPPORT") or {}
    optical_disc = read_json(state_root / "optical-current.json") or {}
    last_protected_attempt = read_json(state_root / "protected-optical-last-attempt.json")
    doctor_authority,doctor_rows=protected_optical_doctor_projection(home,install,state.get("PLUGIN_REGISTRY",{}),
        {"protected":protected,"optical":optical_disc,"last_attempt":last_protected_attempt})
    checks_raw.extend((row["label"],row["status"]) for row in doctor_rows)
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
        blocking |= status in {"FAIL", "STALE", "REBUILD_REQUIRED"} and label != "Plasma optical suppression"
        blocking |= label == "Desktop restore" and status.startswith("FAILED")
        blocking |= label == "Protected optical media" and status == "BLOCKED"
    optional=optional_plugin_states(state.get("PLUGIN_REGISTRY",{}))
    overall = "BLOCKED" if blocking else ("READY" if state["VIDEO_RUNTIME_READY"] else "DEGRADED")
    lifecycle=_runtime_lifecycle(home,install)
    if state["OPTICAL_DRIVE_PRESENT"] and lifecycle.get("appliance_state")=="RUNNING" and lifecycle.get("monitor_instances",0)!=1: overall="DEGRADED"
    return {"schema":1,"overall":overall,"checks":checks,"optional":optional,"capabilities":state,"runtime":lifecycle,"graphics":graphics,"first_run":first_run,"protected_optical_doctor_authority":doctor_authority}


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
