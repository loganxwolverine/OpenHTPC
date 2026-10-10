# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Behavioral regressions for OPENHTPC 1.3.1 lifecycle stabilization."""
from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLEX_SRC = ROOT / "vendor/flex-launcher/src"
FLEX_BUILD = ROOT / "vendor/flex-launcher/build"


def _load_python_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        loader = importlib.machinery.SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_update_fixture(tmp_path: Path, install_body: str, launcher_body: str | None = None):
    home = tmp_path / "home"
    candidate = tmp_path / "candidate"
    payload = candidate / "payload"
    payload.mkdir(parents=True)
    shutil.copy2(ROOT / "update.sh", candidate / "update.sh")
    (candidate / "install.sh").write_text(install_body, encoding="utf-8")
    (candidate / "install.sh").chmod(0o755)
    (candidate / "legacy-managed-files-dev27.txt").write_text("openhtpc\n", encoding="utf-8")
    (payload / "managed-files.txt").write_text("openhtpc\n", encoding="utf-8")
    (payload / "openhtpc-update-managed-files").write_text(
        "#!/usr/bin/env python3\nraise SystemExit(0)\n", encoding="utf-8"
    )
    (payload / "openhtpc-update-managed-files").chmod(0o755)
    (payload / "openhtpc-runtime.py").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (payload / "openhtpc-runtime.py").chmod(0o755)

    install = home / ".local/lib/openhtpc"
    install.mkdir(parents=True)
    (install / ".openhtpc-managed-files").write_text("openhtpc\n", encoding="utf-8")
    if launcher_body is None:
        launcher_body = (
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = start ]; then printf 'start\\n' >> \"$HOME/restart-observed\"; exit 0; fi\n"
            "exit 1\n"
        )
    (install / "openhtpc").write_text(launcher_body, encoding="utf-8")
    (install / "openhtpc").chmod(0o755)

    state = home / ".local/state/openhtpc/runtime-session.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"schema": 1, "state": "RUNNING"}), encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "OPENHTPC_INSTALL_DIR": str(install)}
    return home, candidate, install, env


def test_update_sigterm_after_cleanup_restores_previous_session(tmp_path):
    home, candidate, _install, env = _make_update_fixture(
        tmp_path,
        "#!/bin/sh\nkill -TERM $PPID\nexit 0\n",
    )
    result = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
    assert result.returncode == 143, result.stderr
    assert (home / "restart-observed").read_text(encoding="utf-8") == "start\n"
    assert "session OPENHTPC précédente restaurée" in result.stderr


def test_update_failure_with_missing_launcher_preserves_failure_code(tmp_path):
    home, candidate, install, env = _make_update_fixture(
        tmp_path,
        "#!/bin/sh\nrm -f \"$HOME/.local/lib/openhtpc/openhtpc\"\nexit 23\n",
    )
    result = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
    assert result.returncode == 23
    assert not (install / "openhtpc").exists()
    assert not (home / "restart-observed").exists()
    assert "lanceur OPENHTPC indisponible" in result.stderr


def test_update_restart_failure_retries_once_and_stays_failed(tmp_path):
    launcher = (
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = start ]; then printf 'start\\n' >> \"$HOME/restart-observed\"; exit 9; fi\n"
        "exit 1\n"
    )
    home, candidate, _install, env = _make_update_fixture(tmp_path, "#!/bin/sh\nexit 0\n", launcher)
    result = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
    assert result.returncode == 9
    assert (home / "restart-observed").read_text(encoding="utf-8") == "start\nstart\n"
    assert "impossible de restaurer automatiquement OPENHTPC" in result.stderr


def test_update_refuses_global_playback_lock_before_cleanup(tmp_path):
    home, candidate, _install, env = _make_update_fixture(tmp_path, "#!/bin/sh\nexit 0\n")
    lock_path = home / ".local/state/openhtpc/playback-active.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
    assert result.returncode == 4
    assert "une lecture est en cours" in result.stderr
    assert not (home / "restart-observed").exists()


def test_global_playback_lock_is_shared_by_all_playback_entrypoints_and_update():
    lock_name = "playback-active.lock"
    update = (ROOT / "update.sh").read_text(encoding="utf-8")
    local = (ROOT / "payload/openhtpc-play").read_text(encoding="utf-8")
    dvd = (ROOT / "payload/openhtpc-play-dvd").read_text(encoding="utf-8")
    optical = (ROOT / "payload/openhtpc-play-optical").read_text(encoding="utf-8")
    for source in (update, local, dvd, optical):
        assert lock_name in source
    assert "LOCK_EX | fcntl.LOCK_NB" in local
    assert "LOCK_EX|fcntl.LOCK_NB" in optical
    assert "flock -n 8" in dvd
    assert "flock -n 7" in update


def test_system_pages_can_be_refreshed_from_current_runtime_truth(tmp_path):
    engine = _load_python_module("openhtpc_session_engine_health_refresh", ROOT / "payload/openhtpc-session-engine.py")
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    health = tmp_path / "health"
    health.write_text("BLOCKED", encoding="utf-8")
    (install / "openhtpc-system-page").write_text(
        "def status_model(home, install):\n"
        f"    return {{'health': {str(health)!r}}}\n",
        encoding="utf-8",
    )

    class FakeUi:
        @staticmethod
        def system_page_png(model, target, _font, section):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{section}:{Path(model['health']).read_text()}", encoding="utf-8")

    pages, dashboard, model = engine.render_system_pages(home, install, FakeUi)
    assert model["health"] == str(health)
    assert dashboard.read_text(encoding="utf-8") == "root:BLOCKED"
    assert pages["overview"].read_text(encoding="utf-8") == "overview:BLOCKED"

    health.write_text("READY", encoding="utf-8")
    engine.render_system_pages(home, install, FakeUi)
    assert dashboard.read_text(encoding="utf-8") == "root:READY"
    assert pages["overview"].read_text(encoding="utf-8") == "overview:READY"


def test_home_refreshes_system_health_after_publishing_authoritative_flex_pid():
    source = (ROOT / "payload/openhtpc-home.py").read_text(encoding="utf-8")
    publish = source.index('runtime.atomic_json(runtime.paths(home)["session"], session)')
    exact_child_probe = source.index('proc.pid in runtime.managed_processes(home, install)["ui"]', publish)
    refresh = source.index("engine.render_system_pages(home, install)", publish)
    started = source.index('runtime.log(home, "ui", "FLEX_STARTED"', refresh)
    assert publish < exact_child_probe < refresh < started
    assert "proc.poll() is None" in source[publish:refresh]


def test_media_flex_telemetry_finds_exact_launcher_with_posix_regex(tmp_path):
    player = _load_python_module("openhtpc_play_flex_telemetry", ROOT / "payload/openhtpc-play")
    install = tmp_path / "install"
    launcher = install / "flex/bin/flex-launcher"
    launcher.parent.mkdir(parents=True)
    shutil.copy2("/bin/sleep", launcher)
    child = subprocess.Popen([str(launcher), "10"])
    try:
        count, pids = player.flex_instances(install)
        assert count == 1
        assert pids == [child.pid]
    finally:
        child.terminate()
        child.wait(timeout=5)


def _compile_launch_probe_harness(tmp_path: Path) -> Path:
    if shutil.which("gcc") is None or shutil.which("pkg-config") is None:
        pytest.skip("C compiler or pkg-config unavailable")
    packages = subprocess.run(["pkg-config", "--exists", "sdl2", "inih"], check=False)
    if packages.returncode != 0:
        pytest.skip("SDL2/inih development files unavailable")
    flags = shlex.split(
        subprocess.check_output(["pkg-config", "--cflags", "--libs", "sdl2", "inih"], text=True)
    )
    source = tmp_path / "launch-probe-harness.c"
    source.write_text(r'''#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <SDL.h>
#include "launcher.h"
#include "debug.h"
#include "platform/platform.h"
#include "util.h"

Config config = {0};
static int calls = 0;
''', encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8") + r'''pid_t __wrap_waitpid(pid_t pid, int *status, int options) {
    (void)pid; (void)status; (void)options;
    calls++;
    const char *mode = getenv("OPENHTPC_WAITPID_MODE");
    if (mode && strcmp(mode, "eintr_then_zero") == 0 && calls == 1) {
        errno = EINTR;
        return -1;
    }
    if (mode && strcmp(mode, "hard_error") == 0) {
        errno = ECHILD;
        return -1;
    }
    return 0;
}
void copy_string(char *dest, const char *string, size_t size) {
    if (size == 0) return;
    snprintf(dest, size, "%s", string ? string : "");
}
void output_log(LogLevel level, const char *format, ...) {
    (void)level; (void)format;
}
int main(void) {
    config.on_launch = ON_LAUNCH_BLANK;
    bool ok = start_process("/bin/true", true, false);
    printf("ok=%d calls=%d\n", ok ? 1 : 0, calls);
    return ok ? 0 : 7;
}
''', encoding="utf-8")
    binary = tmp_path / "launch-probe-harness"
    command = [
        "gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-ffunction-sections", "-fdata-sections",
        f"-I{FLEX_SRC}", f"-I{FLEX_SRC / 'platform'}", f"-I{FLEX_BUILD}",
        str(FLEX_SRC / "platform/unix.c"), str(source),
        "-Wl,--gc-sections", "-Wl,--wrap=waitpid", "-o", str(binary), *flags,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return binary


def test_classic_launch_probe_executes_production_waitpid_contract(tmp_path):
    binary = _compile_launch_probe_harness(tmp_path)

    zero = subprocess.run(
        [str(binary)], env={**os.environ, "OPENHTPC_WAITPID_MODE": "zero"},
        capture_output=True, text=True,
    )
    assert zero.returncode == 0
    assert "ok=1 calls=1" in zero.stdout

    interrupted = subprocess.run(
        [str(binary)], env={**os.environ, "OPENHTPC_WAITPID_MODE": "eintr_then_zero"},
        capture_output=True, text=True,
    )
    assert interrupted.returncode == 0
    assert "ok=1 calls=2" in interrupted.stdout

    hard = subprocess.run(
        [str(binary)], env={**os.environ, "OPENHTPC_WAITPID_MODE": "hard_error"},
        capture_output=True, text=True,
    )
    assert hard.returncode == 7
    assert "ok=0 calls=1" in hard.stdout


def test_standalone_dvd_return_releases_dispatch_locks_before_ui(tmp_path):
    home = tmp_path / "home"
    install = home / ".local/lib/openhtpc"
    install.mkdir(parents=True)
    marker = tmp_path / "returned-ui-ready"
    ui = install / "openhtpc-dvd-ui"
    ui.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, time\n"
        f"pathlib.Path({str(marker)!r}).write_text('ready')\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    ui.chmod(0o755)
    env = {**os.environ, "OPENHTPC_HOME": str(home), "OPENHTPC_INSTALL_DIR": str(install)}
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "OPENHTPC_FLEX_RETAINED"):
        env.pop(name, None)
    # Invalid input reaches the actual production fail-and-return path before
    # any device access or player launch. The exact owned child becomes the UI.
    child = subprocess.Popen(
        ["bash", str(ROOT / "payload/openhtpc-play-dvd"), "invalid-device"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 3
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "standalone UI was not reached"
        assert child.poll() is None, "returned UI must still be alive during lock check"
        for name in ("playback-active.lock", "play-dvd.lock"):
            with (home / ".local/state/openhtpc" / name).open("a+") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)
