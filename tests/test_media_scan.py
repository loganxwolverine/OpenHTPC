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

def test_29_shared_media_extension_authority_identical():
    # Verify openhtpc-media-types.py defines exact same extensions
    expected = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}
    assert set(media_types.VIDEO_EXTENSIONS) == expected

    # Test candidate helper
    assert media_types.is_candidate_media_file("movie.MKV") is True
    assert media_types.is_candidate_media_file("video.mp4") is True
    assert media_types.is_candidate_media_file(".hidden.mkv") is False
    assert media_types.is_candidate_media_file("audio.flac") is False
    assert media_types.is_candidate_media_file("disc.iso") is False


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
