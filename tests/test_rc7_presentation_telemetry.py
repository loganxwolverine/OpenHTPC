"""Hermetic tests for MPV presentation telemetry collection via IPC.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations
import importlib.util
import json
import os
import pathlib
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "payload" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = module("openhtpc-refresh-match.py")
P = module("openhtpc-playback-policy.py")


class MockMPVIPCServer:
    """Hermetic local UNIX socket server responding to MPV JSON-IPC get_property commands."""

    def __init__(self, socket_path: pathlib.Path | str, properties: dict):
        self.path = str(socket_path)
        self.properties = dict(properties)
        self.stop_event = threading.Event()
        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.path)
        self.server_sock.listen(5)
        self.server_sock.settimeout(0.2)
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                conn, _ = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.settimeout(0.5)
            buf = b""
            while not self.stop_event.is_set():
                try:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line:
                            req = json.loads(line.decode("utf-8"))
                            req_id = req.get("request_id")
                            cmd = req.get("command", [])
                            if cmd and cmd[0] == "get_property" and len(cmd) > 1:
                                prop_name = cmd[1]
                                val = self.properties.get(prop_name)
                                resp = {"request_id": req_id, "error": "success", "data": val}
                                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except (OSError, ValueError):
                    break
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self.stop_event.set()
        try:
            self.server_sock.close()
        except OSError:
            pass
        self.thread.join(timeout=0.5)
        if os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                pass


class PresentationTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)

    def test_collector_instant_stop_without_socket(self):
        sock = self.home / "nonexistent.sock"
        collector = M.TelemetryCollector(sock)
        collector.start()
        collector.stop()
        self.assertIsNone(collector.result())

    def test_collector_reads_all_properties_from_mock_ipc(self):
        sock = self.home / "mpv_test.sock"
        mock_props = {
            "video-sync": "audio",
            "container-fps": 23.976023976,
            "estimated-vf-fps": 23.976,
            "display-fps": 23.976,
            "estimated-display-fps": 23.9759998,
            "vsync-ratio": 1.0,
            "vsync-jitter": 0.0001,
            "frame-drop-count": 2,
            "decoder-frame-drop-count": 1,
            "mistimed-frame-count": 3,
            "vo-delayed-frame-count": 1,
            "avsync": -0.004,
            "total-avsync-change": 0.001,
            "vo-passes": {"fresh": [{"desc": "scale", "last": 1200000}]},
        }
        server = MockMPVIPCServer(sock, mock_props)
        server.start()
        self.addCleanup(server.close)

        collector = M.TelemetryCollector(sock)
        collector.start()
        # Allow collector to perform at least 1 sample cycle
        time.sleep(0.15)
        collector.stop()

        res = collector.result()
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "CAPTURED")
        self.assertGreaterEqual(res["samples_count"], 1)
        self.assertEqual(res["effective_video_sync"], "audio")
        self.assertAlmostEqual(res["container_fps"], 23.976023976)
        self.assertAlmostEqual(res["estimated_vf_fps"], 23.976)
        self.assertAlmostEqual(res["display_fps"], 23.976)
        self.assertAlmostEqual(res["estimated_display_fps"], 23.9759998)
        self.assertEqual(res["vsync_ratio"], 1.0)
        self.assertEqual(res["vsync_jitter"], 0.0001)
        self.assertEqual(res["frame_drop_count"], 2)
        self.assertEqual(res["decoder_frame_drop_count"], 1)
        self.assertEqual(res["mistimed_frame_count"], 3)
        self.assertEqual(res["vo_delayed_frame_count"], 1)
        self.assertEqual(res["max_frame_drop_count"], 2)
        self.assertEqual(res["max_decoder_frame_drop_count"], 1)
        self.assertEqual(res["max_mistimed_frame_count"], 3)
        self.assertEqual(res["max_vo_delayed_frame_count"], 1)
        self.assertAlmostEqual(res["last_avsync"], -0.004)
        self.assertAlmostEqual(res["total_avsync_change"], 0.001)
        self.assertEqual(res["vo_passes"], {"fresh": [{"desc": "scale", "last": 1200000}]})

    def test_collector_preserves_null_when_mpv_does_not_expose(self):
        sock = self.home / "mpv_null_props.sock"
        mock_props = {
            "video-sync": "audio",
            "container-fps": 24.0,
            "estimated-vf-fps": 24.0,
            "display-fps": None,
            "estimated-display-fps": None,
            "vsync-ratio": None,
            "vsync-jitter": None,
            "frame-drop-count": 0,
            "decoder-frame-drop-count": 0,
            "mistimed-frame-count": None,
            "vo-delayed-frame-count": 0,
            "avsync": None,
            "total-avsync-change": None,
            "vo-passes": None,
        }
        server = MockMPVIPCServer(sock, mock_props)
        server.start()
        self.addCleanup(server.close)

        collector = M.TelemetryCollector(sock)
        collector.start()
        time.sleep(0.15)
        collector.stop()

        res = collector.result()
        self.assertIsNotNone(res)
        self.assertEqual(res["effective_video_sync"], "audio")
        self.assertIsNone(res["display_fps"])
        self.assertIsNone(res["vsync_ratio"])
        self.assertIsNone(res["mistimed_frame_count"])
        self.assertIsNone(res["last_avsync"])
        self.assertIsNone(res["vo_passes"])

    def test_run_playback_injects_ipc_server_and_records_telemetry(self):
        passed_commands = []
        captured_props = {
            "video-sync": "audio",
            "container-fps": 23.976024,
            "estimated-vf-fps": 23.976,
            "display-fps": 60.0,
            "estimated-display-fps": 60.001,
            "vsync-ratio": None,
            "vsync-jitter": None,
            "frame-drop-count": 0,
            "decoder-frame-drop-count": 0,
            "mistimed-frame-count": None,
            "vo-delayed-frame-count": 0,
            "avsync": 0.002,
            "total-avsync-change": 0.0,
            "vo-passes": None,
        }

        def mock_runner(cmd, **kwargs):
            passed_commands.append(list(cmd))
            # Extract injected socket path and run mock server while runner is executing
            sock_arg = next((a for a in cmd if a.startswith("--input-ipc-server=")), None)
            self.assertIsNotNone(sock_arg)
            sock_path = sock_arg.split("=", 1)[1]
            server = MockMPVIPCServer(sock_path, captured_props)
            server.start()
            try:
                time.sleep(0.2)
            finally:
                server.close()
            return mock.Mock(returncode=0)

        initial_cmd = ["mpv", "--no-config", "--fullscreen=yes", "--", "/path/to/media.mkv"]
        res = M.run_playback(self.home, initial_cmd, runner=mock_runner, dispatch_id="disp-telemetry-1")
        self.assertEqual(res.returncode, 0)

        # Check injected argument position: before '--'
        self.assertEqual(len(passed_commands), 1)
        executed_cmd = passed_commands[0]
        self.assertIn("--", executed_cmd)
        dash_idx = executed_cmd.index("--")
        self.assertTrue(any(a.startswith("--input-ipc-server=") for a in executed_cmd[:dash_idx]))

        # Verify presentation-telemetry-last.json
        diag = M.read_presentation_telemetry(self.home)
        self.assertIsNotNone(diag)
        self.assertEqual(diag["schema"], 1)
        self.assertEqual(diag["dispatch_id"], "disp-telemetry-1")
        self.assertEqual(diag["effective_video_sync"], "audio")
        self.assertAlmostEqual(diag["container_fps"], 23.976024)
        self.assertAlmostEqual(diag["display_fps"], 60.0)
        self.assertIsNone(diag["vsync_ratio"])
        self.assertEqual(diag["frame_drop_count"], 0)

        # Verify refresh-match-last.json has presentation_telemetry
        match_last = M.read(self.home / ".local/state/openhtpc/refresh-match-last.json")
        self.assertIn("presentation_telemetry", match_last)
        self.assertEqual(match_last["presentation_telemetry"]["effective_video_sync"], "audio")

    def test_read_presentation_telemetry_malformed_fails_closed(self):
        target = self.home / ".local/state/openhtpc/presentation-telemetry-last.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        target.write_text("not json")
        self.assertIsNone(M.read_presentation_telemetry(self.home))

        target.write_text(json.dumps({"schema": 2}))
        self.assertIsNone(M.read_presentation_telemetry(self.home))

        target.write_text(json.dumps(["not a dict"]))
        self.assertIsNone(M.read_presentation_telemetry(self.home))


if __name__ == "__main__":
    unittest.main()
