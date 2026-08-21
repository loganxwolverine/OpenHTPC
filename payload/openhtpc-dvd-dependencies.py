#!/usr/bin/env python3
"""Read-only Fedora DVD CSS capability detection and installation planning."""

import argparse
import ctypes
import ctypes.util
import json
import shutil
import subprocess


TAINTED_REPO = "rpmfusion-free-tainted"
TAINTED_RELEASE = "rpmfusion-free-release-tainted"
FREE_REPO = "rpmfusion-free"
ACTIONS = (
    "ENABLE_RPMFUSION_FREE",
    "ENABLE_RPMFUSION_FREE_TAINTED",
    "INSTALL_LIBDVDCSS",
)


def run(command, timeout=30):
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def libdvdcss_capability(finder=ctypes.util.find_library, loader=ctypes.CDLL):
    library = finder("dvdcss")
    if not library:
        return {"state": "LIBDVDCSS_MISSING", "library": None, "error": None}
    try:
        loader(library)
    except OSError as exc:
        return {"state": "LIBDVDCSS_BROKEN", "library": library, "error": str(exc)}
    return {"state": "LIBDVDCSS_READY", "library": library, "error": None}


def repo_enabled(repo_id, dnf, runner=run):
    result = runner([dnf, "-q", "repolist", "--enabled"], 30)
    return result.returncode == 0 and repo_id in result.stdout.split()


def package_available(package, dnf, runner=run):
    result = runner([dnf, "-q", "repoquery", "--available", package], 30)
    return result.returncode == 0 and bool(result.stdout.strip())


def fedora_release(rpm, runner=run):
    if not rpm:
        return None
    result = runner([rpm, "-E", "%fedora"], 30)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value.isdigit() else None


def free_bootstrap_url(release):
    if not isinstance(release, str) or not release.isdigit():
        return None
    return f"https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-{release}.noarch.rpm"


def inspect(which=shutil.which, runner=run, finder=ctypes.util.find_library, loader=ctypes.CDLL):
    capability = libdvdcss_capability(finder, loader)
    dnf = which("dnf5") or which("dnf")
    rpm = which("rpm")
    release = fedora_release(rpm, runner)
    free_enabled = False
    enabled = False
    release_available = False
    if dnf:
        free_enabled = repo_enabled(FREE_REPO, dnf, runner)
        enabled = repo_enabled(TAINTED_REPO, dnf, runner)
        if free_enabled and not enabled:
            release_available = package_available(TAINTED_RELEASE, dnf, runner)
    if capability["state"] == "LIBDVDCSS_READY":
        actions = []
    elif enabled:
        actions = ["INSTALL_LIBDVDCSS"]
    elif release_available:
        actions = ["ENABLE_RPMFUSION_FREE_TAINTED", "INSTALL_LIBDVDCSS"]
    elif not free_enabled and free_bootstrap_url(release):
        actions = ["ENABLE_RPMFUSION_FREE", "ENABLE_RPMFUSION_FREE_TAINTED", "INSTALL_LIBDVDCSS"]
    else:
        actions = []
    return {
        "libdvdcss": capability,
        "dnf": dnf,
        "fedora_release": release,
        "rpmfusion_free_enabled": free_enabled,
        "rpmfusion_free_bootstrap_url": free_bootstrap_url(release),
        "free_tainted_enabled": enabled,
        "free_tainted_release_available": release_available,
        "actions": actions,
        "plan": actions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()
    result = inspect()
    if args.shell:
        print("LIBDVDCSS_STATE=" + result["libdvdcss"]["state"])
        print("FEDORA_RELEASE=" + (result["fedora_release"] or ""))
        print("RPMFUSION_FREE_ENABLED=" + str(result["rpmfusion_free_enabled"]).lower())
        print("RPMFUSION_FREE_BOOTSTRAP_URL=" + (result["rpmfusion_free_bootstrap_url"] or ""))
        print("FREE_TAINTED_ENABLED=" + str(result["free_tainted_enabled"]).lower())
        print("FREE_TAINTED_RELEASE_AVAILABLE=" + str(result["free_tainted_release_available"]).lower())
        print("DVD_DNF=" + (result["dnf"] or ""))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
