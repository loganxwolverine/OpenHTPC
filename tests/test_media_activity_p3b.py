#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
FLEX = ROOT / "vendor/flex-launcher/src"


def load(name: str, filename: str):
    path = PAYLOAD / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


activity = load("p3b_activity", "openhtpc-media-activity.py")
session = load("p3b_session", "openhtpc-session-engine.py")


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds: float):
        self.value += seconds


def media_dir(home: Path) -> Path:
    target = home / ".local/state/openhtpc/media"
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_status(home: Path, kind: str, state: str, *, started: str, finished=None, pid=111, operation=None, summary=None):
    name = "library-update-status.json" if kind == "library" else "media-action-status.json"
    value = {
        "state": state,
        "started_at": started,
        "finished_at": finished,
        "pid": pid,
        "exit_code": 0 if state == "SUCCESS" else (1 if state == "FAILED" else None),
        "origin": "UI",
    }
    if operation is not None:
        value["operation_id"] = operation
    if summary is not None:
        value["summary"] = summary
    path = media_dir(home) / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@contextmanager
def hold_lock(home: Path, kind: str):
    name = "library-update.lock" if kind == "library" else "media-action.lock"
    path = media_dir(home) / name
    stream = path.open("a+b")
    fcntl.flock(stream, fcntl.LOCK_EX)
    try:
        yield stream
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def live(home: Path):
    path = activity.state_path(home)
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3
    return rows, path


def test_startup_private_idle_does_not_replay_stale_final(tmp_path):
    home = tmp_path / "home"
    write_status(home, "library", "SUCCESS", started="2026-09-22T10:00:00+00:00",
                 finished="2026-09-22T10:00:03+00:00", pid=101)
    write_status(home, "action", "FAILED", started="2026-09-22T10:01:00+00:00",
                 finished="2026-09-22T10:01:04+00:00", pid=102, operation="old-action")
    pub = activity.ActivityPublisher(home)
    rows, path = live(home)
    assert rows[:2] == ["IDLE", ""]
    assert rows[2] == "1"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    pub.poll()
    assert live(home)[0] == rows


def test_library_running_requires_real_lock_and_maps_exact_message(tmp_path):
    home = tmp_path / "home"
    pub = activity.ActivityPublisher(home)
    write_status(home, "library", "RUNNING", started="2026-09-22T11:00:00+00:00", pid=201)
    pub.poll()
    assert live(home)[0][0] == "IDLE"
    with hold_lock(home, "library"):
        pub.poll()
        assert live(home)[0][:2] == ["RUNNING", "Médiathèque · mise à jour en cours…"]


def test_action_running_requires_real_lock_and_maps_exact_message(tmp_path):
    home = tmp_path / "home"
    pub = activity.ActivityPublisher(home)
    write_status(home, "action", "RUNNING", started="2026-09-22T11:00:00+00:00",
                 pid=202, operation="action-new")
    pub.poll()
    assert live(home)[0][0] == "IDLE"
    with hold_lock(home, "action"):
        pub.poll()
        assert live(home)[0][:2] == ["RUNNING", "Fiche du film · mise à jour en cours…"]


def test_newest_running_wins_and_running_overrides_pending_final(tmp_path):
    home = tmp_path / "home"
    clock = FakeClock()
    pub = activity.ActivityPublisher(home, clock=clock)
    write_status(home, "action", "SUCCESS", started="2026-09-22T11:00:00+00:00",
                 finished="2026-09-22T11:00:02+00:00", pid=210, operation="done")
    pub.poll()
    assert live(home)[0][0] == "SUCCESS"

    write_status(home, "library", "RUNNING", started="2026-09-22T11:01:00+00:00", pid=211)
    write_status(home, "action", "RUNNING", started="2026-09-22T11:02:00+00:00",
                 pid=212, operation="running-newer")
    with ExitStack() as stack:
        stack.enter_context(hold_lock(home, "library"))
        stack.enter_context(hold_lock(home, "action"))
        pub.poll()
        assert live(home)[0][:2] == ["RUNNING", "Fiche du film · mise à jour en cours…"]


def test_success_ttl_is_three_seconds_then_idle(tmp_path):
    home = tmp_path / "home"
    clock = FakeClock()
    pub = activity.ActivityPublisher(home, clock=clock)
    write_status(home, "library", "SUCCESS", started="2026-09-22T12:00:00+00:00",
                 finished="2026-09-22T12:00:04+00:00", pid=301)
    pub.poll()
    assert live(home)[0][:2] == ["SUCCESS", "Médiathèque · mise à jour terminée"]
    clock.advance(2.99); pub.poll()
    assert live(home)[0][0] == "SUCCESS"
    clock.advance(0.01); pub.poll()
    assert live(home)[0][:2] == ["IDLE", ""]


def test_library_success_surfaces_pedagogical_scan_summary(tmp_path):
    home = tmp_path / "home"
    pub = activity.ActivityPublisher(home)
    write_status(
        home, "library", "SUCCESS",
        started="2026-09-25T12:00:00+00:00",
        finished="2026-09-25T12:00:05+00:00",
        pid=303,
        summary={"files_discovered": 150, "still_unmatched": 62},
    )
    pub.poll()
    assert live(home)[0][:2] == [
        "SUCCESS",
        "Médiathèque · 150 médias trouvés · 88 identifiés · 62 à vérifier",
    ]


def test_library_success_invalid_summary_falls_back_to_generic_message(tmp_path):
    home = tmp_path / "home"
    pub = activity.ActivityPublisher(home)
    write_status(
        home, "library", "SUCCESS",
        started="2026-09-25T12:01:00+00:00",
        finished="2026-09-25T12:01:05+00:00",
        pid=304,
        summary={"files_discovered": 2, "still_unmatched": 9},
    )
    pub.poll()
    assert live(home)[0][:2] == ["SUCCESS", "Médiathèque · mise à jour terminée"]


def test_failed_ttl_is_six_seconds_then_idle(tmp_path):
    home = tmp_path / "home"
    clock = FakeClock()
    pub = activity.ActivityPublisher(home, clock=clock)
    write_status(home, "action", "FAILED", started="2026-09-22T12:00:00+00:00",
                 finished="2026-09-22T12:00:05+00:00", pid=302, operation="failed")
    pub.poll()
    assert live(home)[0][:2] == ["FAILED", "Fiche du film · échec de la mise à jour"]
    clock.advance(5.99); pub.poll()
    assert live(home)[0][0] == "FAILED"
    clock.advance(0.01); pub.poll()
    assert live(home)[0][:2] == ["IDLE", ""]


def test_live_file_atomic_private_three_lines_and_serial_only_on_visible_change(tmp_path):
    home = tmp_path / "home"
    pub = activity.ActivityPublisher(home)
    rows, path = live(home)
    inode = path.stat().st_ino
    pub.poll()
    rows2, path2 = live(home)
    assert rows2 == rows and path2.stat().st_ino == inode

    write_status(home, "action", "SUCCESS", started="2026-09-22T13:00:00+00:00",
                 finished="2026-09-22T13:00:03+00:00", pid=401, operation="secret-token-title-path")
    pub.poll()
    rows3, path3 = live(home)
    assert int(rows3[2]) == int(rows[2]) + 1
    text = path3.read_text(encoding="utf-8")
    assert "secret-token-title-path" not in text
    assert "/" not in rows3[1]
    assert len(rows3[1].encode("utf-8")) <= activity.MAX_MESSAGE_BYTES
    assert list(path3.parent.glob("activity-state.*")) == []


def test_home_integration_orders_controllers_before_publisher_poll_and_close():
    source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    assert 'media_activity = load("media_activity", install / "openhtpc-media-activity.py")' in source
    assert source.index("update_controller = media_control.UpdateController") < source.index("activity_publisher = media_activity.ActivityPublisher")
    assert source.index("action_controller = media_action_control.ActionController") < source.index("activity_publisher = media_activity.ActivityPublisher")
    loop = source[source.index("while proc.poll() is None"):source.index("activity_publisher.close()")]
    assert loop.index("update_controller.poll()") < loop.index("action_controller.poll()") < loop.index("activity_publisher.poll()")
    tail = source[source.index("activity_publisher.close()"):]
    assert tail.index("activity_publisher.close()") < tail.index("action_controller.close()") < tail.index("update_controller.close()")


def test_generated_flex_config_declares_canonical_live_activity_path(tmp_path):
    home = tmp_path / "home"
    target = home / ".config/openhtpc/flex-v1.ini"
    target.parent.mkdir(parents=True)
    session.write_flex_config(target, home, [], PAYLOAD, media_generation="p3b-test")
    text = target.read_text(encoding="utf-8")
    assert f"LiveActivityState={home}/.local/state/openhtpc/media/activity-state" in text
    assert "LiveOpticalState=" in text


def test_flex_config_watcher_and_render_contract():
    header = (FLEX / "launcher.h").read_text(encoding="utf-8")
    util = (FLEX / "util.c").read_text(encoding="utf-8")
    source = (FLEX / "launcher.c").read_text(encoding="utf-8")
    assert "char *live_activity_state;" in header
    assert 'MATCH(name, "LiveActivityState")' in util
    assert "free(config.live_activity_state);" in source

    start = source.index("static void refresh_live_activity_state(void)\n{")
    end = source.index("static void draw_activity_overlay(void)", start)
    watcher = source[start:end]
    for token in ("info.st_ino", "info.st_mtime", "info.st_size", "render_text_texture",
                  "activity_info.max_width = (geo.screen_width * 42) / 100",
                  "activity_info.oversize_mode = OVERSIZE_SHRINK",
                  "clear_live_activity_overlay()"):
        assert token in watcher
    for forbidden in ("tracked_", "current_menu =", "current_entry =", "reload_menu_section(", "reload_media_menu_sections("):
        assert forbidden not in watcher


def test_flex_draws_banner_after_entries_before_screensaver_without_input_hooks():
    source = (FLEX / "launcher.c").read_text(encoding="utf-8")
    draw_start = source.index("static void draw_screen()")
    draw_end = source.index("// A function to execute the user's command", draw_start)
    draw = source[draw_start:draw_end]
    assert draw.index("entry = entry-> next;") < draw.index("draw_activity_overlay();") < draw.index("// Draw screensaver")
    overlay_start = source.index("static void draw_activity_overlay(void)\n{")
    overlay_end = source.index("/* The non-graphical metadata worker", overlay_start)
    overlay = source[overlay_start:overlay_end]
    assert "fill_rounded_rect" in overlay and "SDL_RenderCopy(renderer, activity_texture" in overlay
    for forbidden in ("tracked_", "handle_keypress", "execute_command(", "current_menu =", "current_entry ="):
        assert forbidden not in overlay
    loop_anchor = source.index('log_debug("Begin program loop")')
    assert source.index("refresh_live_optical_state();", loop_anchor) < source.index("refresh_live_activity_state();", loop_anchor)


def test_activity_module_is_product_managed_file():
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    managed = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
    assert "openhtpc-media-activity.py" in installer
    assert managed.count("openhtpc-media-activity.py") == 1
