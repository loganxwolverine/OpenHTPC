#!/usr/bin/env python3
"""Hermetic unit test suite for OpenHTPC Generic Living-Room Text Entry (DEV5C3B2).

Validates all 22 required test points for the generic text-entry component.
Runs 100% offline and headless.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

PAYLOAD_DIR = Path(__file__).resolve().parent.parent / "payload"
TEXT_ENTRY_PATH = PAYLOAD_DIR / "openhtpc-text-entry.py"


def _load_text_entry_module():
    spec = importlib.util.spec_from_file_location("openhtpc_text_entry", str(TEXT_ENTRY_PATH))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def text_entry_mod():
    return _load_text_entry_module()


# 1. INITIAL TEXT
def test_01_initial_text(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Spirited Away")
    assert m.text == "Spirited Away"
    assert m.row == 0
    assert m.col == 0
    assert m.current_key_label == "A"
    assert not m.submitted
    assert not m.cancelled


# 2. MAX LENGTH
def test_02_max_length(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="ABC", max_length=5)
    m.append_char("D")
    assert m.text == "ABCD"
    m.append_char("E")
    assert m.text == "ABCDE"
    # Bound reached: cannot exceed max_length
    m.append_char("F")
    assert m.text == "ABCDE"
    assert len(m.text) == 5


# 3. CHARACTER APPEND
def test_03_character_append(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="")
    m.append_char("H")
    m.append_char("E")
    m.append_char("L")
    m.append_char("L")
    m.append_char("O")
    assert m.text == "HELLO"


# 4. PHYSICAL KEYBOARD PRINTABLE INPUT
def test_04_physical_keyboard_printable_input(text_entry_mod):
    # Simulated key presses via PySide6 QKeyEvent
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.argv[0], "-platform", "offscreen"])
    m = text_entry_mod.TextEntryModel(initial_text="")
    win_cls = text_entry_mod.create_text_entry_window_class()
    win = win_cls(m)

    # Send physical key events 'T', 'e', 's', 't'
    for ch in "Test":
        event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            0,
            QtCore.Qt.KeyboardModifier.NoModifier,
            ch,
        )
        win.keyPressEvent(event)

    assert m.text == "Test"
    win.close()


# 5. ARROWS
def test_05_arrows_navigation(text_entry_mod):
    m = text_entry_mod.TextEntryModel()
    assert m.current_key_label == "A"

    m.move_right()
    assert m.current_key_label == "B"
    m.move_left()
    assert m.current_key_label == "A"

    m.move_down()
    assert m.current_key_label == "G"
    m.move_up()
    assert m.current_key_label == "A"

    # Top clamp
    m.move_up()
    assert m.row == 0
    assert m.current_key_label == "A"


# 6. ROW TRANSITIONS
def test_06_row_transitions(text_entry_mod):
    m = text_entry_mod.TextEntryModel()
    # Move to row 5 (last grid row: 4, 5, 6, 7, 8, 9)
    for _ in range(5):
        m.move_down()
    assert m.row == 5
    assert m.col == 0
    assert m.current_key_label == "4"

    # Move right to col 5 ("9")
    for _ in range(5):
        m.move_right()
    assert m.col == 5
    assert m.current_key_label == "9"

    # Transition to action row: col clamped from 5 to 4 (len(action_row)-1)
    m.move_down()
    assert m.row == text_entry_mod.ACTION_ROW_INDEX
    assert m.col == 4
    assert m.current_key_label == "ANNULER"

    # Transition back up to row 5: row becomes 5, col clamped to min(4, 5) = 4 ("8")
    m.move_up()
    assert m.row == 5
    assert m.col == 4
    assert m.current_key_label == "8"


# 7. HORIZONTAL WRAP
def test_07_horizontal_wrap(text_entry_mod):
    m = text_entry_mod.TextEntryModel()
    # Row 0 col 0 is "A". Moving left wraps to col 5 ("F")
    m.move_left()
    assert m.col == 5
    assert m.current_key_label == "F"

    # Moving right wraps back to col 0 ("A")
    m.move_right()
    assert m.col == 0
    assert m.current_key_label == "A"

    # Action row horizontal wrap
    for _ in range(6):
        m.move_down()
    assert m.row == text_entry_mod.ACTION_ROW_INDEX
    assert m.col == 0
    assert m.current_key_label == "ESPACE"

    # Moving left on action row wraps to last item ("ANNULER")
    m.move_left()
    assert m.col == 4
    assert m.current_key_label == "ANNULER"

    # Moving right wraps back to col 0 ("ESPACE")
    m.move_right()
    assert m.col == 0
    assert m.current_key_label == "ESPACE"


# 8. ENTER
def test_08_enter_activation(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="")
    assert m.current_key_label == "A"
    res = m.activate_current()
    assert res is None
    assert m.text == "A"

    m.move_right()  # "B"
    res = m.activate_current()
    assert res is None
    assert m.text == "AB"


# 9. SPACE
def test_09_space_handling(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Star")
    # Move to action row col 0 ("ESPACE")
    for _ in range(6):
        m.move_down()
    assert m.current_key_label == "ESPACE"
    m.activate_current()
    assert m.text == "Star "

    # Consecutive spaces prevented
    m.activate_current()
    assert m.text == "Star "


# 10. BACKSPACE
def test_10_backspace(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="OpenHTPC")
    m.backspace()
    assert m.text == "OpenHTP"
    m.backspace()
    assert m.text == "OpenHT"


# 11. UNICODE BACKSPACE
def test_11_unicode_backspace(text_entry_mod):
    # French accent test: "Amélie"
    m = text_entry_mod.TextEntryModel(initial_text="Amélie")
    m.backspace()
    assert m.text == "Améli"
    m.backspace()
    assert m.text == "Amél"
    m.backspace()
    assert m.text == "Amé"

    # CJK character test: "千と千尋の神隠し"
    m_cjk = text_entry_mod.TextEntryModel(initial_text="千と千尋")
    m_cjk.backspace()
    assert m_cjk.text == "千と千"
    m_cjk.backspace()
    assert m_cjk.text == "千と"


# 12. CLEAR
def test_12_clear(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Existing Text to Clear")
    # Move to action row col 2 ("VIDER")
    for _ in range(6):
        m.move_down()
    m.move_right()  # EFFACER
    m.move_right()  # VIDER
    assert m.current_key_label == "VIDER"
    m.activate_current()
    assert m.text == ""


# 13. SEARCH/SUBMIT
def test_13_search_submit(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="  Inception  ")
    for _ in range(6):
        m.move_down()
    m.move_right()  # EFFACER
    m.move_right()  # VIDER
    m.move_right()  # RECHERCHER
    assert m.current_key_label == "RECHERCHER"
    res = m.activate_current()
    assert res == {
        "ok": True,
        "cancelled": False,
        "text": "Inception",
    }
    assert m.submitted is True
    assert m.cancelled is False


# 14. CANCEL BUTTON
def test_14_cancel_button(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Spirited Away")
    for _ in range(6):
        m.move_down()
    m.move_left()  # Wraps to ANNULER
    assert m.current_key_label == "ANNULER"
    res = m.activate_current()
    assert res == {
        "ok": False,
        "cancelled": True,
        "text": "Spirited Away",
    }
    assert m.submitted is False
    assert m.cancelled is True


# 15. ESCAPE CANCEL
def test_15_escape_cancel(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Interstellar")
    res = m.cancel()
    assert res == {
        "ok": False,
        "cancelled": True,
        "text": "Interstellar",
    }
    assert m.cancelled is True


# 16. JSON SUBMIT
def test_16_json_submit(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Blade Runner")
    m.submit()
    data = json.loads(m.to_result_json())
    assert data["ok"] is True
    assert data["cancelled"] is False
    assert data["text"] == "Blade Runner"


# 17. JSON CANCEL
def test_17_json_cancel(text_entry_mod):
    m = text_entry_mod.TextEntryModel(initial_text="Dune")
    m.cancel()
    data = json.loads(m.to_result_json())
    assert data["ok"] is False
    assert data["cancelled"] is True
    assert data["text"] == "Dune"


# 18. JSON ESCAPING
def test_18_json_escaping(text_entry_mod):
    tricky_title = 'Film with "Quotes", \\backslashes\\ and /slash/'
    m = text_entry_mod.TextEntryModel(initial_text=tricky_title)
    m.submit()
    raw_json = m.to_result_json()
    data = json.loads(raw_json)
    assert data["text"] == tricky_title


# 19. UNICODE PREFILL
def test_19_unicode_prefill(text_entry_mod):
    unicode_title = "Le Fabuleux Destin d'Amélie Poulain"
    m = text_entry_mod.TextEntryModel(initial_text=unicode_title)
    assert m.text == unicode_title
    m.submit()
    data = json.loads(m.to_result_json())
    assert data["text"] == unicode_title


# 20. MALFORMED ARGS
def test_20_malformed_args():
    res = subprocess.run(
        [sys.executable, str(TEXT_ENTRY_PATH), "--max-length", "-10"],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "ERROR" in res.stderr or "error" in res.stderr


# 21. OFFSCREEN QT STARTUP
def test_21_offscreen_qt_startup(tmp_path):
    out_file = tmp_path / "result.json"
    cmd = [
        sys.executable,
        str(TEXT_ENTRY_PATH),
        "-platform",
        "offscreen",
        "--initial-text",
        "Headless Test",
        "--output",
        str(out_file),
    ]
    # Launch process and immediately send SIGINT / close
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = p.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        p.terminate()
        p.wait()
    # Process initializes PySide6 offscreen without crash (segfault)
    assert p.returncode in (0, -15, 143)


# 22. ZERO MEDIA/TMDB DEPENDENCY IMPORTS
def test_22_zero_media_tmdb_dependency_imports():
    source = TEXT_ENTRY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_words = {
        "media_match",
        "media_db",
        "media_probe",
        "media_ingest",
        "media_scan",
        "media_provider_tmdb",
        "media_types",
        "tmdb",
        "sqlite3",
        "requests",
        "works",
        "candidates",
    }

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)

    for name in imported_names:
        for forbidden in forbidden_words:
            assert forbidden not in name.lower(), f"Forbidden media/TMDb import detected: {name}"
