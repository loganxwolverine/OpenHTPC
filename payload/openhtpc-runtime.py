#!/usr/bin/env python3
"""OPENHTPC user-session ownership, lifecycle logging and bounded cleanup."""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import pathlib
import signal
import tempfile
import time

START_REASONS = frozenset({"SESSION_START", "USER_START", "CONTROLLED_REFRESH", "PLAYBACK_RETURN", "CRASH_RECOVERY"})
STOP_REASONS = frozenset({"CONTROLLED_REFRESH", "NORMAL_EXIT", "USER_QUIT", "UPDATE_CLEANUP", "CRASH"})
EXIT_REASONS = frozenset({"USER_QUIT_TO_DESKTOP","USER_POWEROFF","PLAYER_RETURN","FLEX_UNEXPECTED_EXIT","SESSION_STOP","UNKNOWN"})
MAX_LOG_BYTES=512*1024


def paths(home: pathlib.Path) -> dict[str, pathlib.Path]:
    root = home / ".local/state/openhtpc"
    return {"root": root, "log": root / "runtime.log", "session": root / "runtime-session.json", "monitor": root / "optical-monitor.pid", "backdrop": root / "backdrop.pid", "crashes": root / "flex-crashes.json", "desktop":root/"desktop-restore.json"}


def crash_loop_state(home: pathlib.Path, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    try: value = json.loads(paths(home)["crashes"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): value = {}
    events = [float(item) for item in value.get("events", []) if isinstance(item, (int, float)) and now - float(item) <= 300]
    return {"events": events, "count": len(events), "blocked": len(events) >= 3, "window_seconds": 300, "burst": 3}


def record_flex_exit(home: pathlib.Path, returncode: int, runtime_seconds: float, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    state = crash_loop_state(home, now)
    abnormal = returncode != 0
    events = state["events"] + ([now] if abnormal else [])
    if not abnormal or runtime_seconds >= 300:
        events = []
    atomic_json(paths(home)["crashes"], {"schema": 1, "events": events, "last_returncode": returncode,
                                        "last_runtime_seconds": round(runtime_seconds, 3), "updated": now})
    result = crash_loop_state(home, now)
    log(home, "ui", "FLEX_CRASH_RECORDED" if abnormal else "FLEX_EXIT_CLEAN",
        returncode=returncode, runtime_seconds=round(runtime_seconds, 3), crash_count=result["count"], crash_loop_blocked=result["blocked"])
    return result


def atomic_json(target: pathlib.Path, value: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def log(home: pathlib.Path, component: str, event: str, **fields) -> None:
    if event == "FLEX_STARTED" and fields.get("start_reason") not in START_REASONS: raise ValueError("UNKNOWN_UI_START_REASON")
    if event == "FLEX_STOPPED" and fields.get("stop_reason") not in STOP_REASONS: raise ValueError("UNKNOWN_UI_STOP_REASON")
    target = paths(home)["log"]
    try: target.parent.mkdir(parents=True, exist_ok=True)
    except OSError: return
    record = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "component": component,
              "event": event, "pid": os.getpid(), "ppid": os.getppid(), **fields}
    try:
        if target.is_file() and target.stat().st_size>=MAX_LOG_BYTES:
            previous=target.with_suffix(".log.1")
            try: previous.unlink()
            except FileNotFoundError: pass
            os.replace(target,previous)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError: return
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX); stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        try: os.chmod(target, 0o600)
        except OSError: pass


def log_navigation(home: pathlib.Path, flex_pid: int, source_page: str, destination_page: str, action_type: str = "NAVIGATE") -> None:
    log(home, "ui", "NAVIGATION", flex_pid=flex_pid, action_type=action_type,
        source_page=source_page, destination_page=destination_page,
        ui_pid_before=flex_pid, ui_pid_after=flex_pid)


def process_command(pid: int, proc_root: pathlib.Path = pathlib.Path("/proc")) -> list[str]:
    try: return [item.decode(errors="replace") for item in (proc_root / str(pid) / "cmdline").read_bytes().split(b"\0") if item]
    except OSError: return []


def managed_processes(home: pathlib.Path, install: pathlib.Path, proc_root: pathlib.Path = pathlib.Path("/proc")) -> dict[str, list[int]]:
    result = {"ui": [], "monitor": [], "controllers": []}; own = os.getuid()
    try: candidates = [item for item in proc_root.iterdir() if item.name.isdigit()]
    except OSError: return result
    flex = str(install / "flex/bin/flex-launcher"); monitor = str(install / "openhtpc-optical-monitor")
    ui_helpers = {str(install / name) for name in ("openhtpc-home.py", "openhtpc-disc-sheet.py", "openhtpc-system-page", "openhtpc-media-browser.py", "openhtpc-power-menu")}
    for item in candidates:
        try:
            if item.stat().st_uid != own: continue
        except OSError: continue
        command = process_command(int(item.name), proc_root)
        if not command: continue
        if flex in command: result["ui"].append(int(item.name))
        if any(helper in command for helper in ui_helpers): result["controllers"].append(int(item.name))
        if monitor in command: result["monitor"].append(int(item.name))
    return {key: sorted(set(value)) for key, value in result.items()}


def read_pid(path: pathlib.Path) -> int | None:
    try: return int(path.read_text().strip())
    except (OSError, ValueError): return None


def stop_pid(pid: int | None, expected: str, proc_root: pathlib.Path = pathlib.Path("/proc"), timeout: float = 3.0) -> bool:
    if not pid or expected not in process_command(pid, proc_root): return False
    try: os.kill(pid, signal.SIGTERM)
    except ProcessLookupError: return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not (proc_root / str(pid)).exists(): return True
        time.sleep(0.05)
    return False


def cleanup_legacy(home: pathlib.Path, install: pathlib.Path, proc_root: pathlib.Path = pathlib.Path("/proc")) -> dict:
    backdrop = read_pid(paths(home)["backdrop"])
    if backdrop: stop_pid(backdrop, "--title=OPENHTPC-Backdrop", proc_root)
    found = managed_processes(home, install, proc_root); stopped = []
    for kind, pids in found.items():
        expected = str(install / ("openhtpc-optical-monitor" if kind == "monitor" else "flex/bin/flex-launcher"))
        for pid in pids:
            command = process_command(pid, proc_root)
            marker = expected if expected in command else next((arg for arg in command if arg.startswith(str(install) + "/")), "")
            if marker and stop_pid(pid, marker, proc_root): stopped.append(pid)
    log(home, "runtime", "LEGACY_CLEANUP", stopped=stopped)
    atomic_json(paths(home)["session"], {"schema": 1, "state": "STOPPED", "stop_reason": "UPDATE_CLEANUP"})
    try: paths(home)["backdrop"].unlink()
    except FileNotFoundError: pass
    remaining = managed_processes(home, install, proc_root)
    return {"found": found, "stopped": stopped, "remaining": remaining}

def stop_session(home: pathlib.Path, install: pathlib.Path, proc_root: pathlib.Path = pathlib.Path("/proc")) -> dict:
    found = managed_processes(home, install, proc_root); stopped = []
    for kind in ("ui", "controllers", "monitor"):
        for pid in found[kind]:
            command = process_command(pid, proc_root)
            marker = next((arg for arg in command if arg == str(install / "flex/bin/flex-launcher") or arg.startswith(str(install) + "/")), "")
            if marker and stop_pid(pid, marker, proc_root): stopped.append(pid)
    log(home, "runtime", "SESSION_PROCESSES_STOPPED", stopped=stopped)
    return {"found": found, "stopped": stopped}


def status(home: pathlib.Path, install: pathlib.Path) -> dict:
    found = managed_processes(home, install); session = paths(home)["session"]
    try: state = json.loads(session.read_text())
    except (OSError, json.JSONDecodeError): state = {"state": "STOPPED"}
    active = state.get("state") == "RUNNING"
    ui_count = len(found["ui"]); monitor_count = len(found["monitor"])
    healthy = (ui_count <= 1 and monitor_count <= 1 and ((ui_count == 1 and monitor_count == 1) if active else (ui_count == 0 and monitor_count == 0)))
    crash = crash_loop_state(home)
    desktop={}
    try: desktop=json.loads(paths(home)["desktop"].read_text())
    except (OSError,json.JSONDecodeError): pass
    return {"ui_instances": ui_count, "authoritative_flex_pid":state.get("authoritative_flex_pid"),"unexpected_flex_pids":[pid for pid in found["ui"] if pid!=state.get("authoritative_flex_pid")],"monitor_instances": monitor_count, "appliance_state": state.get("state", "STOPPED"),
            "runtime_ownership": "PASS" if healthy else "FAIL", "refresh_lock": "AVAILABLE",
            "crash_loop_state": "BLOCKED" if crash["blocked"] else "PASS", "recent_flex_crashes": crash["count"],
            "last_exit":state.get("exit_reason","UNKNOWN"),"desktop_restore":desktop.get("result","NOT_TESTED")}

def record_exit(home:pathlib.Path,reason:str,desktop_restore:str="NOT_TESTED")->None:
    if reason not in EXIT_REASONS: raise ValueError("UNKNOWN_EXIT_REASON")
    atomic_json(paths(home)["session"],{"schema":2,"state":"STOPPED","exit_reason":reason,"desktop_restore":desktop_restore,"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    log(home,"session","EXIT",reason=reason,desktop_restore=desktop_restore)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("status", "cleanup-legacy", "stop-session", "record-exit", "log")); parser.add_argument("--event"); parser.add_argument("--component", default="runtime");parser.add_argument("--reason",choices=sorted(EXIT_REASONS));parser.add_argument("--desktop-restore",default="NOT_TESTED")
    args = parser.parse_args(); home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())); install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    if args.command == "status": print(json.dumps(status(home, install), sort_keys=True)); return 0
    if args.command == "cleanup-legacy":
        result=cleanup_legacy(home, install); print(json.dumps(result, sort_keys=True))
        return 1 if any(result["remaining"][key] for key in ("ui","monitor","controllers")) else 0
    if args.command == "stop-session": print(json.dumps(stop_session(home, install), sort_keys=True)); return 0
    if args.command == "record-exit": record_exit(home,args.reason or "UNKNOWN",args.desktop_restore);return 0
    log(home, args.component, args.event or "EVENT"); return 0


if __name__ == "__main__": raise SystemExit(main())
