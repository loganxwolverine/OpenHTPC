"""Global pytest test session isolation and safety guards for OPENHTPC test suite.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import pytest

# Create a dedicated, hermetic session temporary directory
SESSION_SANDBOX = tempfile.TemporaryDirectory(prefix="openhtpc-test-sandbox-")
SANDBOX_PATH = pathlib.Path(SESSION_SANDBOX.name).resolve()

# Real user home that must NEVER be written to or touched by tests
REAL_USER_HOME = pathlib.Path.home().resolve()
REAL_STATE_DIR = REAL_USER_HOME / ".local/state/openhtpc"
REAL_CONFIG_DIR = REAL_USER_HOME / ".config/openhtpc"


def _record_real_tree_state() -> dict[pathlib.Path, float]:
    """Capture mtimes of existing files in real user state/config dirs if they exist."""
    state = {}
    for root in (REAL_STATE_DIR, REAL_CONFIG_DIR):
        if root.is_dir():
            for p in root.rglob("*"):
                try:
                    state[p.resolve()] = p.stat().st_mtime_ns
                except OSError:
                    pass
    return state


def pytest_configure(config):
    """Enforce hermetic environment at pytest configuration time."""
    sandbox_config = SANDBOX_PATH / ".config"
    sandbox_state = SANDBOX_PATH / ".local/state"
    sandbox_cache = SANDBOX_PATH / ".cache"
    sandbox_share = SANDBOX_PATH / ".local/share"
    sandbox_runtime = SANDBOX_PATH / ".runtime"

    for d in (sandbox_config, sandbox_state, sandbox_cache, sandbox_share, sandbox_runtime):
        d.mkdir(parents=True, exist_ok=True)

    # Set hermetic environment variables for current process and child processes
    os.environ["HOME"] = str(SANDBOX_PATH)
    os.environ["OPENHTPC_HOME"] = str(SANDBOX_PATH)
    os.environ["XDG_CONFIG_HOME"] = str(sandbox_config)
    os.environ["XDG_STATE_HOME"] = str(sandbox_state)
    os.environ["XDG_CACHE_HOME"] = str(sandbox_cache)
    os.environ["XDG_DATA_HOME"] = str(sandbox_share)
    os.environ["XDG_RUNTIME_DIR"] = str(sandbox_runtime)
    os.environ["OPENHTPC_TEST_ENVIRONMENT"] = "1"

    # Scrub display variables so no graphical dialogs (kdialog, zenity, etc.) can ever open
    os.environ.pop("DISPLAY", None)
    os.environ.pop("WAYLAND_DISPLAY", None)


@pytest.fixture(autouse=True, scope="session")
def session_isolation_guard():
    """Ensure session sandbox is active and clean up on session finish."""
    before_state = _record_real_tree_state()
    yield
    after_state = _record_real_tree_state()
    SESSION_SANDBOX.cleanup()

    # Verify no file in real user state/config was modified or created during test session
    new_files = set(after_state.keys()) - set(before_state.keys())
    modified_files = [p for p in before_state if p in after_state and before_state[p] != after_state[p]]
    if new_files or modified_files:
        raise RuntimeError(
            f"TEST ISOLATION LEAK DETECTED: Files written to real user directories during tests: "
            f"new={new_files}, modified={modified_files}"
        )


@pytest.fixture(autouse=True)
def per_test_environment_guard(monkeypatch):
    """Ensure each test runs with isolated HOME, XDG paths, and no graphical display."""
    monkeypatch.setenv("HOME", str(SANDBOX_PATH))
    monkeypatch.setenv("OPENHTPC_HOME", str(SANDBOX_PATH))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(SANDBOX_PATH / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(SANDBOX_PATH / ".local/state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(SANDBOX_PATH / ".cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(SANDBOX_PATH / ".local/share"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(SANDBOX_PATH / ".runtime"))
    monkeypatch.setenv("OPENHTPC_TEST_ENVIRONMENT", "1")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
