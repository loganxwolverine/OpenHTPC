"""Focused hermetic regression tests for RC7 audio bitstream and display lifecycle.

Verifies the lifecycle invariant:
FINAL DISPLAY MUTATION -> AUDIO BITSTREAM PREPARATION -> MPV -> DISPLAY RESTORATION

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def _load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


POLICY = _load("openhtpc_playback_policy", PAYLOAD / "openhtpc-playback-policy.py")
REFRESH = _load("openhtpc_refresh_match", PAYLOAD / "openhtpc-refresh-match.py")
PLAY = _load("openhtpc_play", PAYLOAD / "openhtpc-play")


def make_snapshot(rates=(60, 23.976), current="0", current_hdr="INACTIVE", hdr_capable="SUPPORTED"):
    modes = [dict(id=str(i), width=3840, height=2160, refresh_hz=rate) for i, rate in enumerate(rates)]
    output = dict(
        connector="HDMI-A-1",
        output_id=1,
        display_identity="0123456789abcdef" * 4,
        active=True,
        connected=True,
        current_mode_id=current,
        current_mode={k: v for k, v in modes[int(current)].items() if k != "id"},
        available_modes=modes,
        scale=1,
        hdr_capable={"status": hdr_capable, "sources": ["DRM"]},
        current_hdr_mode={"status": current_hdr, "sources": ["KSCREEN_HDR"]},
    )
    return dict(outputs=[output], active_output=output)


class FakeLifecycleRuntime:
    def __init__(self, snap, timeline=None):
        self.value = copy.deepcopy(snap)
        self.timeline = timeline if timeline is not None else []
        self.calls = []
        self.fail = False

    def snapshot(self):
        return copy.deepcopy(self.value)

    def apply(self, output, mode_id=None, hdr_enable=None):
        self.calls.append((output.get("output_id"), mode_id, hdr_enable))
        if self.fail:
            self.timeline.append(("display_switch_failed", mode_id, hdr_enable))
            return False
        o = self.value["active_output"]
        if mode_id is not None:
            o["current_mode_id"] = mode_id
            o["current_mode"] = {k: v for k, v in next(m for m in o["available_modes"] if m["id"] == mode_id).items() if k != "id"}
        if hdr_enable is not None:
            o["current_hdr_mode"] = {"status": "ACTIVE" if hdr_enable else "INACTIVE", "sources": ["KSCREEN_HDR"]}
        self.timeline.append(("display_switch_applied", mode_id, hdr_enable, o["current_mode_id"], o["current_hdr_mode"]["status"]))
        return True


class AudioDisplayLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        cfg_dir = self.home / ".config/openhtpc"
        cfg_dir.mkdir(parents=True)
        user_cfg = {
            "presentation_mode": "PURE",
            "audio_language_policy": "FR",
            "audio_output_mode": "BITSTREAM",
            "subtitle_policy": "AUTO",
            "refresh_matching": "AUTO",
            "hdr_matching": "OFF",
        }
        (cfg_dir / "user-config.json").write_text(json.dumps(user_cfg, indent=2))
        (cfg_dir / "profile.json").write_text(json.dumps({
            "runtime": {"status": "ready"},
            "runtime_profiles": {"profiles": {"PURE": {"generation_status": "generated", "config_path": str(cfg_dir / "pure.conf")}}},
        }))
        (cfg_dir / "pure.conf").write_text("# pure runtime config\n")

    def tearDown(self):
        self.tmp.cleanup()

    # 1. BITSTREAM + refresh switch: display mutation occurs BEFORE bitstream preparation
    def test_01_bitstream_refresh_switch_display_mutates_before_audio_prep(self):
        timeline = []
        snap = make_snapshot(rates=(60, 23.976), current="0")
        runtime = FakeLifecycleRuntime(snap, timeline=timeline)

        decision = {
            "audio_output": {"requested": "BITSTREAM", "source_codec": "dts", "resolved": "BITSTREAM", "reason": "user_bitstream", "audio_spdif": "dts,dts-hd"},
            "audio_target": {"configured": "SYSTEM", "sink_target": "@DEFAULT_AUDIO_SINK@"},
        }

        def mock_audio_prep(settle_timeout: float = 0.0):
            current_mode = runtime.value["active_output"]["current_mode_id"]
            timeline.append(("audio_prep", current_mode, settle_timeout))
            self.assertEqual(current_mode, "1", "Display must be switched to target mode 1 (23.976 Hz) when audio_prep runs")
            return {"audio_sink_id": 42, "iec958_prepare_status": "SUCCESS"}

        def mock_runner(cmd, **kwargs):
            timeline.append(("mpv_launch", list(cmd) if isinstance(cmd, list) else str(cmd)))
            return mock.Mock(returncode=0)

        cadence_ev = {"cadence_fps": 24000 / 1001, "cadence_rational": "24000/1001", "cadence_reason": "PROVEN"}

        with mock.patch.object(REFRESH, "probe_cadence_evidence", return_value=cadence_ev), \
             mock.patch.object(REFRESH, "Runtime", return_value=runtime):
            result = REFRESH.run_playback(
                self.home,
                ["mpv", "synthetic.mkv"],
                media=pathlib.Path("synthetic.mkv"),
                runner=mock_runner,
                audio_prep=mock_audio_prep,
                decision=decision,
            )

        self.assertEqual(result.returncode, 0)
        action_names = [item[0] for item in timeline]
        self.assertIn("display_switch_applied", action_names)
        self.assertIn("audio_prep", action_names)
        self.assertIn("mpv_launch", action_names)

        switch_idx = action_names.index("display_switch_applied")
        prep_idx = action_names.index("audio_prep")
        mpv_idx = action_names.index("mpv_launch")

        self.assertLess(switch_idx, prep_idx, "Display switch must happen BEFORE audio_prep")
        self.assertLess(prep_idx, mpv_idx, "Audio prep must happen BEFORE mpv_launch")

    # 2. BITSTREAM + no display mutation: audio preparation still occurs before MPV
    def test_02_bitstream_no_display_mutation_audio_prep_still_occurs_before_mpv(self):
        timeline = []
        snap = make_snapshot(rates=(60,), current="0")
        runtime = FakeLifecycleRuntime(snap, timeline=timeline)

        POLICY.write_preference(self.home, "refresh_matching", "OFF")

        decision = {
            "audio_output": {"requested": "BITSTREAM", "source_codec": "ac3", "resolved": "BITSTREAM", "reason": "user_bitstream", "audio_spdif": "ac3"},
            "audio_target": {"configured": "SYSTEM", "sink_target": "@DEFAULT_AUDIO_SINK@"},
        }

        def mock_audio_prep(settle_timeout: float = 0.0):
            timeline.append(("audio_prep", settle_timeout))
            self.assertEqual(settle_timeout, 0.0, "No switch occurred, so settle_timeout should be 0.0")
            return {"audio_sink_id": 42, "iec958_prepare_status": "SUCCESS"}

        def mock_runner(cmd, **kwargs):
            timeline.append(("mpv_launch", list(cmd) if isinstance(cmd, list) else str(cmd)))
            return mock.Mock(returncode=0)

        with mock.patch.object(REFRESH, "Runtime", return_value=runtime):
            result = REFRESH.run_playback(
                self.home,
                ["mpv", "standard.mkv"],
                media=pathlib.Path("standard.mkv"),
                runner=mock_runner,
                audio_prep=mock_audio_prep,
                decision=decision,
            )

        self.assertEqual(result.returncode, 0)
        action_names = [item[0] for item in timeline]
        self.assertNotIn("display_switch_applied", action_names)
        self.assertIn("audio_prep", action_names)
        self.assertIn("mpv_launch", action_names)
        self.assertLess(action_names.index("audio_prep"), action_names.index("mpv_launch"))

    # 3. PCM: no HD bitstream preparation occurs
    def test_03_pcm_no_hd_bitstream_preparation(self):
        decision = {
            "audio_output": {"requested": "PCM", "source_codec": "dts", "resolved": "PCM", "reason": "user_pcm", "audio_spdif": "none"},
            "audio_target": {"configured": "SYSTEM", "sink_target": "@DEFAULT_AUDIO_SINK@"},
        }

        mock_runner = mock.Mock()
        mock_finder = mock.Mock(return_value="/usr/bin/pw-cli")

        fake_sink = {"id": 42, "name": "alsa_output.hdmi", "is_hdmi": True, "codecs": ["PCM", "DTS", "AC3"]}
        with mock.patch.object(POLICY, "inspect_sink", return_value=fake_sink):
            diag = POLICY.prepare_audio_target_bitstream(decision, runner=mock_runner, finder=mock_finder)

        self.assertEqual(diag["iec958_prepare_status"], "SKIPPED")
        self.assertEqual(diag["iec958_prepare_reason"], "PCM_MODE")
        self.assertFalse(diag["iec958_prepare_attempted"])
        self.assertEqual(mock_runner.call_count, 0, "PCM playback must not invoke pw-cli or runner")

    # 4. Display switch failure/fallback: audio preparation occurs only after fallback display state is established
    def test_04_display_switch_failure_restores_before_audio_prep(self):
        timeline = []
        snap = make_snapshot(rates=(60, 23.976), current="0")
        runtime = FakeLifecycleRuntime(snap, timeline=timeline)
        runtime.fail = True  # Simulated kscreen failure during mode apply

        decision = {
            "audio_output": {"requested": "BITSTREAM", "source_codec": "dts", "resolved": "BITSTREAM", "reason": "user_bitstream", "audio_spdif": "dts"},
            "audio_target": {"configured": "SYSTEM", "sink_target": "@DEFAULT_AUDIO_SINK@"},
        }

        def mock_audio_prep(settle_timeout: float = 0.0):
            current_mode = runtime.value["active_output"]["current_mode_id"]
            timeline.append(("audio_prep", current_mode, settle_timeout))
            self.assertEqual(current_mode, "0", "Audio prep must run on the restored/fallback display mode '0'")
            return {"audio_sink_id": 42, "iec958_prepare_status": "SUCCESS"}

        def mock_runner(cmd, **kwargs):
            timeline.append(("mpv_launch", list(cmd) if isinstance(cmd, list) else str(cmd)))
            return mock.Mock(returncode=0)

        cadence_ev = {"cadence_fps": 24000 / 1001, "cadence_rational": "24000/1001", "cadence_reason": "PROVEN"}

        with mock.patch.object(REFRESH, "probe_cadence_evidence", return_value=cadence_ev), \
             mock.patch.object(REFRESH, "Runtime", return_value=runtime):
            result = REFRESH.run_playback(
                self.home,
                ["mpv", "fallback_video.mkv"],
                media=pathlib.Path("fallback_video.mkv"),
                runner=mock_runner,
                audio_prep=mock_audio_prep,
                decision=decision,
            )

        self.assertEqual(result.returncode, 0)
        action_names = [item[0] for item in timeline]
        self.assertIn("display_switch_failed", action_names)
        self.assertIn("audio_prep", action_names)
        self.assertIn("mpv_launch", action_names)

        fail_idx = action_names.index("display_switch_failed")
        prep_idx = action_names.index("audio_prep")
        mpv_idx = action_names.index("mpv_launch")

        self.assertLess(fail_idx, prep_idx, "Display switch failure and restore must complete BEFORE audio_prep")
        self.assertLess(prep_idx, mpv_idx, "Audio prep must complete BEFORE mpv_launch")

    # 5. MPV launches immediately after audio preparation
    def test_05_mpv_launches_immediately_after_audio_prep(self):
        order = []
        snap = make_snapshot(rates=(60, 23.976), current="0")
        runtime = FakeLifecycleRuntime(snap)

        cadence_ev = {"cadence_fps": 24000 / 1001, "cadence_rational": "24000/1001", "cadence_reason": "PROVEN"}

        def mock_audio_prep(settle_timeout: float = 0.0):
            order.append("audio_prep")
            return {"audio_sink_id": 42, "iec958_prepare_status": "SUCCESS"}

        def mock_runner(cmd, **kwargs):
            order.append("mpv")
            return mock.Mock(returncode=0)

        with mock.patch.object(REFRESH, "probe_cadence_evidence", return_value=cadence_ev), \
             mock.patch.object(REFRESH, "Runtime", return_value=runtime):
            POLICY.play_mpv(
                self.home,
                ["mpv", "direct.mkv"],
                media=pathlib.Path("direct.mkv"),
                runner=mock_runner,
                audio_prep=mock_audio_prep,
            )

        self.assertEqual(order, ["audio_prep", "mpv"], "MPV must launch immediately after audio_prep")

    # 6. Shared policy.play_mpv falls back safely if refresh match module fails to load
    def test_06_play_mpv_fallback_still_runs_audio_prep_before_runner(self):
        order = []
        def mock_audio_prep(settle_timeout: float = 0.0):
            order.append("audio_prep")
            return {"audio_sink_id": 42}

        def mock_runner(cmd, **kwargs):
            order.append("runner")
            return mock.Mock(returncode=0)

        with mock.patch.object(POLICY.importlib.util, "spec_from_file_location", side_effect=ImportError("broken_helper")):
            result = POLICY.play_mpv(
                self.home,
                ["mpv", "test.mkv"],
                runner=mock_runner,
                audio_prep=mock_audio_prep,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(order, ["audio_prep", "runner"], "Fallback play_mpv must execute audio_prep before runner")


if __name__ == "__main__":
    unittest.main()
