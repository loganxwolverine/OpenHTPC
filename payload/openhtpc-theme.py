#!/usr/bin/env python3
"""Canonical lightweight visual theme for OPENHTPC Basic Flex pages."""
from __future__ import annotations

import pathlib

COLORS = {
    "fallback": "#050B13",
    "panel": "#081525",
    "primary": "#00AEEF",
    "secondary": "#B8C7D9",
    "accent": "#F59E0B",
    "success": "#7ED957",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "text": "#FFFFFF",
}


def assets(install: pathlib.Path) -> dict[str, pathlib.Path]:
    root = install / "assets/branding"
    return {"logo": root / "openhtpc-logo.png", "wallpaper": root / "openhtpc-wallpaper.png"}


def background_block(install: pathlib.Path, opacity: int = 46) -> str:
    """Return an image background with an automatic dark-color fallback."""
    wallpaper = assets(install)["wallpaper"]
    if wallpaper.is_file():
        return (
            "[Background]\nMode=Image\n"
            f"Color={COLORS['fallback']}\nImage={wallpaper}\n"
            f"Overlay=true\nOverlayColor={COLORS['fallback']}\nOverlayOpacity={opacity}%"
        )
    return f"[Background]\nMode=Color\nColor={COLORS['fallback']}\nOverlay=false"


def highlight_block(accent: bool = False) -> str:
    color = COLORS["accent"] if accent else COLORS["primary"]
    return (
        "[Highlight]\nEnabled=true\n"
        f"FillColor={COLORS['panel']}\nFillOpacity=84%\n"
        f"OutlineSize=3\nOutlineColor={color}\nOutlineOpacity=100%\n"
        "CornerRadius=12\nVPadding=22\nHPadding=24"
    )


def title_block(font: pathlib.Path, size: int, padding: int) -> str:
    return (
        "[Titles]\nEnabled=true\n"
        f"Font={font}\nFontSize={size}\nColor={COLORS['text']}\nOpacity=100%\n"
        "Shadows=true\nShadowColor=#000000\nOversizeMode=Shrink\n"
        f"Padding={padding}"
    )
