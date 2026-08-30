#!/usr/bin/env python3
"""Read-only capability model for externally configured protected optical media."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import ctypes
import ctypes.util
import os
import pathlib
import stat
from typing import Any, Callable


SUPPORT_STATES = {"NOT_AVAILABLE", "NOT_CONFIGURED", "AVAILABLE", "BLOCKED"}


def _library(name: str, finder: Callable[[str], str | None],
             loader: Callable[[str], Any]) -> dict[str, Any]:
    candidate = finder(name)
    if not candidate:
        return {"status": "NOT_AVAILABLE", "detected": False, "loadable": False}
    try:
        loader(candidate)
    except OSError:
        return {"status": "NOT_AVAILABLE", "detected": True, "loadable": False}
    return {"status": "AVAILABLE", "detected": True, "loadable": True}


def external_key_database(home: pathlib.Path, environment: dict[str, str] | None = None,
                          readable: Callable[[pathlib.Path, int], bool] = os.access) -> dict[str, Any]:
    """Detect KEYDB.cfg metadata without opening, reading, copying, or changing it."""
    values = os.environ if environment is None else environment
    configured = values.get("XDG_CONFIG_HOME")
    root = pathlib.Path(configured) if configured else home / ".config"
    path = root / "aacs" / "KEYDB.cfg"
    source = "XDG_CONFIG_HOME" if configured else "HOME_CONFIG_FALLBACK"
    try:
        metadata = path.lstat()
    except OSError:
        return {"status": "NOT_CONFIGURED", "detected": False, "regular": False,
                "readable": False, "source": source}
    regular = stat.S_ISREG(metadata.st_mode)
    can_read = regular and readable(path, os.R_OK)
    return {"status": "DETECTED" if can_read else "NOT_CONFIGURED",
            "detected": True, "regular": regular, "readable": bool(can_read),
            "source": source}


def detect(home: pathlib.Path, environment: dict[str, str] | None = None,
           finder: Callable[[str], str | None] = ctypes.util.find_library,
           loader: Callable[[str], Any] = ctypes.CDLL,
           readable: Callable[[pathlib.Path, int], bool] = os.access) -> dict[str, Any]:
    """Return a generic provider-ready model; never attempts decryption or playback."""
    libraries = {name: _library(name, finder, loader) for name in ("bluray", "aacs", "bdplus")}
    key_database = external_key_database(home, environment, readable)
    required = libraries["bluray"]["status"] == libraries["aacs"]["status"] == "AVAILABLE"
    support = ("NOT_AVAILABLE" if not required else
               "NOT_CONFIGURED" if key_database["status"] != "DETECTED" else "AVAILABLE")
    return {
        "capability": "PROTECTED_OPTICAL_SUPPORT",
        "status": support,
        "available": support == "AVAILABLE",
        "can_open_protected_optical_media": support == "AVAILABLE",
        "dependencies": {f"lib{name}": value for name, value in libraries.items()},
        "external_key_database": key_database,
    }


def status(model: dict[str, Any]) -> str:
    value = model.get("status")
    return value if value in SUPPORT_STATES else "BLOCKED"


def available(model: dict[str, Any]) -> bool:
    return status(model) == "AVAILABLE"


def can_open_protected_optical_media(model: dict[str, Any]) -> bool:
    return available(model)
