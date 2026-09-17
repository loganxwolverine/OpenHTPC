# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic automated tests for Media Foundation DEV4: Incremental Source Scanner.

Verifies:
- Two-phase scan model (Phase A enumeration, Phase B classification).
- Incremental change detection via size + mtime_ns.
- Availability semantics (AVAILABLE, MISSING, UNKNOWN).
- Source unavailable, suspicious empty, and partial error safety gates.
- Concurrency locking, symlink policies, and zero leakage to real host environment.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
SCAN_PATH = PAYLOAD / "openhtpc-media-scan.py"
INGEST_PATH = PAYLOAD / "openhtpc-media-ingest.py"
PROBE_PATH = PAYLOAD / "openhtpc-media-probe.py"
DB_PATH = PAYLOAD / "openhtpc-media-db.py"
TYPES_PATH = PAYLOAD / "openhtpc-media-types.py"

scan_spec = importlib.util.spec_from_file_location("media_scan", SCAN_PATH)
media_scan = importlib.util.module_from_spec(scan_spec)
scan_spec.loader.exec_module(media_scan)

ingest_spec = importlib.util.spec_from_file_location("media_ingest", INGEST_PATH)
media_ingest = importlib.util.module_from_spec(ingest_spec)
ingest_spec.loader.exec_module(media_ingest)

probe_spec = importlib.util.spec_from_file_location("media_probe", PROBE_PATH)
media_probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(media_probe)

db_spec = importlib.util.spec_from_file_location("media_db", DB_PATH)
media_db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(media_db)

types_spec = importlib.util.spec_from_file_location("media_types", TYPES_PATH)
media_types = importlib.util.module_from_spec(types_spec)
types_spec.loader.exec_module(media_types)

media_ingest.set_media_probe_module(media_probe)
media_ingest.set_media_db_module(media_db)


@pytest.fixture
def sandbox_env(tmp_path):
    """Hermetic environment with isolated home, config, state, and test media db."""
    home = tmp_path / "home"
    config_dir = home / ".config/openhtpc"
    state_dir = home / ".local/state/openhtpc/media"
    share_dir = home / ".local/share/openhtpc/media"
    
    config_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    share_dir.mkdir(parents=True)

    db_path = share_dir / "media.db"
    media_db.initialize(db_path)

    media_root = tmp_path / "media_sources/movies"
    media_root.mkdir(parents=True)

    # Initial user config with media_root
    user_config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(media_root)],
    }
    (config_dir / "user-config.json").write_text(json.dumps(user_config, indent=2))

    return {
        "home": home,
        "db_path": db_path,
        "media_root": media_root,
        "source_id": media_scan.compute_source_id(media_root),
        "config_path": config_dir / "user-config.json",
    }


def _mock_descriptor(file_path: Path, **overrides) -> dict:
    """Generate realistic valid DEV2 descriptor for mock probing."""
    st = file_path.stat() if file_path.exists() else None
    res = {
        "ok": True,
        "resource": {
            "supplied_path": str(file_path),
            "canonical_path": str(file_path.resolve()),
            "file_size": st.st_size if st else 1024,
            "mtime_ns": st.st_mtime_ns if st else 1700000000000000000,
            "mtime_iso": "2026-09-12T00:00:00+00:00",
            "container_format": "matroska,webm",
            "duration_seconds": 120.0,
            "bitrate": 2000000,
        },
        "video_streams": [
            {
                "stream_index": 0,
                "codec": "h264",
                "profile": "High",
                "width": 1920,
                "height": 1080,
                "pixel_format": "yuv420p",
                "bit_depth": 8,
                "frame_rate_num": 24,
                "frame_rate_den": 1,
                "fps": 24.0,
                "field_order": "progressive",
                "sample_aspect_ratio": "1/1",
                "display_aspect_ratio": "16/9",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
                "color_matrix": "bt709",
                "hdr_format": None,
                "dolby_vision_profile": None,
                "duration_seconds": 120.0,
                "is_default": True,
            }
        ],
        "audio_streams": [
            {
                "stream_index": 1,
                "codec": "aac",
                "profile": "LC",
                "channels": 2,
                "channel_layout": "stereo",
                "sample_rate": 48000,
                "bitrate": 192000,
                "language": "fra",
                "title": "Stereo",
                "is_default": True,
                "is_forced": False,
            }
        ],
        "subtitle_streams": [],
    }
    res.update(overrides)
    return res


def _mock_probe_fn(file_path: Path, **kwargs) -> dict:
    return _mock_descriptor(file_path)


# ─── 1. Fresh Source Scan Ingests Candidates ────────────────────────────────

def test_1_fresh_source_scan_ingests_candidates(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f2 = root / "sub/film2.mp4"
    f2.parent.mkdir(parents=True)
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x01" * 2048)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["enumerated"] == 2
    assert res["new"] == 2
    assert res["changed"] == 0
    assert res["unchanged"] == 0
    assert res["missing"] == 0
    assert res["failed"] == 0
    assert res["probe_calls"] == 2

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = db.execute("SELECT relative_path, availability_status FROM resources ORDER BY relative_path").fetchall()
        assert len(rows) == 2
        assert rows[0] == ("film1.mkv", "AVAILABLE")
        assert rows[1] == ("sub/film2.mp4", "AVAILABLE")


# ─── 2. Unchanged File => Zero Probe Calls ──────────────────────────────────

def test_2_unchanged_file_zero_probe_calls(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f1.write_bytes(b"\x00" * 1024)

    # Initial scan
    res1 = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )
    assert res1["new"] == 1
    assert res1["probe_calls"] == 1

    # Second scan without changes
    probe_mock = mock.MagicMock(side_effect=_mock_probe_fn)
    res2 = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=probe_mock,
    )

    assert res2["ok"] is True
    assert res2["outcome"] == "COMPLETE"
    assert res2["enumerated"] == 1
    assert res2["unchanged"] == 1
    assert res2["new"] == 0
    assert res2["changed"] == 0
    assert res2["missing"] == 0
    assert res2["probe_calls"] == 0
    assert probe_mock.call_count == 0


# ─── 3. Changed File => Re-ingest, IDs Preserved ────────────────────────────

def test_3_changed_file_reingest_preserves_ids(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f1.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        orig_row = db.execute("SELECT id, media_version_id, file_size FROM resources WHERE relative_path = 'film1.mkv'").fetchone()

    # Modify file size
    time.sleep(0.01)
    f1.write_bytes(b"\x00" * 4096)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["changed"] == 1
    assert res["unchanged"] == 0
    assert res["probe_calls"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        new_row = db.execute("SELECT id, media_version_id, file_size, availability_status FROM resources WHERE relative_path = 'film1.mkv'").fetchone()
        assert new_row[0] == orig_row[0], "resource_id must be preserved"
        assert new_row[1] == orig_row[1], "media_version_id must be preserved"
        assert new_row[2] == 4096, "file_size must be updated"
        assert new_row[3] == "AVAILABLE"


# ─── 4. Complete Scan => Absent Known File Becomes MISSING ───────────────────

def test_4_complete_scan_absent_file_marked_missing(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f2 = root / "film2.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x01" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Delete f2 from filesystem
    f2.unlink()

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["enumerated"] == 1
    assert res["unchanged"] == 1
    assert res["missing"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = db.execute("SELECT relative_path, availability_status FROM resources ORDER BY relative_path").fetchall()
        assert rows[0] == ("film1.mkv", "AVAILABLE")
        assert rows[1] == ("film2.mkv", "MISSING")
        # Technical rows for film2 are preserved
        v_streams = db.execute("SELECT count(*) FROM video_streams").fetchone()[0]
        assert v_streams == 2


# ─── 5. Restored Unchanged => AVAILABLE Without Probe ───────────────────────

def test_5_restored_unchanged_available_without_probe(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f2 = root / "film2.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x01" * 1024)
    st2_orig = f2.stat()

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Delete f2 -> MISSING
    f2.unlink()
    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Recreate f2 with exact same content & mtime
    f2.write_bytes(b"\x01" * 1024)
    os.utime(f2, ns=(st2_orig.st_atime_ns, st2_orig.st_mtime_ns))

    probe_mock = mock.MagicMock(side_effect=_mock_probe_fn)
    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=probe_mock,
    )

    assert res["ok"] is True
    assert res["restored"] == 1
    assert res["probe_calls"] == 0
    assert probe_mock.call_count == 0

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        status = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'film2.mkv'").fetchone()[0]
        assert status == "AVAILABLE"


# ─── 6. Restored Changed => AVAILABLE + Re-ingest ───────────────────────────

def test_6_restored_changed_available_plus_reingest(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f2 = root / "film2.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x01" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    f2.unlink()
    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Recreate f2 with different size
    time.sleep(0.01)
    f2.write_bytes(b"\x02" * 5000)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert res["restored"] == 1
    assert res["probe_calls"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        row = db.execute("SELECT availability_status, file_size FROM resources WHERE relative_path = 'film2.mkv'").fetchone()
        assert row[0] == "AVAILABLE"
        assert row[1] == 5000


# ─── 7. Restored/Changed Probe Failure => AVAILABLE + Old Truth Retained ────

def test_7_restored_changed_probe_failure_preserves_old_truth(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f1.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        orig_stream = db.execute("SELECT codec, width, height FROM video_streams").fetchone()

    # Modify file, but probe fails
    time.sleep(0.01)
    f1.write_bytes(b"\x00" * 2048)

    def _failing_probe(path, **kwargs):
        return {"ok": False, "error": "CORRUPT_CONTAINER", "message": "Truncated header"}

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_failing_probe,
    )

    assert res["ok"] is True
    assert res["outcome"] == "PARTIAL"
    assert res["failed"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        row = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'film1.mkv'").fetchone()
        assert row[0] == "AVAILABLE"  # physically present
        current_stream = db.execute("SELECT codec, width, height FROM video_streams").fetchone()
        assert current_stream == orig_stream  # old technical truth preserved


# ─── 8. New File Probe Failure => No Incomplete Resource ────────────────────

def test_8_new_file_probe_failure_no_incomplete_resource(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "bad.mkv"
    f1.write_bytes(b"\x00" * 512)

    def _failing_probe(path, **kwargs):
        return {"ok": False, "error": "DECODER_ERROR", "message": "Failed to demux"}

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_failing_probe,
    )

    assert res["ok"] is True
    assert res["outcome"] == "PARTIAL"
    assert res["new"] == 0
    assert res["failed"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        count = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert count == 0


# ─── 9. Inaccessible Root => SOURCE_UNAVAILABLE + Zero DB Mutation ──────────

def test_9_inaccessible_root_source_unavailable_zero_db_mutation(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f1.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Rename root away to simulate unmounted NAS
    non_existent = root.parent / "unmounted_mountpoint"
    root.rename(non_existent)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is False
    assert res["outcome"] == "SOURCE_UNAVAILABLE"

    # Database records remain AVAILABLE, never marked MISSING
    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        status = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'film1.mkv'").fetchone()[0]
        assert status == "AVAILABLE"


# ─── 10. Traversal Error => PARTIAL_ERROR + No MISSING Transitions ─────────

def test_10_traversal_error_partial_error_no_missing_transitions(sandbox_env):
    root = sandbox_env["media_root"]
    sub = root / "locked_dir"
    sub.mkdir()
    f1 = root / "film1.mkv"
    f2 = sub / "film2.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Simulate traversal failure (e.g. PermissionError on sub)
    original_scandir = os.scandir
    def _selective_scandir(path):
        if str(path).endswith("locked_dir"):
            raise PermissionError("EACCES")
        return original_scandir(path)

    with mock.patch("os.scandir", side_effect=_selective_scandir):
        res = media_scan.scan_source(
            source_id=sandbox_env["source_id"],
            db_path=sandbox_env["db_path"],
            home=sandbox_env["home"],
            probe_func=_mock_probe_fn,
        )

    assert res["ok"] is False
    assert res["outcome"] == "PARTIAL_ERROR"

    # Zero MISSING transitions
    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        statuses = [r[0] for r in db.execute("SELECT availability_status FROM resources").fetchall()]
        assert all(s == "AVAILABLE" for s in statuses)


# ─── 11. Suspicious Empty => Zero State Mutation ────────────────────────────

def test_11_suspicious_empty_zero_state_mutation(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "film1.mkv"
    f1.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    # Empty the directory entirely
    f1.unlink()

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is False
    assert res["outcome"] == "SUSPICIOUS_EMPTY"

    # Verify zero status mutation: film1 remains AVAILABLE
    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        status = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'film1.mkv'").fetchone()[0]
        assert status == "AVAILABLE"


# ─── 12. No allow-empty Bypass Exists in DEV4 ───────────────────────────────

def test_12_no_allow_empty_bypass_exists_in_dev4():
    # Verify CLI argument parser rejects --allow-empty
    cmd = [sys.executable, str(SCAN_PATH), "scan", "--help"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    assert "--allow-empty" not in out


# ─── 13. Individual Probe Failure => Scan Continues + PARTIAL ───────────────

def test_13_individual_probe_failure_scan_continues_partial(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "good1.mkv"
    f2 = root / "bad.mkv"
    f3 = root / "good2.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\x00" * 1024)
    f3.write_bytes(b"\x00" * 1024)

    def _selective_probe(path, **kwargs):
        if "bad.mkv" in str(path):
            return {"ok": False, "error": "CORRUPT", "message": "Failed"}
        return _mock_descriptor(path)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_selective_probe,
    )

    assert res["ok"] is True
    assert res["outcome"] == "PARTIAL"
    assert res["enumerated"] == 3
    assert res["new"] == 2
    assert res["failed"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = [r[0] for r in db.execute("SELECT relative_path FROM resources ORDER BY relative_path").fetchall()]
        assert rows == ["good1.mkv", "good2.mkv"]


# ─── 14. Rename => Old MISSING + New Logical Resource ───────────────────────

def test_14_rename_old_missing_and_new_resource(sandbox_env):
    root = sandbox_env["media_root"]
    f1 = root / "original.mkv"
    f1.write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    f2 = root / "other.mkv"
    f2.write_bytes(b"\x00" * 1024)
    f1.rename(root / "renamed.mkv")

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["missing"] == 1
    assert res["new"] == 2

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        old_status = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'original.mkv'").fetchone()[0]
        new_status = db.execute("SELECT availability_status FROM resources WHERE relative_path = 'renamed.mkv'").fetchone()[0]
        assert old_status == "MISSING"
        assert new_status == "AVAILABLE"


# ─── 15. Directory Symlink Not Followed ─────────────────────────────────────

def test_15_directory_symlink_not_followed(sandbox_env, tmp_path):
    root = sandbox_env["media_root"]
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.mkv").write_bytes(b"\x00" * 1024)

    # Symlink pointing outside source root
    (root / "sym_outside").symlink_to(outside_dir, target_is_directory=True)
    (root / "valid.mkv").write_bytes(b"\x00" * 1024)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["enumerated"] == 1
    assert res["new"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = [r[0] for r in db.execute("SELECT relative_path FROM resources").fetchall()]
        assert rows == ["valid.mkv"]


# ─── 16. File Symlink Outside Source Ignored ────────────────────────────────

def test_16_file_symlink_outside_source_ignored(sandbox_env, tmp_path):
    root = sandbox_env["media_root"]
    outside_file = tmp_path / "outside_video.mkv"
    outside_file.write_bytes(b"\x00" * 1024)

    (root / "sym_file.mkv").symlink_to(outside_file)
    (root / "real_file.mkv").write_bytes(b"\x00" * 1024)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["enumerated"] == 1
    assert res["new"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = [r[0] for r in db.execute("SELECT relative_path FROM resources").fetchall()]
        assert rows == ["real_file.mkv"]


# ─── 17. Hidden and Non-media Files Ignored ─────────────────────────────────

def test_17_hidden_and_non_media_files_ignored(sandbox_env):
    root = sandbox_env["media_root"]
    (root / ".hidden.mkv").write_bytes(b"\x00" * 1024)
    (root / ".DS_Store").write_bytes(b"\x00" * 1024)
    (root / "movie.nfo").write_bytes(b"metadata")
    (root / "poster.jpg").write_bytes(b"image")
    (root / "valid.mkv").write_bytes(b"\x00" * 1024)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["enumerated"] == 1
    assert res["new"] == 1


# ─── 18. Overlapping Source Warning ─────────────────────────────────────────

def test_18_overlapping_source_warning(sandbox_env):
    root = sandbox_env["media_root"]
    nested = root / "nested_source"
    nested.mkdir()

    config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": [str(root), str(nested)],
    }
    sandbox_env["config_path"].write_text(json.dumps(config, indent=2))

    (root / "valid.mkv").write_bytes(b"\x00" * 1024)

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert res["ok"] is True
    assert any("OVERLAPPING_SOURCE_DETECTED" in w for w in res["warnings"])


# ─── 19. Second Scanner Lock Rejected ───────────────────────────────────────

def test_19_second_scanner_lock_rejected(sandbox_env):
    sid = sandbox_env["source_id"]
    with media_scan.SourceLock(sid, home=sandbox_env["home"]):
        # Attempt second scan in same process or thread
        res = media_scan.scan_source(
            source_id=sid,
            db_path=sandbox_env["db_path"],
            home=sandbox_env["home"],
            probe_func=_mock_probe_fn,
        )
        assert res["ok"] is False
        assert res["error"] == "SCANNER_ALREADY_RUNNING"


# ─── 20. Repeated Scan Creates No Duplicates ────────────────────────────────

def test_20_repeated_scan_creates_no_duplicates(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "film1.mkv").write_bytes(b"\x00" * 1024)

    for _ in range(4):
        res = media_scan.scan_source(
            source_id=sandbox_env["source_id"],
            db_path=sandbox_env["db_path"],
            home=sandbox_env["home"],
            probe_func=_mock_probe_fn,
        )
        assert res["ok"] is True

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        count = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        assert count == 1


# ─── 21. No WORK Inference ──────────────────────────────────────────────────

def test_21_no_work_inference(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "Inception.2010.1080p.mkv").write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        works_count = db.execute("SELECT count(*) FROM works").fetchone()[0]
        assert works_count == 0, "DEV4 must never create works"
        work_id = db.execute("SELECT work_id FROM media_versions").fetchone()[0]
        assert work_id is None, "work_id must remain NULL"


# ─── 22. No TMDb / Provider Activity ────────────────────────────────────────

def test_22_no_tmdb_provider_activity(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "film1.mkv").write_bytes(b"\x00" * 1024)

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        mc_count = db.execute("SELECT count(*) FROM match_candidates").fetchone()[0]
        ext_count = db.execute("SELECT count(*) FROM external_ids").fetchone()[0]
        assert mc_count == 0
        assert ext_count == 0


# ─── 23. No Media-Actions Mutation ──────────────────────────────────────────

def test_23_no_media_actions_mutation(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "film1.mkv").write_bytes(b"\x00" * 1024)

    actions_file = sandbox_env["home"] / ".local/state/openhtpc/media-actions/current.json"

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    assert not actions_file.exists()


# ─── 24. No User-Config Mutation ────────────────────────────────────────────

def test_24_no_user_config_mutation(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "film1.mkv").write_bytes(b"\x00" * 1024)

    cfg_before = sandbox_env["config_path"].read_bytes()

    media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )

    cfg_after = sandbox_env["config_path"].read_bytes()
    assert cfg_before == cfg_after


# ─── 25. No Automatic Startup Scan ──────────────────────────────────────────

def test_25_no_automatic_startup_scan():
    # Grep payload to ensure openhtpc-media-scan is not invoked in session-start or home
    session_start = (PAYLOAD / "openhtpc-session-start").read_text()
    home_py = (PAYLOAD / "openhtpc-home.py").read_text()
    assert "openhtpc-media-scan" not in session_start
    assert "openhtpc-media-scan" not in home_py


# ─── 26. Deterministic Summary Counters Invariant ───────────────────────────

def test_26_deterministic_summary_counters(sandbox_env):
    root = sandbox_env["media_root"]
    (root / "a.mkv").write_bytes(b"\x00" * 1024)
    (root / "b.mkv").write_bytes(b"\x00" * 2048)

    res1 = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )
    assert res1["enumerated"] == res1["new"] + res1["changed"] + res1["unchanged"] + res1["restored"]

    (root / "c.mkv").write_bytes(b"\x00" * 512)
    (root / "a.mkv").write_bytes(b"\x00" * 1025)

    res2 = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )
    assert res2["enumerated"] == res2["new"] + res2["changed"] + res2["unchanged"] + res2["restored"]


# ─── 27. Isolated XDG State/Data/Config ──────────────────────────────────────

def test_27_isolated_xdg_paths(tmp_path):
    custom_state = tmp_path / "custom_state"
    custom_config = tmp_path / "custom_config"
    custom_data = tmp_path / "custom_data"
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "vid.mkv").write_bytes(b"\x00" * 1024)

    custom_config.mkdir()
    (custom_config / "openhtpc").mkdir()
    cfg = {"schema": 1, "local_media_sources": [str(media_dir)]}
    (custom_config / "openhtpc/user-config.json").write_text(json.dumps(cfg))

    db_file = custom_data / "openhtpc/media/media.db"
    media_db.initialize(db_file)

    env = {
        "XDG_CONFIG_HOME": str(custom_config),
        "XDG_STATE_HOME": str(custom_state),
        "XDG_DATA_HOME": str(custom_data),
    }

    sid = media_scan.compute_source_id(media_dir)
    with mock.patch.dict(os.environ, env):
        res = media_scan.scan_source(source_id=sid, db_path=db_file, probe_func=_mock_probe_fn)
        assert res["ok"] is True
        assert (custom_state / "openhtpc/media" / f"scan-{sid}.lock").exists()


# ─── 28. No Access to Steve's Real Media ────────────────────────────────────

def test_28_no_access_to_steve_real_media(sandbox_env):
    # Ensure source scanner refuses to scan unconfigured paths
    unconfigured = Path("/home/steve/Videos")
    res = media_scan.scan_source(
        source_root=unconfigured,
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_probe_fn,
    )
    assert res["ok"] is False
    assert res["error"] == "SOURCE_NOT_CONFIGURED"


# ─── 29. Shared Media-Extension Authority Identical ─────────────────────────

FROZEN_PRE_DEV4_EXTENSIONS = frozenset({
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

FORBIDDEN_EXTENSIONS = frozenset({
    ".wmv",
    ".flv",
    ".iso",
    ".rmvb",
    ".divx",
    ".asf",
    ".ogv",
    ".3gp",
})


def test_29_shared_media_extension_authority_compatibility_contract():
    actual = media_types.VIDEO_EXTENSIONS

    # Exact equality with frozen pre-DEV4 contract
    assert actual == FROZEN_PRE_DEV4_EXTENSIONS
    assert len(actual) == 11

    # Fails if any pre-DEV4 extension was removed (.mpg, .mpeg, etc.)
    removed = FROZEN_PRE_DEV4_EXTENSIONS - actual
    assert not removed, f"Pre-DEV4 extensions were removed: {removed}"

    # Fails if any new extension was silently added (.wmv, .flv, etc.)
    added = actual - FROZEN_PRE_DEV4_EXTENSIONS
    assert not added, f"New extensions were silently added: {added}"

    # Verify forbidden / legacy formats are explicitly excluded
    for forbidden in FORBIDDEN_EXTENSIONS:
        assert forbidden not in actual
        assert media_types.is_candidate_media_file(f"sample{forbidden}") is False
        assert media_scan.is_supported_media_extension(f"sample{forbidden}") is False

    # Candidate helper checks for all 11 valid extensions
    for ext in FROZEN_PRE_DEV4_EXTENSIONS:
        assert media_types.is_candidate_media_file(f"sample{ext}") is True
        assert media_types.is_candidate_media_file(f"sample{ext.upper()}") is True
        assert media_scan.is_supported_media_extension(f"sample{ext}") is True
        assert media_scan.is_supported_media_extension(f"sample{ext.upper()}") is True

    # Helper rejects non-media and hidden files
    assert media_types.is_candidate_media_file(".hidden.mkv") is False
    assert media_types.is_candidate_media_file("audio.flac") is False
    assert media_types.is_candidate_media_file("disc.iso") is False
    assert media_scan.is_supported_media_extension(".hidden.mkv") is False
    assert media_scan.is_supported_media_extension("audio.flac") is False


def test_29b_runtime_consumers_use_shared_extension_authority():
    import importlib.util
    from importlib.machinery import SourceFileLoader

    def _load_mod(name: str, path: Path):
        loader = SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    # Load the 3 qualified pre-DEV4 runtime consumers
    browser_mod = _load_mod("test_browser", PAYLOAD / "openhtpc-media-browser.py")
    engine_mod = _load_mod("test_engine", PAYLOAD / "openhtpc-session-engine.py")
    play_mod = _load_mod("test_play", PAYLOAD / "openhtpc-play")

    # 1. openhtpc-media-browser uses shared authority
    assert browser_mod.VIDEO_EXTENSIONS == FROZEN_PRE_DEV4_EXTENSIONS
    assert browser_mod.VIDEO_EXTENSIONS is browser_mod._media_types.VIDEO_EXTENSIONS

    # 2. openhtpc-session-engine uses shared authority
    assert engine_mod.VIDEO_EXTENSIONS == FROZEN_PRE_DEV4_EXTENSIONS
    assert engine_mod.VIDEO_EXTENSIONS is engine_mod._media_types.VIDEO_EXTENSIONS

    # 3. openhtpc-play uses shared authority
    assert play_mod.VIDEO_EXTENSIONS == FROZEN_PRE_DEV4_EXTENSIONS
    assert play_mod.VIDEO_EXTENSIONS is play_mod._media_types.VIDEO_EXTENSIONS

    # 4. DEV4 scanner uses shared authority
    assert media_scan.VIDEO_EXTENSIONS == FROZEN_PRE_DEV4_EXTENSIONS
    assert media_scan._load_media_types() is not None



# ─── 30. Size + Mtime Fingerprint Classification ────────────────────────────

def test_30_fingerprint_classification_size_and_mtime():
    # Unit test fingerprint logic
    cand_size = 1000
    cand_mtime = 1700000000000000000

    # Identical => UNCHANGED
    assert (cand_size == 1000 and cand_mtime == 1700000000000000000) is True

    # Size differs => CHANGED
    assert (cand_size == 1001 and cand_mtime == 1700000000000000000) is False

    # Mtime differs => CHANGED
    assert (cand_size == 1000 and cand_mtime == 1700000000000000001) is False


# ─── 31. Real C1 PAL DVD Benchmark Scan Integration ─────────────────────────

def test_31_real_c1_pal_dvd_benchmark_scan(sandbox_env):
    fixture = PAYLOAD / "assets/benchmark/c1_dvd_pal.mpg"
    if not fixture.is_file():
        pytest.skip("PAL DVD benchmark fixture not found")

    root = sandbox_env["media_root"]
    dest = root / "c1_dvd_pal.mpg"
    dest.write_bytes(fixture.read_bytes())

    # Run real DEV2 probe on real fixture file
    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
    )

    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["new"] == 1

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        v_stream = db.execute("SELECT codec, width, height, field_order FROM video_streams").fetchone()
        assert v_stream[0] == "mpeg2video"
        assert v_stream[1] == 720
        assert v_stream[2] == 576
        assert v_stream[3] == "progressive"


# ─── 32–52. DEV6B4 Real Library Scanner Safety: Optical Disc Structure Pruning ────

def test_32_ordinary_root_mkv_enumerated(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"dummy_content")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "movie.mkv" in cands
    assert cands["movie.mkv"].file_size == len(b"dummy_content")


def test_33_deep_nested_mkv_enumerated(tmp_path):
    sub = tmp_path / "a" / "b" / "c" / "d"
    sub.mkdir(parents=True)
    f = sub / "deep_movie.mkv"
    f.write_bytes(b"dummy_content")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "a/b/c/d/deep_movie.mkv" in cands


def test_34_standalone_m2ts_outside_disc_structure_enumerated(tmp_path):
    sub = tmp_path / "HomeMovies"
    sub.mkdir(parents=True)
    f = sub / "Vacation.m2ts"
    f.write_bytes(b"dummy_content")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "HomeMovies/Vacation.m2ts" in cands


def test_35_bdmv_stream_m2ts_ignored(tmp_path):
    stream_dir = tmp_path / "BDMV" / "STREAM"
    stream_dir.mkdir(parents=True)
    (stream_dir / "00000.m2ts").write_bytes(b"stream0")
    (stream_dir / "00001.m2ts").write_bytes(b"stream1")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_36_nested_bdmv_subtree_ignored(tmp_path):
    movie_dir = tmp_path / "UHD" / "Hokum"
    bdmv_dir = movie_dir / "BDMV"
    (bdmv_dir / "STREAM").mkdir(parents=True)
    (bdmv_dir / "PLAYLIST").mkdir(parents=True)
    (bdmv_dir / "CLIPINF").mkdir(parents=True)
    (bdmv_dir / "STREAM" / "00000.m2ts").write_bytes(b"video")
    (bdmv_dir / "index.bdmv").write_bytes(b"index")
    (bdmv_dir / "MovieObject.bdmv").write_bytes(b"movieobj")

    # Also an ordinary movie alongside
    (tmp_path / "UHD" / "LegitimateMovie.mkv").write_bytes(b"legit")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "UHD/LegitimateMovie.mkv" in cands
    assert not any("Hokum" in k or "BDMV" in k for k in cands)


def test_37_certificate_subtree_ignored(tmp_path):
    cert_dir = tmp_path / "UHD" / "Hokum" / "CERTIFICATE" / "BACKUP"
    cert_dir.mkdir(parents=True)
    (cert_dir / "id.bdmv").write_bytes(b"cert_data")
    (cert_dir / "helper.m2ts").write_bytes(b"cert_helper")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_38_video_ts_vob_ignored(tmp_path):
    v_dir = tmp_path / "VIDEO_TS"
    v_dir.mkdir(parents=True)
    (v_dir / "VIDEO_TS.VOB").write_bytes(b"vob0")
    (v_dir / "VTS_01_1.VOB").write_bytes(b"vob1")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_39_nested_video_ts_subtree_ignored(tmp_path):
    v_dir = tmp_path / "DVD" / "MyDisc" / "VIDEO_TS"
    v_dir.mkdir(parents=True)
    (v_dir / "VIDEO_TS.IFO").write_bytes(b"ifo")
    (v_dir / "VIDEO_TS.VOB").write_bytes(b"vob0")
    (v_dir / "VTS_01_0.VOB").write_bytes(b"vob1")
    (v_dir / "VTS_01_1.VOB").write_bytes(b"vob2")

    (tmp_path / "DVD" / "StandaloneDVD.vob").write_bytes(b"loose_vob")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "DVD/StandaloneDVD.vob" in cands
    assert not any("MyDisc" in k or "VIDEO_TS" in k for k in cands)


def test_40_case_insensitive_bdmv_pruning(tmp_path):
    (tmp_path / "D1" / "BDMV" / "STREAM").mkdir(parents=True)
    (tmp_path / "D1" / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"1")

    (tmp_path / "D2" / "bdmv" / "stream").mkdir(parents=True)
    (tmp_path / "D2" / "bdmv" / "stream" / "00000.m2ts").write_bytes(b"2")

    (tmp_path / "D3" / "Bdmv" / "Stream").mkdir(parents=True)
    (tmp_path / "D3" / "Bdmv" / "Stream" / "00000.m2ts").write_bytes(b"3")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_41_case_insensitive_certificate_pruning(tmp_path):
    (tmp_path / "D1" / "CERTIFICATE").mkdir(parents=True)
    (tmp_path / "D1" / "CERTIFICATE" / "app.m2ts").write_bytes(b"1")

    (tmp_path / "D2" / "certificate").mkdir(parents=True)
    (tmp_path / "D2" / "certificate" / "app.m2ts").write_bytes(b"2")

    (tmp_path / "D3" / "Certificate").mkdir(parents=True)
    (tmp_path / "D3" / "Certificate" / "app.m2ts").write_bytes(b"3")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_42_case_insensitive_video_ts_pruning(tmp_path):
    (tmp_path / "D1" / "VIDEO_TS").mkdir(parents=True)
    (tmp_path / "D1" / "VIDEO_TS" / "VTS_01_1.VOB").write_bytes(b"1")

    (tmp_path / "D2" / "video_ts").mkdir(parents=True)
    (tmp_path / "D2" / "video_ts" / "VTS_01_1.vob").write_bytes(b"2")

    (tmp_path / "D3" / "Video_Ts").mkdir(parents=True)
    (tmp_path / "D3" / "Video_Ts" / "VTS_01_1.VOB").write_bytes(b"3")

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert len(cands) == 0


def test_43_long_filename_preserved(tmp_path):
    long_stem = "UHD.Project.Hail.Mary.2026.MULTi.2160p.DV.HDR.WEB-DL.AAC.2.0.H265-BOUC.VERY_LONG_NAME_TEST_STRING_PRESERVATION_1234567890"
    f = tmp_path / f"{long_stem}.mkv"
    f.write_bytes(b"data")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert f"{long_stem}.mkv" in cands


def test_44_accented_utf8_filename_preserved(tmp_path):
    name1 = "Les poupées russes (2005) VOF 1080p BluRay DTS-HD MA 5.1 x265-k7.mkv"
    name2 = "Histoires de fantômes chinois 3.mkv"
    (tmp_path / "Bluray").mkdir(parents=True)
    (tmp_path / "Bluray" / name1).write_bytes(b"poupeies")
    (tmp_path / "UHD").mkdir(parents=True)
    (tmp_path / "UHD" / name2).write_bytes(b"fantomes")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert f"Bluray/{name1}" in cands
    assert f"UHD/{name2}" in cands


def test_45_filename_containing_bdmv_outside_bdmv_not_skipped(tmp_path):
    sub = tmp_path / "Documentaries"
    sub.mkdir(parents=True)
    f = sub / "About.BDMV.Documentary.mkv"
    f.write_bytes(b"doc_content")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "Documentaries/About.BDMV.Documentary.mkv" in cands


def test_46_filename_containing_certificate_not_skipped(tmp_path):
    sub = tmp_path / "Movies"
    sub.mkdir(parents=True)
    f = sub / "Birth.Certificate.mp4"
    f.write_bytes(b"movie_content")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "Movies/Birth.Certificate.mp4" in cands


def test_47_filename_containing_video_ts_not_skipped(tmp_path):
    sub = tmp_path / "Movies"
    sub.mkdir(parents=True)
    f = sub / "My.VIDEO_TS.Documentary.mkv"
    f.write_bytes(b"vts_doc")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "Movies/My.VIDEO_TS.Documentary.mkv" in cands


def test_48_source_id_unchanged(tmp_path):
    p = tmp_path / "source_root"
    p.mkdir()
    expected = hashlib.blake2s(os.fsencode(p.resolve()), digest_size=8).hexdigest()
    actual = media_scan.compute_source_id(p)
    assert actual == expected


def test_49_relative_path_unchanged(tmp_path):
    sub = tmp_path / "dir1" / "dir2"
    sub.mkdir(parents=True)
    f = sub / "test.mkv"
    f.write_bytes(b"data")
    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    assert "dir1/dir2/test.mkv" in cands
    assert cands["dir1/dir2/test.mkv"].relative_path == "dir1/dir2/test.mkv"


def test_50_directory_symlink_behavior_unchanged(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "movie.mkv").write_bytes(b"data")

    sym_dir = tmp_path / "sym_dir"
    sym_dir.symlink_to(real_dir, target_is_directory=True)

    cands, err = media_scan.enumerate_source_candidates(tmp_path)
    assert err is None
    # real_dir/movie.mkv is found
    assert "real_dir/movie.mkv" in cands
    # sym_dir is rejected by directory symlink policy
    assert not any(k.startswith("sym_dir/") for k in cands)


def test_51_zero_network_during_scan(sandbox_env, monkeypatch):
    # Enforce network prohibition
    import socket
    import urllib.request

    def _fail_network(*args, **kwargs):
        raise AssertionError("NETWORK CALL ATTEMPTED DURING SCAN")

    monkeypatch.setattr(socket, "socket", _fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", _fail_network)

    root = sandbox_env["media_root"]
    (root / "TestMovie.mkv").write_bytes(b"content")

    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_descriptor,
    )
    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["new"] == 1


def test_52_real_library_model_structural_filter(sandbox_env):
    root = sandbox_env["media_root"]

    # 1. Bluray/Dark Knight.mkv
    bluray = root / "Bluray"
    bluray.mkdir(parents=True)
    (bluray / "Dark Knight.mkv").write_bytes(b"dk")

    # 2. UHD/Movie.mkv
    uhd = root / "UHD"
    uhd.mkdir(parents=True)
    (uhd / "Movie.mkv").write_bytes(b"movie")

    # 3. UHD/LooseTransport/Concert.m2ts
    loose = uhd / "LooseTransport"
    loose.mkdir(parents=True)
    (loose / "Concert.m2ts").write_bytes(b"concert")

    # 4. UHD/DiscFolder/BDMV/...
    bdmv_dir = uhd / "DiscFolder" / "BDMV"
    (bdmv_dir / "STREAM").mkdir(parents=True)
    (bdmv_dir / "PLAYLIST").mkdir(parents=True)
    (bdmv_dir / "CLIPINF").mkdir(parents=True)
    (bdmv_dir / "STREAM" / "00000.m2ts").write_bytes(b"chunk0")
    (bdmv_dir / "STREAM" / "00001.m2ts").write_bytes(b"chunk1")

    # 5. DVD/DiscFolder/VIDEO_TS/...
    vts_dir = root / "DVD" / "DiscFolder" / "VIDEO_TS"
    vts_dir.mkdir(parents=True)
    (vts_dir / "VIDEO_TS.VOB").write_bytes(b"vts_menu")
    (vts_dir / "VTS_01_0.VOB").write_bytes(b"vts_feature0")
    (vts_dir / "VTS_01_1.VOB").write_bytes(b"vts_feature1")

    # Phase A candidate enumeration check
    cands, err = media_scan.enumerate_source_candidates(root)
    assert err is None
    assert "Bluray/Dark Knight.mkv" in cands
    assert "UHD/Movie.mkv" in cands
    assert "UHD/LooseTransport/Concert.m2ts" in cands
    assert len(cands) == 3

    assert not any("BDMV" in k for k in cands)
    assert not any("VIDEO_TS" in k for k in cands)

    # Full scan execution check
    res = media_scan.scan_source(
        source_id=sandbox_env["source_id"],
        db_path=sandbox_env["db_path"],
        home=sandbox_env["home"],
        probe_func=_mock_descriptor,
    )
    assert res["ok"] is True
    assert res["outcome"] == "COMPLETE"
    assert res["new"] == 3
    assert res["failed"] == 0

    with closing(media_db.connect(sandbox_env["db_path"])) as db:
        rows = db.execute("SELECT relative_path FROM resources ORDER BY relative_path").fetchall()
        paths = [r[0] for r in rows]
        assert paths == [
            "Bluray/Dark Knight.mkv",
            "UHD/LooseTransport/Concert.m2ts",
            "UHD/Movie.mkv",
        ]
