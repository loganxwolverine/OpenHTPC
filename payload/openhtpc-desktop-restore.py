#!/usr/bin/env python3
"""Restore KDE desktop ownership only after an explicit OPENHTPC Quit."""
from __future__ import annotations
import datetime, json, os, pathlib, subprocess, time

SERVICE = "plasma-plasmashell.service"


def run(command, timeout=8):
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def resolve_desktop(runner=run) -> str:
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP", "") + " " + os.environ.get("DESKTOP_SESSION", "")).strip().upper()
    if "KDE" in desktop or "PLASMA" in desktop or "GNOME" in desktop:
        return desktop
    # Fallback to systemctl --user show-environment
    try:
        env_probe = runner(["systemctl", "--user", "show-environment"])
        if env_probe.returncode == 0:
            env_dict = {}
            for line in env_probe.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_dict[k.strip()] = v.strip()
            user_desktop = (env_dict.get("XDG_CURRENT_DESKTOP", "") + " " + env_dict.get("DESKTOP_SESSION", "")).strip().upper()
            if user_desktop:
                return user_desktop
    except Exception:
        pass
    return desktop


def restore(home: pathlib.Path, runner=run, sleeper=time.sleep, timeout=12.0) -> dict:
    desktop = resolve_desktop(runner)
    probe = runner(["systemctl", "--user", "show", SERVICE, "--property=LoadState", "--value"])
    supported = ("KDE" in desktop or "PLASMA" in desktop) and probe.returncode == 0 and probe.stdout.strip() == "loaded"
    result = {"schema": 1, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "service": SERVICE, "result": "SKIPPED_UNSUPPORTED_ENVIRONMENT"}
    if supported:
        restarted = runner(["systemctl", "--user", "restart", SERVICE], timeout=10)
        if restarted.returncode == 0:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                active = runner(["systemctl", "--user", "is-active", SERVICE], timeout=3)
                process = runner(["pgrep", "-x", "plasmashell"], timeout=3)
                if active.returncode == 0 and active.stdout.strip() == "active" and process.returncode == 0:
                    result["result"] = "PASS"
                    break
                sleeper(0.25)
            else:
                result["result"] = "FAILED_TIMEOUT"
        else:
            result["result"] = "FAILED_RESTART"
    target = home / ".local/state/openhtpc/desktop-restore.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return result


def main():
    home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    result = restore(home)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] in {"PASS", "SKIPPED_UNSUPPORTED_ENVIRONMENT"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
