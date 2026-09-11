#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Single-resource technical media probe.

Produces a normalized technical JSON descriptor for one explicitly supplied media file
using ffprobe. Does NOT scan directories, write to databases, identify works, or modify
runtime or configuration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any

# Default bounded timeout for ffprobe execution in seconds
DEFAULT_FFPROBE_TIMEOUT = 15.0


def parse_frame_rate(avg_rate: str | None, r_rate: str | None) -> tuple[int | None, int | None, float | None]:
    """Normalize positive rational evidence only when valid sources agree."""
    rates = set()
    for candidate in (avg_rate, r_rate):
        if not candidate or not isinstance(candidate, str) or candidate == "0/0":
            continue
        try:
            frac = Fraction(candidate)
            if frac.numerator > 0 and frac.denominator > 0:
                rates.add(frac)
        except (ValueError, ZeroDivisionError):
            continue
    if len(rates) == 1:
        rate = rates.pop()
        return rate.numerator, rate.denominator, round(float(rate), 6)
    return None, None, None


def parse_bit_depth(raw_bits: Any, pix_fmt: str | None) -> int | None:
    """Derive pixel bit depth when provable from stream metadata or pixel format."""
    if raw_bits is not None:
        try:
            val = int(raw_bits)
            if val in (8, 9, 10, 12, 14, 16):
                return val
        except (ValueError, TypeError):
            pass
    if isinstance(pix_fmt, str):
        fmt = pix_fmt.lower()
        if any(marker in fmt for marker in ("10le", "10be", "p10le", "p10be", "10")):
            return 10
        if any(marker in fmt for marker in ("12le", "12be", "p12le", "p12be", "12")):
            return 12
        if any(marker in fmt for marker in ("14le", "14be", "p14le", "p14be")):
            return 14
        if any(marker in fmt for marker in ("16le", "16be", "p16le", "p16be", "16")):
            return 16
        if any(marker in fmt for marker in ("yuv420p", "yuv422p", "yuv444p", "nv12", "yuyv422", "rgb24", "bgr24", "rgba", "bgra")):
            return 8
    return None


def parse_hdr(color_transfer: str | None, side_data_list: list[dict] | None) -> tuple[str | None, int | None]:
    """Expose normalized HDR technical facts when strictly supported by ffprobe evidence."""
    dv_profile: int | None = None
    has_dovi = False

    if isinstance(side_data_list, list):
        for entry in side_data_list:
            if not isinstance(entry, dict):
                continue
            data_type = str(entry.get("side_data_type", "")).lower()
            if "dovi" in data_type or "dolby vision" in data_type:
                has_dovi = True
                profile = entry.get("dv_profile")
                if profile is not None:
                    try:
                        dv_profile = int(profile)
                    except (ValueError, TypeError):
                        pass
                break

    if has_dovi:
        return "Dolby Vision", dv_profile

    transfer = (color_transfer or "").lower()
    if transfer == "arib-std-b67":
        return "HLG", None

    return None, None


def normalize_video_stream(stream: dict[str, Any], index_fallback: int) -> dict[str, Any]:
    """Map raw ffprobe video stream to normalized technical facts."""
    stream_index = stream.get("index")
    try:
        idx = int(stream_index) if stream_index is not None else index_fallback
    except (ValueError, TypeError):
        idx = index_fallback

    width = stream.get("width")
    height = stream.get("height")
    width_val = int(width) if isinstance(width, int) or (isinstance(width, str) and width.isdigit()) else None
    height_val = int(height) if isinstance(height, int) or (isinstance(height, str) and height.isdigit()) else None

    avg_rate = stream.get("avg_frame_rate")
    r_rate = stream.get("r_frame_rate")
    rate_num, rate_den, fps = parse_frame_rate(avg_rate, r_rate)

    bit_depth = parse_bit_depth(stream.get("bits_per_raw_sample"), stream.get("pix_fmt"))
    hdr_format, dovi_profile = parse_hdr(stream.get("color_transfer"), stream.get("side_data_list"))

    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    language = tags.get("language") or tags.get("LANGUAGE")
    if language:
        language = str(language).strip()

    disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}

    duration_sec = None
    if stream.get("duration"):
        try:
            duration_sec = round(float(stream["duration"]), 6)
        except (ValueError, TypeError):
            pass

    bit_rate = None
    if stream.get("bit_rate"):
        try:
            bit_rate = int(stream["bit_rate"])
        except (ValueError, TypeError):
            pass

    return {
        "stream_index": idx,
        "codec": stream.get("codec_name"),
        "profile": stream.get("profile"),
        "width": width_val,
        "height": height_val,
        "pixel_format": stream.get("pix_fmt"),
        "bit_depth": bit_depth,
        "avg_frame_rate": avg_rate,
        "r_frame_rate": r_rate,
        "frame_rate_num": rate_num,
        "frame_rate_den": rate_den,
        "fps": fps,
        "field_order": stream.get("field_order"),
        "color_range": stream.get("color_range"),
        "color_space": stream.get("color_space"),
        "color_matrix": stream.get("color_space"),
        "color_transfer": stream.get("color_transfer"),
        "color_primaries": stream.get("color_primaries"),
        "side_data_list": stream.get("side_data_list"),
        "hdr_format": hdr_format,
        "dolby_vision_profile": dovi_profile,
        "sample_aspect_ratio": stream.get("sample_aspect_ratio"),
        "display_aspect_ratio": stream.get("display_aspect_ratio"),
        "duration_seconds": duration_sec,
        "bitrate": bit_rate,
        "language": language,
        "is_default": bool(disposition.get("default", 0) == 1),
        "is_forced": bool(disposition.get("forced", 0) == 1),
    }


def normalize_audio_stream(stream: dict[str, Any], index_fallback: int) -> dict[str, Any]:
    """Map raw ffprobe audio stream to normalized technical facts."""
    stream_index = stream.get("index")
    try:
        idx = int(stream_index) if stream_index is not None else index_fallback
    except (ValueError, TypeError):
        idx = index_fallback

    channels = stream.get("channels")
    channels_val = int(channels) if isinstance(channels, int) or (isinstance(channels, str) and channels.isdigit()) else None

    sample_rate = stream.get("sample_rate")
    sample_rate_val = int(sample_rate) if isinstance(sample_rate, int) or (isinstance(sample_rate, str) and sample_rate.isdigit()) else None

    bit_rate = None
    if stream.get("bit_rate"):
        try:
            bit_rate = int(stream["bit_rate"])
        except (ValueError, TypeError):
            pass

    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    language = tags.get("language") or tags.get("LANGUAGE")
    title = tags.get("title") or tags.get("TITLE")
    profile = stream.get("profile")

    disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}

    return {
        "stream_index": idx,
        "codec": stream.get("codec_name"),
        "profile": profile,
        "channels": channels_val,
        "channel_layout": stream.get("channel_layout"),
        "sample_rate": sample_rate_val,
        "bitrate": bit_rate,
        "language": str(language).strip() if language else None,
        "title": str(title).strip() if title else None,
        "is_default": bool(disposition.get("default", 0) == 1),
        "is_forced": bool(disposition.get("forced", 0) == 1),
    }


def normalize_subtitle_stream(stream: dict[str, Any], index_fallback: int) -> dict[str, Any]:
    """Map raw ffprobe subtitle stream to normalized technical facts."""
    stream_index = stream.get("index")
    try:
        idx = int(stream_index) if stream_index is not None else index_fallback
    except (ValueError, TypeError):
        idx = index_fallback

    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    language = tags.get("language") or tags.get("LANGUAGE")
    title = tags.get("title") or tags.get("TITLE")
    disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}

    return {
        "stream_index": idx,
        "codec": stream.get("codec_name"),
        "language": str(language).strip() if language else None,
        "title": str(title).strip() if title else None,
        "is_default": bool(disposition.get("default", 0) == 1),
        "is_forced": bool(disposition.get("forced", 0) == 1),
    }


def probe_raw_ffprobe(path: Path, ffprobe_bin: str | None = None, timeout: float = DEFAULT_FFPROBE_TIMEOUT) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Invoke ffprobe in a bounded subprocess and parse the output JSON.

    Returns (raw_json_dict, error_dict).
    """
    binary = ffprobe_bin or shutil.which("ffprobe")
    if not binary:
        return None, {
            "ok": False,
            "error": "FFPROBE_UNAVAILABLE",
            "message": "ffprobe binary not found on system PATH",
        }

    command = [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", "--", str(path)]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, {
            "ok": False,
            "error": "FFPROBE_TIMEOUT",
            "message": f"ffprobe timed out after {timeout} seconds",
        }
    except OSError as exc:
        return None, {
            "ok": False,
            "error": "FFPROBE_EXECUTION_ERROR",
            "message": f"Failed to execute ffprobe: {exc}",
        }

    if result.returncode != 0:
        return None, {
            "ok": False,
            "error": "FFPROBE_NONZERO_EXIT",
            "message": f"ffprobe exited with code {result.returncode}",
            "exit_code": result.returncode,
            "stderr": result.stderr.strip()[:1000] if result.stderr else "",
        }

    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            return None, {
                "ok": False,
                "error": "FFPROBE_MALFORMED_OUTPUT",
                "message": "ffprobe output is not a valid JSON object",
            }
        return data, None
    except json.JSONDecodeError as exc:
        return None, {
            "ok": False,
            "error": "FFPROBE_MALFORMED_OUTPUT",
            "message": f"Failed to parse ffprobe JSON output: {exc}",
        }


def normalize_descriptor(supplied_path: Path, file_stat: os.stat_result, probe_data: dict[str, Any]) -> dict[str, Any]:
    """Build canonical DEV2 descriptor from validated file stat and ffprobe raw data."""
    fmt = probe_data.get("format") if isinstance(probe_data.get("format"), dict) else {}
    streams = probe_data.get("streams") if isinstance(probe_data.get("streams"), list) else []

    duration_sec = None
    if fmt.get("duration"):
        try:
            duration_sec = round(float(fmt["duration"]), 6)
        except (ValueError, TypeError):
            pass

    overall_bitrate = None
    if fmt.get("bit_rate"):
        try:
            overall_bitrate = int(fmt["bit_rate"])
        except (ValueError, TypeError):
            pass

    try:
        canonical = str(supplied_path.resolve(strict=True))
    except OSError:
        canonical = str(supplied_path.absolute())

    mtime_dt = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)

    resource_info = {
        "supplied_path": str(supplied_path),
        "canonical_path": canonical,
        "file_size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
        "mtime_iso": mtime_dt.isoformat(),
        "container_format": fmt.get("format_name"),
        "duration_seconds": duration_sec,
        "bitrate": overall_bitrate,
    }

    video_streams: list[dict[str, Any]] = []
    audio_streams: list[dict[str, Any]] = []
    subtitle_streams: list[dict[str, Any]] = []

    for idx, stream in enumerate(streams):
        if not isinstance(stream, dict):
            continue
        codec_type = stream.get("codec_type")
        disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}
        if disposition.get("attached_pic"):
            # Attached pictures (embedded poster/cover) are not playable video streams
            continue
        if codec_type == "video":
            video_streams.append(normalize_video_stream(stream, idx))
        elif codec_type == "audio":
            audio_streams.append(normalize_audio_stream(stream, idx))
        elif codec_type == "subtitle":
            subtitle_streams.append(normalize_subtitle_stream(stream, idx))

    return {
        "ok": True,
        "resource": resource_info,
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "subtitle_streams": subtitle_streams,
    }


def probe(path_value: str | Path, ffprobe_bin: str | None = None, timeout: float = DEFAULT_FFPROBE_TIMEOUT) -> dict[str, Any]:
    """Execute bounded probe of a single media file and return normalized descriptor."""
    target_path = Path(path_value)

    if not target_path.exists():
        return {
            "ok": False,
            "error": "FILE_NOT_FOUND",
            "message": f"Media file not found: {target_path}",
            "supplied_path": str(target_path),
        }

    try:
        file_stat = target_path.stat()
    except OSError as exc:
        return {
            "ok": False,
            "error": "STAT_FAILED",
            "message": f"Cannot stat media file: {exc}",
            "supplied_path": str(target_path),
        }

    if not stat.S_ISREG(file_stat.st_mode):
        return {
            "ok": False,
            "error": "NOT_A_REGULAR_FILE",
            "message": f"Path is not a regular file: {target_path}",
            "supplied_path": str(target_path),
        }

    probe_data, err = probe_raw_ffprobe(target_path, ffprobe_bin=ffprobe_bin, timeout=timeout)
    if err is not None:
        err["supplied_path"] = str(target_path)
        return err

    return normalize_descriptor(target_path, file_stat, probe_data or {})


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for openhtpc-media-probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=False)

    probe_p = subparsers.add_parser("probe", help="Probe a single media file")
    probe_p.add_argument("path", help="Path to media file")
    probe_p.add_argument("--ffprobe", help="Path to custom ffprobe binary", default=None)
    probe_p.add_argument("--timeout", type=float, help="Timeout in seconds", default=DEFAULT_FFPROBE_TIMEOUT)

    # Fallback when run directly without subcommand: `openhtpc-media-probe.py /path/to/media.mkv`
    parser.add_argument("direct_path", nargs="?", help="Direct path to media file")
    parser.add_argument("--ffprobe", help="Path to custom ffprobe binary", default=None)
    parser.add_argument("--timeout", type=float, help="Timeout in seconds", default=DEFAULT_FFPROBE_TIMEOUT)

    args = parser.parse_args(argv)

    target_file = None
    ffprobe_bin = getattr(args, "ffprobe", None)
    timeout = getattr(args, "timeout", DEFAULT_FFPROBE_TIMEOUT)

    if args.action == "probe":
        target_file = args.path
    elif args.direct_path:
        target_file = args.direct_path

    if not target_file:
        parser.print_help(sys.stderr)
        return 2

    result = probe(target_file, ffprobe_bin=ffprobe_bin, timeout=timeout)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
