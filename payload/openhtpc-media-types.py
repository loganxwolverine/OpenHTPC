#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Authoritative candidate media file extensions and helper functions.

Central authority for supported playable local media file extensions across
OpenHTPC navigation, dispatch, playback, and scanning.
"""
from __future__ import annotations

import os
from pathlib import Path

# Authoritative set of supported video file extensions (all lowercase, leading dot).
VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".mov",
    ".webm",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts",
    ".vob",
})


def is_candidate_media_file(name_or_path: str | Path) -> bool:
    """Return True if filename or path has a supported media extension and is not hidden.

    Hidden files (starting with '.') are excluded.
    Matching is strictly case-insensitive.
    """
    name = Path(name_or_path).name
    if name.startswith("."):
        return False
    ext = os.path.splitext(name)[1].casefold()
    return ext in VIDEO_EXTENSIONS
