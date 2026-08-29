from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
SPEC = importlib.util.spec_from_file_location("rc2_initial_setup", PAYLOAD / "openhtpc-initial-setup.py")
SETUP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(SETUP)


class Rc2InitialSetupContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "install"
        self.install.mkdir()

    def run_main(self, *arguments: str, stdin: str = "") -> tuple[int, str, str]:
        argv = ["openhtpc-initial-setup.py", "--home", str(self.home), *arguments]
        environment = {"OPENHTPC_INSTALL_DIR": str(self.install)}
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
             mock.patch.dict(os.environ, environment, clear=True), \
             mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            try:
                result = SETUP.main()
            except SystemExit as error:
                result = int(error.code)
        return result, stdout.getvalue(), stderr.getvalue()

    def config(self) -> dict:
        return json.loads((self.home / ".config/openhtpc/user-config.json").read_text())

    def test_public_openhtpc_setup_reaches_assistant_without_attribute_error(self):
        for name in ("openhtpc", "openhtpc-core.py", "openhtpc-initial-setup.py"):
            shutil.copy2(PAYLOAD / name, self.install / name)
        environment = {**os.environ, "OPENHTPC_HOME": str(self.home), "OPENHTPC_INSTALL_DIR": str(self.install)}
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)
        result = subprocess.run(
            [sys.executable, str(self.install / "openhtpc"), "setup"],
            input="", text=True, capture_output=True, env=environment, check=False,
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertNotIn("AttributeError", result.stderr)

    def test_graphical_mode_is_selected_and_saved(self):
        media = self.root / "media"
        media.mkdir()
        with mock.patch.object(SETUP, "graphical", return_value=([str(media)], None)) as graphical, \
             mock.patch.dict(os.environ, {"DISPLAY": ":1", "OPENHTPC_INSTALL_DIR": str(self.install)}, clear=True), \
             mock.patch.object(sys, "argv", ["setup", "--home", str(self.home)]):
            self.assertEqual(SETUP.main(), 0)
        graphical.assert_called_once_with(self.home)
        self.assertEqual(self.config()["local_media_sources"], [str(media)])

    def test_non_interactive_accepts_media_source(self):
        media = self.root / "media"
        media.mkdir()
        result, _, _ = self.run_main("--non-interactive", "--media-source", str(media))
        self.assertEqual(result, 0)
        self.assertEqual(self.config()["local_media_sources"], [str(media)])

    def test_non_interactive_accepts_no_sources(self):
        result, _, _ = self.run_main("--non-interactive", "--no-media-sources")
        self.assertEqual(result, 0)
        self.assertEqual(self.config()["local_media_sources"], [])

    def test_non_interactive_rejects_conflicting_source_arguments(self):
        media = self.root / "media"
        media.mkdir()
        result, _, stderr = self.run_main(
            "--non-interactive", "--media-source", str(media), "--no-media-sources"
        )
        self.assertEqual(result, 2)
        self.assertIn("incompatibles", stderr)

    def test_tmdb_token_from_stdin_is_private_and_not_logged(self):
        token = "synthetic-test-token-not-a-credential"
        result, stdout, stderr = self.run_main(
            "--non-interactive", "--no-media-sources", "--tmdb-from-stdin", stdin=token
        )
        self.assertEqual(result, 0)
        self.assertNotIn(token, stdout + stderr)
        credential = self.home / ".config/openhtpc/secrets/tmdb-token"
        self.assertEqual(credential.read_text().strip(), token)
        self.assertEqual(credential.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
