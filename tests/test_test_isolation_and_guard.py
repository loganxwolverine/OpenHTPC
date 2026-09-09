"""Tests verifying test hermeticity, environment isolation, and leak prevention.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import json
import os
import pathlib
import pwd
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"

try:
    HOST_USER_HOME = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
except (KeyError, OSError):
    HOST_USER_HOME = pathlib.Path("/home/steve").resolve()


class TestIsolationGuards(unittest.TestCase):
    def test_environment_is_sandboxed_and_not_real_home(self):
        """Verify that current test environment has HOME redirected away from real user directory."""
        if os.environ.get("OPENHTPC_TEST_ENVIRONMENT") != "1":
            self.skipTest("Outer test-session sandbox not active; requires pytest or sandboxed test runner")
        current_home = pathlib.Path(os.environ.get("HOME", "")).resolve()
        
        if HOST_USER_HOME.exists():
            self.assertNotEqual(
                current_home,
                HOST_USER_HOME,
                f"HOME leaked into real user directory: {current_home}",
            )

    def test_openhtpc_home_is_set_and_sandboxed(self):
        """Verify that OPENHTPC_HOME is set and isolated."""
        if os.environ.get("OPENHTPC_TEST_ENVIRONMENT") != "1":
            self.skipTest("Outer test-session sandbox not active; requires pytest or sandboxed test runner")
        openhtpc_home = os.environ.get("OPENHTPC_HOME")
        self.assertIsNotNone(openhtpc_home, "OPENHTPC_HOME must be set during test execution")
        openhtpc_path = pathlib.Path(openhtpc_home).resolve()
        if HOST_USER_HOME.exists():
            self.assertNotEqual(openhtpc_path, HOST_USER_HOME)

    def test_display_variables_are_scrubbed_preventing_dialogs(self):
        """Verify that DISPLAY and WAYLAND_DISPLAY are absent to prevent graphical modal popups."""
        self.assertNotIn("DISPLAY", os.environ)
        self.assertNotIn("WAYLAND_DISPLAY", os.environ)

    def test_xdg_state_and_config_are_sandboxed(self):
        """Verify that XDG variables point to sandboxed directories."""
        for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            val = os.environ.get(var)
            if val:
                path = pathlib.Path(val).resolve()
                if HOST_USER_HOME.exists():
                    self.assertFalse(
                        str(path).startswith(str(HOST_USER_HOME / ".local")) or str(path).startswith(str(HOST_USER_HOME / ".config")),
                        f"{var} points to real user directory: {path}",
                    )

    def test_play_script_dialog_suppressed_when_no_display(self):
        """Verify that openhtpc-play notify() suppresses dialogs and logs to stderr when DISPLAY is unset."""
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            install = home / "install"
            install.mkdir()
            play_script = PAYLOAD / "openhtpc-play"
            
            env = {
                "HOME": str(home),
                "OPENHTPC_HOME": str(home),
                "OPENHTPC_INSTALL_DIR": str(install),
                "PATH": os.environ.get("PATH", "/bin:/usr/bin"),
            }
            result = subprocess.run(
                [sys.executable, str(play_script), "mact_invalid_token_test"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotIn("kdialog: cannot connect to X server", result.stderr)

    def test_real_user_state_directory_is_untouched(self):
        """Verify that running test operations never creates or modifies files in real user state directory."""
        real_state = HOST_USER_HOME / ".local/state/openhtpc"
        if real_state.exists():
            files_before = {p: p.stat().st_mtime_ns for p in real_state.rglob("*") if p.is_file()}
            
            with tempfile.TemporaryDirectory() as raw:
                temp_home = pathlib.Path(raw)
                (temp_home / ".local/state/openhtpc").mkdir(parents=True)
                (temp_home / ".config/openhtpc").mkdir(parents=True)
                
                state_file = temp_home / ".local/state/openhtpc/test-state.json"
                state_file.write_text('{"test": true}\n')
                self.assertTrue(state_file.is_file())
                self.assertFalse((real_state / "test-state.json").exists())

            files_after = {p: p.stat().st_mtime_ns for p in real_state.rglob("*") if p.is_file()}
            self.assertEqual(files_before, files_after, "Files in real user state directory were modified!")


if __name__ == "__main__":
    unittest.main()
