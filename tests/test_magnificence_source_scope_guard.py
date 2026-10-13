"""Hermetic regression guard for the Magnificence SD source-scope classifier.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.

Scope: payload/openhtpc-playback-policy.py :: _magnificence_source_scope.

These tests encode the invariant that the `DVD_PAL_FILM` class may only be
returned for 625-line PAL geometry (576 active lines), because every consuming
Magnificence profile declares `source_scope = {class: DVD_PAL_FILM,
resolution: 720x576, fps: 25.0}`.  NTSC 480-line SD and other sub-576-line
geometry must fail closed to PURE rather than select a PAL-declared profile.

They are hermetic: no /sys, /dev/dri, Wayland, salon hardware or real ffprobe.
"""
from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
SPEC = importlib.util.spec_from_file_location(
    "magnificence_source_scope_guard", PAYLOAD / "openhtpc-playback-policy.py"
)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def _probe(width: int, height: int, fps: str, field_order: str | None = None) -> dict:
    video = {
        "codec_type": "video",
        "codec_name": "mpeg2video",
        "width": width,
        "height": height,
        "avg_frame_rate": fps,
        "r_frame_rate": fps,
    }
    if field_order is not None:
        video["field_order"] = field_order
    return {"streams": [video]}


def test_pal_film_geometry_still_classifies_as_dvd_pal_film():
    # 720x576 @ 25 fps: the exact geometry the PAL-film profiles declare.
    assert policy._magnificence_source_scope("local", _probe(720, 576, "25/1", "progressive")) == "DVD_PAL_FILM"
    # 576-line geometry stays PAL even when flagged interlaced: the family/HD
    # recipes carry BWDIF precisely for interlaced PAL DVD material.
    assert policy._magnificence_source_scope("local", _probe(720, 576, "25/1", "tt")) == "DVD_PAL_FILM"
    # 704x576 (PAL D1) is still 576-line PAL.
    assert policy._magnificence_source_scope("local", _probe(704, 576, "25/1", "progressive")) == "DVD_PAL_FILM"


def test_ntsc_480_line_sd_does_not_claim_the_pal_class():
    # NTSC SD is 480 active lines; it must not be labelled PAL.
    assert policy._magnificence_source_scope("local", _probe(720, 480, "30000/1001", "progressive")) is None
    assert policy._magnificence_source_scope("local", _probe(640, 480, "30000/1001", "progressive")) is None


def test_other_sub_576_sd_geometry_is_not_folded_into_the_pal_class():
    assert policy._magnificence_source_scope("local", _probe(352, 288, "25/1", "progressive")) is None


def test_no_profile_can_be_selected_for_ntsc_sd_end_to_end():
    """An NTSC 720x480 local file must fall back to PURE, not a PAL profile."""
    import json
    import tempfile

    temp = tempfile.TemporaryDirectory()
    try:
        home = pathlib.Path(temp.name)
        runtime = home / ".config/openhtpc/runtime"
        runtime.mkdir(parents=True)
        caps = {
            "graphics": {
                "devices": [
                    {"active": True, "vendor_id": "8086", "device_id": "46d4",
                     "model": "Intel Corporation Alder Lake-N [Intel Graphics]"}
                ]
            },
            "display": {"active_output": {"current_mode": {"width": 1920, "height": 1080, "refresh_hz": 60.0}}},
        }
        (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
        policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")

        ntsc = policy.resolve(home, kind="local", probe=_probe(720, 480, "30000/1001", "progressive"),
                              gpu_binding={"mpv_args": []})
        assert ntsc["presentation"]["resolved"] == "PURE"
        assert ntsc["presentation"]["reason"] == "no_qualified_magnificence_profile"

        # The genuine PAL counterpart still resolves the qualified profile.
        pal = policy.resolve(home, kind="local", probe=_probe(720, 576, "25/1", "progressive"),
                             gpu_binding={"mpv_args": []})
        assert pal["presentation"]["resolved"] == "RECIPE_C2_DVD_KRIG_BILATERAL"
        assert pal["presentation"]["profile_id"] == "intel_n150_8086_46d4_sd_1080p"
    finally:
        temp.cleanup()
