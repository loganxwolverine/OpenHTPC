#!/usr/bin/env python3
"""Derive OPENHTPC optical-media UI artwork from Steve's supplied masters.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "payload/assets/ui"

SPECS = {
    "Dvd_logo.jpg": {
        "media": ("dvd-media.png", (160, 24, 1248, 752), (1024, 688)),
        "badge": ("dvd-media-badge.png", (300, 72, 1108, 450), (512, 256)),
    },
    "bluray_logo.jpg": {
        "media": ("bluray-media.png", (160, 24, 1248, 752), (1024, 688)),
        "badge": ("bluray-media-badge.png", (220, 68, 1190, 452), (512, 256)),
    },
    "bluray_UH_4K_logo.jpg": {
        "media": ("uhd-bluray-media.png", (160, 8, 1248, 752), (1024, 700)),
        "badge": ("uhd-bluray-media-badge.png", (220, 8, 1190, 444), (512, 256)),
    },
}


def derive(source: pathlib.Path, crop: tuple[int, int, int, int], size: tuple[int, int]) -> Image.Image:
    with Image.open(source) as master:
        master.load()
        cropped = master.convert("RGB").crop(crop)
    fitted = ImageOps.contain(cropped, (size[0] - 8, size[1] - 8), method=Image.Resampling.LANCZOS)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(fitted.convert("RGBA"), ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=pathlib.Path)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for master_name, variants in SPECS.items():
        source = args.source_dir / master_name
        if not source.is_file():
            raise FileNotFoundError(source)
        for output_name, crop, size in variants.values():
            derive(source, crop, size).save(OUTPUT / output_name, optimize=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
