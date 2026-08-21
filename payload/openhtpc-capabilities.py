#!/usr/bin/env python3
"""Canonical, read-only OPENHTPC system capability engine."""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

SCHEMA = 1
PROBE_VERSION = "1.1-phase-a-3"
STATES = {"SUPPORTED", "UNSUPPORTED", "AVAILABLE", "UNAVAILABLE", "DETECTED", "VALIDATED", "UNVALIDATED", "UNKNOWN", "ACTIVE", "INACTIVE", "NOT_APPLICABLE", "NOT_RUN", "NOT_EVALUATED"}
Runner = Callable[[list[str], float], dict[str, Any]]


def fact(status: str, evidence: list[str] | None = None, validated: bool = False, **details: Any) -> dict[str, Any]:
    if status not in STATES:
        raise ValueError(f"invalid capability state: {status}")
    return {"status": status, "evidence": sorted(set(evidence or [])), "validated": bool(validated), **details}


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def default_runner(argv: list[str], timeout: float = 5.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
        return {"status": "OK" if result.returncode == 0 else "FAILED", "returncode": result.returncode,
                "stdout": result.stdout[:131072], "stderr": result.stderr[:8192],
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except FileNotFoundError:
        return {"status": "COMMAND_UNAVAILABLE", "returncode": None, "stdout": "", "stderr": "", "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"status": "TIMEOUT", "returncode": None, "stdout": (exc.stdout or "")[:131072] if isinstance(exc.stdout, str) else "",
                "stderr": "probe timeout", "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except OSError as exc:
        return {"status": "FAILED", "returncode": None, "stdout": "", "stderr": str(exc)[:512], "elapsed_ms": round((time.monotonic() - started) * 1000)}


def run_probe(name: str, argv: list[str], diagnostics: dict[str, Any], runner: Runner, timeout: float = 5.0) -> dict[str, Any]:
    result = runner(argv, timeout)
    diagnostics[name] = {key: result.get(key) for key in ("status", "returncode", "elapsed_ms")}
    if result.get("status") not in {"OK", "COMMAND_UNAVAILABLE"}:
        diagnostics[name]["error_class"] = "PROBE_TIMEOUT" if result.get("status") == "TIMEOUT" else "PROBE_FAILED"
        diagnostics[name]["message"] = str(result.get("stderr", ""))[:240].replace("\n", " ")
    return result


GRAPHICAL_KEYS = ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "KDE_FULL_SESSION")


def _safe_graphical_environment(values: dict[str, str], uid: int) -> dict[str, str]:
    runtime = f"/run/user/{uid}"
    result: dict[str, str] = {}
    if values.get("XDG_RUNTIME_DIR") == runtime: result["XDG_RUNTIME_DIR"] = runtime
    bus = values.get("DBUS_SESSION_BUS_ADDRESS", "")
    if bus in {f"unix:path={runtime}/bus", f"unix:path={runtime}/bus,guid="} or bus.startswith(f"unix:path={runtime}/bus,guid="):
        result["DBUS_SESSION_BUS_ADDRESS"] = bus
    wayland = values.get("WAYLAND_DISPLAY", "")
    if re.fullmatch(r"wayland-[0-9]+", wayland): result["WAYLAND_DISPLAY"] = wayland
    display = values.get("DISPLAY", "")
    if re.fullmatch(r":[0-9]+(?:\.[0-9]+)?", display): result["DISPLAY"] = display
    session_type=values.get("XDG_SESSION_TYPE","").lower()
    if session_type in {"wayland","x11"}:result["XDG_SESSION_TYPE"]=session_type
    for key in ("XDG_CURRENT_DESKTOP", "KDE_FULL_SESSION"):
        value=values.get(key,"")
        if value and len(value)<128 and not re.search(r"[\x00\r\n]",value):result[key]=value
    return result if "DBUS_SESSION_BUS_ADDRESS" in result and ("WAYLAND_DISPLAY" in result or "DISPLAY" in result) else {}


def _process_context(process: pathlib.Path, uid: int) -> tuple[str, list[str], dict[str, str]] | None:
    """Return only non-sensitive identity and graphical environment for a same-UID process."""
    try:
        status=(process/"status").read_text(errors="replace")
        uid_line=next(line for line in status.splitlines() if line.startswith("Uid:"))
        if int(uid_line.split()[1]) != uid:return None
        name=(process/"comm").read_text(errors="replace").strip()
        command=[item.decode(errors="replace") for item in (process/"cmdline").read_bytes().split(b"\0") if item]
        raw=(process/"environ").read_bytes().decode(errors="replace").split("\0")
        values={key:value for key,value in (entry.split("=",1) for entry in raw if "=" in entry) if key in GRAPHICAL_KEYS}
        safe=_safe_graphical_environment(values,uid)
        return (name,command,safe) if safe else None
    except (OSError,StopIteration,ValueError):return None


def resolve_graphical_context(proc_root: pathlib.Path = pathlib.Path("/proc"), uid: int | None = None,
                              environment: dict[str, str] | None = None, home: pathlib.Path | None = None,
                              install: pathlib.Path | None = None) -> dict[str, Any]:
    """Resolve the active same-user graphical session without mutating it."""
    uid=os.getuid() if uid is None else uid
    current=_safe_graphical_environment(dict(os.environ if environment is None else environment),uid)
    if current:return {"status":"RESOLVED","evidence":"CALLER_ENVIRONMENT","environment":current}
    home=pathlib.Path.home() if home is None else home
    install=home/".local/lib/openhtpc" if install is None else install
    session=read_json(home/".local/state/openhtpc/runtime-session.json")
    if session.get("state")=="RUNNING":
        owned=(("OPENHTPC_CONTROLLER",session.get("owner_pid"),(str(install/"openhtpc-home.py"),str(install/"openhtpc-session-start"))),
               ("AUTHORITATIVE_FLEX",session.get("authoritative_flex_pid"),(str(install/"flex/bin/flex-launcher"),)))
        for evidence,pid,markers in owned:
            if not isinstance(pid,int) or pid<=1:continue
            context=_process_context(proc_root/str(pid),uid)
            if context and any(marker in context[1] for marker in markers):
                return {"status":"RESOLVED","evidence":evidence,"environment":context[2]}
    candidates=[]
    try:entries=[item for item in proc_root.iterdir() if item.name.isdigit()]
    except OSError:entries=[]
    priority={"kwin_wayland":0,"plasmashell":1,"startplasma-wayland":2}
    for process in entries:
        context=_process_context(process,uid)
        if not context or context[0] not in priority:continue
        candidates.append((priority[context[0]],-int(process.name),context[0],context[2]))
    if not candidates:return {"status":"UNAVAILABLE","evidence":"NONE","environment":{}}
    _,_,name,safe=sorted(candidates)[0]
    return {"status":"RESOLVED","evidence":name.upper(),"environment":safe}


def parse_lspci(text: str) -> list[dict[str, Any]]:
    devices, current = [], None
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F:.]+)\s+([^:]+):\s+(.+?)(?:\s+\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\])?$", line)
        if match and any(kind in match.group(2).lower() for kind in ("vga", "3d controller", "display controller")):
            identity = re.search(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line)
            model = re.sub(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\](?:\s*\(rev [^)]+\))?\s*$", "", match.group(3)).strip()
            current = {"pci_address": match.group(1), "class": match.group(2), "model": model,
                       "vendor_id": identity.group(1) if identity else match.group(4), "device_id": identity.group(2) if identity else match.group(5), "kernel_driver": None,
                       "drm_nodes": [], "render_nodes": [], "active": None, "memory_type": "UNKNOWN"}
            lower = current["model"].lower()
            current["vendor"] = "Intel" if "intel" in lower else "AMD" if "amd" in lower or "advanced micro" in lower else "NVIDIA" if "nvidia" in lower else "Unknown"
            devices.append(current)
        elif current and line.startswith("\tKernel driver in use:"):
            current["kernel_driver"] = line.split(":", 1)[1].strip()
    return devices


def gpu_sysfs(devices: list[dict[str, Any]], sys_root: pathlib.Path) -> None:
    drm = sys_root / "class/drm"
    if not drm.is_dir():
        return
    for card in sorted(item for item in drm.iterdir() if re.fullmatch(r"card[0-9]+", item.name)):
        try:
            address = (card / "device").resolve().name
        except OSError:
            continue
        match = next((item for item in devices if item.get("pci_address", "").endswith(address)), None)
        if not match:
            match = {"pci_address": address, "class": "graphics", "model": "Unknown graphics device", "vendor": "Unknown", "vendor_id": None,
                     "device_id": None, "kernel_driver": None, "drm_nodes": [], "render_nodes": [], "active": None, "memory_type": "UNKNOWN"}
            devices.append(match)
        match["drm_nodes"].append(card.name)
        render = sorted((card / "device/drm").glob("renderD*"))
        match["render_nodes"].extend(f"/dev/dri/{item.name}" for item in render)
        driver = card / "device/driver"
        if driver.exists():
            try: match["kernel_driver"] = driver.resolve().name
            except OSError: pass
        if match.get("vendor") in {"Intel", "AMD"} and not any(key in match.get("model", "").lower() for key in ("arc", "radeon rx", "firepro")):
            match["memory_type"] = "shared"


def parse_vulkan(text: str) -> list[dict[str, Any]]:
    devices, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"GPU[0-9]+:", line) or line.startswith("VkPhysicalDeviceProperties"):
            if current and any(current.values()): devices.append(current)
            current = {}
        if current is None: current = {}
        for key, output in (("deviceName", "name"), ("apiVersion", "api_version"), ("driverName", "driver_name"), ("driverInfo", "driver_version"), ("deviceType", "device_type")):
            match = re.search(rf"\b{key}\s*=\s*(.+)$", line)
            if match: current[output] = match.group(1).strip()
    if current and any(current.values()): devices.append(current)
    return devices


CODECS = {
    "mpeg2": ("mpeg2video", ("VAProfileMPEG2",)),
    "h264_8bit": ("h264", ("VAProfileH264",)),
    "hevc_main": ("hevc", ("VAProfileHEVCMain ", "VAProfileHEVCMain:")),
    "hevc_main10": ("hevc", ("VAProfileHEVCMain10",)),
    "vp9_profile0": ("vp9", ("VAProfileVP9Profile0",)),
    "vp9_10bit": ("vp9", ("VAProfileVP9Profile2",)),
    "av1_main": ("av1", ("VAProfileAV1Profile0",)),
}


def parse_vaapi(text: str) -> tuple[str | None, dict[str, bool]]:
    driver = None
    match = re.search(r"Driver version:\s*(.+)", text)
    if match: driver = match.group(1).strip()
    return driver, {key: any(token in text and re.search(re.escape(token) + r".*VAEntrypointVLD", text) for token in tokens) for key, (_, tokens) in CODECS.items()}


def parse_ffmpeg_decoders(text: str) -> set[str]:
    return {match.group(1) for line in text.splitlines() if (match := re.match(r"^\s*[VAS\.FBD]{6}\s+([a-zA-Z0-9_]+)\s", line))}


def parse_kscreen(text: str) -> list[dict[str, Any]]:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    displays = []
    for block in re.split(r"(?=Output:\s*\d+\s+)", text):
        first = re.search(r"Output:\s*\d+\s+([^\s]+)", block, re.I)
        if not first: continue
        active = bool(re.search(r"^\s*enabled\s*$", block, re.I|re.M)); connected = bool(re.search(r"^\s*connected\s*$", block, re.I|re.M))
        display = {"connector": first.group(1), "active": active, "connected": connected,
                   "current_mode": None, "available_modes": [], "physical_size_mm": None, "hdr_capable": fact("UNKNOWN", ["DRM"]), "current_hdr_mode": fact("UNKNOWN", ["KDE"])}
        geometry = re.search(r"Geometry:\s*\d+,\d+\s+(\d+)x(\d+)", block)
        modes = re.search(r"Modes:\s*(.+)", block)
        if geometry: display["logical_geometry"] = {"width": int(geometry.group(1)), "height": int(geometry.group(2))}
        if modes:
            for width, height, refresh, flags in re.findall(r"\d+:(\d+)x(\d+)@(\d+(?:\.\d+)?)([^\s]*)", modes.group(1)):
                mode = {"width": int(width), "height": int(height), "refresh_hz": float(refresh)}
                display["available_modes"].append(mode)
                if "*" in flags: display["current_mode"] = {**mode, "evidence": ["KDE"]}
        size = re.search(r"Physical size:\s*(\d+)x(\d+)\s*mm", block)
        if size: display["physical_size_mm"] = {"width": int(size.group(1)), "height": int(size.group(2))}
        scale = re.search(r"^\s*Scale:\s*(\d+(?:\.\d+)?)", block, re.M)
        if scale: display["scale"] = float(scale.group(1))
        hdr = re.search(r"^\s*HDR:\s*(enabled|disabled)", block, re.I|re.M)
        if hdr: display["current_hdr_mode"] = fact("ACTIVE" if hdr.group(1).lower()=="enabled" else "INACTIVE",["KDE"])
        depth = re.search(r"Color resolution:\s*[^\n]*\((\d+)\)[^\n]*range:\s*\[(\d+);\s*(\d+)\]",block,re.I)
        if depth: display["color_depth"]={"current_bits":int(depth.group(1)),"minimum_bits":int(depth.group(2)),"maximum_bits":int(depth.group(3)),"evidence":["KDE"]}
        displays.append(display)
    return displays


def fallback_displays(sys_root: pathlib.Path) -> list[dict[str, Any]]:
    result = []
    for status in sorted((sys_root / "class/drm").glob("card*-*/status")):
        try: connected = status.read_text().strip() == "connected"
        except OSError: continue
        modes = []
        try:
            for line in (status.parent / "modes").read_text().splitlines():
                if match := re.fullmatch(r"(\d+)x(\d+)", line): modes.append({"width": int(match.group(1)), "height": int(match.group(2)), "refresh_hz": None})
        except OSError: pass
        try: active = (status.parent / "enabled").read_text().strip() == "enabled"
        except OSError: active = None
        result.append({"connector": status.parent.name.split("-", 1)[-1], "connected": connected, "active": active, "current_mode": None,
                       "available_modes": modes, "physical_size_mm": None, "hdr_capable": fact("UNKNOWN", ["DRM"]), "current_hdr_mode": fact("UNKNOWN", ["DRM"])})
    return result


def parse_wpctl(status: str, inspect: str) -> dict[str, Any]:
    sink = None
    in_sinks = False
    for line in status.splitlines():
        if "Sinks:" in line: in_sinks = True; continue
        if in_sinks and re.search(r"Sources:|Filters:|Streams:", line): in_sinks = False
        if in_sinks and "*" in line:
            sink = re.sub(r"^[^*]*\*\s*\d+\.\s*", "", line).strip().rstrip(".")
            break
    properties = dict(re.findall(r"^\s*([\w.]+)\s*=\s*\"?([^\"\n]+)\"?\s*$", inspect, re.M))
    description = properties.get("node.description") or properties.get("device.description") or sink
    media_class = properties.get("media.class")
    return {"backend": "PipeWire", "default_sink": description, "connection_class": "HDMI" if description and re.search(r"HDMI|DisplayPort", description, re.I) else "UNKNOWN",
            "channels": properties.get("audio.channels"), "sample_rates": [], "formats": [], "passthrough": fact("UNKNOWN", ["PIPEWIRE"]),
            "status": fact("DETECTED", ["PIPEWIRE"]) if description or media_class else fact("UNKNOWN", ["PIPEWIRE"])}


LEDGER_FIELDS = {"container", "codec", "profile", "bit_depth", "width", "height", "fps", "hardware_decode_backend", "successful", "validated_at", "hardware_fingerprint", "runtime_fingerprint"}


def validation_history(home: pathlib.Path) -> list[dict[str, Any]]:
    history_path = home / ".local/state/openhtpc/capability-validation.json"
    stored = read_json(history_path).get("records", [])
    return [item for item in stored if isinstance(item, dict) and set(item).issubset(LEDGER_FIELDS) and item.get("successful") is True][-64:]


def _atomic_json(path:pathlib.Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);fd,temporary=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as output:
            json.dump(value,output,ensure_ascii=False,indent=2,sort_keys=True);output.write("\n");output.flush();os.fsync(output.fileno())
        os.chmod(temporary,0o600);json.loads(pathlib.Path(temporary).read_text());os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def record_playback_validation(home:pathlib.Path,media:pathlib.Path,hardware_backend:str|None=None,runner:Runner=default_runner,validated_at:str|None=None)->dict[str,Any]|None:
    """Append one exact technical signature after confirmed successful playback."""
    result=runner(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,profile,pix_fmt,width,height,r_frame_rate","-show_entries","format=format_name","-of","json",str(media)],8)
    try:value=json.loads(result.get("stdout", "")) if result.get("status")=="OK" else {}
    except json.JSONDecodeError:value={}
    stream=(value.get("streams") or [{}])[0]
    if not stream.get("codec_name"):return None
    pix=str(stream.get("pix_fmt", ""));depth=10 if re.search(r"(?:^|[^0-9])10(?:[^0-9]|$)|p010",pix) else 12 if re.search(r"(?:^|[^0-9])12(?:[^0-9]|$)",pix) else 8 if pix else None
    snapshot=load_snapshot(home);backend=hardware_backend if hardware_backend in {"vaapi","nvdec","vulkan-video"} else None
    record={"container":(value.get("format") or {}).get("format_name"),"codec":str(stream.get("codec_name")).lower(),"profile":stream.get("profile"),"bit_depth":depth,
            "width":stream.get("width"),"height":stream.get("height"),"fps":stream.get("r_frame_rate"),"hardware_decode_backend":backend,"successful":True,
            "validated_at":validated_at or datetime.datetime.now(datetime.timezone.utc).isoformat(),"hardware_fingerprint":snapshot.get("hardware_fingerprint") if backend else None,"runtime_fingerprint":snapshot.get("runtime_fingerprint") if backend else None}
    ledger=home/".local/state/openhtpc/capability-validation.json";lock=ledger.with_suffix(".lock");lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open("w") as stream_lock:
        fcntl.flock(stream_lock,fcntl.LOCK_EX);records=validation_history(home)
        signature=lambda item:tuple(item.get(key) for key in ("container","codec","profile","bit_depth","width","height","fps","hardware_decode_backend","hardware_fingerprint","runtime_fingerprint"))
        records=[item for item in records if signature(item)!=signature(record)];records.append(record);_atomic_json(ledger,{"schema":1,"records":records[-64:]})
    return record


def record_validates_class(record:dict[str,Any],key:str)->bool:
    codec=str(record.get("codec","")).lower();depth=record.get("bit_depth");profile=str(record.get("profile","")).lower().replace(" ","")
    if not record.get("successful"):return False
    if key=="mpeg2":return codec in {"mpeg2","mpeg2video"}
    if key=="h264_8bit":return codec in {"h264","avc1"} and depth==8
    if key=="hevc_main":return codec in {"hevc","h265"} and depth==8 and "main10" not in profile
    if key=="hevc_main10":return codec in {"hevc","h265"} and depth==10 and (not profile or "main10" in profile)
    if key=="vp9_profile0":return codec=="vp9" and depth==8 and (not profile or "profile0" in profile)
    if key=="vp9_10bit":return codec=="vp9" and depth==10 and (not profile or "profile2" in profile)
    if key=="av1_main":return codec in {"av1","av01"} and depth==8 and (not profile or "main" in profile)
    return False


def generate(home: pathlib.Path, install: pathlib.Path, runner: Runner = default_runner, sys_root: pathlib.Path = pathlib.Path("/sys"), proc_root: pathlib.Path = pathlib.Path("/proc")) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    profile = read_json(home / ".config/openhtpc/profile.json")
    user = read_json(home / ".config/openhtpc/user-config.json")
    detected = profile.get("detected", {}) if isinstance(profile.get("detected"), dict) else {}
    cpu_model = detected.get("cpu")
    if not cpu_model:
        try:
            cpuinfo = (proc_root / "cpuinfo").read_text(errors="replace")
            match = re.search(r"^(?:model name|Hardware)\s*:\s*(.+)$", cpuinfo, re.M); cpu_model = match.group(1).strip() if match else platform.processor() or "Unknown"
        except OSError: cpu_model = platform.processor() or "Unknown"
    try:
        cpuinfo_text=(proc_root/"cpuinfo").read_text(errors="replace");mem_kib = int(re.search(r"^MemTotal:\s*(\d+)", (proc_root / "meminfo").read_text(), re.M).group(1))
    except (OSError, AttributeError, ValueError): mem_kib = None
    cpu_vendor_match=re.search(r"^vendor_id\s*:\s*(.+)$",cpuinfo_text,re.M) if 'cpuinfo_text' in locals() else None
    lspci = run_probe("lspci", ["lspci", "-Dnnk"], diagnostics, runner)
    gpus = parse_lspci(lspci.get("stdout", "")); gpu_sysfs(gpus, sys_root)
    topology = profile.get("gpu_topology", {}) if isinstance(profile.get("gpu_topology"), dict) else {}
    passport_gpus = topology.get("gpus") if isinstance(topology.get("gpus"), list) else []
    if not gpus and passport_gpus:
        gpus = [{"pci_address": item.get("pci_address"), "vendor": item.get("vendor", "Unknown"), "model": item.get("model", "Unknown"),
                 "device_id": item.get("device_id"), "kernel_driver": item.get("kernel_driver"), "drm_nodes": [item.get("drm_card")] if item.get("drm_card") else [],
                 "render_nodes": [item.get("render_node")] if item.get("render_node") else [], "active": item.get("active"), "memory_type": "UNKNOWN"} for item in passport_gpus]
    vulkan = run_probe("vulkan", ["vulkaninfo", "--summary"], diagnostics, runner, 8)
    vulkan_devices = parse_vulkan(vulkan.get("stdout", ""))
    render_nodes = [node for gpu in gpus for node in gpu.get("render_nodes", [])] or [str(path) for path in sorted(pathlib.Path("/dev/dri").glob("renderD*"))]
    va_profiles: dict[str, bool] = {key: False for key in CODECS}; va_drivers=[]; va_observed=False
    for index, node in enumerate(render_nodes or [""]):
        argv = ["vainfo"] if not node else ["vainfo", "--display", "drm", "--device", node]
        va = run_probe(f"vaapi_{index}", argv, diagnostics, runner, 8)
        if va.get("status") == "OK":
            va_observed=True; driver, support=parse_vaapi(va.get("stdout", "")+va.get("stderr", "")); va_drivers.extend([driver] if driver else [])
            va_profiles={key:va_profiles[key] or support[key] for key in va_profiles}
            gpu=next((item for item in gpus if node in item.get("render_nodes",[])),None)
            if gpu is not None: gpu["video_decode"]={"backend":"vaapi","driver":driver,"profiles":support}
    ffmpeg = run_probe("ffmpeg", ["ffmpeg", "-hide_banner", "-decoders"], diagnostics, runner, 8)
    decoders = parse_ffmpeg_decoders(ffmpeg.get("stdout", "") + ffmpeg.get("stderr", ""))
    ffver = run_probe("ffmpeg_version", ["ffmpeg", "-version"], diagnostics, runner)
    mpv = run_probe("mpv", ["mpv", "--no-config", "--version"], diagnostics, runner)
    mpv_help = run_probe("mpv_vo", ["mpv", "--no-config", "--vo=help"], diagnostics, runner)
    fingerprint_data={"gpus":[[g.get("vendor_id"),g.get("device_id"),g.get("kernel_driver")] for g in gpus],"architecture":platform.machine()}
    hardware_fingerprint=hashlib.sha256(json.dumps(fingerprint_data,sort_keys=True).encode()).hexdigest()
    runtime_data={"mpv":(mpv.get("stdout","").splitlines() or [None])[0],"ffmpeg":(ffver.get("stdout","").splitlines() or [None])[0],"vaapi_drivers":sorted(set(va_drivers)),"gpu_drivers":[g.get("kernel_driver") for g in gpus]}
    runtime_fingerprint=hashlib.sha256(json.dumps(runtime_data,sort_keys=True).encode()).hexdigest()
    history = validation_history(home)
    codec_matrix={}
    for key,(decoder,_) in CODECS.items():
        validated = any(record_validates_class(item,key) for item in history)
        hardware_validated=any(record_validates_class(item,key) and item.get("hardware_decode_backend")=="vaapi" and item.get("hardware_fingerprint")==hardware_fingerprint and item.get("runtime_fingerprint")==runtime_fingerprint for item in history)
        codec_matrix[key]={"codec":decoder,"profile":key,"bit_depth":10 if "10" in key else 8,
                           "software_decode":fact("AVAILABLE" if decoder in decoders else "UNAVAILABLE" if ffmpeg.get("status")=="OK" else "UNKNOWN",["FFMPEG"]),
                           "hardware_decode":fact("SUPPORTED" if va_profiles[key] else "UNSUPPORTED" if va_observed else "UNKNOWN",["VAAPI","OPENHTPC_RUNTIME_TEST"] if hardware_validated else ["VAAPI"] if va_observed else [],hardware_validated),
                           "hardware_backends":["vaapi"] if va_profiles[key] else [],
                           "validated_playback":fact("VALIDATED" if validated else "UNVALIDATED",["OPENHTPC_RUNTIME_TEST"] if validated else [],validated)}
    graphical=resolve_graphical_context(proc_root,home=home,install=install)
    graphical_argv=["env","-u","DISPLAY","-u","WAYLAND_DISPLAY","-u","XDG_RUNTIME_DIR","-u","DBUS_SESSION_BUS_ADDRESS",*(f"{key}={value}" for key,value in graphical.get("environment",{}).items()),"kscreen-doctor","-o"] if graphical.get("status")=="RESOLVED" else ["kscreen-doctor","-o"]
    kscreen = run_probe("display", graphical_argv, diagnostics, runner, 6)
    displays = parse_kscreen(kscreen.get("stdout", "")) if kscreen.get("status") == "OK" else fallback_displays(sys_root)
    for gpu in gpus: gpu["active"] = False if displays else None
    for output in displays:
        if not output.get("active"): continue
        for connector in (sys_root/"class/drm").glob(f"card*-{output.get('connector','')}"):
            card=connector.name.split("-",1)[0]
            for gpu in gpus:
                if card in gpu.get("drm_nodes",[]):gpu["active"]=True
    wpstatus = run_probe("pipewire_status", ["wpctl", "status", "-n"], diagnostics, runner, 5)
    wpinspect = run_probe("pipewire_sink", ["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], diagnostics, runner, 5)
    audio = parse_wpctl(wpstatus.get("stdout", ""), wpinspect.get("stdout", "")) if wpstatus.get("status") == "OK" else {"backend":"PipeWire","default_sink":None,"connection_class":"UNKNOWN","channels":None,"sample_rates":[],"formats":[],"passthrough":fact("UNKNOWN"),"status":fact("UNKNOWN")}
    sources=[]
    for index, raw in enumerate(user.get("local_media_sources", []) if isinstance(user.get("local_media_sources"), list) else []):
        if not isinstance(raw,str): continue
        path=pathlib.Path(raw); accessible=path.is_dir(); fstype=None
        if accessible:
            mounted=run_probe(f"media_source_{index}",["findmnt","-T",str(path),"-n","-o","FSTYPE"],diagnostics,runner,3)
            if mounted.get("status")=="OK": fstype=mounted.get("stdout","").strip().splitlines()[0] if mounted.get("stdout","").strip() else None
        kind="network" if fstype and fstype.lower() in {"cifs","smb3","nfs","nfs4","sshfs","fuse.sshfs"} else "local" if fstype else "unknown"
        sources.append({"source_id":hashlib.sha256(str(index).encode()).hexdigest()[:12],"accessible":accessible,"filesystem_class":kind,"filesystem_type":fstype})
    optical_devices=[]
    for path in sorted((sys_root/"class/block").glob("sr*")) if (sys_root/"class/block").is_dir() else []:
        optical_devices.append({"device":f"/dev/{path.name}","detected":True,"dvd_readable":fact("UNKNOWN",["HARDWARE"]),"bluray_drive_capability":fact("UNKNOWN",["HARDWARE"]),"libredrive":fact("UNKNOWN")})
    if not optical_devices:
        for item in detected.get("optical_drives",[]) if isinstance(detected.get("optical_drives"),list) else []:
            device=item.get("path") if isinstance(item,dict) else item
            if isinstance(device,str): optical_devices.append({"device":device,"detected":True,"dvd_readable":fact("UNKNOWN",["HARDWARE_PASSPORT"]),"bluray_drive_capability":fact("UNKNOWN"),"libredrive":fact("UNKNOWN")})
    active_display=next((item for item in displays if item.get("active")),None)
    snapshot={"schema":SCHEMA,"probe_version":PROBE_VERSION,"generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "hardware_fingerprint":hardware_fingerprint,"runtime_fingerprint":runtime_fingerprint,
      "hardware":{"system":{"manufacturer":_read_safe(sys_root/"class/dmi/id/sys_vendor"),"model":_read_safe(sys_root/"class/dmi/id/product_name")},
                  "cpu":{"vendor":cpu_vendor_match.group(1).strip() if cpu_vendor_match else None,"model":cpu_model,"architecture":platform.machine(),"logical_cores":os.cpu_count(),"physical_cores":None},
                  "memory":{"total_bytes":mem_kib*1024 if mem_kib else None}},
      "graphics":{"devices":gpus,"vulkan":{"loader":fact("AVAILABLE" if vulkan.get("status")=="OK" else "UNAVAILABLE" if vulkan.get("status")=="COMMAND_UNAVAILABLE" else "UNKNOWN",["VULKAN"]),"devices":vulkan_devices},
                  "vaapi":{"status":fact("AVAILABLE" if va_observed else "UNAVAILABLE" if all(diagnostics.get(f"vaapi_{i}",{}).get("status")=="COMMAND_UNAVAILABLE" for i in range(max(1,len(render_nodes)))) else "UNKNOWN",["VAAPI"] if va_observed else []),"drivers":sorted(set(va_drivers)),"render_nodes":render_nodes},
                  "opengl":fact("UNKNOWN")},
      "display":{"outputs":displays,"active_output":active_display,"configured":user.get("display") if isinstance(user.get("display"),dict) else {},"hdr_pipeline_validated":fact("UNVALIDATED"),"session_context":{"status":graphical.get("status"),"evidence":graphical.get("evidence")}},
      "video_decode":{"ffmpeg":{"status":fact("AVAILABLE" if ffmpeg.get("status")=="OK" else "UNAVAILABLE" if ffmpeg.get("status")=="COMMAND_UNAVAILABLE" else "UNKNOWN",["FFMPEG"]),"version":(ffver.get("stdout","").splitlines() or [None])[0]},
                      "mpv":{"status":fact("AVAILABLE" if mpv.get("status")=="OK" else "UNAVAILABLE" if mpv.get("status")=="COMMAND_UNAVAILABLE" else "UNKNOWN",["MPV"]),"version":(mpv.get("stdout","").splitlines() or [None])[0],"gpu_next":fact("AVAILABLE" if "gpu-next" in mpv_help.get("stdout","") else "UNKNOWN",["MPV"])},"codecs":codec_matrix},
      "audio":audio,
      "optical":{"drives":optical_devices,"dvd":{"physical_support":fact("DETECTED" if optical_devices else "UNAVAILABLE",["HARDWARE_PASSPORT"] if optical_devices else []),"css_support":fact("AVAILABLE" if shutil.which("lsdvd") else "UNKNOWN",["OPENHTPC_RUNTIME"]),"validated_playback":fact("UNVALIDATED")},"bluray_plugin":fact("UNAVAILABLE",["PLUGIN_REGISTRY"]),"uhd_plugin":fact("UNAVAILABLE",["PLUGIN_REGISTRY"])},
      "media":{"configured_sources":len(sources),"accessible_sources":sum(item["accessible"] for item in sources),"sources":sources,"playback_backend":"mpv"},
      "video_processing":{"gpu_backend":fact("AVAILABLE" if any(item.get('device_type')!='PHYSICAL_DEVICE_TYPE_CPU' for item in vulkan_devices) else "UNKNOWN",["VULKAN"]),"render_backend":fact("AVAILABLE" if "gpu-next" in mpv_help.get("stdout","") else "UNKNOWN",["MPV"]),"output_mode":active_display.get("current_mode") if active_display else None,"benchmark":{"version":None,"status":"NOT_RUN","results":{}},"recommended_profile":None,"recommendation_status":"NOT_EVALUATED","active_profile":"PURE"},
      "validation":{"records":history},"confidence":{"partial":any(item.get("status") not in {"OK"} for item in diagnostics.values()),"probe_diagnostics":diagnostics}}
    validate_snapshot(snapshot)
    return snapshot


def _read_safe(path: pathlib.Path) -> str | None:
    try: return path.read_text(errors="replace").strip()[:160] or None
    except OSError: return None


def validate_snapshot(value: dict[str, Any]) -> None:
    required={"schema","probe_version","generated_at","hardware_fingerprint","runtime_fingerprint","hardware","graphics","display","video_decode","audio","optical","media","video_processing","validation","confidence"}
    if set(value) != required or value.get("schema") != SCHEMA or not isinstance(value.get("graphics",{}).get("devices"),list) or not isinstance(value.get("display",{}).get("outputs"),list):
        raise ValueError("CAPABILITY_SCHEMA_INVALID")
    encoded=json.dumps(value,ensure_ascii=False)
    if re.search(r"(?i)(serial|machine_uuid|filesystem_uuid|mac_address|password|api_key|token)\"\s*:",encoded):
        raise ValueError("CAPABILITY_PRIVACY_INVALID")


def snapshot_path(home: pathlib.Path) -> pathlib.Path:
    return home / ".config/openhtpc/runtime/capabilities.json"


def refresh(home: pathlib.Path, install: pathlib.Path, runner: Runner = default_runner, sys_root: pathlib.Path = pathlib.Path("/sys"), proc_root: pathlib.Path = pathlib.Path("/proc")) -> dict[str, Any]:
    target=snapshot_path(home);target.parent.mkdir(parents=True,exist_ok=True);lock=target.with_suffix(".lock")
    with lock.open("w") as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        value=generate(home,install,runner,sys_root,proc_root)
        fd,temporary=tempfile.mkstemp(prefix="capabilities.",suffix=".tmp",dir=target.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as output:
                json.dump(value,output,ensure_ascii=False,indent=2,sort_keys=True);output.write("\n");output.flush();os.fsync(output.fileno())
            os.chmod(temporary,0o600);json.loads(pathlib.Path(temporary).read_text());os.replace(temporary,target)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    return value


def load_snapshot(home: pathlib.Path) -> dict[str, Any]:
    value=read_json(snapshot_path(home))
    try: validate_snapshot(value);return value
    except ValueError:return {}


def summary(value: dict[str, Any]) -> str:
    hardware=value.get("hardware",{});graphics=value.get("graphics",{});display=value.get("display",{});audio=value.get("audio",{});processing=value.get("video_processing",{})
    cpu=hardware.get("cpu",{});memory=hardware.get("memory",{}).get("total_bytes");active=display.get("active_output") or {};mode=active.get("current_mode") or {}
    lines=["SYSTÈME",str(cpu.get("model") or "Inconnu"),f"RAM : {memory/1024**3:.1f} Gio" if memory else "RAM : inconnue","","GRAPHIQUES"]
    for gpu in graphics.get("devices",[]):lines.append(f"{gpu.get('model','Inconnu')} — pilote {gpu.get('kernel_driver') or 'inconnu'}")
    lines.extend([f"Vulkan : {graphics.get('vulkan',{}).get('loader',{}).get('status','UNKNOWN')}",f"VA-API : {graphics.get('vaapi',{}).get('status',{}).get('status','UNKNOWN')}","","AFFICHAGE"])
    lines.append(f"{mode.get('width','?')}x{mode.get('height','?')} @ {mode.get('refresh_hz','?')} Hz — {active.get('connector','aucune sortie active')}")
    lines.extend([f"HDR actif : {(active.get('current_hdr_mode') or {}).get('status','UNKNOWN')}","","DÉCODAGE VIDÉO"])
    for key,item in value.get("video_decode",{}).get("codecs",{}).items():
        lines.append(f"{key:<16} logiciel {item['software_decode']['status']:<11} matériel {item['hardware_decode']['status']:<11} validation {item['validated_playback']['status']}")
    lines.extend(["","AUDIO",f"{audio.get('backend','Inconnu')} / {audio.get('default_sink') or 'sortie inconnue'}",f"Canaux : {audio.get('channels') or 'inconnus'} / Passthrough : {audio.get('passthrough',{}).get('status','UNKNOWN')}","","TRAITEMENT VIDÉO",f"Benchmark : {processing.get('benchmark',{}).get('status','NOT_RUN')}",f"Profil adaptatif : {processing.get('recommendation_status','NOT_EVALUATED')}"])
    return "\n".join(lines)


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--json",action="store_true");parser.add_argument("--refresh",action="store_true");args=parser.parse_args()
    home=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home()));install=pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR",home/".local/lib/openhtpc"))
    value=refresh(home,install) if args.refresh else load_snapshot(home)
    if not value:value=refresh(home,install)
    print(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True) if args.json else summary(value));return 0


if __name__ == "__main__": raise SystemExit(main())
