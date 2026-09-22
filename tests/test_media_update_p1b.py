# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic P1B request, ownership, lock and status checks."""

import fcntl
import ast
from contextlib import redirect_stdout
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import pytest
import signal
import subprocess
import sys
import threading
import time


PAYLOAD = Path(__file__).resolve().parents[1] / "payload"


def load(name, file):
    path = PAYLOAD / file
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


update = load("p1b_update", "openhtpc-media-library-update")
control = load("p1b_control", "openhtpc-media-update-control.py")


def test_media_entry_is_unconditional_and_uses_short_helper(tmp_path):
    engine = load("p1b_menu_engine", "openhtpc-session-engine.py")
    _root, sections = engine.media_menu_sections(tmp_path, [], tmp_path / "icon")
    root = sections.split("\n\n", 1)[0]
    assert "Entry1=METTRE À JOUR LA MÉDIATHÈQUE" in root
    assert ":fork " + str(tmp_path / ".local/lib/openhtpc/openhtpc-media-update-request") in root
    assert "openhtpc-media-library-update" not in root


def test_request_is_fast_and_consumed_once(tmp_path):
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    script = install / "openhtpc-media-library-update"
    script.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    script.chmod(0o755)
    owner = control.UpdateController(home, install)
    try:
        started = time.monotonic()
        result = subprocess.run(
            [str(PAYLOAD / "openhtpc-media-update-request")],
            env={**os.environ, "OPENHTPC_HOME": str(home)},
            capture_output=True, timeout=2,
        )
        assert result.returncode == 0
        assert time.monotonic() - started < 0.5
        assert owner.child is None
        owner.poll()
        child = owner.child
        assert child is not None and child.poll() is None
        owner.poll()
        assert owner.child is child
    finally:
        owner.close()
    assert child.poll() is not None
    assert not control.request_path(home).exists()


def test_ui_request_during_cli_update_does_not_launch(tmp_path):
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    lock_path = home / ".local/state/openhtpc/media/library-update.lock"
    lock_path.parent.mkdir(parents=True)
    owner = control.UpdateController(home, install)
    try:
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            assert control.request_update(home)
            owner.poll()
            assert owner.child is None
    finally:
        owner.close()


def test_home_reaps_finished_updater(tmp_path):
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    script = install / "openhtpc-media-library-update"
    script.write_text("#!/usr/bin/env python3\n")
    script.chmod(0o755)
    owner = control.UpdateController(home, install)
    try:
        assert control.request_update(home)
        owner.poll()
        child = owner.child
        assert child is not None
        deadline = time.monotonic() + 2
        while owner.child is not None and time.monotonic() < deadline:
            owner.poll()
            time.sleep(0.01)
        assert owner.child is None
        assert child.returncode == 0
    finally:
        owner.close()


def test_flex_publication_waits_for_shared_lock(tmp_path, monkeypatch):
    engine = load("p1b_engine", "openhtpc-session-engine.py")
    home = tmp_path / "home"
    entered = threading.Event()
    done = threading.Event()
    monkeypatch.setattr(engine, "_write_flex_config", lambda *args: entered.set() or True)
    with engine.flex_publication_lock(home):
        thread = threading.Thread(target=lambda: (engine.write_flex_config(tmp_path / "f.ini", home, []), done.set()))
        thread.start()
        assert not entered.wait(0.1)
    thread.join(timeout=2)
    assert done.is_set() and entered.is_set()


def test_updater_lock_and_status_are_owned_by_first_run(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    state = home / ".local/state/openhtpc/media"
    state.mkdir(parents=True)
    lock_path = state / "library-update.lock"
    status_path = state / "library-update-status.json"
    status_path.write_text('{"state":"RUNNING","pid":123}\n')
    calls = []
    def successful_update(*args):
        running = json.loads(status_path.read_text())
        assert running["state"] == "RUNNING"
        assert running["pid"] == os.getpid()
        assert running["started_at"] and running["origin"] == "CLI"
        calls.append(args)
        return {"ok": True, "flex_published": True}
    monkeypatch.setattr(update, "update_library", successful_update)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # flock is process-wide only per open file description; a separate open conflicts.
        assert update.main(["--home", str(home)]) == update.ALREADY_RUNNING_EXIT
        assert json.loads(capsys.readouterr().out)["state"] == "ALREADY_RUNNING"
        assert json.loads(status_path.read_text()) == {"state": "RUNNING", "pid": 123}
        assert calls == []
    assert update.main(["--home", str(home)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    final = json.loads(status_path.read_text())
    assert final["state"] == "SUCCESS" and final["exit_code"] == 0
    assert final["summary"]["flex_published"] is True
    assert Path(final["log_path"]).is_file()
    monkeypatch.setattr(update, "update_library", lambda *args: {"ok": False, "error": "diagnostic"})
    assert update.main(["--home", str(home)]) == 1
    failed = json.loads(status_path.read_text())
    assert failed["state"] == "FAILED" and failed["exit_code"] == 1
    assert failed["finished_at"] and failed["started_at"]
    assert update.main(["--home", str(home)]) == 1  # failure releases lock


def test_home_and_cli_share_updater_command_and_deployment():
    home = (PAYLOAD / "openhtpc-home.py").read_text()
    assert "update_controller.poll()" in home
    assert "update_controller.close()" in home
    assert "publish_flex_config(target, home" in home
    assert "active_media_generation(home)" not in home
    calls = [node.func.attr for node in ast.walk(ast.parse(home))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "publish_flex_config" in calls
    assert "activate_media_manifest" not in calls
    assert '"--origin", "UI"' in (PAYLOAD / "openhtpc-media-update-control.py").read_text()
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
    managed = (PAYLOAD / "managed-files.txt").read_text()
    for name in ("openhtpc-media-update-control.py", "openhtpc-media-update-request"):
        assert name in installer and name in managed


def _wait_not_running(pid, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0]
        except FileNotFoundError:
            return
        if state == "Z":
            return
        time.sleep(0.01)
    raise AssertionError(f"process {pid} still running")


def _owned_updater(install, *, ignore_term=False, descendant_only_ignores_term=False):
    script = install / "openhtpc-media-library-update"
    descendant_code = "import pathlib,signal,time; "
    if ignore_term or descendant_only_ignores_term:
        descendant_code += "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    descendant_code += "pathlib.Path(%r).write_text('1'); time.sleep(60)" % "DESCENDANT_READY_PATH"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import fcntl, json, os, pathlib, signal, subprocess, sys, time\n"
        "home = pathlib.Path(sys.argv[sys.argv.index('--home') + 1])\n"
        "state = home / '.local/state/openhtpc/media'\n"
        "state.mkdir(parents=True, exist_ok=True)\n"
        "lock = (state / 'library-update.lock').open('a+b')\n"
        "fcntl.flock(lock, fcntl.LOCK_EX)\n"
        f"descendant = subprocess.Popen([sys.executable, '-c', {descendant_code!r}.replace('DESCENDANT_READY_PATH', str(state / 'descendant.ready'))])\n"
        "(state / 'descendant.pid').write_text(str(descendant.pid))\n"
        "while not (state / 'descendant.ready').exists(): time.sleep(0.01)\n"
        "(state / 'library-update-status.json').write_text(json.dumps("
        "{'state':'RUNNING','pid':os.getpid(),'started_at':'START',"
        "'origin':'UI','log_path':str(state / 'library-update.log')}))\n"
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_term else "")
        + "(state / 'ready').write_text('1')\n"
        + "time.sleep(60)\n"
    )
    script.chmod(0o755)


def _wait_owned_ready(home, owner):
    status_path = home / ".local/state/openhtpc/media/library-update-status.json"
    descendant_path = status_path.with_name("descendant.pid")
    ready_path = status_path.with_name("ready")
    assert control.request_update(home)
    owner.poll()
    assert owner.child is not None
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not ready_path.exists():
        time.sleep(0.01)
    assert ready_path.exists() and descendant_path.exists()
    return status_path, int(descendant_path.read_text()), owner.child


def test_close_signals_owned_group_reaps_exact_child_and_spares_cli(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    cli_home = tmp_path / "cli-home"
    install.mkdir()
    _owned_updater(install)
    cli = subprocess.Popen([str(install / "openhtpc-media-library-update"),
                            "--home", str(cli_home)], start_new_session=True)
    owner = control.UpdateController(home, install)
    try:
        cli_ready = cli_home / ".local/state/openhtpc/media/descendant.pid"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not cli_ready.exists():
            time.sleep(0.01)
        assert cli_ready.exists()
        status_path, descendant_pid, child = _wait_owned_ready(home, owner)
        owner.close()
        owner.close()
        assert child.returncode is not None
        _wait_not_running(child.pid)
        _wait_not_running(descendant_pid)
        assert cli.poll() is None
        status = json.loads(status_path.read_text())
        assert status["state"] == "FAILED" and status["pid"] == child.pid
        assert status["reason"] == "SESSION_STOPPED"
    finally:
        owner.close()
        try:
            os.killpg(cli.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cli.wait(timeout=2)


def test_forced_stop_repairs_only_owned_running_status(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    _owned_updater(install, ignore_term=True)
    owner = control.UpdateController(home, install)
    try:
        status_path, descendant_pid, child = _wait_owned_ready(home, owner)
        owner.close()
        _wait_not_running(child.pid)
        _wait_not_running(descendant_pid)
        status = json.loads(status_path.read_text())
        assert status["state"] == "FAILED" and status["pid"] == child.pid
        assert status["reason"] == "FORCED_STOP"
        assert status["terminated_signal"] == signal.SIGKILL
        assert status["exit_code"] != 0 and status["finished_at"]
        assert status["started_at"] == "START" and status["origin"] == "UI"
        assert status["log_path"].endswith("library-update.log")
    finally:
        owner.close()


def test_leader_exits_first_but_term_ignoring_descendant_is_killed(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    _owned_updater(install, descendant_only_ignores_term=True)
    owner = control.UpdateController(home, install)
    try:
        status_path, descendant_pid, child = _wait_owned_ready(home, owner)
        owner.close()
        assert child.returncode == -signal.SIGTERM
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        assert not control.process_group_has_live_members(child.pid)
        _wait_not_running(child.pid)
        _wait_not_running(descendant_pid)
        status = json.loads(status_path.read_text())
        assert status["state"] == "FAILED" and status["pid"] == child.pid
        assert status["reason"] == "FORCED_STOP"
        assert status["terminated_signal"] == signal.SIGTERM
        assert status["group_stop_signal"] == signal.SIGKILL
        assert status["exit_code"] != 0
    finally:
        owner.close()


def test_stopped_ui_child_cannot_overwrite_another_pid(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    _owned_updater(install)
    owner = control.UpdateController(home, install)
    try:
        status_path, descendant_pid, child = _wait_owned_ready(home, owner)
        other = {"state": "RUNNING", "pid": child.pid + 99999, "origin": "CLI"}
        status_path.write_text(json.dumps(other))
        owner.close()
        _wait_not_running(descendant_pid)
        assert json.loads(status_path.read_text()) == other
    finally:
        owner.close()


def test_status_repair_skips_busy_execution_lock(tmp_path):
    home = tmp_path / "home"
    state = home / ".local/state/openhtpc/media"
    state.mkdir(parents=True)
    status_path = state / "library-update-status.json"
    current = {"state": "RUNNING", "pid": 123, "origin": "CLI"}
    status_path.write_text(json.dumps(current))
    with (state / "library-update.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        control.repair_stopped_status(home, 123, -signal.SIGKILL, "FORCED_STOP")
        assert time.monotonic() - started < 0.5
    assert json.loads(status_path.read_text()) == current


def test_ui_log_contains_one_final_json_and_cli_stdout_remains(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setattr(update, "update_library", lambda *args: {"ok": True, "marker": "ONE_FINAL_RESULT"})
    log_path = home / ".local/state/openhtpc/media/library-update.log"
    log_path.parent.mkdir(parents=True)
    with log_path.open("a", encoding="utf-8") as log, redirect_stdout(log):
        assert update.main(["--home", str(home), "--origin", "UI"]) == 0
    assert log_path.read_text().count("ONE_FINAL_RESULT") == 1
    assert update.main(["--home", str(home)]) == 0
    assert capsys.readouterr().out.count("ONE_FINAL_RESULT") == 1


def test_playback_setting_waits_for_publication_before_read(tmp_path, monkeypatch):
    engine = load("p1b_playback_engine", "openhtpc-session-engine.py")
    setting = load("p1b_playback_setting", "openhtpc-playback-setting")
    home = tmp_path / "home"
    target = home / ".config/openhtpc/flex-v1.ini"
    target.parent.mkdir(parents=True)
    target.write_text("[SYSTEM_AUDIO]\nEntry1=MODE AUDIO : PCM;i;:submenu AUDIO_OUTPUT_MODE\n")
    entered_read = threading.Event()
    original_read = Path.read_text
    def observed_read(path, *args, **kwargs):
        if path == target:
            entered_read.set()
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", observed_read)
    with engine.flex_publication_lock(home):
        worker = threading.Thread(target=setting.refresh_audio_mode_label, args=(home, "BITSTREAM"))
        worker.start()
        assert not entered_read.wait(0.15)
        assert "MODE AUDIO : PCM" in original_read(target)
    worker.join(timeout=3)
    assert not worker.is_alive() and entered_read.is_set()
    assert "MODE AUDIO : BITSTREAM" in original_read(target)
