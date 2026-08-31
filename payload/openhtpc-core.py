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
    capability_authority,protected_contribution=protected_optical_capability_projection(home,install,registry,protected)
    decision_authority,protected_decision=protected_optical_playback_decision_projection(home,install,registry,optical,protected)
    presentation_authority,presentation=optical_presentation_descriptor(home,install,registry,optical)
    ui_authority,ui_contribution=protected_optical_ui_contribution(home,install,registry,presentation,protected_decision)
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
        "PROTECTED_OPTICAL_CAPABILITY": protected_contribution,
        "PROTECTED_OPTICAL_CAPABILITY_AUTHORITY": capability_authority,
        "PROTECTED_OPTICAL_PLAYBACK_DECISION": protected_decision,
        "PROTECTED_OPTICAL_PLAYBACK_DECISION_AUTHORITY": decision_authority,
        "PROTECTED_OPTICAL_PRESENTATION": presentation,
        "PROTECTED_OPTICAL_PRESENTATION_AUTHORITY": presentation_authority,
        "PROTECTED_OPTICAL_UI_CONTRIBUTION": ui_contribution,
        "PROTECTED_OPTICAL_UI_CONTRIBUTION_AUTHORITY": ui_authority,
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
PROTECTED_CAPABILITY_STATES={"AVAILABLE","NOT_CONFIGURED","NOT_AVAILABLE","BLOCKED"}
PROTECTED_PLAYBACK_REASONS={"MEDIA_NOT_PLAYABLE","PROTECTION_UNKNOWN","UNPROTECTED_MEDIA","STRUCTURAL_SUPPORT_NOT_AVAILABLE",
 "PROTECTED_SUPPORT_AVAILABLE","PROTECTED_SUPPORT_NOT_CONFIGURED","PROTECTED_SUPPORT_NOT_AVAILABLE","PROTECTED_SUPPORT_BLOCKED",
 "PROTECTION_STATE_INVALID"}
OPTICAL_UI_ITEM_KINDS={"NONE","OPTICAL_PLAYBACK"}
OPTICAL_UI_ACTION_INTENTS={"NONE","PLAY_CURRENT_OPTICAL_MEDIA"}

def _canonical_optical_state(value:dict[str,Any]|None)->str:
    value=value if isinstance(value,dict) else {};canonical=value.get("canonical_state")
    if canonical:return canonical
    return {"DVD":"DVD_VIDEO","BLURAY":"BLURAY_VIDEO","UHD":"UHD_BLURAY_VIDEO","EMPTY":"DRIVE_PRESENT_NO_MEDIA",
            "NO_DRIVE":"NO_OPTICAL_DRIVE","UNKNOWN_DISC":"UNKNOWN_OPTICAL_MEDIA"}.get(value.get("state"),"DETECTION_INDETERMINATE")

def core_protected_optical_playback_decision(optical:dict[str,Any]|None,snapshot:dict[str,Any]|None)->dict[str,Any]:
    """Temporary exact Core fallback for the bounded playback-decision projection."""
    optical=optical if isinstance(optical,dict) else {};canonical=_canonical_optical_state(optical);protection=optical.get("protection","UNKNOWN")
    snapshot=snapshot if isinstance(snapshot,dict) else {};support=snapshot.get("status","NOT_AVAILABLE")
    dependencies=snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"),dict) else {}
    bluray=(dependencies.get("libbluray") or {}).get("status","NOT_AVAILABLE")
    media_type={"DVD_VIDEO":"DVD","BLURAY_VIDEO":"BLURAY","BLURAY_FAMILY":"BLURAY","UHD_BLURAY_VIDEO":"UHD_BLURAY"}.get(canonical,"UNKNOWN")
    owned=canonical in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}
    if canonical=="DVD_VIDEO":enabled,reason=True,"DVD_EXISTING_PATH"
    elif not owned:enabled,reason=False,"MEDIA_NOT_PLAYABLE"
    elif protection=="UNKNOWN":enabled,reason=False,"PROTECTION_UNKNOWN"
    elif protection=="UNPROTECTED" and bluray=="AVAILABLE":enabled,reason=True,"UNPROTECTED_MEDIA"
    elif protection=="UNPROTECTED":enabled,reason=False,"STRUCTURAL_SUPPORT_NOT_AVAILABLE"
    elif protection=="PROTECTED" and support=="AVAILABLE":enabled,reason=True,"PROTECTED_SUPPORT_AVAILABLE"
    elif protection=="PROTECTED":enabled,reason=False,f"PROTECTED_SUPPORT_{support}"
    else:enabled,reason=False,"PROTECTION_STATE_INVALID"
    return {"owned":owned,"media_type":media_type,"protection":protection,"protected_media_support":support,
            "playback_action":"ENABLED" if enabled else "DISABLED","playback_reason":reason,"playable":enabled,
            "playback_provider":"core" if canonical=="DVD_VIDEO" else "protected-optical-provider"}

def _valid_protected_optical_playback_decision(value:Any)->bool:
    fields={"owned","media_type","protection","protected_media_support","playback_action","playback_reason","playable","playback_provider"}
    if not isinstance(value,dict) or set(value)!=fields or not isinstance(value.get("owned"),bool) or not isinstance(value.get("playable"),bool):return False
    if value.get("media_type") not in {"UNKNOWN","DVD","BLURAY","UHD_BLURAY"} or value.get("protection") not in {"UNKNOWN","UNPROTECTED","PROTECTED"}:return False
    if value.get("protected_media_support") not in PROTECTED_CAPABILITY_STATES or value.get("playback_action") not in {"ENABLED","DISABLED"}:return False
    if value.get("playback_reason") not in PROTECTED_PLAYBACK_REASONS|{"DVD_EXISTING_PATH"}:return False
    return value["playable"] is (value["playback_action"]=="ENABLED") and value.get("playback_provider") in {"core","protected-optical-provider"}

def protected_optical_playback_decision_projection(home:pathlib.Path,install:pathlib.Path,registry:dict[str,Any],
                                                   optical:dict[str,Any]|None,snapshot:dict[str,Any]|None)->tuple[str,dict[str,Any]]:
    """Select a declarative decision authority; Core remains enforcement authority."""
    fallback=core_protected_optical_playback_decision(optical,snapshot)
    plugin=next((item for item in registry.get("plugins",[]) if item.get("id")=="plugin.bluray"),None)
    if not plugin or plugin.get("state")!="AVAILABLE":return "CORE_FALLBACK",fallback
    loaded=plugin_registry(install).load_entrypoint(home,install,"plugin.bluray")
    try:value=loaded["module"].playback_decision(optical or {},snapshot or {}) if loaded.get("state")=="AVAILABLE" else None
    except (Exception,SystemExit):value=None
    if _valid_protected_optical_playback_decision(value) and value==fallback:return "PLUGIN_P2",value
    plugin["state"]="BROKEN";registry.setdefault("errors",[]).append({"id":"plugin.bluray","state":"BROKEN","reason":"PLUGIN_PLAYBACK_DECISION_BROKEN"})
    return "CORE_FALLBACK",fallback

def core_protected_optical_ui_contribution(presentation:dict[str,Any]|None,decision:dict[str,Any]|None)->dict[str,Any]:
    """Build declarative Blu-ray/UHD UI data without rendering or execution."""
    if not _valid_optical_presentation_descriptor(presentation) or not _valid_protected_optical_playback_decision(decision):
        return {"owned":False,"item_kind":"NONE","visible":False,"display_label":"","badge_key":"NONE","enabled":False,
                "disabled_reason":"NONE","action_intent":"NONE"}
    if not presentation["owned"] or not decision["owned"]:
        return {"owned":False,"item_kind":"NONE","visible":False,"display_label":"","badge_key":"NONE","enabled":False,
                "disabled_reason":"NONE","action_intent":"NONE"}
    enabled=decision["playback_action"]=="ENABLED"
    return {"owned":True,"item_kind":"OPTICAL_PLAYBACK","visible":True,"display_label":presentation["display_label"],
            "badge_key":presentation["badge_key"],"enabled":enabled,
            "disabled_reason":"NONE" if enabled else decision["playback_reason"],
            "action_intent":"PLAY_CURRENT_OPTICAL_MEDIA" if enabled else "NONE"}

def _valid_protected_optical_ui_contribution(value:Any)->bool:
    fields={"owned","item_kind","visible","display_label","badge_key","enabled","disabled_reason","action_intent"}
    if not isinstance(value,dict) or set(value)!=fields or not all(isinstance(value.get(key),bool) for key in ("owned","visible","enabled")):return False
    if value.get("item_kind") not in OPTICAL_UI_ITEM_KINDS or value.get("badge_key") not in OPTICAL_BADGE_KEYS or value.get("action_intent") not in OPTICAL_UI_ACTION_INTENTS:return False
    if not isinstance(value.get("display_label"),str) or value.get("disabled_reason") not in PROTECTED_PLAYBACK_REASONS|{"NONE"}:return False
    if not value["owned"]:return value==core_protected_optical_ui_contribution(None,None)
    if not value["visible"] or value["item_kind"]!="OPTICAL_PLAYBACK" or value["badge_key"]=="NONE" or not value["display_label"]:return False
    return ((value["enabled"] and value["action_intent"]=="PLAY_CURRENT_OPTICAL_MEDIA" and value["disabled_reason"]=="NONE") or
            (not value["enabled"] and value["action_intent"]=="NONE" and value["disabled_reason"]!="NONE"))

def protected_optical_ui_contribution(home:pathlib.Path,install:pathlib.Path,registry:dict[str,Any],
                                      presentation:dict[str,Any]|None,decision:dict[str,Any]|None)->tuple[str,dict[str,Any]]:
    """Select declarative UI authority; Core alone secures and renders it."""
    fallback=core_protected_optical_ui_contribution(presentation,decision)
    plugin=next((item for item in registry.get("plugins",[]) if item.get("id")=="plugin.bluray"),None)
    if (not _valid_optical_presentation_descriptor(presentation) or not _valid_protected_optical_playback_decision(decision) or
            not plugin or plugin.get("state")!="AVAILABLE"):return "CORE_FALLBACK",fallback
    loaded=plugin_registry(install).load_entrypoint(home,install,"plugin.bluray")
    try:value=loaded["module"].ui_contribution(presentation,decision) if loaded.get("state")=="AVAILABLE" else None
    except (Exception,SystemExit):value=None
    if _valid_protected_optical_ui_contribution(value) and value==fallback:return "PLUGIN_P2",value
    plugin["state"]="BROKEN";registry.setdefault("errors",[]).append({"id":"plugin.bluray","state":"BROKEN","reason":"PLUGIN_UI_CONTRIBUTION_BROKEN"})
    return "CORE_FALLBACK",fallback

def core_protected_optical_capability(snapshot:dict[str,Any]|None)->dict[str,Any]:
    """Project a Core-generated provider snapshot into the bounded P2 contract."""
    snapshot=snapshot if isinstance(snapshot,dict) else {};raw=snapshot.get("status")
    status=("NOT_AVAILABLE" if not snapshot else raw if raw in PROTECTED_CAPABILITY_STATES else "BLOCKED")
    dependencies=snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"),dict) else {}
    dependency_states={name:(dependencies.get(name) or {}).get("status","NOT_AVAILABLE") for name in ("libbluray","libaacs","libbdplus")}
    key_database=snapshot.get("external_key_database") if isinstance(snapshot.get("external_key_database"),dict) else {}
    ready=status=="AVAILABLE"
    return {"capability_id":"PROTECTED_OPTICAL_SUPPORT","availability_state":status,"provider_state":status,
            "playback_capability_state":status,"available":ready,"ready_to_attempt":ready,
            "supported_media_kinds":["BLURAY","UHD_BLURAY"],"dependency_states":dependency_states,
            "external_key_database_state":key_database.get("status","NOT_CONFIGURED"),"blocking":status=="BLOCKED"}

def _valid_protected_optical_capability(value:Any)->bool:
    fields={"capability_id","availability_state","provider_state","playback_capability_state","available","ready_to_attempt",
            "supported_media_kinds","dependency_states","external_key_database_state","blocking"}
    if not isinstance(value,dict) or set(value)!=fields or value.get("capability_id")!="PROTECTED_OPTICAL_SUPPORT":return False
    status=value.get("provider_state")
    return (status in PROTECTED_CAPABILITY_STATES and value.get("availability_state")==status and value.get("playback_capability_state")==status and
            value.get("available") is (status=="AVAILABLE") and value.get("ready_to_attempt") is (status=="AVAILABLE") and
            value.get("blocking") is (status=="BLOCKED") and value.get("supported_media_kinds")==["BLURAY","UHD_BLURAY"] and
            isinstance(value.get("dependency_states"),dict) and set(value["dependency_states"])=={"libbluray","libaacs","libbdplus"} and
            all(item in PROTECTED_CAPABILITY_STATES|{"DETECTED"} for item in [*value["dependency_states"].values(),value.get("external_key_database_state")]))

def protected_optical_capability_projection(home:pathlib.Path,install:pathlib.Path,registry:dict[str,Any],snapshot:dict[str,Any]|None)->tuple[str,dict[str,Any]]:
    fallback=core_protected_optical_capability(snapshot)
    plugin=next((item for item in registry.get("plugins",[]) if item.get("id")=="plugin.bluray"),None)
    if not plugin or plugin.get("state")!="AVAILABLE":return "CORE_FALLBACK",fallback
    loaded=plugin_registry(install).load_entrypoint(home,install,"plugin.bluray")
    try:value=loaded["module"].capability_contribution(snapshot or {}) if loaded.get("state")=="AVAILABLE" else None
    except (Exception,SystemExit):value=None
    if _valid_protected_optical_capability(value) and value==fallback:return "PLUGIN_P2",value
    plugin["state"]="BROKEN";registry.setdefault("errors",[]).append({"id":"plugin.bluray","state":"BROKEN","reason":"PLUGIN_CAPABILITY_BROKEN"})
    return "CORE_FALLBACK",fallback

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
