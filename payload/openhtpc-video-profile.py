#!/usr/bin/env python3
"""OPENHTPC 1.1 Phase C4 Video Profile Persistence.

Manages the user-facing video profile selection:
  PURE       — Always uses the immutable PURE runtime. No shaders. Maximum stability.
  CINEMA_AUTO — Resolves presentation dynamically via content scope + Recipe Catalogue
               + Performance Map. Fallback to PURE if map absent, stale, or yields
               no stable candidate.

Fresh-install default: PURE.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

STATE_DIR = pathlib.Path(os.environ.get("OPENHTPC_STATE_DIR", pathlib.Path.home() / ".local/state/openhtpc"))
CONFIG_DIR = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())) / ".config/openhtpc"
PROFILE_PATH = CONFIG_DIR / "video-profile.json"
SCHEMA = 1
VALID_PROFILES = {"PURE", "CINEMA_AUTO"}
FALLBACK = "PURE"


def read_profile(home: pathlib.Path | None = None) -> str:
    """Return active profile; always PURE or CINEMA_AUTO. Never raises."""
    path = (home / ".config/openhtpc/video-profile.json") if home else PROFILE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = data.get("active_profile", FALLBACK)
        return profile if profile in VALID_PROFILES else FALLBACK
    except Exception:
        return FALLBACK


def write_profile(profile: str, home: pathlib.Path | None = None) -> None:
    """Atomically write active profile. Raises ValueError for invalid profiles."""
    if profile not in VALID_PROFILES:
        raise ValueError(f"INVALID_PROFILE:{profile}")
    path = (home / ".config/openhtpc/video-profile.json") if home else PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": SCHEMA, "active_profile": profile}
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cinema_auto_status(home: pathlib.Path | None = None, install: pathlib.Path | None = None) -> dict:
    """Return C4 status dict without triggering calibration or probing hardware."""
    _home = home or pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    _install = install or pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", _home / ".local/lib/openhtpc"))
    map_path = _home / ".local/state/openhtpc/performance_map.json"
    map_present = map_path.exists()
    map_schema_ok = False
    if map_present:
        try:
            data = json.loads(map_path.read_text(encoding="utf-8"))
            map_schema_ok = isinstance(data, dict) and data.get("schema_version") == 2
        except Exception:
            pass
    # Check staleness via cinema-auto engine (read-only)
    map_current = False
    if map_schema_ok:
        try:
            import importlib.util
            engine_path = _install / "openhtpc-cinema-auto.py"
            if engine_path.is_file():
                spec = importlib.util.spec_from_file_location("openhtpc_cinema_auto", engine_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                pmap = module._load_map()
                if pmap is not None:
                    stale, _ = module.is_map_stale(pmap)
                    map_current = not stale
        except Exception:
            pass
    active = read_profile(_home)
    return {
        "active_profile": active,
        "map_present": map_present,
        "map_schema_ok": map_schema_ok,
        "map_current": map_current,
        "can_activate": map_present and map_schema_ok,
    }


def _refresh_ui(home: pathlib.Path, install: pathlib.Path) -> None:
    """Regenerate system PNGs and Flex configuration after profile update."""
    try:
        action_bin = install / "openhtpc-system-action"
        if action_bin.is_file():
            import subprocess
            subprocess.run([str(action_bin), "refresh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass
    try:
        se_path = install / "openhtpc-session-engine.py"
        if se_path.is_file():
            import importlib.util as ilu
            spec = ilu.spec_from_file_location("se", se_path)
            if spec and spec.loader:
                se = ilu.module_from_spec(spec)
                spec.loader.exec_module(se)
                ini_path = se.canonical_flex_config_path(home)
                if ini_path.parent.is_dir():
                    se.write_flex_config(ini_path, home, [], install=install)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="OPENHTPC C4 Video Profile")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("get", help="Print active profile")
    sp = sub.add_parser("set", help="Set active profile")
    sp.add_argument("profile", choices=["PURE", "CINEMA_AUTO", "pure", "cinema_auto"])
    sub.add_parser("status", help="Print C4 status as JSON")
    args = parser.parse_args()
    home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    if args.cmd == "get" or args.cmd is None:
        print(read_profile(home))
        return 0
    if args.cmd == "set":
        profile = args.profile.upper()
        try:
            write_profile(profile, home)
            _refresh_ui(home, install)
            print(f"Profile set: {profile}")
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.cmd == "status":
        status = cinema_auto_status(home, install)
        print(json.dumps(status, indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
