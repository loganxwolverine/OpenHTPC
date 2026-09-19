# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic concurrency and session ownership tests for openhtpc-session-start (DEV6C3J).

Guarantees:
- Authoritative session lock is acquired BEFORE any config mutation or generation.
- A secondary start while active returns START_ALREADY_ACTIVE with ZERO config/manifest mutation.
- Active flex-v1.ini and current.json maintain 100% token coverage and generation equality.
- Failed start cleanly releases lock without activating partial manifests.
"""
from __future__ import annotations

import configparser
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
SESSION_START_BIN = PAYLOAD / "openhtpc-session-start"
SESSION_ENGINE_BIN = PAYLOAD / "openhtpc-session-engine.py"
PLAY_BIN = PAYLOAD / "openhtpc-play"

def _load_module(name: str, path: pathlib.Path):
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod

play_mod = _load_module("openhtpc_play_test", PLAY_BIN)
session_mod = _load_module("openhtpc_session_engine_test", SESSION_ENGINE_BIN)


class TestSessionStartConcurrency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.install = self.home / ".local/lib/openhtpc"
        self.install.mkdir(parents=True, exist_ok=True)
        self.state_dir = self.home / ".local/state/openhtpc"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.home / ".config/openhtpc"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Media directory with test files
        self.media_dir = self.home / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        (self.media_dir / "UHD").mkdir(parents=True, exist_ok=True)
        (self.media_dir / "Dvd").mkdir(parents=True, exist_ok=True)
        self.movie1 = self.media_dir / "UHD/500 Days of Summer (2009).WEBDL-2160p.x265.DTS.5.1.[FR+EN].mkv"
        self.movie1.write_bytes(b"dummy_video_bytes_uhd")
        self.movie2 = self.media_dir / "Dvd/Alerte.mkv"
        self.movie2.write_bytes(b"dummy_video_bytes_dvd")

        # Configurations
        user_config = {
            "configuration_completed": True,
            "local_media_sources": [str(self.media_dir)],
            "tmdb": {"configured": False},
        }
        (self.config_dir / "user-config.json").write_text(json.dumps(user_config), encoding="utf-8")

        pure_conf = self.config_dir / "pure.conf"
        pure_conf.write_text("vo=null\n", encoding="utf-8")
        profile = {
            "generator": {"name": "OPENHTPC Builder", "version": "4"},
            "detected": {},
            "gpu_topology": {"processing_gpu": {}},
            "video_backend": {
                "status": "observed",
                "decode_api": "vaapi",
                "render_api": "vulkan",
                "render_node": "/dev/null",
            },
            "runtime": {"status": "ready", "playback_validated": False},
            "runtime_profiles": {
                "profiles": {
                    "PURE": {"generation_status": "generated", "config_path": str(pure_conf)}
                }
            },
        }
        (self.config_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")

        # Symlink payload items with absolute target
        for item in PAYLOAD.resolve().iterdir():
            dest = self.install / item.name
            if item.name == "flex":
                continue
            if not dest.exists():
                dest.symlink_to(item)

        # Mock flex launcher binary that sleeps
        self.flex_bin = self.install / "flex/bin/flex-launcher"
        self.flex_bin.parent.mkdir(parents=True, exist_ok=True)
        mock_flex = """#!/usr/bin/env bash
while true; do
    sleep 0.1
done
"""
        self.flex_bin.write_text(mock_flex, encoding="utf-8")
        self.flex_bin.chmod(0o755)

        # Symlink flex/assets so fonts and themes resolve
        (self.install / "flex/assets").symlink_to((PAYLOAD / "flex/assets").resolve())

        # Fast mocks for auxiliary scripts so tests run in <1s
        for mock_bin in ["openhtpc-system-view", "openhtpc-optical-monitor", "openhtpc-appliance-mode", "openhtpc-disc-view.py"]:
            p = self.install / mock_bin
            p.unlink(missing_ok=True)
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(0o755)

        # Python mock for openhtpc-refresh-match.py (invoked via python3)
        p_rf = self.install / "openhtpc-refresh-match.py"
        p_rf.unlink(missing_ok=True)
        p_rf.write_text("import sys\nsys.exit(0)\n")
        p_rf.chmod(0o755)

        # Base environment
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(self.install),
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
            "OPENHTPC_INHIBITED": "1",  # hermetic: bypass systemd-inhibit re-exec in test
        }

    def _file_hash(self, path: pathlib.Path) -> str:
        if not path.is_file():
            return "NON_EXISTENT"
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_01_check_only_is_read_only_and_does_not_mutate_or_lock(self):
        """Scenario: openhtpc-session-start --check-only performs zero mutation and acquires no lock."""
        flex_ini = self.config_dir / "flex-v1.ini"
        candidate_json = self.config_dir / "flex-v1.ini.media-actions.json"
        current_json = self.state_dir / "media-actions/current.json"
        menu_gen = self.state_dir / "menu-generation"
        session_lock = self.state_dir / "ui-session.lock"

        cmd = [str(SESSION_START_BIN), "--check-only"]
        res = subprocess.run(cmd, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0, f"check-only failed: {res.stderr}")
        self.assertIn("Hardware, viabilité, runtime et configuration : PASS", res.stdout)

        # Zero mutation
        self.assertFalse(flex_ini.exists())
        self.assertFalse(candidate_json.exists())
        self.assertFalse(current_json.exists())
        self.assertFalse(menu_gen.exists())

        # Lock is not held
        if session_lock.exists():
            with open(session_lock, "w") as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)

    def _wait_for_flex_active(self, timeout: float = 10.0) -> int:
        deadline = time.time() + timeout
        session_file = self.state_dir / "runtime-session.json"
        while time.time() < deadline:
            if session_file.is_file():
                try:
                    data = json.loads(session_file.read_text(encoding="utf-8"))
                    pid = data.get("authoritative_flex_pid")
                    if isinstance(pid, int) and pid > 0:
                        try:
                            os.kill(pid, 0)
                            return pid
                        except OSError:
                            pass
                except Exception:
                    pass
            time.sleep(0.05)
        self.fail("Timed out waiting for authoritative Flex process to be active")

    def test_02_cold_start_acquires_lock_and_generates_coherent_manifest(self):
        """Scenario: cold start creates flex-v1.ini, candidate, and current.json with matching generation and 100% token coverage."""
        # Start in new session so killpg kills all children (home controller, flex, monitors)
        proc = subprocess.Popen([str(SESSION_START_BIN)], env=self.env, start_new_session=True)
        self.addCleanup(self._kill_proc, proc)

        flex_ini = self.config_dir / "flex-v1.ini"
        candidate_json = self.config_dir / "flex-v1.ini.media-actions.json"
        current_json = self.state_dir / "media-actions/current.json"

        # Wait for Flex to start
        self._wait_for_flex_active()
        self.assertTrue(flex_ini.is_file())
        self.assertTrue(candidate_json.is_file())
        self.assertTrue(current_json.is_file())

        # Verify generation equality across flex-v1.ini, candidate, and current.json
        first_line = flex_ini.read_text(encoding="utf-8").splitlines()[0]
        gen_match = re.search(r"media_generation=(\S+)", first_line)
        self.assertIsNotNone(gen_match)
        active_gen = gen_match.group(1)

        candidate_data = json.loads(candidate_json.read_text(encoding="utf-8"))
        current_data = json.loads(current_json.read_text(encoding="utf-8"))

        self.assertEqual(candidate_data.get("manifest_generation"), active_gen)
        self.assertEqual(current_data.get("manifest_generation"), active_gen)

        # Verify 100% token coverage
        config = configparser.ConfigParser(interpolation=None)
        config.read(flex_ini)
        tokens_in_ini = set()
        for sec in config.sections():
            for k, v in config.items(sec):
                m = re.search(r"openhtpc-play\s+(mact_[0-9a-f]{32})", v)
                if m:
                    tokens_in_ini.add(m.group(1))

        self.assertGreater(len(tokens_in_ini), 0, "No media play tokens found in generated config")
        current_tokens = set(current_data.get("items", {}).keys())

        missing = tokens_in_ini - current_tokens
        self.assertEqual(len(missing), 0, f"Tokens missing from current.json: {missing}")

    def test_03_second_start_while_active_returns_already_active_with_zero_mutation(self):
        """Scenarios:
        - second start while active returns START_ALREADY_ACTIVE
        - second start does not rewrite flex-v1.ini, candidate manifest, or current.json
        - second start does not increment menu generation
        - second start does not change existing media tokens
        - second start does not spawn a second Flex
        - mtime and SHA256 of all 3 files remain unchanged
        """
        # Start initial session
        proc1 = subprocess.Popen([str(SESSION_START_BIN)], env=self.env, start_new_session=True)
        self.addCleanup(self._kill_proc, proc1)

        flex_ini = self.config_dir / "flex-v1.ini"
        candidate_json = self.config_dir / "flex-v1.ini.media-actions.json"
        current_json = self.state_dir / "media-actions/current.json"
        menu_gen = self.state_dir / "menu-generation"

        active_flex_pid = self._wait_for_flex_active()

        # Record initial state
        ini_sha_before = self._file_hash(flex_ini)
        cand_sha_before = self._file_hash(candidate_json)
        curr_sha_before = self._file_hash(current_json)

        ini_mtime_before = flex_ini.stat().st_mtime_ns
        cand_mtime_before = candidate_json.stat().st_mtime_ns
        curr_mtime_before = current_json.stat().st_mtime_ns

        menu_gen_before = menu_gen.read_text().strip()
        current_items_before = json.loads(current_json.read_text())["items"]

        # Run SECOND openhtpc-session-start
        res2 = subprocess.run([str(SESSION_START_BIN)], env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(res2.returncode, 0, f"Second start failed: {res2.stderr}")
        self.assertIn("Une session OPENHTPC est déjà active", res2.stdout)

        # Inspect files after second start
        ini_sha_after = self._file_hash(flex_ini)
        cand_sha_after = self._file_hash(candidate_json)
        curr_sha_after = self._file_hash(current_json)

        ini_mtime_after = flex_ini.stat().st_mtime_ns
        cand_mtime_after = candidate_json.stat().st_mtime_ns
        curr_mtime_after = current_json.stat().st_mtime_ns

        menu_gen_after = menu_gen.read_text().strip()
        current_items_after = json.loads(current_json.read_text())["items"]

        # Assert zero mutation
        self.assertEqual(ini_sha_before, ini_sha_after, "flex-v1.ini SHA was modified by second start!")
        self.assertEqual(cand_sha_before, cand_sha_after, "candidate manifest SHA was modified by second start!")
        self.assertEqual(curr_sha_before, curr_sha_after, "current.json SHA was modified by second start!")

        self.assertEqual(ini_mtime_before, ini_mtime_after, "flex-v1.ini mtime was modified by second start!")
        self.assertEqual(cand_mtime_before, cand_mtime_after, "candidate manifest mtime was modified by second start!")
        self.assertEqual(curr_mtime_before, curr_mtime_after, "current.json mtime was modified by second start!")

        self.assertEqual(menu_gen_before, menu_gen_after, "menu-generation counter was incremented by second start!")
        self.assertEqual(current_items_before, current_items_after, "media action tokens were altered by second start!")

        # Verify only one Flex process is running
        ps = subprocess.run(["pgrep", "-f", str(self.flex_bin)], capture_output=True, text=True, check=False)
        flex_pids = [p for p in ps.stdout.splitlines() if p.strip()]
        self.assertEqual(flex_pids, [str(active_flex_pid)], f"Expected exactly 1 Flex instance with PID {active_flex_pid}, found {flex_pids}")

    def test_04_failed_first_start_releases_lock_cleanly_without_partial_manifest(self):
        """Scenario: if gate evaluation fails on cold start, lock is released and no partial manifest is activated."""
        # Corrupt user-config.json to cause GateError
        (self.config_dir / "user-config.json").write_text("NOT_JSON", encoding="utf-8")

        res = subprocess.run([str(SESSION_START_BIN)], env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 3)

        current_json = self.state_dir / "media-actions/current.json"
        self.assertFalse(current_json.exists(), "current.json should not exist after failed start")

        # Verify lock was released cleanly
        session_lock = self.state_dir / "ui-session.lock"
        self.assertTrue(session_lock.exists())
        with open(session_lock, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)

    def test_05_stop_and_restart_produces_coherent_new_generation(self):
        """Scenario: normal stop and fresh start cleanly increments generation and maintains 100% token coverage."""
        proc1 = subprocess.Popen([str(SESSION_START_BIN)], env=self.env, start_new_session=True)
        self.addCleanup(self._kill_proc, proc1)

        flex_ini = self.config_dir / "flex-v1.ini"
        current_json = self.state_dir / "media-actions/current.json"
        session_file = self.state_dir / "runtime-session.json"
        self._wait_for_flex_active()

        gen1 = json.loads(current_json.read_text())["manifest_generation"]

        # Stop first session
        self._kill_proc(proc1)
        session_file.unlink(missing_ok=True)
        time.sleep(0.3)

        # Start second session
        proc2 = subprocess.Popen([str(SESSION_START_BIN)], env=self.env, start_new_session=True)
        self.addCleanup(self._kill_proc, proc2)

        self._wait_for_flex_active()

        first_line = flex_ini.read_text(encoding="utf-8").splitlines()[0]
        gen2 = re.search(r"media_generation=(\S+)", first_line).group(1)
        gen2_current = json.loads(current_json.read_text())["manifest_generation"]

        self.assertNotEqual(gen1, gen2, "Subsequent cold start should produce a new generation")
        self.assertEqual(gen2, gen2_current, "flex-v1.ini and current.json must agree on new generation")

    def test_06_detail_page_token_validation_and_stale_page_semantics(self):
        """Scenario: openhtpc-play load_media_action validates tokens against current.json and handles STALE_PAGE."""
        proc = subprocess.Popen([str(SESSION_START_BIN)], env=self.env, start_new_session=True)
        self.addCleanup(self._kill_proc, proc)

        current_json = self.state_dir / "media-actions/current.json"
        self._wait_for_flex_active()

        current_data = json.loads(current_json.read_text())
        items = current_data["items"]
        self.assertGreater(len(items), 0)

        first_tok, first_meta = next(iter(items.items()))

        # Set current-page to matching page_id
        current_page_file = self.state_dir / "media-actions/current-page"
        current_page_file.write_text(first_meta["page_id"], encoding="utf-8")

        # Loading valid token succeeds
        loaded = play_mod.load_media_action(self.home, first_tok)
        self.assertEqual(loaded["semantic_id"], first_meta["semantic_id"])

        # Mismatched page raises STALE_PAGE
        current_page_file.write_text("WRONG_PAGE_ID", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            play_mod.load_media_action(self.home, first_tok)
        self.assertEqual(str(ctx.exception), "STALE_PAGE")

        # Unknown token raises TOKEN_NOT_FOUND
        with self.assertRaises(ValueError) as ctx:
            play_mod.load_media_action(self.home, "mact_" + "f" * 32)
        self.assertEqual(str(ctx.exception), "TOKEN_NOT_FOUND")

    def _wait_for_file(self, path: pathlib.Path, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if path.is_file() and path.stat().st_size > 0:
                return
            time.sleep(0.05)
        self.fail(f"Timed out waiting for file: {path}")

    def _kill_proc(self, proc: subprocess.Popen):
        if proc.poll() is None:
            try:
                # Terminate entire process group instantly
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

