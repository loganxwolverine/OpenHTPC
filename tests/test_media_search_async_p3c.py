#!/usr/bin/env python3
"""Hermetic RC8 P3C asynchronous manual TMDb search checks."""

from __future__ import annotations

from contextlib import contextmanager
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
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, filename: str):
    path = PAYLOAD / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


control = load("p3c_search_control", "openhtpc-media-search-control.py")
manual = load("p3c_manual_search_ui", "openhtpc-media-manual-search-ui")
activity = load("p3c_activity", "openhtpc-media-activity.py")


def make_worker(install: Path, body: str = "time.sleep(60)") -> Path:
    worker = install / "openhtpc-media-manual-search-ui"
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


def wait_for(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def finish(owner, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while owner.child is not None and time.monotonic() < deadline:
        owner.poll()
        time.sleep(0.01)
    assert owner.child is None


def tiny_db(home: Path) -> Path:
    path = home / ".local/share/openhtpc/media/media.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(path).close()
    return path


def foreground_search(home: Path, install: Path, accepted: bool, monkeypatch):
    db = tiny_db(home)
    submitted = mock.MagicMock(return_value=accepted)
    fake_control = type("Control", (), {"request_search": staticmethod(submitted)})
    monkeypatch.setattr(manual, "get_prefill_hints", lambda db, mv: ("Initial", "2001"))
    monkeypatch.setattr(manual, "invoke_text_entry", mock.MagicMock(side_effect=[
        {"ok": True, "cancelled": False, "text": "Query Film"},
        {"ok": True, "cancelled": False, "text": "2002"},
    ]))
    monkeypatch.setattr(manual, "show_confirmation_window", lambda **kw: "SEARCH")
    monkeypatch.setattr(manual, "_load_search_control", lambda install: fake_control)
    monkeypatch.setattr(manual, "_load_media_match", lambda *a, **k: (_ for _ in ()).throw(AssertionError("foreground provider call")))
    monkeypatch.setattr(manual, "_load_media_match_ui", lambda *a, **k: (_ for _ in ()).throw(AssertionError("foreground regeneration")))
    started = time.monotonic()
    rc = manual.orchestrate_manual_search(
        media_version_id=7, home=home, install=install, custom_db_path=db
    )
    return rc, time.monotonic() - started, submitted


def test_request_validation_and_absent_controller_is_fast(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = time.monotonic()
    assert not control.request_search(home, 1, "Valid Film", 2020)
    assert time.monotonic() - started < 0.5
    assert control.normalize_request(1, "  Valid Film  ", 2020) == {
        "media_version_id": 1, "title": "Valid Film", "year": 2020
    }


def test_valid_request_launches_exact_one_worker_and_drops_queued_duplicate(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    worker = make_worker(install)
    real_popen = subprocess.Popen
    calls = []

    def recording(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(control.subprocess, "Popen", recording)
    owner = control.SearchController(home, install)
    try:
        assert control.request_search(home, 11, "Film One", 2021)
        owner.poll()
        wait_for(home / ".local/state/openhtpc/media/worker-ready")
        payload = json.dumps({"media_version_id": 12, "title": "Film Two", "year": 2022}).encode() + b"\n"
        fd = os.open(control.request_path(home), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        owner.poll()
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == [
            str(worker), "--worker-search", "--media-version-id", "11",
            "--title", "Film One", "--year", "2021",
            "--home", str(home), "--install-dir", str(install),
        ]
        assert "shell" not in kwargs
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.STDOUT
        assert kwargs["start_new_session"] is True
        assert kwargs["pass_fds"] == (owner.lock_fd,)
        os.killpg(owner.child.pid, signal.SIGTERM)
        finish(owner)
        owner.poll()
        assert len(calls) == 1
    finally:
        owner.close()


def test_invalid_requests_never_launch(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    owner = control.SearchController(home, install)
    launches = []
    monkeypatch.setattr(control.subprocess, "Popen", lambda *a, **k: launches.append((a, k)))
    invalid = [
        (0, "Film", 2020), (1, "", 2020), (1, "x" * 256, 2020),
        (1, "Bad\nFilm", 2020), (1, "Bad\tFilm", 2020),
        (1, "Film", 1869), (1, "Film", 2101), (1, "Film", "2020"),
    ]
    try:
        for args in invalid:
            assert not control.request_search(home, *args)
        fd = os.open(control.request_path(home), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"not-json\n{}\n")
        finally:
            os.close(fd)
        owner.poll()
        assert launches == []
    finally:
        owner.close()


def test_inherited_lock_stays_busy_for_worker_lifetime(tmp_path):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    make_worker(install)
    owner = control.SearchController(home, install)
    try:
        assert control.request_search(home, 2, "Lock Film", None)
        owner.poll()
        wait_for(home / ".local/state/openhtpc/media/worker-ready")
        assert control.search_running(home)
        os.close(owner.lock_fd)
        owner.lock_fd = None
        assert control.search_running(home)
    finally:
        owner.close()
    assert not control.search_running(home)


@pytest.mark.parametrize(("exit_code", "expected"), [(0, "SUCCESS"), (7, "FAILED")])
def test_status_running_to_final_is_private_and_log_bounded(tmp_path, exit_code, expected):
    home, install = tmp_path / "home", tmp_path / "install"
    install.mkdir()
    make_worker(
        install,
        f"sys.stdout.write('x' * 300000); sys.stdout.flush(); time.sleep(0.1); raise SystemExit({exit_code})",
    )
    owner = control.SearchController(home, install)
    try:
        assert control.request_search(home, 3, "Secret Film Title", 1999)
        owner.poll()
        running = json.loads(control.status_path(home).read_text())
        text = json.dumps(running)
        assert running["state"] == "RUNNING" and running["origin"] == "UI"
        assert running["pid"] == owner.child.pid
        assert "Secret Film Title" not in text and "1999" not in text
        assert control.status_path(home).stat().st_mode & 0o777 == 0o600
        assert control.log_path(home).stat().st_mode & 0o777 == 0o600
        finish(owner)
        final = json.loads(control.status_path(home).read_text())
        assert final["state"] == expected and final["exit_code"] == exit_code
        assert final["finished_at"]
        assert "Secret Film Title" not in json.dumps(final)
        assert control.log_path(home).stat().st_size == control.MAX_LOG_BYTES
        assert list(control.status_path(home).parent.glob("media-search-status.json.*")) == []
    finally:
        owner.close()


def test_close_reaps_owned_group_and_spares_unrelated_worker(tmp_path):
    home, other, install = tmp_path / "home", tmp_path / "other", tmp_path / "install"
    install.mkdir()
    worker = make_worker(
        install,
        "desc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "(state / 'descendant.pid').write_text(str(desc.pid)); time.sleep(60)",
    )
    unrelated = subprocess.Popen(
        [str(worker), "--worker-search", "--media-version-id", "99", "--title", "CLI",
         "--home", str(other), "--install-dir", str(install)],
        start_new_session=True,
    )
    owner = control.SearchController(home, install)
    try:
        wait_for(other / ".local/state/openhtpc/media/worker-ready")
        assert control.request_search(home, 4, "Owned Film", 2020)
        owner.poll()
        child = owner.child
        wait_for(home / ".local/state/openhtpc/media/worker-ready")
        descendant_path = home / ".local/state/openhtpc/media/descendant.pid"
        wait_for(descendant_path)
        descendant = int(descendant_path.read_text())
        owner.close()
        assert child.returncode == -signal.SIGTERM
        assert not control.process_group_has_live_members(child.pid)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant, 0)
        assert unrelated.poll() is None
        final = json.loads(control.status_path(home).read_text())
        assert final["state"] == "FAILED" and final["reason"] == "SESSION_STOPPED"
    finally:
        owner.close()
        try:
            os.killpg(unrelated.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        unrelated.wait(timeout=2)


def test_foreground_search_submits_and_returns_without_provider_or_regeneration(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    home.mkdir(); install.mkdir()
    rc, elapsed, submitted = foreground_search(home, install, True, monkeypatch)
    assert rc == 0 and elapsed < 0.5
    submitted.assert_called_once_with(home, 7, "Query Film", 2002)


def test_submission_failure_never_falls_back_to_sync_provider(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    home.mkdir(); install.mkdir()
    rc, elapsed, submitted = foreground_search(home, install, False, monkeypatch)
    assert rc != 0 and elapsed < 0.5
    assert submitted.call_count == 1


def test_worker_executes_exactly_one_search_and_regenerates_once(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    home.mkdir(); install.mkdir()
    db = tiny_db(home)
    search = mock.MagicMock(return_value={"ok": True, "status": "OK", "revision": "r1"})
    ui = mock.MagicMock()
    monkeypatch.setattr(manual, "_load_media_match_ui", lambda install: ui)
    rc = manual.execute_manual_search(
        media_version_id=8, title="Worker Film", year=2024, home=home, install=install,
        db_path=db, search_fn=search,
    )
    assert rc == 0
    assert search.call_count == 1
    ui._regenerate_ui.assert_called_once_with(home, install)


def test_worker_provider_failure_is_nonzero_without_regeneration_or_popup(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    home.mkdir(); install.mkdir()
    db = tiny_db(home)
    search = mock.MagicMock(return_value={"ok": False, "error": "TMDB_TIMEOUT"})
    ui = mock.MagicMock()
    monkeypatch.setattr(manual, "_load_media_match_ui", lambda install: ui)
    monkeypatch.setattr(manual, "show_error_window", lambda **kw: (_ for _ in ()).throw(AssertionError("worker popup")))
    rc = manual.execute_manual_search(
        media_version_id=9, title="Failure Film", year=None, home=home, install=install,
        db_path=db, search_fn=search,
    )
    assert rc != 0
    assert search.call_count == 1
    assert ui._regenerate_ui.call_count == 0


def test_worker_no_results_is_success_and_regenerates_once(tmp_path, monkeypatch):
    home, install = tmp_path / "home", tmp_path / "install"
    home.mkdir(); install.mkdir()
    db = tiny_db(home)
    search = mock.MagicMock(return_value={"ok": True, "status": "OK_NO_RESULTS", "revision": "r0"})
    ui = mock.MagicMock()
    monkeypatch.setattr(manual, "_load_media_match_ui", lambda install: ui)
    assert manual.execute_manual_search(
        media_version_id=10, title="Nothing", year=None, home=home, install=install,
        db_path=db, search_fn=search,
    ) == 0
    assert search.call_count == 1
    assert ui._regenerate_ui.call_count == 1


def test_worker_cli_bypasses_qt_and_calls_worker_function_once(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(manual, "execute_manual_search", lambda **kw: seen.update(kw) or 17)
    monkeypatch.setattr(manual, "invoke_text_entry", lambda **kw: (_ for _ in ()).throw(AssertionError("Qt path")))
    rc = manual.main([
        "--worker-search", "--media-version-id", "12", "--title", "CLI Worker",
        "--year", "2025", "--home", str(tmp_path), "--install-dir", str(PAYLOAD),
    ])
    assert rc == 17
    assert seen["media_version_id"] == 12 and seen["title"] == "CLI Worker" and seen["year"] == 2025


def test_home_integration_poll_and_close_order():
    source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    assert 'load("media_search_control", install / "openhtpc-media-search-control.py")' in source
    assert source.index("action_controller = media_action_control.ActionController") < source.index("search_controller = media_search_control.SearchController") < source.index("activity_publisher = media_activity.ActivityPublisher")
    loop = source[source.index("while proc.poll() is None"):source.index("activity_publisher.close()")]
    assert loop.index("update_controller.poll()") < loop.index("action_controller.poll()") < loop.index("search_controller.poll()") < loop.index("activity_publisher.poll()")
    tail = source[source.index("activity_publisher.close()"):]
    assert tail.index("activity_publisher.close()") < tail.index("search_controller.close()") < tail.index("action_controller.close()") < tail.index("update_controller.close()")


class FakeClock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def advance(self, amount):
        self.value += amount


@contextmanager
def held_search_lock(home: Path):
    path = home / ".local/state/openhtpc/media/media-search.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    fcntl.flock(stream, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def write_search_status(home: Path, state: str, *, started: str, finished=None, pid=77, op="search-op"):
    path = home / ".local/state/openhtpc/media/media-search-status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "state": state, "started_at": started, "finished_at": finished, "pid": pid,
        "exit_code": 0 if state == "SUCCESS" else (1 if state == "FAILED" else None),
        "origin": "UI", "operation_id": op,
    }))
    return path


def live_state(home: Path):
    return (home / ".local/state/openhtpc/media/activity-state").read_text(encoding="utf-8").splitlines()


def test_activity_search_messages_and_ttls_without_library_action_regression(tmp_path):
    home = tmp_path / "home"
    clock = FakeClock()
    pub = activity.ActivityPublisher(home, clock=clock)
    write_search_status(home, "RUNNING", started="2026-09-22T14:00:00+00:00")
    with held_search_lock(home):
        pub.poll()
        assert live_state(home)[:2] == ["RUNNING", "Recherche TMDb · en cours…"]
    write_search_status(home, "SUCCESS", started="2026-09-22T14:00:00+00:00",
                        finished="2026-09-22T14:00:05+00:00")
    pub.poll()
    assert live_state(home)[:2] == ["SUCCESS", "Recherche TMDb · terminée"]
    clock.advance(3.0); pub.poll()
    assert live_state(home)[:2] == ["IDLE", ""]

    write_search_status(home, "FAILED", started="2026-09-22T14:01:00+00:00",
                        finished="2026-09-22T14:01:05+00:00", op="search-fail")
    pub.poll()
    assert live_state(home)[:2] == ["FAILED", "Recherche TMDb · échec de la recherche"]
    clock.advance(5.99); pub.poll()
    assert live_state(home)[0] == "FAILED"
    clock.advance(0.01); pub.poll()
    assert live_state(home)[0] == "IDLE"


def test_resolver_command_stays_same_and_deployment_lists_include_search_controller():
    ui = (PAYLOAD / "openhtpc-media-match-ui").read_text(encoding="utf-8")
    assert 'ms_launch_cmd = f":applyback {search_helper_path} {media_version_id}"' in ui
    assert 'search_helper_path = "$HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui"' in ui
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    managed = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
    assert installer.count("openhtpc-media-search-control.py") == 1
    assert managed.count("openhtpc-media-search-control.py") == 1
