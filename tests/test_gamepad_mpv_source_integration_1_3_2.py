# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic production integration checks for the physically qualified gamepad."""
from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
MAP = PAYLOAD / "assets/mpv/gamepad-input.conf"


def bindings():
    lines = [x.strip() for x in MAP.read_text().splitlines()]
    entries = [line.split(None, 1) for line in lines if line.startswith("GAMEPAD_")]
    assert len(entries) == len({key for key, _ in entries}) == 18
    return dict(entries)


def test_controller_actions_and_persistent_stats_page_switching():
    b = bindings()
    expected = {
        "GAMEPAD_BACK": "script-binding stats/display-stats-toggle",
        "GAMEPAD_ACTION_LEFT": "script-binding stats/display-page-1",
        "GAMEPAD_ACTION_UP": "script-binding stats/display-page-2",
        "GAMEPAD_RIGHT_STICK": "script-binding stats/display-page-3",
        "GAMEPAD_ACTION_DOWN": "cycle pause",
        "GAMEPAD_ACTION_RIGHT": "quit",
        "GAMEPAD_START": "cycle pause",
        "GAMEPAD_MENU": "show-progress",
        "GAMEPAD_DPAD_LEFT": "seek -10",
        "GAMEPAD_DPAD_RIGHT": "seek 10",
        "GAMEPAD_DPAD_UP": "add volume 5",
        "GAMEPAD_DPAD_DOWN": "add volume -5",
        "GAMEPAD_LEFT_STICK_LEFT": "seek -5",
        "GAMEPAD_LEFT_STICK_RIGHT": "seek 5",
        "GAMEPAD_LEFT_STICK_UP": "add volume 5",
        "GAMEPAD_LEFT_STICK_DOWN": "add volume -5",
        "GAMEPAD_LEFT_SHOULDER": "seek -60",
        "GAMEPAD_RIGHT_SHOULDER": "seek 60",
    }
    assert b == expected
    assert all("page-" not in action or not action.endswith("-toggle") for action in b.values())


def test_flex_main_menu_gamepad_mapping():
    main = (PAYLOAD / "openhtpc-session-engine.py").read_text()
    section = main.split("[Gamepad]", 1)[1].split("[OPENHTPC]", 1)[0]
    assert "Enabled=true" in section and "DeviceIndex=-1" in section
    for entry in ("ButtonA=:select", "ButtonB=:back", "ButtonDPadLeft=:left",
                  "ButtonDPadRight=:right", "ButtonDPadUp=:left", "ButtonDPadDown=:right"):
        assert entry in section
    # Flex v1's menu layout is horizontal, so vertical inputs follow its tested fallback.
    assert "LStickY-=:left" in section and "LStickY+=:right" in section


def test_flex_media_browser_gamepad_generated_hermetically(tmp_path, monkeypatch):
    path = PAYLOAD / "openhtpc-media-browser.py"
    loader = importlib.machinery.SourceFileLoader("gamepad_media_browser_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)

    class FakeTheme:
        def background_block(self, *args):
            return "BackgroundColor=#000000"
        def title_block(self, *args):
            return "TitleColor=#FFFFFF"
        def highlight_block(self):
            return "HighlightColor=#FFFFFF"

    monkeypatch.setattr(mod, "load_theme", lambda _: FakeTheme())
    target = tmp_path / "flex-menu.ini"
    scale = {"icon": 64, "clock": 24, "title": 28, "padding": 8}
    mod.write_menu(target, tmp_path, None, [], scale)
    text = target.read_text()
    section = text.split("[Gamepad]", 1)[1].split("[Médias]", 1)[0]
    assert "Enabled=true" in section
    for line in ("LStickX-=:left", "LStickX+=:right",
                 "LStickY-=:left", "LStickY+=:right",
                 "ButtonA=:select", "ButtonB=:back",
                 "ButtonDPadUp=:left", "ButtonDPadDown=:right"):
        assert line in section
    assert "[Médias]" in text


def test_local_mpv_dispatch_gamepad_and_missing_map_fallback(tmp_path):
    tree = ast.parse((PAYLOAD / "openhtpc-play").read_text())
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    index = next(i for i, n in enumerate(main.body)
                 if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "gamepad_mapping" for t in n.targets))
    statements = main.body[index:index + 2]
    assert isinstance(statements[1], ast.If)
    snippet = compile(ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[])),
                      "<gamepad-args>", "exec")

    def run():
        cmd = ["mpv", "--no-config", "--include=/runtime", "--fullscreen=yes", "--", "/film.mkv"]
        scope = {"pathlib": pathlib, "install": tmp_path, "command": cmd}
        exec(snippet, scope)
        return cmd

    assert run() == ["mpv", "--no-config", "--include=/runtime", "--fullscreen=yes", "--", "/film.mkv"]
    mapped = tmp_path / "assets/mpv/gamepad-input.conf"
    mapped.parent.mkdir(parents=True)
    mapped.write_text(MAP.read_text())
    cmd = run()
    assert cmd[3:5] == ["--input-gamepad=yes", f"--input-conf={mapped}"]
    assert cmd[-2:] == ["--", "/film.mkv"]
    assert cmd.count("--input-gamepad=yes") == 1


def test_dvd_gamepad_args_are_optional_and_bounded(tmp_path):
    text = (PAYLOAD / "openhtpc-play-dvd").read_text()
    block = text.split("# SDL gamepad input belongs", 1)[1].split("refresh_runner=()", 1)[0]
    block = "# SDL gamepad input belongs" + block
    assert block.count("gamepad_args=(--input-gamepad=yes") == 1
    assert '"${gamepad_args[@]}" --log-file="$dvd_attempt"' in text
    assert "dvd://longest" in text
    assert "flock -n 9" in text and 'return_ui' in text

    def run():
        result = subprocess.run(
            ["bash", "-c", 'set -eu\nINSTALL="$1"\n' + block
             + '\nprintf "%s\\n" "${gamepad_args[@]}"', "test", str(tmp_path)],
            capture_output=True, text=True, check=True,
        )
        return [line for line in result.stdout.splitlines() if line]

    assert run() == []
    mapped = tmp_path / "assets/mpv/gamepad-input.conf"
    mapped.parent.mkdir(parents=True)
    mapped.write_text(MAP.read_text())
    assert run() == ["--input-gamepad=yes", f"--input-conf={mapped}"]


def test_installer_and_updater_own_static_mpv_map():
    path = "assets/mpv/gamepad-input.conf"
    managed = (PAYLOAD / "managed-files.txt").read_text().splitlines()
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
    assert managed.count(path) == 1
    assert f'install -Dm 0644 "$SCRIPT_DIR/{path}" "$INSTALL_DIR/{path}"' in installer
    assert f'[[ -r $SCRIPT_DIR/{path} ]]' in installer
    assert '"$ROOT/install.sh" "$@"' in (ROOT / "update.sh").read_text()
    assert MAP.is_file() and MAP.stat().st_size > 200


def test_no_machine_qa_paths_or_global_redispatch():
    combined = "\n".join((PAYLOAD / x).read_text() for x in
                         ("openhtpc-play", "openhtpc-play-dvd", "openhtpc-media-browser.py",
                          "openhtpc-session-engine.py"))
    assert "gamepad-qa-20261020" not in combined
    assert "192.168.1.47" not in combined
    assert "--input-ipc-server" not in (PAYLOAD / "openhtpc-play-dvd").read_text()
    assert "killall" not in (PAYLOAD / "openhtpc-play-dvd").read_text()
