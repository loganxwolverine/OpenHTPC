"""Standalone, no-KDE regression guards for the 1.3.x managed uninstall contract."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "uninstall.sh"


class ManagedUninstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "test-home"
        self.home.mkdir()
        self.install = self.home / ".local/lib/openhtpc"
        self.install.mkdir(parents=True)
        self.config = self.home / ".config/openhtpc"
        self.config.mkdir(parents=True)
        (self.config / "user-config.json").write_text("{}")
        self.media = self.home / "Videos"
        self.media.mkdir()
        (self.media / "movie.mkv").write_bytes(b"KEEP ORIGINAL USER MEDIA")
        (self.install / "VERSION").write_text("1.3.2-rc1\n")
        (self.install / "openhtpc").write_text("product")
        (self.install / "flex/bin").mkdir(parents=True)
        (self.install / "flex/bin/flex-launcher").write_text("binary")
        (self.install / ".openhtpc-managed-files").write_text(
            ".openhtpc-managed-files\nVERSION\nopenhtpc\nflex/bin/flex-launcher\n"
        )
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        (self.bin / "openhtpc").symlink_to(self.install / "openhtpc")
        (self.bin / "openhtpc-validator").symlink_to(self.install / "openhtpc-validator")
        self.external = self.root / "EXTERNAL"
        self.external.write_text("SENTINEL")

    def run_uninstall(self, *args):
        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
        }
        return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)

    def assert_user_media_preserved(self):
        self.assertEqual((self.media / "movie.mkv").read_bytes(), b"KEEP ORIGINAL USER MEDIA")
        self.assertEqual(self.external.read_text(), "SENTINEL")

    def test_clean_purge_rc1_removes_managed_install_and_config_and_links(self):
        r = self.run_uninstall("--purge-config")
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        self.assertFalse(self.install.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse((self.bin / "openhtpc").is_symlink())
        self.assertFalse((self.bin / "openhtpc-validator").is_symlink())
        self.assert_user_media_preserved()

    def test_uninstall_without_purge_preserves_user_config(self):
        r = self.run_uninstall()
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        self.assertFalse(self.install.exists())
        self.assertEqual((self.config / "user-config.json").read_text(), "{}")
        self.assert_user_media_preserved()

    def test_stable_131_is_also_supported(self):
        (self.install / "VERSION").write_text("1.3.1\n")
        r = self.run_uninstall("--purge-config")
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        self.assertFalse(self.install.exists())
        self.assert_user_media_preserved()

    def test_custom_plugin_is_preserved_under_install(self):
        custom = self.install / "plugins/available/plugin.user/secret.ini"
        custom.parent.mkdir(parents=True)
        custom.write_text("keep me")
        r = self.run_uninstall("--purge-config")
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        self.assertEqual(custom.read_text(), "keep me")
        self.assertFalse((self.install / "openhtpc").exists())
        self.assertIn("Unmanaged files preserved", r.stdout)
        self.assert_user_media_preserved()

    def test_symlink_parent_never_followed(self):
        (self.install / "flex/bin/flex-launcher").unlink()
        (self.install / "flex/bin").rmdir()
        (self.install / "flex").rmdir()
        outside = self.root / "outside"
        (outside / "bin").mkdir(parents=True)
        (outside / "bin/flex-launcher").write_text("preserve")
        (self.install / "flex").symlink_to(outside, target_is_directory=True)
        r = self.run_uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPENHTPC_UNINSTALL_MANAGED_PATH_ESCAPES_ROOT", r.stderr)
        self.assertEqual((outside / "bin/flex-launcher").read_text(), "preserve")
        self.assert_user_media_preserved()

    def test_manifest_path_traversal_is_rejected(self):
        (self.install / ".openhtpc-managed-files").write_text(
            ".openhtpc-managed-files\nVERSION\nopenhtpc\n../EXTERNAL\n"
        )
        r = self.run_uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPENHTPC_UNINSTALL_MANIFEST_UNSAFE", r.stderr)
        self.assertTrue((self.install / "VERSION").exists())
        self.assert_user_media_preserved()

    def test_unsafe_late_entry_does_not_partially_delete_managed_files(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("never remove")
        (self.install / "zz-outside").symlink_to(outside, target_is_directory=True)
        (self.install / ".openhtpc-managed-files").write_text(
            ".openhtpc-managed-files\nVERSION\nopenhtpc\n"
            "a-product\nzz-outside/sentinel.txt\n"
        )
        (self.install / "a-product").write_text("keep until preflight")
        r = self.run_uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPENHTPC_UNINSTALL_MANAGED_PATH_ESCAPES_ROOT", r.stderr)
        self.assertEqual((self.install / "a-product").read_text(), "keep until preflight")
        self.assertEqual((outside / "sentinel.txt").read_text(), "never remove")

    def test_manifest_missing_refuses_clean_up(self):
        (self.install / ".openhtpc-managed-files").unlink()
        r = self.run_uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPENHTPC_UNINSTALL_MANIFEST_MISSING", r.stderr)
        self.assertTrue((self.install / "VERSION").exists())
        self.assert_user_media_preserved()


if __name__ == "__main__":
    unittest.main()
