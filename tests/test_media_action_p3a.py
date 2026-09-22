# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic RC8 P3A media action request and lifecycle checks."""

import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name, filename):
    path = PAYLOAD / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


control = load("p3a_action_control", "openhtpc-media-action-control.py")


def make_worker(install: Path, body: str = "time.sleep(60)") -> Path:
    worker = install / "openhtpc-media-enrich.py"
    worker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, subprocess, sys, time\n"
        "home = pathlib.Path(sys.argv[sys.argv.index('--home') + 1])\n"
        "state = home / '.local/state/openhtpc/media'\n"
        "state.mkdir(parents=True, exist_ok=True)\n"
        "(state / 'worker-argv.json').write_text(json.dumps(sys.argv))\n"
        "(state / 'worker-ready').write_text('1')\n"
        f"{body}\n",
        encoding="utf-8",
    )
    worker.chmod(0o755)
    return worker


def wait_for(path: Path, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def finish(owner, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while owner.child is not None and time.monotonic() < deadline:
        owner.poll()
        time.sleep(0.01)
    assert owner.child is None


def test_request_helper_is_fast_and_fails_without_controller(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = time.monotonic()
    result = subprocess.run(
        [str(PAYLOAD / "openhtpc-media-action-request"), "iact_valid_1"],
        env={**os.environ, "OPENHTPC_HOME": str(home)},
        capture_output=True,
        timeout=2,
    )
    assert result.returncode != 0
    assert time.monotonic() - started < 0.5
    owner = control.ActionController(home, tmp_path / "install")
    try:
        started = time.monotonic()
        result = subprocess.run(
            [str(PAYLOAD / "openhtpc-media-action-request"), "iact_valid_1"],
            env={**os.environ, "OPENHTPC_HOME": str(home)},
            capture_output=True,
            timeout=2,
        )
        assert result.returncode == 0
        assert time.monotonic() - started < 0.5
        assert owner.child is None
    finally:
        owner.close()


def test_invalid_tokens_never_launch(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    owner = control.ActionController(home, install)
    launches = []
    monkeypatch.setattr(control.subprocess, "Popen", lambda *a, **k: launches.append((a, k)))
    invalid = ["", "iact_", "bad_1", "iact_bad token", "iact_é", "iact_" + "a" * 252]
    try:
        for token in invalid:
            assert not control.request_action(home, token)
        fd = os.open(control.request_path(home), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"bad_raw\niact_bad raw\n\xff\n")
        finally:
            os.close(fd)
        owner.poll()
        assert launches == []
    finally:
        owner.close()


def test_valid_request_launches_one_exact_argv_without_shell_and_drops_duplicate(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    worker = make_worker(install)
    real_popen = subprocess.Popen
    calls = []

    def recording_popen(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(control.subprocess, "Popen", recording_popen)
    owner = control.ActionController(home, install)
    try:
        assert control.request_action(home, "iact_first")
        owner.poll()
        wait_for(control.status_path(home).with_name("worker-ready"))
        fd = os.open(control.request_path(home), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"iact_partial")
        finally:
            os.close(fd)
        owner.poll()
        fd = os.open(control.request_path(home), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"\niact_second\n")
        finally:
            os.close(fd)
        owner.poll()
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == [str(worker), "--token", "iact_first", "--home", str(home), "--install", str(install)]
        assert "shell" not in kwargs
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.STDOUT
        assert kwargs["start_new_session"] is True
        assert kwargs["pass_fds"] == (owner.lock_fd,)
    finally:
        owner.close()


@pytest.mark.parametrize(("token", "exit_code", "final_state"), [
    ("iact_success", 0, "SUCCESS"),
    ("iact_failure", 7, "FAILED"),
])
def test_running_to_final_status_is_atomic_and_private(tmp_path, token, exit_code, final_state):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    make_worker(install, f"print(sys.argv[sys.argv.index('--token') + 1], flush=True); sys.stdout.write('x' * 300000); sys.stdout.flush(); time.sleep(0.15); raise SystemExit({exit_code})")
    owner = control.ActionController(home, install)
    try:
        assert (control.request_path(home).stat().st_mode & 0o777) == 0o600
        assert (control.request_path(home).parent.stat().st_mode & 0o777) == 0o700
        assert control.request_action(home, token)
        owner.poll()
        running = json.loads(control.status_path(home).read_text())
        assert running["state"] == "RUNNING" and running["origin"] == "UI"
        assert running["pid"] == owner.child.pid and running["started_at"]
        assert running["operation_id"].startswith(f"media-action-{owner.child.pid}-")
        assert token not in json.dumps(running)
        assert (control.status_path(home).stat().st_mode & 0o777) == 0o600
        assert (control.log_path(home).stat().st_mode & 0o777) == 0o600
        finish(owner)
        final = json.loads(control.status_path(home).read_text())
        assert final["state"] == final_state and final["exit_code"] == exit_code
        assert final["finished_at"] and final["operation_id"] == running["operation_id"]
        log = control.log_path(home)
        assert log.stat().st_size == control.MAX_LOG_BYTES
        assert token not in log.read_text()
        assert "<action-token>" in log.read_text()
        assert list(control.status_path(home).parent.glob("media-action-status.json.*")) == []
    finally:
        owner.close()


def test_close_reaps_owned_group_and_spares_unrelated_cli(tmp_path):
    home, cli_home, install = tmp_path / "home", tmp_path / "cli-home", tmp_path / "install"
    install.mkdir()
    worker = make_worker(
        install,
        "descendant = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "(state / 'descendant.pid').write_text(str(descendant.pid)); time.sleep(60)",
    )
    unrelated = subprocess.Popen(
        [str(worker), "--token", "iact_cli", "--home", str(cli_home), "--install", str(install)],
        start_new_session=True,
    )
    owner = control.ActionController(home, install)
    try:
        wait_for(cli_home / ".local/state/openhtpc/media/worker-ready")
        assert control.request_action(home, "iact_owned")
        owner.poll()
        child = owner.child
        wait_for(home / ".local/state/openhtpc/media/worker-ready")
        descendant_path = home / ".local/state/openhtpc/media/descendant.pid"
        wait_for(descendant_path)
        descendant_pid = int(descendant_path.read_text())
        owner.close()
        assert child.returncode == -signal.SIGTERM
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        assert not control.process_group_has_live_members(child.pid)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant_pid, 0)
        assert unrelated.poll() is None
        status = json.loads(control.status_path(home).read_text())
        assert status["state"] == "FAILED" and status["reason"] == "SESSION_STOPPED"
        assert status["terminated_signal"] == signal.SIGTERM
    finally:
        owner.close()
        try:
            os.killpg(unrelated.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        unrelated.wait(timeout=2)


def test_action_lock_is_busy_for_owned_child_lifetime(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    make_worker(install)
    owner = control.ActionController(home, install)
    try:
        assert control.request_action(home, "iact_lock")
        owner.poll()
        wait_for(home / ".local/state/openhtpc/media/worker-ready")
        assert control.action_running(home)
        with control.lock_path(home).open("a+b") as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.close(owner.lock_fd)
        owner.lock_fd = None
        assert control.action_running(home)
    finally:
        owner.close()
    assert not control.action_running(home)


def test_resolver_commands_preserve_p3a_boundaries(monkeypatch):
    ui = load("p3a_match_ui", "openhtpc-media-match-ui")
    candidate = {"id": 42, "title": "Candidate", "year": 2020, "status": "PENDING"}
    monkeypatch.setattr(ui, "get_ui_candidates", lambda *args: [candidate])
    monkeypatch.setattr(ui, "is_work_same", lambda *args: False)

    def render(state):
        monkeypatch.setattr(ui, "get_status", lambda *args: {
            "candidate_set_revision": "revision",
            "identification_state": state,
            "work_id": 7 if state != "UNMATCHED" else None,
            "work": {"title": "Current", "year": 2010},
        })
        with sqlite3.connect(":memory:") as db:
            sections = ui.build_resolver_menu_sections(
                Path("/home/test"), Path("/install"), db, 1,
                "MEDIA_R12345678", "generation", {}, Path("/icon.png"),
            )
        return "\n".join(sections)

    accept = render("UNMATCHED")
    replace = render("USER_MATCHED")
    request = ":applyback $HOME/.local/lib/openhtpc/openhtpc-media-action-request iact_generation_12345678_42"
    assert request in accept and request in replace
    assert "openhtpc-media-enrich.py" not in accept + replace
    assert ":applyback $HOME/.local/lib/openhtpc/openhtpc-media-match-ui dispatch iact_generation_12345678_rej" in accept
    manual = ":applyback $HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui 1"
    assert manual in accept and manual in replace


def test_home_controller_and_deployment_lists_include_p3a_files():
    home_source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    assert 'load("media_action_control", install / "openhtpc-media-action-control.py")' in home_source
    assert "media_action_control.ActionController(home, install)" in home_source
    assert "atexit.register(action_controller.close)" in home_source
    assert "action_controller.poll()" in home_source
    assert "action_controller.close()" in home_source
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    managed = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
    for filename in ("openhtpc-media-action-control.py", "openhtpc-media-action-request"):
        assert installer.count(filename) == 1
        assert managed.count(filename) == 1


def test_direct_enrich_token_parser_path_remains_supported(monkeypatch, tmp_path):
    enrich = load("p3a_direct_enrich", "openhtpc-media-enrich.py")
    seen = {}

    def direct(**kwargs):
        seen.update(kwargs)
        return 23

    monkeypatch.setattr(enrich, "enrich_action_token", direct)
    assert enrich._main([
        "--token", "iact_direct", "--home", str(tmp_path), "--install", str(PAYLOAD)
    ]) == 23
    assert seen["token"] == "iact_direct"
    assert seen["home"] == tmp_path.resolve()
    assert seen["install"] == PAYLOAD.resolve()
