#!/usr/bin/env python3
"""Summarize an explicit physical codec-validation MPV run without claiming validation."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any


def match(pattern: str, text: str) -> str | None:
    found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return found.group(1).strip() if found else None


def summarize(label: str, log: str, probe: dict[str, Any], rc: int, requested: str | None,
              render_node: str | None, visually_fluid: bool) -> dict[str, Any]:
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), {})
    hwdec = match(r"Using hardware decoding\s*\(([^)]+)\)", log)
    vo = match(r"\bVO:\s*\[([^]]+)\]", log)
    software = not hwdec and bool(vo)
    metrics = re.findall(r"OPENHTPC_METRICS\s+vo_drop=(\d+)\s+decoder_drop=(\d+)", log)
    vo_drops, decoder_drops = (map(int, metrics[-1]) if metrics else (None, None))
    errors = []
    for line in log.splitlines():
        if re.search(r"Error decoding|Could not open codec|Failed to initialize video|Exiting.*(?:error|fatal)", line, re.I):
            clean = line.strip()
            if clean and clean not in errors:
                errors.append(clean[:500])
    return {
        "schema": 1,
        "test_label": label,
        "source": {
            "codec": stream.get("codec_name") or match(r"\bVideo\s+--vid=\d+\s+\(([^,\s)]+)", log),
            "profile": stream.get("profile"),
            "pixel_format": stream.get("pix_fmt"),
            "bit_depth": 10 if "10" in str(stream.get("pix_fmt") or "") else 8 if stream.get("pix_fmt") else None,
        },
        "decode": {
            "requested": requested,
            "observed": hwdec if hwdec else "software" if software else None,
            "software_fallback": software,
            "render_node": render_node,
        },
        "playback": {
            "mpv_exit_code": rc,
            "clean_exit": rc == 0,
            "vo": vo,
            "vo_dropped_frames": vo_drops,
            "decoder_dropped_frames": decoder_drops,
            "decoder_errors": errors,
            "visually_fluid_confirmed_by_operator": visually_fluid,
            "physical_qualification": "PENDING_REVIEW",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--log", required=True, type=pathlib.Path)
    parser.add_argument("--probe", required=True, type=pathlib.Path)
    parser.add_argument("--mpv-exit", required=True, type=int)
    parser.add_argument("--requested")
    parser.add_argument("--render-node")
    parser.add_argument("--visually-fluid", choices=("yes", "no"), default="no")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        log = args.log.read_text(encoding="utf-8", errors="replace")
        probe = json.loads(args.probe.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    result = summarize(args.label, log, probe, args.mpv_exit, args.requested, args.render_node,
                       args.visually_fluid == "yes")
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
