# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
"""Focused tests for runtime graphical context resolution, live socket verification,
headless failure guards, and kscreen-doctor safety contracts.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


caps_mod = _load_module("openhtpc_capabilities", PAYLOAD / "openhtpc-capabilities.py")
sys.modules["openhtpc_capabilities"] = caps_mod
engine_mod = _load_module("openhtpc_session_engine_test", PAYLOAD / "openhtpc-session-engine.py")
cinema_mod = _load_module("openhtpc_cinema_auto_test", PAYLOAD / "openhtpc-cinema-auto.py")
calibrate_mod = _load_module("openhtpc_calibrate_test", PAYLOAD / "openhtpc-calibrate.py")
benchmark_mod = _load_module("openhtpc_benchmark_test", PAYLOAD / "openhtpc-benchmark.py")


class TestRuntimeGraphicalContext(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = pathlib.Path(self.temp_dir.name) / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.runtime_dir = pathlib.Path(self.temp_dir.name) / "run_user"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def _create_unix_socket(self, directory: pathlib.Path, name: str) -> pathlib.Path:
        path = directory / name
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(str(path))
        self.addCleanup(s.close)
        return path

    def test_1_session_engine_no_graphical_context_does_not_invoke_kscreen(self):
        """When no graphical context exists, observed_display_size returns None and never runs kscreen."""
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "UNAVAILABLE", "environment": {}}):
                size = engine_mod.observed_display_size(environment={})
                self.assertIsNone(size)
                # Verify subprocess.run was NEVER called with kscreen-doctor
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_2_session_engine_valid_resolved_wayland_context_invokes_kscreen_with_resolved_env(self):
        """When a valid Wayland context is resolved, observed_display_size runs kscreen-doctor with that env."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        fake_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
            "XDG_SESSION_TYPE": "wayland",
        }
        kscreen_json = json.dumps({
            "outputs": [{
                "id": "1",
                "name": "DP-1",
                "enabled": True,
                "currentModeId": "mode-1",
                "modes": [{"id": "mode-1", "size": {"width": 3840, "height": 2160}, "refreshRate": 60.0}]
            }]
        })
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=kscreen_json, stderr="")
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "RESOLVED", "environment": fake_env}):
                size = engine_mod.observed_display_size(environment={})
                self.assertEqual(size, (3840, 2160))
                # Verify kscreen-doctor was called with the resolved environment
                self.assertTrue(any(
                    call[0][0] == ["kscreen-doctor", "-j"] and
                    call[1].get("env", {}).get("WAYLAND_DISPLAY") == "wayland-0"
                    for call in mock_run.call_args_list
                ))

    def test_3_capabilities_no_graphical_context_does_not_invoke_kscreen(self):
        """Capabilities collect_display does not launch kscreen-doctor when graphical context is unavailable."""
        calls = []
        def runner(argv, timeout):
            calls.append(argv)
            return {"status": "FAILED", "returncode": 1, "stdout": "", "stderr": ""}

        with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "UNAVAILABLE", "environment": {}}):
            result = caps_mod.collect_display(self.home, PAYLOAD, runner)
            self.assertIsNone(result["active_output"])
            self.assertEqual(result["outputs"], [])
            self.assertEqual(calls, [])

    def test_4_capabilities_valid_graphical_context_invokes_probe_with_resolved_env(self):
        """Capabilities collect_display invokes probe with the exact resolved environment when valid."""
        fake_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
            "XDG_SESSION_TYPE": "wayland",
        }
        calls = []
        def runner(argv, timeout):
            calls.append(argv)
            return {"status": "OK", "returncode": 0, "stdout": json.dumps({"outputs": []}), "stderr": ""}

        with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "RESOLVED", "environment": fake_env}):
            with mock.patch.object(caps_mod, "is_graphical_context_usable", return_value=True):
                result = caps_mod.collect_display(self.home, PAYLOAD, runner)
                self.assertEqual(len(calls), 1)
                cmd = calls[0]
                self.assertEqual(cmd[-2:], ["kscreen-doctor", "-j"])
                self.assertIn("WAYLAND_DISPLAY=wayland-0", cmd)

    def test_5_stale_missing_wayland_socket_treated_as_unusable_context(self):
        """A stale or missing Wayland socket path is rejected as unusable."""
        empty_proc = pathlib.Path(self.temp_dir.name) / "proc"
        empty_proc.mkdir(parents=True, exist_ok=True)
        stale_env = {
            "WAYLAND_DISPLAY": "wayland-999",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
        }
        # The socket does not exist
        self.assertFalse(caps_mod.is_graphical_context_usable(stale_env, uid=os.getuid()))
        res = caps_mod.resolve_graphical_context(proc_root=empty_proc, environment=stale_env, require_live_socket=True)
        self.assertEqual(res["status"], "UNAVAILABLE")

        # And observed_display_size does not invoke kscreen
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value=res):
                size = engine_mod.observed_display_size(environment=stale_env)
                self.assertIsNone(size)
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_6_native_kde_graphical_environment_preserved(self):
        """When a real Wayland socket exists, context is verified as usable and resolved."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        uid = os.getuid()
        valid_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "KDE",
        }
        self.assertTrue(caps_mod.is_graphical_context_usable(valid_env, uid=uid))
        with mock.patch.object(caps_mod, "_safe_graphical_environment", return_value=valid_env):
            res = caps_mod.resolve_graphical_context(environment=valid_env, require_live_socket=True)
            self.assertEqual(res["status"], "RESOLVED")
            self.assertEqual(res["environment"]["WAYLAND_DISPLAY"], "wayland-0")

    def test_7_ssh_like_environment_with_resolvable_session_propagates_variables(self):
        """When called from SSH (no display in env) but active session exists in /proc, resolve_graphical_context discovers it."""
        mock_proc = self.temp_dir.name + "/proc"
        proc_path = pathlib.Path(mock_proc)
        proc_path.mkdir(parents=True, exist_ok=True)
        uid = os.getuid()
        kwin = proc_path / "10"
        kwin.mkdir()
        (kwin / "comm").write_text("kwin_wayland\n")
        (kwin / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        child = proc_path / "11"
        child.mkdir()
        (child / "comm").write_text("plasma-keyboard\n")
        (child / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nPPid:\t10\n")
        (child / "cmdline").write_bytes(b"/usr/bin/plasma-keyboard\0")
        (child / "environ").write_bytes(
            f"XDG_RUNTIME_DIR=/run/user/{uid}\0DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus\0WAYLAND_DISPLAY=wayland-0\0XDG_SESSION_TYPE=wayland\0KDE_FULL_SESSION=true\0".encode()
        )
        res = caps_mod.resolve_graphical_context(proc_root=proc_path, uid=uid, environment={}, require_live_socket=False)
        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["environment"]["WAYLAND_DISPLAY"], "wayland-0")
        self.assertEqual(res["environment"]["XDG_SESSION_TYPE"], "wayland")

    def test_8_ssh_like_environment_with_no_graphical_session_clean_failure(self):
        """When starting openhtpc-session-start with no graphical context, it exits cleanly with code 3 and specific message."""
        empty_proc = pathlib.Path(self.temp_dir.name) / "proc"
        empty_proc.mkdir(parents=True, exist_ok=True)
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(PAYLOAD),
            "OPENHTPC_PROC_ROOT": str(empty_proc),
        }
        result = subprocess.run(
            [str(PAYLOAD / "openhtpc-session-start")],
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("OPENHTPC_GRAPHICAL_SESSION_UNAVAILABLE", result.stderr)

    def test_9_flex_launch_safeguard_blocks_when_display_missing(self):
        """In openhtpc-home.py, if graphical session is unavailable, startup is blocked before launching Flex."""
        home_path = PAYLOAD / "openhtpc-home.py"
        empty_proc = pathlib.Path(self.temp_dir.name) / "proc"
        empty_proc.mkdir(parents=True, exist_ok=True)
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(PAYLOAD),
            "OPENHTPC_PROC_ROOT": str(empty_proc),
        }
        result = subprocess.run(
            [sys.executable, str(home_path)],
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENHTPC_GRAPHICAL_SESSION_UNAVAILABLE", result.stderr)

    def test_10_no_coredump_producing_subprocess_path_in_headless_fixtures(self):
        """Diagnostic scripts and engine do not execute kscreen-doctor when headless."""
        empty_proc = pathlib.Path(self.temp_dir.name) / "proc"
        empty_proc.mkdir(parents=True, exist_ok=True)
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(PAYLOAD),
            "OPENHTPC_PROC_ROOT": str(empty_proc),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, clean_env, clear=True):
                sig = cinema_mod._build_current_output_sig()
                self.assertEqual(sig, "")
                cal_sig = calibrate_mod._get_display_signature()
                self.assertEqual(cal_sig["connector"], "UNKNOWN")
                bm_sig = benchmark_mod.get_display_signature()
                self.assertEqual(bm_sig["resolution"], "UNKNOWN")
                size = engine_mod.observed_display_size(environment={})
                self.assertIsNone(size)

            for call in mock_run.call_args_list:
                cmd = call[0][0] if call[0] else []
                self.assertNotIn("kscreen-doctor", cmd)

    def test_11_refresh_matcher_policy_and_50hz_cadence_preserved(self):
        """Refresh matching rules and conservative 25 fps -> 50 Hz selection remain intact."""
        refresh_mod = _load_module("openhtpc_refresh_match_test", PAYLOAD / "openhtpc-refresh-match.py")
        modes = [
            {"id": "mode-60", "width": 1920, "height": 1080, "refresh_hz": 60.0},
            {"id": "mode-50", "width": 1920, "height": 1080, "refresh_hz": 50.0},
            {"id": "mode-24", "width": 1920, "height": 1080, "refresh_hz": 24.0},
        ]
        output = {
            "connector": "HDMI-A-1",
            "output_id": 1,
            "display_identity": "0" * 64,
            "active": True,
            "connected": True,
            "scale": 1.0,
            "current_mode_id": "mode-60",
            "current_mode": {"width": 1920, "height": 1080, "refresh_hz": 60.0},
            "available_modes": modes,
        }
        snap = {"outputs": [output], "active_output": output}
        status, match = refresh_mod.select(snap, 25.0)
        self.assertEqual(status, "MATCH_AVAILABLE")
        self.assertIsNotNone(match)
        self.assertEqual(match["refresh_hz"], 50.0)
        self.assertEqual(match["id"], "mode-50")

    def test_12_no_db_schema_version_change(self):
        """Database schema and product version remain strictly untouched."""
        db_mod = _load_module("openhtpc_media_db_test", PAYLOAD / "openhtpc-media-db.py")
        self.assertEqual(db_mod.SCHEMA_VERSION, 2)
        version_text = (ROOT / "VERSION").read_text().strip()
        self.assertEqual(version_text, "1.2.0-rc7")

    def test_13_cinema_auto_stale_wayland_socket_does_not_invoke_kscreen(self):
        """Case A: cinema-auto with WAYLAND_DISPLAY present but socket missing does not invoke kscreen."""
        stale_env = {
            "WAYLAND_DISPLAY": "wayland-999",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_env, clear=True):
                sig = cinema_mod._build_current_output_sig()
                self.assertEqual(sig, "")
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_14_cinema_auto_valid_wayland_socket_invokes_kscreen(self):
        """Case B: cinema-auto with valid Wayland socket invokes kscreen-doctor normally."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        valid_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        mock_output = "Output: 1 HDMI-A-1\n1920x1080@60.00*\nColor resolution: 8 (8)\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=mock_output)
            with mock.patch.dict(os.environ, valid_env, clear=True):
                sig = cinema_mod._build_current_output_sig()
                self.assertTrue(len(sig) == 64)  # sha256 hex string
                self.assertTrue(any(
                    call[0][0] == ["kscreen-doctor", "-o"]
                    for call in mock_run.call_args_list
                ))

    def test_15_cinema_auto_stale_x11_endpoint_does_not_invoke_kscreen(self):
        """Stale X11 endpoint: cinema-auto with dead DISPLAY does not invoke kscreen."""
        stale_x11 = {
            "DISPLAY": ":99",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_x11, clear=True):
                sig = cinema_mod._build_current_output_sig()
                self.assertEqual(sig, "")
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_16_calibrate_stale_wayland_socket_does_not_invoke_kscreen(self):
        """Case A: calibrate with WAYLAND_DISPLAY present but socket missing does not invoke kscreen."""
        stale_env = {
            "WAYLAND_DISPLAY": "wayland-999",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_env, clear=True):
                sig = calibrate_mod._get_display_signature()
                self.assertEqual(sig["connector"], "UNKNOWN")
                self.assertIsNone(sig["width"])
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_17_calibrate_valid_wayland_socket_invokes_kscreen(self):
        """Case B: calibrate with valid Wayland socket invokes kscreen-doctor normally."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        valid_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        mock_output = "Output: 1 DP-2\n3840x2160@120.00*\nColor resolution: 10 (10)\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=mock_output)
            with mock.patch.dict(os.environ, valid_env, clear=True):
                sig = calibrate_mod._get_display_signature()
                self.assertEqual(sig["connector"], "DP-2")
                self.assertEqual(sig["width"], 3840)
                self.assertEqual(sig["height"], 2160)
                self.assertEqual(sig["refresh_hz"], 120.0)
                self.assertEqual(sig["bit_depth"], 10)
                self.assertTrue(any(
                    call[0][0] == ["kscreen-doctor", "-o"]
                    for call in mock_run.call_args_list
                ))

    def test_18_calibrate_stale_x11_endpoint_does_not_invoke_kscreen(self):
        """Stale X11 endpoint: calibrate with dead DISPLAY does not invoke kscreen."""
        stale_x11 = {
            "DISPLAY": ":99",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_x11, clear=True):
                sig = calibrate_mod._get_display_signature()
                self.assertEqual(sig["connector"], "UNKNOWN")
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_19_benchmark_stale_wayland_socket_does_not_invoke_kscreen(self):
        """Case A: benchmark with WAYLAND_DISPLAY present but socket missing does not invoke kscreen."""
        stale_env = {
            "WAYLAND_DISPLAY": "wayland-999",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_env, clear=True):
                sig = benchmark_mod.get_display_signature()
                self.assertEqual(sig["resolution"], "UNKNOWN")
                self.assertIsNone(sig["width"])
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_20_benchmark_valid_wayland_socket_invokes_kscreen(self):
        """Case B: benchmark with valid Wayland socket invokes kscreen-doctor normally."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        valid_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        mock_output = "Output: 1 HDMI-A-1\n1920x1080@50.00*\nColor resolution: 8 (8)\nScale: 1.0\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=mock_output)
            with mock.patch.dict(os.environ, valid_env, clear=True):
                sig = benchmark_mod.get_display_signature()
                self.assertEqual(sig["connector"], "HDMI-A-1")
                self.assertEqual(sig["resolution"], "1920x1080")
                self.assertEqual(sig["width"], 1920)
                self.assertEqual(sig["height"], 1080)
                self.assertEqual(sig["refresh_rate_hz"], 50.0)
                self.assertTrue(any(
                    call[0][0] == ["kscreen-doctor", "-o"]
                    for call in mock_run.call_args_list
                ))

    def test_21_benchmark_stale_x11_endpoint_does_not_invoke_kscreen(self):
        """Stale X11 endpoint: benchmark with dead DISPLAY does not invoke kscreen."""
        stale_x11 = {
            "DISPLAY": ":99",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.dict(os.environ, stale_x11, clear=True):
                sig = benchmark_mod.get_display_signature()
                self.assertEqual(sig["resolution"], "UNKNOWN")
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_22_refresh_match_runtime_apply_stale_socket_does_not_invoke_kscreen(self):
        """Case A: refresh-match Runtime.apply with stale socket does not invoke kscreen."""
        refresh_mod = _load_module("openhtpc_refresh_match_test2", PAYLOAD / "openhtpc-refresh-match.py")
        r = refresh_mod.Runtime.__new__(refresh_mod.Runtime)
        r.home = self.home
        r.install = PAYLOAD
        r.caps = caps_mod
        stale_env = {
            "WAYLAND_DISPLAY": "wayland-999",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
        }
        output = {"output_id": 1, "connector": "DP-1"}
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "RESOLVED", "environment": stale_env}):
                res = r.apply(output, "mode-1")
                self.assertFalse(res)
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)

    def test_23_refresh_match_runtime_apply_valid_socket_invokes_kscreen(self):
        """Case B: refresh-match Runtime.apply with valid socket invokes kscreen-doctor normally."""
        self._create_unix_socket(self.runtime_dir, "wayland-0")
        refresh_mod = _load_module("openhtpc_refresh_match_test3", PAYLOAD / "openhtpc-refresh-match.py")
        r = refresh_mod.Runtime.__new__(refresh_mod.Runtime)
        r.home = self.home
        r.install = PAYLOAD
        r.caps = caps_mod
        valid_env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": str(self.runtime_dir),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
        }
        output = {"output_id": 1, "connector": "DP-1"}
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0)
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "RESOLVED", "environment": valid_env}):
                res = r.apply(output, "mode-1")
                self.assertTrue(res)
                self.assertTrue(any(
                    call[0][0] == ["kscreen-doctor", "output.1.mode.mode-1"]
                    for call in mock_run.call_args_list
                ))

    def test_24_refresh_match_runtime_apply_stale_x11_does_not_invoke_kscreen(self):
        """Stale X11 endpoint: refresh-match Runtime.apply with dead DISPLAY does not invoke kscreen."""
        refresh_mod = _load_module("openhtpc_refresh_match_test4", PAYLOAD / "openhtpc-refresh-match.py")
        r = refresh_mod.Runtime.__new__(refresh_mod.Runtime)
        r.home = self.home
        r.install = PAYLOAD
        r.caps = caps_mod
        stale_x11 = {"DISPLAY": ":99"}
        output = {"output_id": 1, "connector": "DP-1"}
        with mock.patch("subprocess.run") as mock_run:
            with mock.patch.object(caps_mod, "resolve_graphical_context", return_value={"status": "RESOLVED", "environment": stale_x11}):
                res = r.apply(output, "mode-1")
                self.assertFalse(res)
                for call in mock_run.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    self.assertNotIn("kscreen-doctor", cmd)


if __name__ == "__main__":
    unittest.main()
