# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV3: Descriptor Ingestion.

Tests are isolated, do NOT touch ~/.local/share/openhtpc/media/media.db,
and verify transactional integrity, idempotence, and absence of identity guessing.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"

ingest_spec = importlib.util.spec_from_file_location("media_ingest", INGEST_PATH)
media_ingest = importlib.util.module_from_spec(ingest_spec)
ingest_spec.loader.exec_module(media_ingest)

probe_spec = importlib.util.spec_from_file_location("media_probe", PROBE_PATH)
media_probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(media_probe)

db_spec = importlib.util.spec_from_file_location("media_db", DB_PATH)
media_db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(media_db)

media_ingest.set_media_probe_module(media_probe)
media_ingest.set_media_db_module(media_db)


@pytest.fixture
def test_db(tmp_path):
    """Create and initialize a temporary isolated media.db."""
    db_file = tmp_path / "media/test_media.db"
    media_db.initialize(db_file)
    return db_file


@pytest.fixture
def source_tree(tmp_path):
    """Create a temporary media source tree with sample files."""
    root = tmp_path / "media_root"
    root.mkdir(parents=True)
    dvd_dir = root / "Dvd"
    dvd_dir.mkdir()
    sample_file = dvd_dir / "Alerte.mkv"
    sample_file.write_bytes(b"\x00" * 4096)
    return root, sample_file


def _mock_probe_descriptor(file_path: Path, **overrides) -> dict:
    """Generate a realistic DEV2 descriptor without requiring real ffprobe."""
    try:
        canonical = str(file_path.resolve(strict=True))
    except OSError:
        canonical = str(file_path.absolute())
    st = file_path.stat() if file_path.exists() else None

    base = {
        "ok": True,
        "resource": {
            "supplied_path": str(file_path),
            "canonical_path": canonical,
            "file_size": st.st_size if st else 4096,
            "mtime_ns": st.st_mtime_ns if st else 1700000000000000000,
            "mtime_iso": "2026-09-11T12:00:00+00:00",
            "container_format": "matroska,webm",
            "duration_seconds": 5400.123,
            "bitrate": 4500000,
        },
        "video_streams": [
            {
                "stream_index": 0,
                "codec": "mpeg2video",
                "profile": "Main",
                "width": 720,
                "height": 576,
                "pixel_format": "yuv420p",
                "bit_depth": 8,
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
                "frame_rate_num": 25,
                "frame_rate_den": 1,
                "fps": 25.0,
                "field_order": "tt",
                "sample_aspect_ratio": "16/15",
                "display_aspect_ratio": "4/3",
                "color_primaries": None,
                "color_transfer": None,
                "color_matrix": None,
                "hdr_format": None,
                "dolby_vision_profile": None,
                "duration_seconds": 5400.123,
                "is_default": True,
            }
        ],
        "audio_streams": [
            {
                "stream_index": 1,
                "codec": "ac3",
                "profile": None,
                "channels": 6,
                "channel_layout": "5.1(side)",
                "sample_rate": 48000,
                "bitrate": 384000,
                "language": "fre",
                "title": "Surround 5.1",
                "is_default": True,
            },
            {
                "stream_index": 2,
                "codec": "ac3",
                "profile": None,
                "channels": 2,
                "channel_layout": "stereo",
                "sample_rate": 48000,
                "bitrate": 192000,
                "language": "eng",
                "title": "Stereo",
                "is_default": False,
            },
            {
                "stream_index": 3,
                "codec": "ac3",
                "profile": None,
                "channels": 2,
                "channel_layout": "stereo",
                "sample_rate": 48000,
                "bitrate": 192000,
                "language": "fre",
                "title": "Commentary",
                "is_default": False,
            },
        ],
        "subtitle_streams": [
            {
                "stream_index": 4,
                "codec": "dvd_subtitle",
                "language": "fre",
                "title": "Francais",
                "is_default": False,
                "is_forced": False,
            },
            {
                "stream_index": 5,
                "codec": "dvd_subtitle",
                "language": "eng",
                "title": "English",
                "is_default": False,
                "is_forced": False,
            },
        ],
    }
    base.update(overrides)
    return base


def test_1_fresh_explicit_file_ingestion(test_db, source_tree, monkeypatch):
    """First ingestion creates 1 media_version, 1 resource, and exact stream rows."""
    root, sample_file = source_tree
    desc = _mock_probe_descriptor(sample_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is True
    assert res["action"] == "inserted"
    assert res["relative_path"] == "Dvd/Alerte.mkv"
    expected_sid = hashlib.blake2s(os.fsencode(root.resolve()), digest_size=8).hexdigest()
    assert res["source_id"] == expected_sid
    assert res["streams"] == {"video": 1, "audio": 3, "subtitle": 2}

    with closing(media_db.connect(test_db)) as db:
        stats = media_db.stats(db)
        assert stats["media_versions"] == 1
        assert stats["resources"] == 1
        assert stats["video_streams"] == 1
        assert stats["audio_streams"] == 3
        assert stats["subtitle_streams"] == 2
        # Zero work or candidate records
        assert stats["works"] == 0
        assert stats["external_ids"] == 0
        assert stats["match_candidates"] == 0

        # Verify media_version details
        mv = db.execute("SELECT work_id, identification_state, match_locked, duration_seconds FROM media_versions").fetchone()
        assert mv[0] is None  # work_id remains NULL!
        assert mv[1] == "UNMATCHED"
        assert mv[2] == 0
        assert mv[3] == pytest.approx(5400.123)

        # Verify resource details
        r = db.execute("SELECT resource_kind, source_id, relative_path, file_size, availability_status FROM resources").fetchone()
        assert r[0] == "FILE"
        assert r[1] == expected_sid
        assert r[2] == "Dvd/Alerte.mkv"
        assert r[3] == 4096
        assert r[4] == "AVAILABLE"

        # Verify video_stream facts
        vs = db.execute("SELECT stream_index, codec, profile, width, height, frame_rate_num, frame_rate_den, bit_depth, is_default FROM video_streams").fetchone()
        assert vs == (0, "mpeg2video", "Main", 720, 576, 25, 1, 8, 1)

        # Verify audio_stream facts (atmos and dtsx must NOT be inferred)
        audio_rows = db.execute("SELECT stream_index, codec, channels, sample_rate, language, atmos, dtsx, is_default FROM audio_streams ORDER BY stream_index").fetchall()
        assert len(audio_rows) == 3
        assert audio_rows[0] == (1, "ac3", 6, 48000, "fre", 0, 0, 1)
        assert audio_rows[1] == (2, "ac3", 2, 48000, "eng", 0, 0, 0)
        assert audio_rows[2] == (3, "ac3", 2, 48000, "fre", 0, 0, 0)

        # Verify subtitle_stream facts
        sub_rows = db.execute("SELECT stream_index, codec, language, is_default, is_forced FROM subtitle_streams ORDER BY stream_index").fetchall()
        assert len(sub_rows) == 2
        assert sub_rows[0] == (4, "dvd_subtitle", "fre", 0, 0)
        assert sub_rows[1] == (5, "dvd_subtitle", "eng", 0, 0)

        # Referential integrity
        integrity = media_db.check_integrity(db)
        assert integrity["ok"] is True


def test_2_idempotence_identical_reingest_no_duplicates(test_db, source_tree, monkeypatch):
    """Ingesting the same file a second time MUST NOT create duplicate rows."""
    root, sample_file = source_tree
    desc = _mock_probe_descriptor(sample_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    res1 = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res1["ok"] is True
    assert res1["action"] == "inserted"
    vid1 = res1["media_version_id"]
    rid1 = res1["resource_id"]

    # Re-ingest
    res2 = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res2["ok"] is True
    assert res2["action"] == "updated"
    assert res2["media_version_id"] == vid1
    assert res2["resource_id"] == rid1

    with closing(media_db.connect(test_db)) as db:
        stats = media_db.stats(db)
        assert stats["media_versions"] == 1
        assert stats["resources"] == 1
        assert stats["video_streams"] == 1
        assert stats["audio_streams"] == 3
        assert stats["subtitle_streams"] == 2
        assert stats["works"] == 0
        assert media_db.check_integrity(db)["ok"] is True


def test_3_reingest_refreshes_streams_without_stale_accumulation(test_db, source_tree, monkeypatch):
    """When stream layout changes, re-ingest cleanly replaces streams."""
    root, sample_file = source_tree
    desc1 = _mock_probe_descriptor(sample_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc1)
    media_ingest.ingest_file(sample_file, root, db_path=test_db)

    # Now simulate modified file with only 1 audio stream and 0 subtitles
    desc2 = _mock_probe_descriptor(sample_file)
    desc2["audio_streams"] = [
        {
            "stream_index": 1,
            "codec": "aac",
            "channels": 2,
            "sample_rate": 44100,
            "language": "eng",
            "is_default": True,
        }
    ]
    desc2["subtitle_streams"] = []
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc2)

    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is True
    assert res["action"] == "updated"
    assert res["streams"] == {"video": 1, "audio": 1, "subtitle": 0}

    with closing(media_db.connect(test_db)) as db:
        stats = media_db.stats(db)
        assert stats["media_versions"] == 1
        assert stats["resources"] == 1
        assert stats["video_streams"] == 1
        assert stats["audio_streams"] == 1  # 3 rows cleanly replaced by 1 row
        assert stats["subtitle_streams"] == 0  # 2 rows cleanly removed

        audio = db.execute("SELECT codec, sample_rate FROM audio_streams").fetchone()
        assert audio == ("aac", 44100)


def test_4_work_identification_remains_optional_and_null(test_db, source_tree, monkeypatch):
    """Work guessing from filename or path is forbidden."""
    root, _ = source_tree
    movie_file = root / "The Matrix (1999) 4K Remastered.mkv"
    movie_file.write_bytes(b"\x00" * 1024)

    desc = _mock_probe_descriptor(movie_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    res = media_ingest.ingest_file(movie_file, root, db_path=test_db)
    assert res["ok"] is True

    with closing(media_db.connect(test_db)) as db:
        mv = db.execute("SELECT work_id, provisional_title, provisional_year FROM media_versions").fetchone()
        assert mv[0] is None
        assert mv[1] is None
        assert mv[2] is None
        assert db.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0] == 0


def test_5_path_escape_and_outside_source_root_rejected(test_db, tmp_path, monkeypatch):
    """Files outside source root or escaping paths are strictly rejected."""
    root = tmp_path / "valid_root"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "unauthorized.mkv"
    outside_file.write_bytes(b"\x00" * 100)

    monkeypatch.setattr(media_probe, "probe", lambda *a, **kw: _mock_probe_descriptor(outside_file))

    res = media_ingest.ingest_file(outside_file, root, db_path=test_db)
    assert res["ok"] is False
    assert res["error"] == "PATH_VALIDATION_FAILED"
    assert "outside source root" in res["message"]

    with closing(media_db.connect(test_db)) as db:
        assert media_db.stats(db)["resources"] == 0


def test_6_missing_media_file_zero_db_mutation(test_db, source_tree):
    """Missing media file fails clearly without mutating database."""
    root, _ = source_tree
    missing_file = root / "Dvd/Does_Not_Exist.mkv"

    res = media_ingest.ingest_file(missing_file, root, db_path=test_db)
    assert res["ok"] is False
    assert res["error"] == "PATH_VALIDATION_FAILED"

    with closing(media_db.connect(test_db)) as db:
        assert media_db.stats(db)["resources"] == 0
        assert media_db.stats(db)["media_versions"] == 0


def test_7_probe_failure_zero_db_mutation(test_db, source_tree, monkeypatch):
    """When DEV2 probe fails, database remains completely untouched."""
    root, sample_file = source_tree
    probe_fail = {
        "ok": False,
        "error": "FFPROBE_NONZERO_EXIT",
        "message": "ffprobe corrupted input error",
    }
    monkeypatch.setattr(media_probe, "probe", lambda *a, **kw: probe_fail)

    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is False
    assert res["error"] == "PROBE_FAILED"

    with closing(media_db.connect(test_db)) as db:
        assert media_db.stats(db)["resources"] == 0
        assert media_db.stats(db)["media_versions"] == 0


def test_8_malformed_descriptor_zero_db_mutation(test_db, source_tree, monkeypatch):
    """Malformed descriptor structure fails before DB persistence."""
    root, sample_file = source_tree
    malformed = {"ok": True, "resource": "not_a_dict"}
    monkeypatch.setattr(media_probe, "probe", lambda *a, **kw: malformed)

    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is False
    assert res["error"] == "DESCRIPTOR_INVALID"

    with closing(media_db.connect(test_db)) as db:
        assert media_db.stats(db)["resources"] == 0
        assert media_db.stats(db)["media_versions"] == 0


def test_9_transactional_rollback_on_db_error(test_db, source_tree, monkeypatch):
    """If DB error occurs during stream insertion, media_version and resource are rolled back."""
    root, sample_file = source_tree
    desc = _mock_probe_descriptor(sample_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    # Ingest once cleanly
    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is True

    # Now ingest a new file whose descriptor causes a stream constraint failure
    sample2 = root / "Dvd/Corrupted_Streams.mkv"
    sample2.write_bytes(b"\x00" * 2048)
    desc2 = _mock_probe_descriptor(sample2)
    # Duplicate stream_index 0 triggers UNIQUE(resource_id, stream_index) constraint
    desc2["video_streams"] = [
        {"stream_index": 0, "codec": "h264", "width": 1920, "height": 1080},
        {"stream_index": 0, "codec": "h264", "width": 1920, "height": 1080},
    ]
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc2)

    res2 = media_ingest.ingest_file(sample2, root, db_path=test_db)
    assert res2["ok"] is False
    assert res2["error"] == "DB_PERSISTENCE_FAILED"

    # Verify state rolled back to first clean ingest state (sample2 completely rolled back)
    with closing(media_db.connect(test_db)) as db:
        assert media_db.stats(db)["media_versions"] == 1
        assert media_db.stats(db)["resources"] == 1
        assert media_db.stats(db)["video_streams"] == 1
        assert media_db.check_integrity(db)["ok"] is True


def test_10_unknown_technical_values_remain_null(test_db, source_tree, monkeypatch):
    """Unknown or missing stream facts remain NULL rather than guessed defaults."""
    root, sample_file = source_tree
    desc = _mock_probe_descriptor(sample_file)
    desc["video_streams"][0]["profile"] = None
    desc["video_streams"][0]["color_primaries"] = None
    desc["audio_streams"][0]["language"] = None
    desc["audio_streams"][0]["title"] = None
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is True

    with closing(media_db.connect(test_db)) as db:
        vs = db.execute("SELECT profile, color_primaries FROM video_streams").fetchone()
        assert vs == (None, None)
        as_row = db.execute("SELECT language, title FROM audio_streams WHERE stream_index=1").fetchone()
        assert as_row == (None, None)


def test_11_cli_ingest_invocation(test_db):
    """CLI supports ingest subcommand and direct invocation."""
    benchmark_file = PAYLOAD / "assets/benchmark/c1_dvd_pal.mpg"
    benchmark_root = PAYLOAD / "assets/benchmark"
    if not benchmark_file.is_file():
        pytest.skip("Benchmark asset c1_dvd_pal.mpg not present")
    if subprocess.run(["which", "ffprobe"], capture_output=True).returncode != 0:
        pytest.skip("Real ffprobe is unavailable")

    env = {**os.environ, "PYTHONPATH": str(PAYLOAD)}

    cmd1 = [
        sys.executable,
        str(INGEST_PATH),
        "ingest",
        str(benchmark_file),
        "--source-root",
        str(benchmark_root),
        "--db",
        str(test_db),
    ]
    result1 = subprocess.run(cmd1, env=env, capture_output=True, text=True)
    assert result1.returncode == 0, f"CLI ingest failed: {result1.stderr} {result1.stdout}"
    data1 = json.loads(result1.stdout)
    assert data1["ok"] is True
    assert data1["action"] == "inserted"

    # Run direct CLI invocation (idempotent re-ingest)
    cmd2 = [
        sys.executable,
        str(INGEST_PATH),
        str(benchmark_file),
        "--source-root",
        str(benchmark_root),
        "--db",
        str(test_db),
    ]
    result2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
    assert result2.returncode == 0, f"CLI direct ingest failed: {result2.stderr} {result2.stdout}"
    data2 = json.loads(result2.stdout)
    assert data2["ok"] is True
    assert data2["action"] == "updated"
    assert data2["media_version_id"] == data1["media_version_id"]


def test_12_real_c1_dvd_pal_benchmark_ingestion(test_db):
    """Ingest committed c1_dvd_pal.mpg benchmark file using real probe."""
    benchmark_file = PAYLOAD / "assets/benchmark/c1_dvd_pal.mpg"
    benchmark_root = PAYLOAD / "assets/benchmark"
    if not benchmark_file.is_file():
        pytest.skip("Benchmark asset c1_dvd_pal.mpg not present")
    if shutil_which := subprocess.run(["which", "ffprobe"], capture_output=True).returncode != 0:
        pytest.skip("Real ffprobe is unavailable")

    res = media_ingest.ingest_file(benchmark_file, benchmark_root, db_path=test_db)
    assert res["ok"] is True
    assert res["action"] == "inserted"
    assert res["relative_path"] == "c1_dvd_pal.mpg"

    with closing(media_db.connect(test_db)) as db:
        stats = media_db.stats(db)
        assert stats["media_versions"] == 1
        assert stats["resources"] == 1
        assert stats["video_streams"] >= 1

        vs = db.execute("SELECT codec, width, height, frame_rate_num, frame_rate_den FROM video_streams").fetchone()
        assert vs == ("mpeg2video", 720, 576, 25, 1)

        # Re-ingest benchmark file: must be idempotent!
        res_dup = media_ingest.ingest_file(benchmark_file, benchmark_root, db_path=test_db)
        assert res_dup["ok"] is True
        assert res_dup["action"] == "updated"
        assert media_db.stats(db)["media_versions"] == 1
        assert media_db.stats(db)["resources"] == 1


def test_13_deployment_consistency():
    """Verify openhtpc-media-ingest.py is properly declared in managed files and installer."""
    name = INGEST_PATH.name
    manifest = (PAYLOAD / "managed-files.txt").read_text().splitlines()
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
    products = re.search(r"readonly PRODUCT_FILES=\(([^)]*)\)", installer).group(1).split()

    assert manifest.count(name) == 1, "openhtpc-media-ingest.py must appear exactly once in managed-files.txt"
    assert products.count(name) == 1, "openhtpc-media-ingest.py must appear exactly once in PRODUCT_FILES"
    assert INGEST_PATH.is_file(), "openhtpc-media-ingest.py must exist in payload/"
    assert os.access(INGEST_PATH, os.X_OK), "openhtpc-media-ingest.py must be executable"


def test_14_no_external_runtime_actions_or_side_effects(test_db, source_tree, monkeypatch):
    """Ingestion must not write to runtime logs, flex configs, or user-config."""
    root, sample_file = source_tree
    desc = _mock_probe_descriptor(sample_file)
    monkeypatch.setattr(media_probe, "probe", lambda *args, **kwargs: desc)

    # Ingest and confirm pure function behavior
    res = media_ingest.ingest_file(sample_file, root, db_path=test_db)
    assert res["ok"] is True

    # Check that test_db is the only file created/modified
    assert set(test_db.parent.glob("test_media.db*")) >= {test_db}
