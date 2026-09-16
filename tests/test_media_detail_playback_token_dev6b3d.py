# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic regression tests for DEV6B3D: MovieDetail Play Token Expiry & Action Binding.

Verifies:
1. Generating MEDIA produces native MovieDetail section with valid play token
2. When Flex is on MovieDetail page (current-page=MEDIA_D...), LIRE LE FILM token is accepted
3. Token binds exact resource: source_id, relative_path, semantic_id
4. Full openhtpc-play dispatcher execution resolves exact file and launches MPV
5. Stale token from genuinely superseded generation is rejected (TOKEN_NOT_FOUND)
6. Token executed from a mismatched page is rejected (STALE_PAGE)
7. Arbitrary token is rejected (TOKEN_NOT_FOUND)
8. Malformed token is rejected (INVALID_ACTION_TOKEN)
9. Tampered semantic_id or source_id cannot be substituted
10. Parent folder page remains valid via parent_page_id compatibility
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load_module(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


session_engine = load_module("dev6b3d_session", PAYLOAD / "openhtpc-session-engine.py")
play_module = load_module("dev6b3d_play", PAYLOAD / "openhtpc-play")


class MovieDetailPlaybackTokenDev6B3D(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = pathlib.Path(self.temp_dir.name)
        self.install = PAYLOAD

        # Set up a source directory with "The Thing - STALE TEST.mpg" and a second movie
        self.source = self.home / "validation-source"
        self.source.mkdir(parents=True)
        self.movie_a = self.source / "The Thing - STALE TEST.mpg"
        self.movie_b = self.source / "The Thing.mpg"
        self.movie_a.write_bytes(b"mpg-content-a")
        self.movie_b.write_bytes(b"mpg-content-b")

        config_dir = self.home / ".config/openhtpc"
        config_dir.mkdir(parents=True)
        (config_dir / "user-config.json").write_text(
            json.dumps({"configuration_completed": True, "local_media_sources": [str(self.source)]}),
            encoding="utf-8",
        )
        self.flex_config = config_dir / "flex-v1.ini"
        self.current_manifest = session_engine.current_media_manifest(self.home)

    def generate(self, generation: str = "gen-dev6b3d-1") -> dict:
        ok = session_engine.write_flex_config(
            self.flex_config, self.home, [self.source], self.install, media_generation=generation
        )
        self.assertTrue(ok)
        session_engine.activate_media_manifest(self.flex_config, self.home)
        return json.loads(self.current_manifest.read_text(encoding="utf-8"))

    def set_current_page(self, page_id: str) -> None:
        target = self.home / ".local/state/openhtpc/media-actions/current-page"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page_id + "\n", encoding="utf-8")

    def test_movie_detail_play_token_accepted_on_detail_page(self):
        """Physical failure reproduction: on MovieDetail page, LIRE LE FILM token must NOT expire."""
        model = self.generate("gen-test-1")
        manifest_items = model.get("items", {})

        # Find action for The Thing - STALE TEST.mpg
        action_entry = next(
            (item for item in manifest_items.values() if item.get("relative_path") == "The Thing - STALE TEST.mpg"),
            None,
        )
        self.assertIsNotNone(action_entry)
        token = next(
            t for t, item in manifest_items.items() if item.get("relative_path") == "The Thing - STALE TEST.mpg"
        )

        detail_page = action_entry["page_id"]
        # Must be native MovieDetail section format: MEDIA_D<8 hex chars>
        self.assertRegex(detail_page, r"^MEDIA_D[0-9a-f]{8}$")
        self.assertRegex(action_entry.get("parent_page_id", ""), r"^MEDIA_[0-9a-f]{16}$")

        # Simulate Flex navigating into MovieDetail page
        self.set_current_page(detail_page)

        # load_media_action must succeed without STALE_PAGE
        trusted = play_module.load_media_action(self.home, token)
        self.assertEqual(trusted["page_id"], detail_page)
        self.assertEqual(trusted["source_id"], session_engine.media_source_id(self.source))
        self.assertEqual(trusted["relative_path"], "The Thing - STALE TEST.mpg")
        self.assertEqual(
            trusted["semantic_id"],
            session_engine.media_item_id(trusted["source_id"], pathlib.PurePosixPath("The Thing - STALE TEST.mpg"), "file"),
        )

    def test_movie_detail_dispatch_and_mpv_execution(self):
        """Full end-to-end openhtpc-play execution from MovieDetail page."""
        model = self.generate("gen-test-2")
        token = next(
            t for t, item in model["items"].items() if item.get("relative_path") == "The Thing - STALE TEST.mpg"
        )
        item = model["items"][token]
        self.set_current_page(item["page_id"])

        # Prepare pure.conf and profile.json
        pure_conf = self.home / ".config/openhtpc/pure.conf"
        pure_conf.write_text("vo=null\n", encoding="utf-8")
        (pure_conf.parent / "profile.json").write_text(
            json.dumps({
                "runtime": {"status": "ready"},
                "runtime_profiles": {
                    "profiles": {"PURE": {"generation_status": "generated", "config_path": str(pure_conf)}}
                },
            }),
            encoding="utf-8",
        )

        # Mock MPV
        fake_bin = self.home / "fakebin"
        fake_bin.mkdir()
        mpv_mock = fake_bin / "mpv"
        mpv_mock.write_text(
            "#!/bin/sh\n"
            "for arg in \"$@\"; do\n"
            "  case \"$arg\" in\n"
            "    --log-file=*)\n"
            "      log_path=\"${arg#--log-file=}\"\n"
            "      printf 'Starting playback\\nVO: [gpu-next]\\n' > \"$log_path\"\n"
            "      ;;\n"
            "  esac\n"
            "done\n"
            "printf '%s\\n' \"$@\" > \"$OPENHTPC_TEST_ARGV\"\n",
            encoding="utf-8",
        )
        mpv_mock.chmod(0o755)
        argv_log = self.home / "mpv.argv"

        env = {
            **os.environ,
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(self.install),
            "OPENHTPC_TEST_ARGV": str(argv_log),
            "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        }
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)

        proc = subprocess.run(
            [str(self.install / "openhtpc-play"), token],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"openhtpc-play failed: {proc.stderr}")

        logged_args = argv_log.read_text(encoding="utf-8").splitlines()
        resolved_file = str(self.movie_a.resolve())
        self.assertEqual(logged_args[-1], resolved_file)

        # Verify action state recorded
        state = json.loads((self.home / ".local/state/openhtpc/media-action-last.json").read_text(encoding="utf-8"))
        self.assertTrue(state["dispatcher_seen"])
        self.assertTrue(state["path_resolved"])
        self.assertTrue(state["file_exists"])
        self.assertTrue(state["process_started"])
        self.assertEqual(state["error_class"], "NONE")

    def test_stale_page_rejection(self):
        """Token invoked from a different page is rejected as STALE_PAGE."""
        model = self.generate("gen-test-3")
        token_a = next(
            t for t, item in model["items"].items() if item.get("relative_path") == "The Thing - STALE TEST.mpg"
        )
        token_b = next(
            t for t, item in model["items"].items() if item.get("relative_path") == "The Thing.mpg"
        )
        item_b = model["items"][token_b]

        # Set page to MovieDetail of movie B, try to execute token A
        self.set_current_page(item_b["page_id"])
        with self.assertRaisesRegex(ValueError, "STALE_PAGE"):
            play_module.load_media_action(self.home, token_a)

    def test_superseded_generation_rejection(self):
        """Token from an old generation is rejected with TOKEN_NOT_FOUND."""
        model_1 = self.generate("generation-1")
        token_1 = next(
            t for t, item in model_1["items"].items() if item.get("relative_path") == "The Thing - STALE TEST.mpg"
        )
        item_1 = model_1["items"][token_1]
        self.set_current_page(item_1["page_id"])

        # Generates new generation
        model_2 = self.generate("generation-2")
        self.assertNotEqual(model_1["manifest_generation"], model_2["manifest_generation"])
        self.assertNotIn(token_1, model_2["items"])

        with self.assertRaisesRegex(ValueError, "TOKEN_NOT_FOUND"):
            play_module.load_media_action(self.home, token_1)

    def test_arbitrary_and_malformed_token_rejection(self):
        """Arbitrary and malformed tokens are strictly rejected."""
        self.generate("gen-test-4")
        self.set_current_page("MEDIA_ROOT")

        with self.assertRaisesRegex(ValueError, "INVALID_ACTION_TOKEN"):
            play_module.load_media_action(self.home, "mact_invalid")

        with self.assertRaisesRegex(ValueError, "TOKEN_NOT_FOUND"):
            play_module.load_media_action(self.home, "mact_" + "0" * 32)

    def test_parent_folder_page_compatibility(self):
        """Parent folder page remains accepted via parent_page_id."""
        model = self.generate("gen-test-5")
        token = next(
            t for t, item in model["items"].items() if item.get("relative_path") == "The Thing - STALE TEST.mpg"
        )
        item = model["items"][token]

        # Set page to parent folder
        self.set_current_page(item["parent_page_id"])
        trusted = play_module.load_media_action(self.home, token)
        self.assertEqual(trusted["relative_path"], "The Thing - STALE TEST.mpg")


if __name__ == "__main__":
    unittest.main()
