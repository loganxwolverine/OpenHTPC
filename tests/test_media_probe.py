# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Focused automated tests for Media Foundation DEV2: Media Probe."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"

spec = importlib.util.spec_from_file_location("media_probe", PROBE_PATH)
media_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media_probe)

db_spec = importlib.util.spec_from_file_location("media_db", DB_PATH)
media_db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(media_db)


@pytest.fixture
def dummy_video(tmp_path):
    """Create a dummy regular file for stat and path testing."""
    f = tmp_path / "sample_video.mkv"
    f.write_bytes(b"\x00" * 4096)
    return f


def test_1_simple_progressive_video_descriptor(monkeypatch, dummy_video):
    """Verify simple progressive 1080p video descriptor."""
    mock_raw = {
        "format": {
            "format_name": "matroska,webm",
            "duration": "120.500000",
            "size": "4096",
            "bit_rate": "5000000",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "profile": "High",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "bits_per_raw_sample": "8",
                "avg_frame_rate": "24/1",
                "r_frame_rate": "24/1",
                "field_order": "progressive",
                "color_range": "tv",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "duration": "120.500000",
                "disposition": {"default": 1, "forced": 0},
                "tags": {"language": "eng"},
            }
        ],
    }

    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    resource = res["resource"]
    assert resource["supplied_path"] == str(dummy_video)
    assert resource["canonical_path"] == str(dummy_video.resolve())
    assert resource["file_size"] == 4096
    assert resource["container_format"] == "matroska,webm"
    assert resource["duration_seconds"] == 120.5
    assert resource["bitrate"] == 5000000

    assert len(res["video_streams"]) == 1
    v = res["video_streams"][0]
    assert v["stream_index"] == 0
    assert v["codec"] == "h264"
    assert v["profile"] == "High"
    assert v["width"] == 1920
    assert v["height"] == 1080
    assert v["pixel_format"] == "yuv420p"
    assert v["bit_depth"] == 8
    assert v["avg_frame_rate"] == "24/1"
    assert v["frame_rate_num"] == 24
    assert v["frame_rate_den"] == 1
    assert v["fps"] == 24.0
    assert v["field_order"] == "progressive"
    assert v["color_range"] == "tv"
    assert v["color_space"] == "bt709"
    assert v["color_matrix"] == "bt709"
    assert v["color_transfer"] == "bt709"
    assert v["color_primaries"] == "bt709"
    assert v["hdr_format"] is None
    assert v["language"] == "eng"
    assert v["is_default"] is True
    assert v["is_forced"] is False


def test_2_pal_dvd_case_720x576_mpeg2_interlaced_tt(monkeypatch, dummy_video):
    """MPEG-2 Main 720x576 25/1 fps field_order=tt must be valid and preserved."""
    mock_raw = {
        "format": {
            "format_name": "mpeg",
            "duration": "18.000000",
            "size": "9103360",
            "bit_rate": "4045937",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "mpeg2video",
                "profile": "Main",
                "width": 720,
                "height": 576,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
                "field_order": "tt",
                "color_range": "tv",
                "sample_aspect_ratio": "64:45",
                "display_aspect_ratio": "16:9",
                "duration": "18.000000",
                "disposition": {"default": 0, "forced": 0},
            }
        ],
    }

    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    assert len(res["video_streams"]) == 1
    v = res["video_streams"][0]
    assert v["codec"] == "mpeg2video"
    assert v["profile"] == "Main"
    assert v["width"] == 720
    assert v["height"] == 576
    assert v["fps"] == 25.0
    assert v["frame_rate_num"] == 25
    assert v["frame_rate_den"] == 1
    assert v["field_order"] == "tt"
    assert v["bit_depth"] == 8
    assert v["sample_aspect_ratio"] == "64:45"
    assert v["display_aspect_ratio"] == "16:9"


def test_3_1080p_fractional_frame_rate(monkeypatch, dummy_video):
    """Verify 1080p source with 24000/1001 (23.976) frame rate."""
    mock_raw = {
        "format": {"format_name": "matroska", "duration": "3600.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": "24000/1001",
                "r_frame_rate": "24000/1001",
                "field_order": "progressive",
            }
        ],
    }

    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    v = res["video_streams"][0]
    assert v["frame_rate_num"] == 24000
    assert v["frame_rate_den"] == 1001
    assert abs(v["fps"] - 23.976024) < 1e-5


def test_4_2160p_10bit_pq_facts_and_dovi(monkeypatch, dummy_video):
    """Preserve PQ facts without claiming HDR10; require explicit DOVI/HLG evidence."""
    # Subtest A: PQ transfer alone does not establish HDR10
    mock_pq = {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "60.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "profile": "Main 10",
                "width": 3840,
                "height": 2160,
                "pix_fmt": "yuv420p10le",
                "color_transfer": "smpte2084",
                "color_primaries": "bt2020",
                "color_space": "bt2020nc",
                "avg_frame_rate": "24/1",
            }
        ],
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_pq, None))
    res = media_probe.probe(dummy_video)
    v = res["video_streams"][0]
    assert v["bit_depth"] == 10
    assert v["hdr_format"] is None
    assert v["profile"] == "Main 10"
    assert v["color_space"] == "bt2020nc"
    assert v["dolby_vision_profile"] is None
    assert v["color_transfer"] == "smpte2084"
    assert v["color_primaries"] == "bt2020"

    # Subtest B: Dolby Vision side data
    mock_dovi = {
        "format": {"format_name": "matroska", "duration": "60.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "profile": "Main 10",
                "width": 3840,
                "height": 2160,
                "pix_fmt": "yuv420p10le",
                "color_transfer": "smpte2084",
                "side_data_list": [
                    {
                        "side_data_type": "DOVI configuration record",
                        "dv_profile": 7,
                        "dv_level": 6,
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_dovi, None))
    res_dovi = media_probe.probe(dummy_video)
    v_dovi = res_dovi["video_streams"][0]
    assert v_dovi["hdr_format"] == "Dolby Vision"
    assert v_dovi["dolby_vision_profile"] == 7
    assert v_dovi["side_data_list"] == mock_dovi["streams"][0]["side_data_list"]

    # Subtest C: HLG transfer
    mock_hlg = {
        "format": {"format_name": "matroska", "duration": "60.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "pix_fmt": "yuv420p10le",
                "color_transfer": "arib-std-b67",
            }
        ],
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_hlg, None))
    res_hlg = media_probe.probe(dummy_video)
    assert res_hlg["video_streams"][0]["hdr_format"] == "HLG"


def test_5_multiple_audio_streams_preserve_facts_without_object_inference(monkeypatch, dummy_video):
    """Preserve audio facts and free-form labels without inferring Atmos or DTS:X."""
    mock_raw = {
        "format": {"format_name": "matroska", "duration": "100.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "truehd",
                "profile": "TrueHD + Dolby Atmos",
                "channels": 8,
                "channel_layout": "7.1",
                "sample_rate": "48000",
                "bit_rate": "4500000",
                "disposition": {"default": 1, "forced": 0},
                "tags": {"language": "eng", "title": "Dolby TrueHD Atmos 7.1"},
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 6,
                "channel_layout": "5.1(side)",
                "sample_rate": "48000",
                "bit_rate": "640000",
                "disposition": {"default": 0, "forced": 0},
                "tags": {"language": "fra", "title": "VF AC3 5.1"},
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "dts",
                "profile": "DTS-HD MA",
                "channels": 8,
                "channel_layout": "7.1",
                "sample_rate": "48000",
                "disposition": {"default": 0, "forced": 0},
                "tags": {"language": "deu", "title": "DTS:X German"},
            },
        ],
    }

    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    audio = res["audio_streams"]
    assert len(audio) == 3
    for actual, raw in zip(audio, mock_raw["streams"]):
        assert "atmos" not in actual
        assert "dtsx" not in actual
        assert actual["profile"] == raw.get("profile")
        assert actual["title"] == raw["tags"]["title"]
        assert actual["bitrate"] == (int(raw["bit_rate"]) if "bit_rate" in raw else None)
        assert actual["is_forced"] is False

    # Stream 0: TrueHD Atmos
    assert audio[0]["stream_index"] == 0
    assert audio[0]["codec"] == "truehd"
    assert audio[0]["channels"] == 8
    assert audio[0]["channel_layout"] == "7.1"
    assert audio[0]["sample_rate"] == 48000
    assert audio[0]["language"] == "eng"
    assert audio[0]["is_default"] is True

    # Stream 1: AC3
    assert audio[1]["stream_index"] == 1
    assert audio[1]["codec"] == "ac3"
    assert audio[1]["channels"] == 6
    assert audio[1]["channel_layout"] == "5.1(side)"
    assert audio[1]["language"] == "fra"
    assert audio[1]["is_default"] is False

    # Stream 2: DTS:X
    assert audio[2]["stream_index"] == 2
    assert audio[2]["codec"] == "dts"
    assert audio[2]["language"] == "deu"


def test_6_subtitle_streams(monkeypatch, dummy_video):
    """Verify subtitle streams parsing with default/forced flags."""
    mock_raw = {
        "format": {"format_name": "matroska"},
        "streams": [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "fra", "title": "French Full"},
                "disposition": {"default": 1, "forced": 0},
            },
            {
                "index": 1,
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "fra", "title": "French Forced"},
                "disposition": {"default": 0, "forced": 1},
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "eng"},
                "disposition": {"default": 0, "forced": 0},
            },
        ],
    }

    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    subs = res["subtitle_streams"]
    assert len(subs) == 3

    assert subs[0]["stream_index"] == 0
    assert subs[0]["codec"] == "subrip"
    assert subs[0]["language"] == "fra"
    assert subs[0]["title"] == "French Full"
    assert subs[0]["is_default"] is True
    assert subs[0]["is_forced"] is False

    assert subs[1]["stream_index"] == 1
    assert subs[1]["codec"] == "hdmv_pgs_subtitle"
    assert subs[1]["language"] == "fra"
    assert subs[1]["is_default"] is False
    assert subs[1]["is_forced"] is True

    assert subs[2]["stream_index"] == 2
    assert subs[2]["codec"] == "ass"
    assert subs[2]["language"] == "eng"
    assert subs[2]["is_default"] is False
    assert subs[2]["is_forced"] is False


def test_7_missing_file():
    """Missing file must return explicit machine-readable error without crashing."""
    bogus = Path("/tmp/nonexistent_openhtpc_media_123456.mkv")
    res = media_probe.probe(bogus)
    assert res["ok"] is False
    assert res["error"] == "FILE_NOT_FOUND"
    assert "Media file not found" in res["message"]


def test_8_non_regular_input(tmp_path):
    """Non-regular file (directory) must be rejected with NOT_A_REGULAR_FILE."""
    res = media_probe.probe(tmp_path)
    assert res["ok"] is False
    assert res["error"] == "NOT_A_REGULAR_FILE"


def test_9_ffprobe_failure(dummy_video, monkeypatch):
    """Subprocess error / non-zero returncode must be handled gracefully."""
    err = {
        "ok": False,
        "error": "FFPROBE_NONZERO_EXIT",
        "message": "ffprobe exited with code 1",
        "exit_code": 1,
        "stderr": "Invalid data found when processing input",
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (None, err))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is False
    assert res["error"] == "FFPROBE_NONZERO_EXIT"
    assert res["exit_code"] == 1


def test_10_malformed_ffprobe_output(dummy_video, monkeypatch):
    """Invalid JSON from ffprobe must produce FFPROBE_MALFORMED_OUTPUT."""
    err = {
        "ok": False,
        "error": "FFPROBE_MALFORMED_OUTPUT",
        "message": "Failed to parse ffprobe JSON output",
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (None, err))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is False
    assert res["error"] == "FFPROBE_MALFORMED_OUTPUT"


def test_11_probing_never_modifies_media_db(tmp_path, dummy_video):
    """CLI probe must leave the canonical isolated Media Foundation DB untouched."""
    env = {**os.environ, "HOME": str(tmp_path),
           "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_STATE_HOME": str(tmp_path / "state")}
    subprocess.run([sys.executable, str(DB_PATH), "init"], env=env,
                   capture_output=True, text=True, check=True)
    db_file = media_db.database_path(environ=env, home=tmp_path)
    assert db_file == tmp_path / "data/openhtpc/media/media.db"
    with media_db.closing(media_db.connect(db_file)) as conn:
        stats_before = media_db.stats(conn)

    # A subprocess ffprobe stub makes this passivity test independent of host tools.
    raw = {"format": {"format_name": "matroska", "duration": "50.0"},
           "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264",
                        "width": 1280, "height": 720, "avg_frame_rate": "30/1"}]}
    ffprobe = tmp_path / "ffprobe-stub"
    ffprobe.write_text(f"#!{sys.executable}\nprint({json.dumps(raw)!r})\n")
    ffprobe.chmod(0o755)

    # Snapshot only after initialization and all initial inspections have closed.
    db_bytes_before = db_file.read_bytes()
    db_sha_before = hashlib.sha256(db_bytes_before).hexdigest()
    db_stat_before = db_file.stat()
    files_before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}

    cli_proc = subprocess.run(
        [sys.executable, str(PROBE_PATH), "probe", str(dummy_video),
         "--ffprobe", str(ffprobe)], env=env, capture_output=True, text=True, check=True)
    assert json.loads(cli_proc.stdout)["ok"] is True

    assert db_file.read_bytes() == db_bytes_before
    assert hashlib.sha256(db_file.read_bytes()).hexdigest() == db_sha_before
    assert db_file.stat().st_size == db_stat_before.st_size
    assert db_file.stat().st_mtime_ns == db_stat_before.st_mtime_ns
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == files_before
    # Immutable inspection avoids creating WAL/SHM files while checking row counts.
    with media_db.closing(sqlite3.connect(
            db_file.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        assert media_db.stats(conn) == stats_before



def test_12_audio_only_media_descriptor(monkeypatch, dummy_video):
    """Media with no video stream (e.g. music/podcast/audio track) must succeed with empty video_streams."""
    mock_raw = {
        "format": {"format_name": "flac", "duration": "180.0", "size": "2048"},
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "flac",
                "channels": 2,
                "channel_layout": "stereo",
                "sample_rate": "96000",
                "bits_per_raw_sample": "24",
                "tags": {"title": "High-Res Track"},
            }
        ],
    }
    monkeypatch.setattr(media_probe, "probe_raw_ffprobe", lambda *args, **kwargs: (mock_raw, None))

    res = media_probe.probe(dummy_video)
    assert res["ok"] is True
    assert res["video_streams"] == []
    assert len(res["audio_streams"]) == 1
    assert res["audio_streams"][0]["codec"] == "flac"
    assert res["audio_streams"][0]["sample_rate"] == 96000


def test_13_deployment_consistency():
    """Verify openhtpc-media-probe.py is in managed-files and PRODUCT_FILES."""
    name = "openhtpc-media-probe.py"
    manifest = (ROOT / "payload/managed-files.txt").read_text().splitlines()
    installer = (ROOT / "payload/install-openhtpc-fedora.sh").read_text()
    products = re.search(r"readonly PRODUCT_FILES=\(([^)]*)\)", installer).group(1).split()

    assert manifest.count(name) == 1, "openhtpc-media-probe.py must appear exactly once in managed-files.txt"
    assert products.count(name) == 1, "openhtpc-media-probe.py must appear exactly once in PRODUCT_FILES"
    assert (PAYLOAD / name).is_file(), "openhtpc-media-probe.py must exist in payload/"
    assert os.access(PAYLOAD / name, os.X_OK), "openhtpc-media-probe.py must be executable"


def test_14_real_c1_dvd_pal_benchmark_file():
    """Execute real probe on committed c1_dvd_pal.mpg benchmark asset."""
    pal_file = PAYLOAD / "assets/benchmark/c1_dvd_pal.mpg"
    if not pal_file.is_file():
        pytest.skip("Benchmark asset c1_dvd_pal.mpg not present")

    if shutil.which("ffprobe") is None:
        pytest.skip("Real ffprobe is unavailable")

    res = media_probe.probe(pal_file)
    assert res["ok"] is True
    assert res["resource"]["container_format"] == "mpeg"
    assert len(res["video_streams"]) >= 1
    v = res["video_streams"][0]
    assert v["codec"] == "mpeg2video"
    assert v["width"] == 720
    assert v["height"] == 576
    assert v["fps"] == 25.0
    assert v["frame_rate_num"] == 25
    assert v["frame_rate_den"] == 1
    assert v["avg_frame_rate"] == "25/1"
    assert v["r_frame_rate"] == "25/1"
    assert v["field_order"] == "progressive"


@pytest.mark.parametrize("avg,r_rate,expected", [
    ("24/1", "25/1", (None, None, None)),
    ("50/2", "25/1", (25, 1, 25.0)),
    ("25/1", "0/0", (25, 1, 25.0)),
    ("invalid", "25/1", (25, 1, 25.0)),
    (None, "25/1", (25, 1, 25.0)),
    ("25/1", None, (25, 1, 25.0)),
    ("0/1", "-25/1", (None, None, None)),
])
def test_frame_rate_evidence_agreement(avg, r_rate, expected):
    video = media_probe.normalize_video_stream(
        {"avg_frame_rate": avg, "r_frame_rate": r_rate}, 0)
    assert video["avg_frame_rate"] == avg
    assert video["r_frame_rate"] == r_rate
    assert (video["frame_rate_num"], video["frame_rate_den"], video["fps"]) == expected


def test_ffprobe_unavailable(dummy_video, monkeypatch):
    monkeypatch.setattr(media_probe.shutil, "which", lambda name: None)
    def unexpected_execution(*args, **kwargs):
        pytest.fail("Unavailable ffprobe must not be executed")
    monkeypatch.setattr(media_probe.subprocess, "run", unexpected_execution)
    raw, error = media_probe.probe_raw_ffprobe(dummy_video)
    assert raw is None
    assert error["ok"] is False
    assert error["error"] == "FFPROBE_UNAVAILABLE"
