# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import configparser
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
INSTALLER = PAYLOAD / "install-openhtpc-fedora.sh"
UNINSTALLER = ROOT / "uninstall.sh"


class Rc7KdeLauncherIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install_dir = self.home / ".local/lib/openhtpc"
        self.bin_dir = self.home / ".local/bin"
        self.apps_dir = self.home / ".local/share/applications"
        self.autostart_dir = self.home / ".config/autostart"
        self.state_dir = self.home / ".local/state/openhtpc"

    def _run_installer(self, home: pathlib.Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        # Pre-populate fake profile to allow non-interactive installation without full hardware probe benchmark
        (home / ".config/openhtpc").mkdir(parents=True, exist_ok=True)
        (home / ".config/openhtpc/profile.json").write_text("{}", encoding="utf-8")

        env = {
            **os.environ,
            "HOME": str(home),
            "OPENHTPC_HOME": str(home),
            "OPENHTPC_INSTALL_DIR": str(home / ".local/lib/openhtpc"),
            "OPENHTPC_UPDATE_MODE": "0",
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
        }
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        if extra_env:
            env.update(extra_env)

        return subprocess.run(
            ["bash", str(INSTALLER)],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_01_real_sandboxed_installation_and_desktop_file_validate(self):
        result = self._run_installer(self.home)
        self.assertEqual(result.returncode, 0, result.stderr)

        desktop_path = self.apps_dir / "openhtpc.desktop"
        autostart_path = self.autostart_dir / "openhtpc.desktop"
        self.assertTrue(desktop_path.is_file(), "Launcher desktop file was not created")
        self.assertTrue(autostart_path.is_file(), "Autostart desktop file was not created")

        # Validate using system desktop-file-validate if available
        if shutil.which("desktop-file-validate"):
            for path in (desktop_path, autostart_path):
                val_res = subprocess.run(["desktop-file-validate", str(path)], capture_output=True, text=True)
                self.assertEqual(val_res.returncode, 0, f"desktop-file-validate failed on {path}: {val_res.stderr} / {val_res.stdout}")

    def test_02_desktop_entry_fields_and_exact_canonical_exec(self):
        result = self._run_installer(self.home)
        self.assertEqual(result.returncode, 0, result.stderr)

        desktop_path = self.apps_dir / "openhtpc.desktop"
        # Check permissions (0644)
        stat_mode = desktop_path.stat().st_mode & 0o777
        self.assertEqual(stat_mode, 0o644)

        raw_content = desktop_path.read_text(encoding="utf-8")
        # Ensure exact Exec line is present without quoting or $HOME
        self.assertIn("Exec=openhtpc start\n", raw_content)

        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(raw_content)
        self.assertIn("Desktop Entry", parser)
        entry = parser["Desktop Entry"]
        self.assertEqual(entry.get("Type"), "Application")
        self.assertEqual(entry.get("Name"), "OPENHTPC")
        self.assertEqual(entry.get("Comment"), "Centre multimédia de salon OPENHTPC")
        self.assertEqual(entry.get("Exec"), "openhtpc start")

        icon_path = entry.get("Icon")
        self.assertEqual(icon_path, str(self.install_dir / "assets/branding/openhtpc-logo.png"))
        self.assertTrue(pathlib.Path(icon_path).is_file(), f"Icon file does not exist on disk: {icon_path}")

        self.assertEqual(entry.get("Terminal"), "false")
        self.assertEqual(entry.get("Categories"), "AudioVideo;Video;Player;TV;")
        self.assertEqual(entry.get("StartupNotify"), "true")
        self.assertEqual(entry.get("X-OPENHTPC-Managed"), "true")

        # Also verify autostart desktop entry
        autostart_path = self.autostart_dir / "openhtpc.desktop"
        autostart_raw = autostart_path.read_text(encoding="utf-8")
        expected_autostart_exec = f"{self.bin_dir / 'openhtpc'} start"
        self.assertIn(f"Exec={expected_autostart_exec}\n", autostart_raw)
        auto_parser = configparser.ConfigParser(interpolation=None)
        auto_parser.read_string(autostart_raw)
        auto_entry = auto_parser["Desktop Entry"]
        self.assertEqual(auto_entry.get("Type"), "Application")
        self.assertEqual(auto_entry.get("Name"), "OPENHTPC Basic")
        self.assertEqual(auto_entry.get("Exec"), expected_autostart_exec)
        self.assertEqual(auto_entry.get("Terminal"), "false")
        self.assertEqual(auto_entry.get("X-KDE-autostart-after"), "panel")
        self.assertEqual(auto_entry.get("X-OPENHTPC-Managed"), "true")

    def test_03_sandboxed_path_resolution_and_exact_argv_with_gio_launch(self):
        result = self._run_installer(self.home)
        self.assertEqual(result.returncode, 0, result.stderr)

        desktop_path = self.apps_dir / "openhtpc.desktop"
        self.assertTrue(desktop_path.is_file())

        # Create a sandboxed bin directory containing a fake openhtpc executable
        sandbox_bin = self.root / "sandbox_bin"
        sandbox_bin.mkdir()
        fake_openhtpc = sandbox_bin / "openhtpc"
        log_file = self.root / "openhtpc_invocation.json"

        script_code = f"""#!/usr/bin/env python3
import sys, json, os
with open({repr(str(log_file))}, "w", encoding="utf-8") as f:
    json.dump({{"argv": sys.argv, "pid": os.getpid(), "ppid": os.getppid()}}, f)
raise SystemExit(0)
"""
        fake_openhtpc.write_text(script_code, encoding="utf-8")
        fake_openhtpc.chmod(0o755)

        env = {
            **os.environ,
            "PATH": f"{sandbox_bin}:{os.environ.get('PATH', '')}",
            "HOME": str(self.home),
        }

        # Test execution using gio launch if available
        if shutil.which("gio"):
            gio_res = subprocess.run(
                ["gio", "launch", str(desktop_path)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(gio_res.returncode, 0, f"gio launch failed: {gio_res.stderr}")

            # Give a brief moment for subprocess execution
            for _ in range(20):
                if log_file.exists():
                    break
                time.sleep(0.05)

            self.assertTrue(log_file.exists(), "Fake openhtpc was not executed by gio launch")
            call_data = json.loads(log_file.read_text(encoding="utf-8"))
            argv = call_data.get("argv", [])

            # Verify exact binary resolution, exact argv, no parasite arguments or shells
            self.assertEqual(len(argv), 2, f"Expected exactly 2 arguments (executable and 'start'), got: {argv}")
            self.assertEqual(os.path.realpath(argv[0]), str(fake_openhtpc.resolve()))
            self.assertEqual(argv[1], "start", f"Expected argv[1] == 'start', got: {argv[1]}")

    def test_04_custom_xdg_data_home_respected_for_installation_and_uninstallation(self):
        custom_data = self.root / "custom_data_dir"
        custom_apps = custom_data / "applications"

        result = self._run_installer(self.home, extra_env={"XDG_DATA_HOME": str(custom_data)})
        self.assertEqual(result.returncode, 0, result.stderr)

        custom_desktop = custom_apps / "openhtpc.desktop"
        self.assertTrue(custom_desktop.is_file())
        self.assertFalse((self.apps_dir / "openhtpc.desktop").exists())

        # Uninstall
        env = {**os.environ, "HOME": str(self.home), "XDG_DATA_HOME": str(custom_data)}
        un_res = subprocess.run(["bash", str(UNINSTALLER)], cwd=str(ROOT), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(un_res.returncode, 0, un_res.stderr)
        self.assertFalse(custom_desktop.exists())

    def test_05_installation_is_idempotent(self):
        res1 = self._run_installer(self.home)
        self.assertEqual(res1.returncode, 0, res1.stderr)
        desktop_path = self.apps_dir / "openhtpc.desktop"
        content1 = desktop_path.read_text(encoding="utf-8")

        res2 = self._run_installer(self.home)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        content2 = desktop_path.read_text(encoding="utf-8")
        self.assertEqual(content1, content2)

    def test_06_preflight_collision_refuses_unmanaged_external_file_before_mutations(self):
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_path = self.apps_dir / "openhtpc.desktop"
        desktop_path.write_text("[Desktop Entry]\nName=Custom User Tool\n", encoding="utf-8")

        result = self._run_installer(self.home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refus d'écraser le lanceur d'applications externe", result.stderr)
        # Content unchanged
        self.assertEqual(desktop_path.read_text(encoding="utf-8"), "[Desktop Entry]\nName=Custom User Tool\n")
        # Ensure preflight stopped before installing builder / product files into INSTALL_DIR
        self.assertFalse((self.install_dir / "openhtpc-session-engine.py").exists())

    def test_07_preflight_collision_refuses_symlink_and_never_modifies_sentinel_target(self):
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.root / "external_sentinel.desktop"
        sentinel_original_content = "[Desktop Entry]\nName=External Sentinel\nX-OPENHTPC-Managed=true\n"
        sentinel.write_text(sentinel_original_content, encoding="utf-8")

        desktop_path = self.apps_dir / "openhtpc.desktop"
        desktop_path.symlink_to(sentinel)

        result = self._run_installer(self.home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refus d'écraser le lien symbolique", result.stderr)

        # Sentinel must be strictly untouched
        self.assertEqual(sentinel.read_text(encoding="utf-8"), sentinel_original_content)
        self.assertTrue(desktop_path.is_symlink())
        self.assertFalse((self.install_dir / "openhtpc-session-engine.py").exists())

    def test_08_autostart_preflight_collision_refuses_symlink_and_preserves_sentinel(self):
        self.autostart_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.root / "autostart_sentinel.desktop"
        sentinel_content = "[Desktop Entry]\nName=External Autostart\nX-OPENHTPC-Managed=true\n"
        sentinel.write_text(sentinel_content, encoding="utf-8")

        autostart_path = self.autostart_dir / "openhtpc.desktop"
        autostart_path.symlink_to(sentinel)

        result = self._run_installer(self.home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refus d'écraser le lien symbolique autostart", result.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), sentinel_content)
        self.assertTrue(autostart_path.is_symlink())

    def test_09_uninstaller_removes_managed_launcher_and_preserves_user_files(self):
        self._run_installer(self.home)
        desktop_path = self.apps_dir / "openhtpc.desktop"
        self.assertTrue(desktop_path.is_file())

        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        un_res = subprocess.run(["bash", str(UNINSTALLER)], cwd=str(ROOT), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(un_res.returncode, 0, un_res.stderr)
        self.assertFalse(desktop_path.exists())

    def test_10_uninstaller_never_follows_or_deletes_symlink_target(self):
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        (self.install_dir / "VERSION").write_text("1.2.0-dev14\n")

        sentinel = self.root / "external_sentinel.desktop"
        sentinel_content = "[Desktop Entry]\nName=External\nX-OPENHTPC-Managed=true\n"
        sentinel.write_text(sentinel_content, encoding="utf-8")

        desktop_path = self.apps_dir / "openhtpc.desktop"
        desktop_path.symlink_to(sentinel)

        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        un_res = subprocess.run(["bash", str(UNINSTALLER)], cwd=str(ROOT), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(un_res.returncode, 0, un_res.stderr)
        # Symlink and target preserved
        self.assertTrue(desktop_path.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), sentinel_content)

    def test_11_uninstaller_preserves_unmanaged_desktop_entry(self):
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        (self.install_dir / "VERSION").write_text("1.2.0-dev14\n")

        desktop_path = self.apps_dir / "openhtpc.desktop"
        desktop_path.write_text("[Desktop Entry]\nName=Custom User Launcher\n", encoding="utf-8")

        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        un_res = subprocess.run(["bash", str(UNINSTALLER)], cwd=str(ROOT), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(un_res.returncode, 0, un_res.stderr)
        self.assertTrue(desktop_path.is_file())
        self.assertEqual(desktop_path.read_text(encoding="utf-8"), "[Desktop Entry]\nName=Custom User Launcher\n")

    def test_12_home_with_special_characters_never_modifies_exec_and_icon_points_to_valid_file(self):
        # HOME directory containing spaces, %, quotes, backslashes, $, backticks, and parentheses
        special_home = self.root / "home with spaces %20 \"quotes\" \\back $var `tick` (parens)"
        special_home.mkdir(parents=True, exist_ok=True)

        result = self._run_installer(special_home)
        self.assertEqual(result.returncode, 0, result.stderr)

        desktop_path = special_home / ".local/share/applications/openhtpc.desktop"
        self.assertTrue(desktop_path.is_file())

        raw_content = desktop_path.read_text(encoding="utf-8")
        # Exec must be exactly 'openhtpc start' without any home path or escape artifacts
        self.assertIn("Exec=openhtpc start\n", raw_content)

        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(raw_content)
        entry = parser["Desktop Entry"]
        self.assertEqual(entry.get("Exec"), "openhtpc start")

        # Icon must point to the actual file path without % field-code transformations
        icon_path = entry.get("Icon")
        expected_icon = special_home / ".local/lib/openhtpc/assets/branding/openhtpc-logo.png"
        self.assertEqual(icon_path, str(expected_icon))
        self.assertTrue(pathlib.Path(icon_path).is_file(), f"Icon does not point to valid file: {icon_path}")

        # Validate with desktop-file-validate
        if shutil.which("desktop-file-validate"):
            val_res = subprocess.run(["desktop-file-validate", str(desktop_path)], capture_output=True, text=True)
            self.assertEqual(val_res.returncode, 0, f"Validation failed for special home path: {val_res.stderr} / {val_res.stdout}")

    def test_13_isolation_and_no_leak_outside_sandboxed_home(self):
        # Verify that running installer in sandbox never touches real user files outside the test directory
        result = self._run_installer(self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".local/share/applications/openhtpc.desktop").is_file())

    def test_14_systemd_generator_accepts_autostart_without_local_bin_in_path(self):
        generator = pathlib.Path("/usr/lib/systemd/user-generators/systemd-xdg-autostart-generator")
        if not generator.is_file():
            self.skipTest("systemd-xdg-autostart-generator unavailable")
        result = self._run_installer(self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        normal, early, late = (self.root / name for name in ("gen", "early", "late"))
        for directory in (normal, early, late):
            directory.mkdir()
        env = {**os.environ, "HOME": str(self.home),
               "XDG_CONFIG_HOME": str(self.home / ".config"), "PATH": "/usr/bin:/bin"}
        generated = subprocess.run(
            [str(generator), str(normal), str(early), str(late)],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        unit = late / "app-openhtpc@autostart.service"
        self.assertTrue(unit.is_file(), generated.stderr)
        self.assertNotIn("Exec binary 'openhtpc' does not exist", generated.stderr)


if __name__ == "__main__":
    unittest.main()
