# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Deterministic regression tests for RC7 T8.5Q.1 Protected Optical Tracked Lifecycle."""
from __future__ import annotations

import ctypes
import errno
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
FLEX_SRC = ROOT / "vendor/flex-launcher/src"
FLEX_BIN = PAYLOAD / "flex/bin/flex-launcher"


def load_module(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


session_engine = load_module("tracked_session", PAYLOAD / "openhtpc-session-engine.py")
disc_sheet = load_module("tracked_disc_sheet", PAYLOAD / "openhtpc-disc-sheet.py")
optical_model = load_module("tracked_optical", PAYLOAD / "openhtpc-optical.py")
play_optical = load_module("tracked_play_optical", PAYLOAD / "openhtpc-play-optical")
protected_backend = load_module("tracked_backend", PAYLOAD / "openhtpc-protected-optical-backend.py")
playback_policy = load_module("tracked_policy", PAYLOAD / "openhtpc-playback-policy.py")

SAMPLE_VULKAN_LOG = """[   0.251][v][vo/gpu-next/wayland] Obtained preferred fractional scale, 2.000000, from the compositor.
[   0.251][v][vo/gpu-next/libplacebo] Probing for vulkan devices:
[   0.270][v][vo/gpu-next/libplacebo] Spent 19.682 ms enumerating physical devices
[   0.270][v][vo/gpu-next/libplacebo]     GPU 0: Intel(R) Arc(tm) A310 Graphics (DG2) v1.4.354 (discrete)
[   0.270][v][vo/gpu-next/libplacebo]            uuid: 86:80:a6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo] Vulkan device properties:
[   0.270][v][vo/gpu-next/libplacebo]     Device Name: Intel(R) Arc(tm) A310 Graphics (DG2)
[   0.270][v][vo/gpu-next/libplacebo]     Device ID: 8086:56a6
[   0.270][v][vo/gpu-next/libplacebo]     Device UUID: 86:80:a6:56:05:00:00:00:03:00:00:00:00:00:00:00
[   0.270][v][vo/gpu-next/libplacebo]     Driver version: 6801006
[   0.270][v][vo/gpu-next/libplacebo] Creating vulkan device with extensions:
[   0.270][v][vo/gpu-next/libplacebo] Spent 12.656 ms creating vulkan device
[   0.450][v][vd] Codec list:
[   0.451][v][vd]     h264 - H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
[   0.452][v][vd] Opening video decoder h264
[   0.453][v][vd] Trying hardware decoding via vaapi.
[   0.460][v][vd] Using hardware decoding (vaapi).
[   0.461][v][vd] Decoder format: 1920x1080 [0:1] vaapi[nv12]
[   0.500][v][cplayer] Starting playback...
bd://
"""

# Compile the exact production vendor/flex-launcher/src/lifecycle.c into a shared library.
# No test reimplementation or duplicate state machine: tests and Flex execute the same C source.
_SO_DIR = tempfile.TemporaryDirectory()
_LOG_SHIM = pathlib.Path(_SO_DIR.name) / "log_shim.c"
_LOG_SHIM.write_text("""
#include <stdio.h>
#include <stdarg.h>

static int g_log_count = 0;
void output_log(int log_level, const char *format, ...) {
    (void)log_level;
    (void)format;
    g_log_count++;
}
int test_get_log_count(void) { return g_log_count; }
void test_reset_log_count(void) { g_log_count = 0; }
""", encoding="utf-8")
_SO_PATH = pathlib.Path(_SO_DIR.name) / "liblifecycle_prod.so"
subprocess.run([
    "gcc", "-shared", "-fPIC", "-O2",
    "-I", str(FLEX_SRC),
    str(FLEX_SRC / "lifecycle.c"),
    str(_LOG_SHIM),
    "-o", str(_SO_PATH)
], check=True)
_LIB = ctypes.CDLL(str(_SO_PATH))

# TrackedLifecycle C function signatures
_LIB.tracked_lifecycle_new.restype = ctypes.c_void_p
_LIB.tracked_lifecycle_free.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_init.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_reset.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_is_active.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_is_active.restype = ctypes.c_bool
_LIB.tracked_lifecycle_get_pid.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_get_pid.restype = ctypes.c_int
_LIB.tracked_lifecycle_get_last_reaped_pid.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_get_last_reaped_pid.restype = ctypes.c_int
_LIB.tracked_lifecycle_get_last_exit_status.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_get_last_exit_status.restype = ctypes.c_int
_LIB.tracked_lifecycle_get_echild_log_count.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_get_echild_log_count.restype = ctypes.c_int
_LIB.tracked_lifecycle_can_launch_tracked.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_can_launch_tracked.restype = ctypes.c_bool
_LIB.tracked_lifecycle_start.argtypes = [ctypes.c_void_p, ctypes.c_int]
_LIB.tracked_lifecycle_start.restype = ctypes.c_bool
_LIB.tracked_lifecycle_clear.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_is_interaction_allowed.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_is_interaction_allowed.restype = ctypes.c_bool
_LIB.tracked_lifecycle_guard_command.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
_LIB.tracked_lifecycle_guard_command.restype = ctypes.c_bool
_LIB.tracked_lifecycle_guard_controller.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_guard_controller.restype = ctypes.c_bool

CALLBACK_TYPE = ctypes.CFUNCTYPE(None)
ACTION_EXEC_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_char_p)

_LIB.tracked_lifecycle_handle_controller_action.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ACTION_EXEC_TYPE]
_LIB.tracked_lifecycle_handle_controller_action.restype = ctypes.c_bool
_LIB.tracked_lifecycle_can_restore_on_focus.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_can_restore_on_focus.restype = ctypes.c_bool
_LIB.tracked_lifecycle_can_restore_on_timeout.argtypes = [ctypes.c_void_p]
_LIB.tracked_lifecycle_can_restore_on_timeout.restype = ctypes.c_bool
_LIB.tracked_lifecycle_handle_waitpid_result.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, CALLBACK_TYPE]
_LIB.tracked_lifecycle_handle_waitpid_result.restype = ctypes.c_int
_LIB.tracked_lifecycle_poll_and_update.argtypes = [ctypes.c_void_p, CALLBACK_TYPE]
_LIB.tracked_lifecycle_poll_and_update.restype = ctypes.c_int

TRACKED_STATUS_NONE = 0
TRACKED_STATUS_RUNNING = 1
TRACKED_STATUS_FINISHED = 2
TRACKED_STATUS_ECHILD_FAILURE = 3
TRACKED_STATUS_ERROR = 4


class TrackedLifecycleHarness:
    """Wraps production vendor/flex-launcher/src/lifecycle.c with test harness helpers."""

    def __init__(self):
        self._ptr = _LIB.tracked_lifecycle_new()
        self._post_launch_calls = 0
        self._executed_actions: list[str] = []
        self._owned_children: list[subprocess.Popen] = []

        def _on_restore():
            self._post_launch_calls += 1

        def _on_exec(cmd_bytes):
            if cmd_bytes:
                self._executed_actions.append(cmd_bytes.decode("utf-8"))

        self._c_restore_cb = CALLBACK_TYPE(_on_restore)
        self._c_exec_cb = ACTION_EXEC_TYPE(_on_exec)

    def close(self):
        for p in self._owned_children:
            try:
                if p.poll() is None:
                    p.kill()
                    p.wait()
            except OSError:
                pass
        self._owned_children.clear()
        if self._ptr is not None:
            _LIB.tracked_lifecycle_free(self._ptr)
            self._ptr = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start_process(self, command: str) -> subprocess.Popen:
        """Start a real child process using standard shell execution matching Flex's sh -c command."""
        p = subprocess.Popen(["/bin/sh", "-c", command], preexec_fn=os.setpgrp)
        self._owned_children.append(p)
        return p

    def execute_command(self, command: str) -> bool:
        """Simulate Flex execute_command() using the production lifecycle API."""
        if not _LIB.tracked_lifecycle_guard_command(self._ptr, command.encode("utf-8")):
            return False

        if command.startswith(":tracked "):
            tracked_cmd = command[9:].strip()
            if not tracked_cmd:
                return False
            if not _LIB.tracked_lifecycle_can_launch_tracked(self._ptr):
                return False
            p = self.start_process(tracked_cmd)
            ok = _LIB.tracked_lifecycle_start(self._ptr, p.pid)
            return ok
        return True

    def update(self) -> int:
        """Simulate Flex application state update loop calling tracked_update()."""
        return _LIB.tracked_lifecycle_poll_and_update(self._ptr, self._c_restore_cb)

    def handle_waitpid_result(self, wait_res: int, status: int, err_code: int) -> int:
        """Directly call tracked_lifecycle_handle_waitpid_result() with simulated kernel codes."""
        return _LIB.tracked_lifecycle_handle_waitpid_result(
            self._ptr, wait_res, status, err_code, self._c_restore_cb
        )

    def handle_controller_action(self, cmd: str) -> bool:
        """Simulate Flex poll_gamepad() dispatching through tracked_lifecycle_handle_controller_action."""
        return _LIB.tracked_lifecycle_handle_controller_action(
            self._ptr, cmd.encode("utf-8"), self._c_exec_cb
        )

    def can_restore_on_focus(self) -> bool:
        """Simulate SDL_WINDOWEVENT_FOCUS_LOST check."""
        return _LIB.tracked_lifecycle_can_restore_on_focus(self._ptr)

    def can_restore_on_timeout(self) -> bool:
        """Simulate launcher timeout check."""
        return _LIB.tracked_lifecycle_can_restore_on_timeout(self._ptr)

    def is_interaction_allowed(self) -> bool:
        """Simulate SDL event loop input interaction check."""
        return _LIB.tracked_lifecycle_is_interaction_allowed(self._ptr)

    def is_active(self) -> bool:
        return _LIB.tracked_lifecycle_is_active(self._ptr)

    def get_tracked_pid(self) -> int:
        return _LIB.tracked_lifecycle_get_pid(self._ptr)

    def get_last_reaped_pid(self) -> int:
        return _LIB.tracked_lifecycle_get_last_reaped_pid(self._ptr)

    def get_last_exit_status(self) -> int:
        return _LIB.tracked_lifecycle_get_last_exit_status(self._ptr)

    def get_echild_log_count(self) -> int:
        return _LIB.tracked_lifecycle_get_echild_log_count(self._ptr)

    def get_post_launch_calls(self) -> int:
        return self._post_launch_calls

    def get_executed_actions(self) -> list[str]:
        return list(self._executed_actions)

    def set_tracked_pid(self, pid: int) -> bool:
        return _LIB.tracked_lifecycle_start(self._ptr, pid)


class TestTrackedLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        (self.home / ".config/openhtpc").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/state/openhtpc").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/lib/openhtpc").mkdir(parents=True, exist_ok=True)

        self._env_patch = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
        })
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    # 1. REAL OWNED CHILD ALIVE
    def test_1_behavioral_real_child_alive(self):
        """Start harmless synthetic child that remains alive; verify focus/timeout do NOT restore, 2nd activation rejected."""
        with TrackedLifecycleHarness() as harness:
            ok = harness.execute_command(":tracked /bin/sleep 2")
            self.assertTrue(ok)
            pid = harness.get_tracked_pid()
            self.assertGreater(pid, 0)
            self.assertTrue(harness.is_active())
            self.assertEqual(harness.get_post_launch_calls(), 0)

            # Focus gained/lost check: must NOT allow restoration while tracked child is alive
            self.assertFalse(harness.can_restore_on_focus())
            self.assertEqual(harness.get_post_launch_calls(), 0)
            self.assertEqual(harness.get_tracked_pid(), pid)

            # Timeout check: must NOT allow restoration while tracked child is alive
            self.assertFalse(harness.can_restore_on_timeout())
            self.assertEqual(harness.get_post_launch_calls(), 0)
            self.assertEqual(harness.get_tracked_pid(), pid)

            # Second activation while child alive: rejected
            second_ok = harness.execute_command(":tracked /bin/sleep 2")
            self.assertFalse(second_ok)
            self.assertEqual(harness.get_tracked_pid(), pid)

            # Regular command while child alive: ignored
            cmd_ok = harness.execute_command("/bin/ls")
            self.assertFalse(cmd_ok)

            # Event loop interaction not allowed
            self.assertFalse(harness.is_interaction_allowed())

            # Update while child running: returns RUNNING, no restore callback
            status = harness.update()
            self.assertEqual(status, TRACKED_STATUS_RUNNING)
            self.assertEqual(harness.get_post_launch_calls(), 0)

            # Clean up child
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.02)
            harness.update()

    # 2. REAL CHILD COMPLETION
    def test_2_behavioral_real_child_completion(self):
        """Allow exact owned child to terminate; verify PID reaped, completion and restoration occur exactly once."""
        with TrackedLifecycleHarness() as harness:
            ok = harness.execute_command(":tracked /bin/sleep 0.05")
            self.assertTrue(ok)
            pid = harness.get_tracked_pid()
            self.assertGreater(pid, 0)

            # Wait for child to exit
            time.sleep(0.1)

            # Update harvests child
            status = harness.update()
            self.assertEqual(status, TRACKED_STATUS_FINISHED)
            self.assertEqual(harness.get_tracked_pid(), 0)
            self.assertEqual(harness.get_last_reaped_pid(), pid)
            self.assertFalse(harness.is_active())
            self.assertEqual(harness.get_post_launch_calls(), 1)

            # Subsequent updates do NOT call post_launch again (restoration occurs exactly once)
            status2 = harness.update()
            self.assertEqual(status2, TRACKED_STATUS_NONE)
            self.assertEqual(harness.get_post_launch_calls(), 1)

    # 3. IMMEDIATE CHILD EXIT
    def test_3_behavioral_immediate_child_exit(self):
        """Child exiting immediately (/bin/true); verify exact harvesting, no stuck state, no double restore."""
        with TrackedLifecycleHarness() as harness:
            ok = harness.execute_command(":tracked /bin/true")
            self.assertTrue(ok)
            time.sleep(0.02)

            status = harness.update()
            self.assertEqual(status, TRACKED_STATUS_FINISHED)
            self.assertEqual(harness.get_tracked_pid(), 0)
            self.assertFalse(harness.is_active())
            self.assertEqual(harness.get_post_launch_calls(), 1)

            # Verify subsequent command runs normally without stuck state
            cmd_ok = harness.execute_command("/bin/true")
            self.assertTrue(cmd_ok)
            self.assertTrue(harness.is_interaction_allowed())

    # 4. ECHILD / LOST OWNERSHIP
    def test_4_behavioral_echild_lost_ownership(self):
        """Exercise explicit waitpid -1/ECHILD: fails closed, no post_launch, no duplicate restore, logged once."""
        # Case 4A: Direct kernel ECHILD code passed to waitpid handler
        with TrackedLifecycleHarness() as harness:
            harness.set_tracked_pid(99999)
            self.assertEqual(harness.get_tracked_pid(), 99999)

            res = harness.handle_waitpid_result(-1, 0, errno.ECHILD)
            self.assertEqual(res, TRACKED_STATUS_ECHILD_FAILURE)

            # Fail closed: must NOT call post_launch, must NOT clear state, must log error once
            self.assertEqual(harness.get_post_launch_calls(), 0)
            self.assertEqual(harness.get_tracked_pid(), 99999)
            self.assertTrue(harness.is_active())
            self.assertEqual(harness.get_echild_log_count(), 1)
            self.assertFalse(harness.is_interaction_allowed())

            # Second poll does NOT flood log
            res2 = harness.handle_waitpid_result(-1, 0, errno.ECHILD)
            self.assertEqual(res2, TRACKED_STATUS_ECHILD_FAILURE)
            self.assertEqual(harness.get_post_launch_calls(), 0)
            self.assertEqual(harness.get_echild_log_count(), 1)

        # Case 4B: Real kernel ECHILD from externally reaped process
        child_pid = os.fork()
        if child_pid == 0:
            os._exit(0)
        time.sleep(0.02)
        reaped, _ = os.waitpid(child_pid, 0)
        self.assertEqual(reaped, child_pid)

        with TrackedLifecycleHarness() as harness:
            # Set harness to track child_pid which is already reaped
            harness.set_tracked_pid(child_pid)
            # waitpid on already reaped child yields real OS kernel ECHILD
            res = harness.update()
            self.assertEqual(res, TRACKED_STATUS_ECHILD_FAILURE)
            self.assertEqual(harness.get_post_launch_calls(), 0, "Kernel ECHILD must NOT invoke post_launch")
            self.assertEqual(harness.get_tracked_pid(), child_pid, "State must remain guarded on ECHILD")
            self.assertTrue(harness.is_active())
            self.assertEqual(harness.get_echild_log_count(), 1)

            # Repeated loop step avoids log spam
            res2 = harness.update()
            self.assertEqual(res2, TRACKED_STATUS_ECHILD_FAILURE)
            self.assertEqual(harness.get_echild_log_count(), 1)

    # 5. CONTROLLER / INPUT GUARD
    def test_5_behavioral_controller_and_input_guard(self):
        """Exercise poll_gamepad() controller action dispatch seam: blocked during tracked playback, allowed after reap."""
        with TrackedLifecycleHarness() as harness:
            self.assertTrue(harness.is_interaction_allowed())
            ok = harness.execute_command(":tracked /bin/sleep 2")
            self.assertTrue(ok)
            pid = harness.get_tracked_pid()

            # Gating active
            self.assertFalse(harness.is_interaction_allowed())

            # Real controller actions dispatched through tracked_lifecycle_handle_controller_action: ALL BLOCKED
            self.assertFalse(harness.handle_controller_action(":select"))
            self.assertFalse(harness.handle_controller_action(":right"))
            self.assertFalse(harness.handle_controller_action(":tracked /bin/sleep 1"))
            self.assertFalse(harness.handle_controller_action("openhtpc-eject"))
            self.assertEqual(harness.get_executed_actions(), [])

            # Reaping re-enables interaction
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.02)
            harness.update()
            self.assertEqual(harness.get_tracked_pid(), 0)
            self.assertTrue(harness.is_interaction_allowed())

            # Controller action executes when tracked process has completed
            eject_ok = harness.handle_controller_action("openhtpc-eject")
            self.assertTrue(eject_ok)
            self.assertEqual(harness.get_executed_actions(), ["openhtpc-eject"])

    # 6. DOUBLE ACTIVATION
    def test_6_behavioral_double_activation(self):
        """While a tracked child is alive, attempt second protected activation; exactly one child exists."""
        with TrackedLifecycleHarness() as harness:
            ok1 = harness.execute_command(":tracked /bin/sleep 2")
            self.assertTrue(ok1)
            pid1 = harness.get_tracked_pid()
            self.assertGreater(pid1, 0)

            # Attempt second activation
            ok2 = harness.execute_command(":tracked /bin/sleep 2")
            self.assertFalse(ok2)
            self.assertEqual(harness.get_tracked_pid(), pid1)

            # Clean up
            os.kill(pid1, signal.SIGKILL)
            time.sleep(0.02)
            harness.update()

    # 7. T8.5 CANONICAL HAPPENS-BEFORE ORDERING TEST
    def test_7_t85_happens_before_ordering(self):
        """Proves canonical T8.5 mutation occurs BEFORE child exits and before Flex restores:
        T_canonical_mutation < T_child_exit <= T_flex_restoration."""
        disp_script = self.home / "synthetic_canonical_dispatcher.py"
        disp_id = "test-canonical-dispatch-ordering-42"
        decision = {
            "presentation_mode": "PURE",
            "audio_target": {"node_name": "alsa_output.pci", "description": "AVR"},
            "audio_output": {"requested": "PCM"},
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
            },
            "mpv_args": ["--gpu-api=vulkan", "--vulkan-device=8680a656-0500-0000-0300-000000000000", "--hwdec=vaapi"],
        }

        # Child dispatcher script uses canonical payload/openhtpc-playback-policy.py APIs
        script_code = f"""import sys, time, pathlib, importlib.machinery, importlib.util

loader = importlib.machinery.SourceFileLoader("playback_policy", {repr(str(PAYLOAD / "openhtpc-playback-policy.py"))})
spec = importlib.util.spec_from_loader("playback_policy", loader)
policy = importlib.util.module_from_spec(spec)
loader.exec_module(policy)

home = pathlib.Path({repr(str(self.home))})
disp_id = {repr(disp_id)}
decision = {repr(decision)}
raw_log = {repr(SAMPLE_VULKAN_LOG)}

# 1. Record dispatch
policy.record_playback_dispatch(home, decision, kind="bluray", dispatch_id=disp_id)
(home / "dispatcher_started.txt").write_text(str(time.time()), encoding="utf-8")

# 2. Simulate playback
time.sleep(0.05)

# 3. Record completed observation using canonical playback_policy API
policy.record_playback_observation(home, decision, raw_log, exit_code=0, kind="bluray", dispatch_id=disp_id)

# 4. Verify canonical record on disk is COMPLETED before writing proof timestamp
rec = policy.read_playback_runtime(home)
assert rec is not None and rec["dispatch_status"] == "COMPLETED"
(home / "obs_written.txt").write_text(str(time.time()), encoding="utf-8")

# 5. Brief sleep before child exit
time.sleep(0.05)
(home / "child_exiting.txt").write_text(str(time.time()), encoding="utf-8")
sys.exit(0)
"""
        disp_script.write_text(script_code, encoding="utf-8")

        with TrackedLifecycleHarness() as harness:
            # 1. Launch tracked dispatcher
            ok = harness.execute_command(f":tracked {sys.executable} {disp_script}")
            self.assertTrue(ok)
            pid = harness.get_tracked_pid()
            self.assertGreater(pid, 0)
            self.assertEqual(harness.get_post_launch_calls(), 0)

            # Wait for dispatcher to start
            started_file = self.home / "dispatcher_started.txt"
            for _ in range(50):
                if started_file.is_file():
                    break
                time.sleep(0.02)
            self.assertTrue(started_file.is_file(), "Dispatcher must start")

            # 2. While dispatcher is running, verify Flex does not restore
            status = harness.update()
            self.assertEqual(status, TRACKED_STATUS_RUNNING)
            self.assertEqual(harness.get_post_launch_calls(), 0)
            self.assertEqual(harness.get_tracked_pid(), pid)
            self.assertFalse(harness.handle_controller_action("openhtpc-eject"))

            # Wait for canonical observation to be written
            obs_file = self.home / "obs_written.txt"
            for _ in range(50):
                if obs_file.is_file():
                    break
                time.sleep(0.02)
            self.assertTrue(obs_file.is_file(), "Canonical observation must be written")
            t_canonical_mutation = float(obs_file.read_text(encoding="utf-8"))

            # Validate canonical state on disk via read_playback_runtime()
            canonical_record = playback_policy.read_playback_runtime(self.home)
            self.assertIsNotNone(canonical_record)
            self.assertEqual(canonical_record["dispatch_status"], "COMPLETED")
            self.assertEqual(canonical_record["dispatch_id"], disp_id)

            # At this exact moment, child may still be finishing; Flex has NOT restored yet
            self.assertEqual(harness.get_post_launch_calls(), 0)

            # Wait for child exit marker
            exit_file = self.home / "child_exiting.txt"
            for _ in range(50):
                if exit_file.is_file():
                    break
                time.sleep(0.02)
            self.assertTrue(exit_file.is_file(), "Child must complete execution")
            t_child_exit = float(exit_file.read_text(encoding="utf-8"))

            # 3. Reap child through production lifecycle update
            reaped = False
            for _ in range(50):
                status = harness.update()
                if status == TRACKED_STATUS_FINISHED:
                    reaped = True
                    break
                time.sleep(0.02)
            t_flex_restoration = time.time()

            self.assertTrue(reaped, "Lifecycle must reap child")
            self.assertEqual(harness.get_tracked_pid(), 0)
            self.assertEqual(harness.get_last_reaped_pid(), pid)
            self.assertEqual(harness.get_last_exit_status(), 0)
            self.assertEqual(harness.get_post_launch_calls(), 1)

            # 4. Prove temporal ordering: T_canonical_mutation < T_child_exit <= T_flex_restoration
            self.assertLess(t_canonical_mutation, t_child_exit)
            self.assertLessEqual(t_child_exit, t_flex_restoration)

            # 5. Final state validation via canonical reader
            final_rec = playback_policy.read_playback_runtime(self.home)
            self.assertIsNotNone(final_rec)
            self.assertEqual(final_rec["dispatch_status"], "COMPLETED")
            self.assertEqual(final_rec["render"]["status"], "PROVEN")
            self.assertEqual(final_rec["decode"]["status"], "OBSERVED")
            self.assertEqual(final_rec["decode"]["hardware_active"], True)
            self.assertEqual(final_rec["decode"]["physical_gpu_binding"], "NOT_PROVEN")

    # 8. HERMETIC BACKEND OPEN_DISC ISOLATION
    def test_8_hermetic_backend_open_disc_isolation(self):
        """Hermetic backend open_disc test with synthetic decision and mocks, host independent."""
        call_order = []

        def mock_runner(cmd, **kwargs):
            call_order.append("MPV_RUN")
            for arg in cmd:
                if arg.startswith("--log-file="):
                    log_file = pathlib.Path(arg.split("=", 1)[1])
                    log_file.write_text(SAMPLE_VULKAN_LOG, encoding="utf-8")
            res = mock.MagicMock()
            res.returncode = 0
            return res

        orig_record = playback_policy.record_playback_observation

        def wrapped_record(home, decision, raw_log, **kwargs):
            call_order.append("OBSERVATION_RECORDED")
            return orig_record(home, decision, raw_log, **kwargs)

        request = {
            "device": "/dev/sr0",
            "media_type": "BLURAY",
            "protection": "PROTECTED",
            "provider_status": "AVAILABLE",
            "generation": 1,
        }

        synthetic_decision = {
            "presentation_mode": "PURE",
            "audio_target": {"node_name": "alsa_output.pci", "description": "AVR"},
            "audio_output": {"requested": "PCM"},
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
            },
            "mpv_args": ["--gpu-api=vulkan", "--vulkan-device=8680a656-0500-0000-0300-000000000000", "--hwdec=vaapi"],
        }

        with mock.patch.object(protected_backend, "playback_policy", return_value=(playback_policy, synthetic_decision)),              mock.patch.object(playback_policy, "record_playback_observation", side_effect=wrapped_record),              mock.patch.object(protected_backend, "runtime_config", return_value=pathlib.Path("/tmp/pure.conf")),              mock.patch("subprocess.run"):
            res = protected_backend.open_disc(
                self.home, request, runner=mock_runner, finder=lambda x: "/usr/bin/mpv",
                clock=mock.MagicMock(side_effect=[0.0, 1.0, 1.0, 1.0])
            )

        call_order.append("DISPATCHER_RETURNS")
        self.assertEqual(call_order, ["MPV_RUN", "OBSERVATION_RECORDED", "DISPATCHER_RETURNS"])
        self.assertEqual(res["status"], "OPEN_SUCCESS")
        self.assertEqual(res["exit_code"], 0)

        # Check recorded state file in isolated self.home
        saved = playback_policy.read_playback_runtime(self.home)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["dispatch_status"], "COMPLETED")
        self.assertEqual(saved["observation_scope"], "LAST_COMPLETED_PLAYBACK")
        self.assertEqual(saved["exit_code"], 0)
        self.assertEqual(saved["render"]["status"], "PROVEN")
        self.assertEqual(saved["decode"]["status"], "OBSERVED")
        self.assertEqual(saved["decode"]["hardware_active"], True)
        self.assertEqual(saved["decode"]["physical_gpu_binding"], "NOT_PROVEN")

    # 9. BACKEND NONZERO FAILURE PATH PRESERVES SEMANTICS
    def test_9_backend_nonzero_failure_path_preserves_semantics(self):
        call_order = []

        def mock_failing_runner(cmd, **kwargs):
            call_order.append("MPV_FAILED")
            for arg in cmd:
                if arg.startswith("--log-file="):
                    log_file = pathlib.Path(arg.split("=", 1)[1])
                    log_file.write_text("Failed to open bd://\n", encoding="utf-8")
            res = mock.MagicMock()
            res.returncode = 2
            return res

        orig_record = playback_policy.record_playback_observation

        def wrapped_record(home, decision, raw_log, **kwargs):
            call_order.append("OBSERVATION_RECORDED")
            return orig_record(home, decision, raw_log, **kwargs)

        request = {
            "device": "/dev/sr0",
            "media_type": "BLURAY",
            "protection": "PROTECTED",
            "provider_status": "AVAILABLE",
            "generation": 1,
        }

        synthetic_decision = {
            "presentation_mode": "PURE",
            "audio_target": {"node_name": "alsa_output.pci", "description": "AVR"},
            "audio_output": {"requested": "PCM"},
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
            },
            "mpv_args": ["--gpu-api=vulkan", "--vulkan-device=8680a656-0500-0000-0300-000000000000", "--hwdec=vaapi"],
        }

        with mock.patch.object(protected_backend, "playback_policy", return_value=(playback_policy, synthetic_decision)),              mock.patch.object(playback_policy, "record_playback_observation", side_effect=wrapped_record),              mock.patch.object(protected_backend, "runtime_config", return_value=pathlib.Path("/tmp/pure.conf")),              mock.patch("subprocess.run"):
            res = protected_backend.open_disc(
                self.home, request, runner=mock_failing_runner, finder=lambda x: "/usr/bin/mpv",
                clock=mock.MagicMock(side_effect=[0.0, 1.0, 1.0, 1.0])
            )

        call_order.append("DISPATCHER_RETURNS")
        self.assertEqual(call_order, ["MPV_FAILED", "OBSERVATION_RECORDED", "DISPATCHER_RETURNS"])
        self.assertEqual(res["status"], "OPEN_FAILED")
        self.assertEqual(res["exit_code"], 2)

        saved = playback_policy.read_playback_runtime(self.home)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["dispatch_status"], "FAILED")
        self.assertEqual(saved["observation_scope"], "FAILED_PLAYBACK")
        self.assertEqual(saved["exit_code"], 2)

    # 10. PREFLIGHT REFUSAL NO BORROWED / STALE DISPATCH IDENTITY
    def test_10_preflight_refusal_no_borrowed_or_stale_dispatch_identity(self):
        request = {
            "device": "/dev/sr0",
            "media_type": "UNKNOWN_FORMAT",
            "protection": "PROTECTED",
            "provider_status": "AVAILABLE",
            "generation": 1,
        }
        synthetic_decision = {"presentation_mode": "PURE", "mpv_args": []}
        with mock.patch.object(protected_backend, "playback_policy", return_value=(playback_policy, synthetic_decision)):
            res = protected_backend.open_disc(self.home, request)
        self.assertEqual(res["status"], "UNSUPPORTED")
        self.assertFalse(res["process_started"])

        last_file = self.home / ".local/state/openhtpc/playback-runtime-last.json"
        if last_file.is_file():
            saved = json.loads(last_file.read_text(encoding="utf-8"))
            self.assertNotEqual(saved.get("dispatch_status"), "COMPLETED")

    # 11. LOCAL REGRESSION: UNCHANGED
    def test_11_local_playback_regression_unchanged(self):
        manifest_path = self.home / ".local/state/openhtpc/media-actions/manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "generation": "gen-1",
            "items": {
                "mact_1": {
                    "page_id": "MEDIA_MOVIE",
                    "title": "Local Film",
                    "path": "/movies/film.mkv",
                    "relative_path": "film.mkv",
                }
            }
        }), encoding="utf-8")

        config_path = self.home / ".config/openhtpc/flex-v1.ini"
        session_engine.write_flex_config(config_path, self.home, [pathlib.Path("/movies")], PAYLOAD, media_generation="gen-1")
        config_text = config_path.read_text(encoding="utf-8")
        for line in config_text.splitlines():
            if "openhtpc-play" in line:
                self.assertNotIn(":tracked", line)
                self.assertIn("openhtpc-play", line)

    # 12. DVD REGRESSION: UNCHANGED
    def test_12_dvd_playback_regression_unchanged(self):
        optical_state = {
            "canonical_state": "DVD_VIDEO",
            "state": "DVD",
            "device": "/dev/sr0",
            "media_type": "DVD_VIDEO",
            "generation": 2,
        }
        icons = (pathlib.Path("a.png"), pathlib.Path("b.png"), pathlib.Path("c.png"), pathlib.Path("d.png"))
        menu = session_engine.disc_menu_entries(optical_state, PAYLOAD, icons, self.home)
        self.assertIn("LIRE LE DVD", menu)
        for line in menu.splitlines():
            if "LIRE LE DVD" in line:
                self.assertNotIn(":tracked", line)
                self.assertIn("openhtpc-play-dvd", line)
                self.assertIn("OPENHTPC_FLEX_RETAINED=1", line)

    # 13. PROTECTED OPTICAL BACKEND REGRESSION: UNCHANGED EXCEPT LIFECYCLE OWNERSHIP
    def test_13_protected_optical_backend_regression_unchanged(self):
        optical_state = {
            "canonical_state": "BLURAY_VIDEO",
            "state": "BLURAY",
            "device": "/dev/sr0",
            "media_type": "BLURAY_VIDEO",
            "protection": "PROTECTED",
            "generation": 3,
        }
        icons = (pathlib.Path("a.png"), pathlib.Path("b.png"), pathlib.Path("c.png"), pathlib.Path("d.png"))
        with mock.patch.object(session_engine, "protected_optical_menu_policy", return_value=(
            "PLUGIN_P2",
            {"visible": True, "enabled": True, "action_intent": "PLAY_CURRENT_OPTICAL_MEDIA"},
            {"playback_action": "ENABLED", "playback_reason": "PLAYBACK_ALLOWED"}
        )), mock.patch.object(optical_model, "playback_action_token", return_value="token123"):
            menu = session_engine.disc_menu_entries(optical_state, pathlib.Path("/nonexistent"), icons, pathlib.Path("/nonexistent"))

        self.assertIn("LIRE LE BLU-RAY", menu)
        play_line = [l for l in menu.splitlines() if "LIRE LE BLU-RAY" in l][0]
        self.assertIn(":tracked", play_line)
        self.assertNotIn(":fork", play_line)
        self.assertIn("openhtpc-play-optical", play_line)

        data = {
            "title": "Test Bluray",
            "state": optical_state,
            "artwork": "icon.png",
        }
        with mock.patch.object(optical_model, "canonical_state", return_value="BLURAY_VIDEO"),              mock.patch.object(disc_sheet, "protected_ui_policy", return_value=("PLUGIN_P2", {"enabled": True, "action_intent": "PLAY_CURRENT_OPTICAL_MEDIA"})),              mock.patch.object(optical_model, "playback_action_token", return_value="token123"):
            sheet_menu_path = disc_sheet.write_menu(self.home, PAYLOAD, data)
        sheet_text = sheet_menu_path.read_text(encoding="utf-8")
        sheet_play = [l for l in sheet_text.splitlines() if "LIRE · Test Bluray" in l][0]
        self.assertIn(":tracked", sheet_play)
        self.assertIn("openhtpc-play-optical", sheet_play)

    # 14. T8.5 OBSERVATION REGRESSION: ALL EXISTING TESTS REMAIN PASS
    def test_14_t85_observation_regression_remains_pass(self):
        decision = {
            "presentation_mode": "PURE",
            "audio_target": {"node_name": "alsa_output.pci", "description": "AVR"},
            "audio_output": {"requested": "PCM"},
            "gpu_render_binding": {
                "status": "RENDER_BOUND",
                "pci_address": "0000:03:00.0",
                "vulkan_uuid": "8680a656-0500-0000-0300-000000000000",
                "vulkan_device_name": "Intel(R) Arc(tm) A310 Graphics (DG2)",
            }
        }
        disp = playback_policy.record_playback_dispatch(self.home, decision, kind="bluray")
        self.assertIsNotNone(disp)
        disp_id = disp["dispatch_id"]

        obs = playback_policy.record_playback_observation(
            self.home, decision, SAMPLE_VULKAN_LOG, exit_code=0, kind="bluray", dispatch_id=disp_id
        )
        self.assertIsNotNone(obs)
        self.assertEqual(obs["dispatch_status"], "COMPLETED")
        self.assertEqual(obs["dispatch_id"], disp_id)
        self.assertEqual(obs["render"]["status"], "PROVEN")
        self.assertEqual(obs["decode"]["status"], "OBSERVED")
        self.assertEqual(obs["decode"]["hardware_active"], True)
        self.assertEqual(obs["decode"]["physical_gpu_binding"], "NOT_PROVEN")

    # 15. FLEX BINARY MATCH
    def test_15_flex_binary_contains_echild_fail_closed_code(self):
        """Verify that the compiled flex-launcher binary contains the fail-closed ECHILD strings."""
        bin_path = FLEX_BIN
        self.assertTrue(bin_path.is_file(), f"Binary not found: {bin_path}")
        raw = bin_path.read_bytes()
        self.assertIn(b"Tracked application finished (pid %d)", raw)
        self.assertIn(b"Tracked child ownership failure (pid %d returned ECHILD); failing closed", raw)


if __name__ == "__main__":
    unittest.main()
