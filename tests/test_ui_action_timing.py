# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Production-path tests for synchronous Flex UI-action timing."""
from __future__ import annotations

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


def _compile_sync_harness(tmp_path: Path) -> Path:
    if shutil.which("gcc") is None or shutil.which("pkg-config") is None:
        pytest.skip("C compiler or pkg-config unavailable")
    flags = shlex.split(
        subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "sdl2", "inih"],
            text=True,
        )
    )
    harness_source = tmp_path / "sync-trace-harness.c"
    harness_source.write_text(
        r'''
#include <stdarg.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <SDL.h>
#include "launcher.h"
#include "debug.h"
#include "platform/platform.h"

int __real_setenv(const char *name, const char *value, int overwrite);

int __wrap_setenv(const char *name, const char *value, int overwrite)
{
    if (getenv("OPENHTPC_TEST_FAIL_CHILD_PID_SETENV") != NULL
            && strcmp(name, "OPENHTPC_UI_ACTION_CHILD_PID") == 0) {
        errno = ENOMEM;
        return -1;
    }
    return __real_setenv(name, value, overwrite);
}

void output_log(LogLevel level, const char *format, ...)
{
    (void) level;
    (void) format;
}

int main(int argc, char **argv)
{
    if (argc != 3)
        return 10;
    char operation_id[UI_ACTION_OPERATION_ID_MAX] = {0};
    char command[4096];
    size_t operation_size = strcmp(argv[1], "small") == 0 ? 1 : sizeof(operation_id);
    int trace_started = ui_action_trace_begin(operation_id, operation_size);
    const char *trace_value = getenv("OPENHTPC_TRACE_UI_ACTION");
    if (strcmp(argv[1], "normal") == 0
            && trace_value != NULL && strcmp(trace_value, "1") == 0 && !trace_started)
        return 11;
    int written;
    if (strcmp(argv[1], "command") == 0)
        written = snprintf(command, sizeof(command), "%s", argv[2]);
    else
        written = snprintf(command, sizeof(command), "sleep 0.05; env > '%s'", argv[2]);
    if (written <= 0 || (size_t) written >= sizeof(command))
        return 12;
    return run_process_sync(command, operation_id) ? 0 : 13;
}
''',
        encoding="utf-8",
    )
    binary = tmp_path / "flex-launcher"
    command = [
        "gcc",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-ffunction-sections",
        "-fdata-sections",
        f"-I{FLEX_SRC}",
        f"-I{FLEX_SRC / 'platform'}",
        f"-I{FLEX_BUILD}",
        str(FLEX_SRC / "platform/unix.c"),
        str(harness_source),
        "-Wl,--gc-sections",
        "-Wl,--wrap=setenv",
        "-o",
        str(binary),
        *flags,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return binary


def _read_environment(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def test_sync_trace_uses_exact_owned_child_and_stays_blocking(tmp_path):
    """Execute the production run_process_sync implementation and verify its PID contract."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    child_pid_output = tmp_path / "owned-child-pid"
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENHTPC_TRACE_UI_ACTION": "1",
    }

    started = time.monotonic()
    subprocess.run([str(binary), "normal", str(child_pid_output)], env=env, check=True)
    elapsed = time.monotonic() - started

    trace_path = home / ".local/state/openhtpc/ui-action-timing.jsonl"
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    events = [row["event"] for row in rows]
    assert events == [
        "flex_action_received",
        "sync_before_fork",
        "sync_child_launched",
        "sync_waitpid_returned",
    ]
    launched = rows[2]["child_pid"]
    assert launched > 0
    assert rows[3]["child_pid"] == launched
    child_environment = _read_environment(child_pid_output)
    assert int(child_environment["OPENHTPC_UI_ACTION_CHILD_PID"]) == launched
    assert child_environment["OPENHTPC_UI_ACTION_OPERATION_ID"] == rows[0]["operation_id"]
    assert all(row["operation_id"] == rows[0]["operation_id"] for row in rows)
    assert [row["mono_ns"] for row in rows] == sorted(row["mono_ns"] for row in rows)
    assert elapsed >= 0.04


def test_sync_trace_disabled_preserves_execution_without_output(tmp_path):
    """The production synchronous command still runs with no trace side effect."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    child_pid_output = tmp_path / "owned-child-pid"
    env = {**os.environ, "HOME": str(home)}
    env.pop("OPENHTPC_TRACE_UI_ACTION", None)
    env["OPENHTPC_UI_ACTION_OPERATION_ID"] = "uiaq-999-123"
    env["OPENHTPC_UI_ACTION_CHILD_PID"] = "999"

    result = subprocess.run(
        [str(binary), "normal", str(child_pid_output)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert child_pid_output.is_file()
    child_environment = _read_environment(child_pid_output)
    assert "OPENHTPC_UI_ACTION_OPERATION_ID" not in child_environment
    assert "OPENHTPC_UI_ACTION_CHILD_PID" not in child_environment
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (home / ".local/state/openhtpc/ui-action-timing.jsonl").exists()


def test_sync_trace_failed_operation_setup_clears_stale_environment(tmp_path):
    """A failed current operation leaves no inherited correlation in the child."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    output = tmp_path / "child-environment"
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENHTPC_TRACE_UI_ACTION": "1",
        "OPENHTPC_UI_ACTION_OPERATION_ID": "uiaq-999-123",
        "OPENHTPC_UI_ACTION_CHILD_PID": "999",
    }

    subprocess.run([str(binary), "small", str(output)], env=env, check=True)
    child_environment = _read_environment(output)
    assert "OPENHTPC_UI_ACTION_OPERATION_ID" not in child_environment
    assert "OPENHTPC_UI_ACTION_CHILD_PID" not in child_environment
    assert not (home / ".local/state/openhtpc/ui-action-timing.jsonl").exists()


def test_sync_trace_partial_setenv_failure_clears_both_values(tmp_path):
    """Failure of the second fresh assignment removes the first assignment too."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    output = tmp_path / "child-environment"
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENHTPC_TRACE_UI_ACTION": "1",
        "OPENHTPC_UI_ACTION_OPERATION_ID": "uiaq-999-123",
        "OPENHTPC_UI_ACTION_CHILD_PID": "999",
        "OPENHTPC_TEST_FAIL_CHILD_PID_SETENV": "1",
    }

    subprocess.run([str(binary), "normal", str(output)], env=env, check=True)
    child_environment = _read_environment(output)
    assert "OPENHTPC_UI_ACTION_OPERATION_ID" not in child_environment
    assert "OPENHTPC_UI_ACTION_CHILD_PID" not in child_environment


def test_sync_trace_replaces_stale_environment_with_current_operation(tmp_path):
    """Enabled tracing passes only the freshly generated C-owned correlation."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    output = tmp_path / "child-environment"
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENHTPC_TRACE_UI_ACTION": "1",
        "OPENHTPC_UI_ACTION_OPERATION_ID": "uiaq-999-123",
        "OPENHTPC_UI_ACTION_CHILD_PID": "999",
    }

    subprocess.run([str(binary), "normal", str(output)], env=env, check=True)
    rows = [
        json.loads(line)
        for line in (home / ".local/state/openhtpc/ui-action-timing.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    child_environment = _read_environment(output)
    launched_pid = rows[2]["child_pid"]
    assert child_environment["OPENHTPC_UI_ACTION_OPERATION_ID"] == rows[0]["operation_id"]
    assert child_environment["OPENHTPC_UI_ACTION_OPERATION_ID"] != "uiaq-999-123"
    assert int(child_environment["OPENHTPC_UI_ACTION_CHILD_PID"]) == launched_pid


def test_end_to_end_trace_correlates_production_c_with_real_python(tmp_path):
    """The real Python CLI retains the exact C-owned child correlation through exit."""
    binary = _compile_sync_harness(tmp_path)
    home = tmp_path / "home"
    script_dir = home / ".local/lib/openhtpc"
    script_dir.mkdir(parents=True)
    (script_dir / "openhtpc-media-enrich.py").symlink_to(
        ROOT / "payload/openhtpc-media-enrich.py"
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENHTPC_HOME": str(home),
        "OPENHTPC_TRACE_UI_ACTION": "1",
        "OPENHTPC_UI_ACTION_OPERATION_ID": "uiaq-999-123",
        "OPENHTPC_UI_ACTION_CHILD_PID": "999",
    }
    command = (
        '$HOME/.local/lib/openhtpc/openhtpc-media-enrich.py '
        f"--home {shlex.quote(str(home))} --install {shlex.quote(str(ROOT / 'payload'))} "
        "--token iact_probe"
    )

    result = subprocess.run(
        [str(binary), "command", command],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 13
    rows = [
        json.loads(line)
        for line in (home / ".local/state/openhtpc/ui-action-timing.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    events = [row["event"] for row in rows]
    assert events == [
        "flex_action_received",
        "sync_before_fork",
        "sync_child_launched",
        "python_entry",
        "action_token_invalid",
        "python_exit",
        "sync_waitpid_returned",
    ]
    operation_id = rows[0]["operation_id"]
    assert operation_id.startswith(f"uiaq-{rows[0]['pid']}-")
    assert all(row["operation_id"] == operation_id for row in rows)
    launched_pid = rows[2]["child_pid"]
    python_rows = rows[3:6]
    assert all(row["pid"] == launched_pid for row in python_rows)
    assert all(row["child_pid"] == launched_pid for row in python_rows)
    assert rows[-1]["child_pid"] == launched_pid


def test_applyback_trace_wraps_existing_sync_reload_without_async():
    """T0/T20/T21 surround the unchanged blocking applyback lifecycle."""
    launcher = (FLEX_SRC / "launcher.c").read_text(encoding="utf-8")
    unix = (FLEX_SRC / "platform/unix.c").read_text(encoding="utf-8")
    applyback = launcher.split("SCMD_APPLY_BACK", 1)[1].split("SCMD_REPLACE", 1)[0]
    sync = unix.split("bool run_process_sync", 1)[1].split("int image_filter", 1)[0]

    assert applyback.index("ui_action_trace_begin") < applyback.index("run_process_sync")
    assert applyback.index('ui_action_trace_event("flex_reload_begin"') < applyback.index("reload_menu_section(parent)")
    assert applyback.index("load_menu(parent, false, true)") < applyback.index('ui_action_trace_event("flex_ui_ready"')
    assert "waitpid(child_pid, &status, 0)" in sync
    assert "WNOHANG" not in sync
    assert "pthread" not in sync
