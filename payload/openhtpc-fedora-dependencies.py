#!/usr/bin/env python3
"""Read-only Fedora dependency contracts for OPENHTPC Basic."""
from __future__ import annotations
import argparse
import ctypes
import ctypes.util
import json
import shutil
import subprocess

CONTRACTS = {
    "pciutils": ("COMMAND", ("lspci",)),
    "procps-ng": ("COMMAND", ("ps", "pgrep")),
    "python3": ("COMMAND", ("python3",)),
    "python3-pillow": ("PYTHON", ("PIL",)),
    "mpv": ("COMMAND", ("mpv",)),
    "libva-utils": ("COMMAND", ("vainfo",)),
    "vulkan-tools": ("COMMAND", ("vulkaninfo",)),
    "mesa-vulkan-drivers": ("PACKAGE", ("mesa-vulkan-drivers",)),
    "SDL2": ("LIBRARY", ("SDL2-2.0",)),
    "SDL2_image": ("LIBRARY", ("SDL2_image-2.0",)),
    "SDL2_ttf": ("LIBRARY", ("SDL2_ttf-2.0",)),
    "kdialog": ("COMMAND", ("kdialog",)),
    "ffmpeg-free": ("COMMAND", ("ffmpeg",)),
    "libva-intel-media-driver": ("PACKAGE", ("libva-intel-media-driver",)),
}


def run(command, timeout=30):
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def package_installed(package, runner=run):
    result = runner(["rpm", "-q", "--qf", "%{NAME}\n", package], 30)
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return result.returncode == 0 and package in names


def library_ready(name, finder=ctypes.util.find_library, loader=ctypes.CDLL):
    library = finder(name)
    if not library:
        return False, None, "NOT_FOUND"
    try:
        loader(library)
    except OSError as exc:
        return False, library, str(exc)
    return True, library, None


def dependency_state(package, which=shutil.which, runner=run,
                     finder=ctypes.util.find_library, loader=ctypes.CDLL):
    if package not in CONTRACTS:
        return {"package": package, "contract": "UNKNOWN", "ready": False, "reason": "UNKNOWN_DEPENDENCY"}
    contract, requirements = CONTRACTS[package]
    evidence = []
    if contract == "COMMAND":
        evidence = [which(command) for command in requirements]
        ready = all(evidence)
    elif contract == "LIBRARY":
        ready, library, error = library_ready(requirements[0], finder, loader)
        evidence = [library, error]
    elif contract == "PYTHON":
        import importlib.util
        ready = importlib.util.find_spec(requirements[0]) is not None
        evidence = [requirements[0] if ready else None]
    else:
        ready = package_installed(requirements[0], runner)
        evidence = [requirements[0] if ready else None]
    return {"package": package, "contract": contract, "ready": bool(ready), "evidence": evidence,
            "reason": None if ready else f"{contract}_MISSING"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", choices=sorted(CONTRACTS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.ready:
        result = dependency_state(args.ready)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ready"] else 1
    print(json.dumps({name: dependency_state(name) for name in sorted(CONTRACTS)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
