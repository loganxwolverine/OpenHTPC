#!/usr/bin/env python3
"""OpenHTPC Generic Living-Room Text Entry Component (DEV5C3B2).

Pure PySide6 living-room D-pad character grid.
Zero dependencies on media DB, TMDb, or resolver modules.
Wayland-native, TV-scaled, sofa-distance readable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

CHAR_GRID = [
    ["A", "B", "C", "D", "E", "F"],
    ["G", "H", "I", "J", "K", "L"],
    ["M", "N", "O", "P", "Q", "R"],
    ["S", "T", "U", "V", "W", "X"],
    ["Y", "Z", "0", "1", "2", "3"],
    ["4", "5", "6", "7", "8", "9"],
]

DEFAULT_ACTION_ROW = ["ESPACE", "EFFACER", "VIDER", "RECHERCHER", "ANNULER"]
TOTAL_GRID_ROWS = 6  # Rows 0..5
ACTION_ROW_INDEX = 6


class TextEntryModel:
    """Deterministic navigation and state model for text entry."""

    def __init__(
        self,
        initial_text: str = "",
        max_length: int = 255,
        title: str = "OPENHTPC",
        submit_label: str = "RECHERCHER",
        cancel_label: str = "ANNULER",
    ) -> None:
        self.title = str(title)
        self.text = str(initial_text) if initial_text is not None else ""
        self.max_length = max(1, int(max_length))
        self.submit_label = str(submit_label)
        self.cancel_label = str(cancel_label)
        self.action_row = ["ESPACE", "EFFACER", "VIDER", self.submit_label, self.cancel_label]
        self.row = 0
        self.col = 0
        self.submitted = False
        self.cancelled = False

    @property
    def current_key_label(self) -> str:
        if self.row == ACTION_ROW_INDEX:
            return self.action_row[self.col]
        return CHAR_GRID[self.row][self.col]

    def move_left(self) -> None:
        if self.row == ACTION_ROW_INDEX:
            self.col = (self.col - 1) % len(self.action_row)
        else:
            self.col = (self.col - 1) % len(CHAR_GRID[self.row])

    def move_right(self) -> None:
        if self.row == ACTION_ROW_INDEX:
            self.col = (self.col + 1) % len(self.action_row)
        else:
            self.col = (self.col + 1) % len(CHAR_GRID[self.row])

    def move_up(self) -> None:
        if self.row == 0:
            return
        elif self.row == ACTION_ROW_INDEX:
            self.row = TOTAL_GRID_ROWS - 1
            self.col = min(self.col, len(CHAR_GRID[self.row]) - 1)
        else:
            self.row -= 1
            self.col = min(self.col, len(CHAR_GRID[self.row]) - 1)

    def move_down(self) -> None:
        if self.row == ACTION_ROW_INDEX:
            return
        elif self.row == TOTAL_GRID_ROWS - 1:
            self.row = ACTION_ROW_INDEX
            self.col = min(self.col, len(self.action_row) - 1)
        else:
            self.row += 1
            self.col = min(self.col, len(CHAR_GRID[self.row]) - 1)

    def activate_current(self) -> dict[str, Any] | None:
        if self.row == ACTION_ROW_INDEX:
            action = self.action_row[self.col]
            if action == "ESPACE":
                self.append_space()
            elif action == "EFFACER":
                self.backspace()
            elif action == "VIDER":
                self.clear()
            elif action == self.submit_label or self.col == 3:
                return self.submit()
            elif action == self.cancel_label or self.col == 4:
                return self.cancel()
        else:
            char = CHAR_GRID[self.row][self.col]
            self.append_char(char)
        return None

    def append_char(self, char: str) -> None:
        if len(self.text) < self.max_length:
            self.text += str(char)

    def append_space(self) -> None:
        if len(self.text) < self.max_length and not self.text.endswith(" "):
            self.text += " "

    def backspace(self) -> None:
        if self.text:
            self.text = self.text[:-1]

    def clear(self) -> None:
        self.text = ""

    def submit(self) -> dict[str, Any]:
        self.submitted = True
        return self.to_result_dict()

    def cancel(self) -> dict[str, Any]:
        self.cancelled = True
        return self.to_result_dict()

    def to_result_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.submitted),
            "cancelled": bool(self.cancelled),
            "text": self.text.strip() if self.submitted else self.text,
        }

    def to_result_json(self) -> str:
        return json.dumps(self.to_result_dict(), ensure_ascii=False, indent=2)


# Backwards compatibility / alias for couch keyboard model tests
CouchInputModel = TextEntryModel
ACTION_ROW = DEFAULT_ACTION_ROW


def create_text_entry_window_class():
    from PySide6 import QtCore, QtGui, QtWidgets

    class TextEntryWindow(QtWidgets.QWidget):
        def __init__(
            self,
            model: TextEntryModel,
            output_path: Path | None = None,
        ) -> None:
            super().__init__()
            self.model = model
            self.output_path = output_path
            self.result: dict[str, Any] | None = None

            self.setWindowTitle(self.model.title)
            self.setStyleSheet("""
                QWidget {
                    background-color: #161b22;
                    color: #c9d1d9;
                    font-family: 'Open Sans', 'Noto Sans', sans-serif;
                }
                QLabel#TitleLabel {
                    color: #58a6ff;
                    font-size: 24px;
                    font-weight: bold;
                    padding-bottom: 8px;
                }
                QLineEdit#DisplayField {
                    background-color: #0d1117;
                    border: 2px solid #30363d;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 28px;
                    font-weight: 600;
                    padding: 8px 16px;
                    min-height: 52px;
                }
                QPushButton.KeyBtn {
                    background-color: #21262d;
                    border: 2px solid #30363d;
                    border-radius: 6px;
                    color: #c9d1d9;
                    font-size: 22px;
                    font-weight: 500;
                    min-width: 56px;
                    min-height: 48px;
                }
                QPushButton.KeyBtnSelected {
                    background-color: #1f6feb;
                    border: 3px solid #58a6ff;
                    border-radius: 6px;
                    color: #ffffff;
                    font-size: 24px;
                    font-weight: bold;
                    min-width: 56px;
                    min-height: 48px;
                }
                QPushButton.ActionBtn {
                    background-color: #30363d;
                    border: 2px solid #484f58;
                    border-radius: 8px;
                    color: #f0f6fc;
                    font-size: 18px;
                    font-weight: bold;
                    min-height: 48px;
                    padding: 4px 10px;
                }
                QPushButton.ActionBtnSelected {
                    background-color: #238636;
                    border: 3px solid #56d364;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 19px;
                    font-weight: bold;
                    min-height: 48px;
                    padding: 4px 10px;
                }
                QLabel#HelpLabel {
                    color: #6e7681;
                    font-size: 15px;
                    padding-top: 8px;
                }
            """)

            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(50, 30, 50, 30)
            main_layout.setSpacing(14)

            # Title
            self.title_label = QtWidgets.QLabel(self.model.title)
            self.title_label.setObjectName("TitleLabel")
            self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(self.title_label)

            # Display Box
            self.display_field = QtWidgets.QLineEdit(self.model.text)
            self.display_field.setObjectName("DisplayField")
            self.display_field.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.display_field.setReadOnly(True)
            self.display_field.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            main_layout.addWidget(self.display_field)

            # 6x6 Character Grid
            self.char_buttons: list[list[QtWidgets.QPushButton]] = []
            grid_layout = QtWidgets.QGridLayout()
            grid_layout.setSpacing(8)

            for r_idx, row in enumerate(CHAR_GRID):
                row_btns = []
                for c_idx, char in enumerate(row):
                    btn = QtWidgets.QPushButton(char)
                    btn.setProperty("class", "KeyBtn")
                    btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
                    grid_layout.addWidget(btn, r_idx, c_idx)
                    row_btns.append(btn)
                self.char_buttons.append(row_btns)

            main_layout.addLayout(grid_layout)

            # Action Buttons Row
            self.action_buttons: list[QtWidgets.QPushButton] = []
            action_layout = QtWidgets.QHBoxLayout()
            action_layout.setSpacing(10)

            for c_idx, act in enumerate(self.model.action_row):
                btn = QtWidgets.QPushButton(act)
                btn.setProperty("class", "ActionBtn")
                btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
                action_layout.addWidget(btn)
                self.action_buttons.append(btn)

            main_layout.addLayout(action_layout)

            # Help hint
            help_label = QtWidgets.QLabel("Flèches / D-pad : Navigation  •  Entrée : Sélectionner  •  Échap : Annuler")
            help_label.setObjectName("HelpLabel")
            help_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(help_label)

            self.update_ui_state()

        def update_ui_state(self) -> None:
            self.display_field.setText(self.model.text)

            for r_idx, row in enumerate(self.char_buttons):
                for c_idx, btn in enumerate(row):
                    is_sel = (self.model.row == r_idx and self.model.col == c_idx)
                    btn.setProperty("class", "KeyBtnSelected" if is_sel else "KeyBtn")
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

            for c_idx, btn in enumerate(self.action_buttons):
                is_sel = (self.model.row == ACTION_ROW_INDEX and self.model.col == c_idx)
                btn.setProperty("class", "ActionBtnSelected" if is_sel else "ActionBtn")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
            key = event.key()

            if key == QtCore.Qt.Key.Key_Left:
                self.model.move_left()
                self.update_ui_state()
                event.accept()
            elif key == QtCore.Qt.Key.Key_Right:
                self.model.move_right()
                self.update_ui_state()
                event.accept()
            elif key == QtCore.Qt.Key.Key_Up:
                self.model.move_up()
                self.update_ui_state()
                event.accept()
            elif key == QtCore.Qt.Key.Key_Down:
                self.model.move_down()
                self.update_ui_state()
                event.accept()
            elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                res = self.model.activate_current()
                self.update_ui_state()
                if res is not None:
                    self.finish(res)
                event.accept()
            elif key in (QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Back):
                res = self.model.cancel()
                self.finish(res)
                event.accept()
            elif key == QtCore.Qt.Key.Key_Backspace:
                self.model.backspace()
                self.update_ui_state()
                event.accept()
            elif key == QtCore.Qt.Key.Key_Space:
                self.model.append_space()
                self.update_ui_state()
                event.accept()
            elif event.text() and event.text().isprintable() and len(event.text()) == 1:
                self.model.append_char(event.text())
                self.update_ui_state()
                event.accept()
            else:
                super().keyPressEvent(event)

        def finish(self, res: dict[str, Any]) -> None:
            self.result = res
            json_str = self.model.to_result_json()
            if self.output_path:
                try:
                    self.output_path.parent.mkdir(parents=True, exist_ok=True)
                    self.output_path.write_text(json_str, encoding="utf-8")
                except OSError:
                    pass
            print(json_str)
            sys.stdout.flush()
            self.close()

    return TextEntryWindow


def run_text_entry(
    initial: str = "",
    title: str = "OPENHTPC",
    max_length: int = 255,
    submit_label: str = "RECHERCHER",
    cancel_label: str = "ANNULER",
    output_path: Path | None = None,
    platform_arg: str | None = None,
) -> dict[str, Any]:
    """Execute text entry dialog and return structured result."""
    from PySide6 import QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    created_app = False
    if app is None:
        qt_args = [sys.argv[0]]
        if platform_arg:
            qt_args.extend(["-platform", platform_arg])
        elif os.environ.get("QT_QPA_PLATFORM"):
            qt_args.extend(["-platform", os.environ["QT_QPA_PLATFORM"]])
        app = QtWidgets.QApplication(qt_args)
        created_app = True

    # Attempt to load bundled Open Sans font
    font_candidates = [
        Path(os.environ.get("OPENHTPC_INSTALL_DIR", Path.home() / ".local/lib/openhtpc")) / "flex/assets/fonts/OpenSans-Regular.ttf",
        Path(__file__).resolve().parent / "flex/assets/fonts/OpenSans-Regular.ttf",
    ]
    for fc in font_candidates:
        if fc.is_file():
            fid = QtGui.QFontDatabase.addApplicationFont(str(fc))
            families = QtGui.QFontDatabase.applicationFontFamilies(fid)
            if families:
                app.setFont(QtGui.QFont(families[0], 14))
                break

    model = TextEntryModel(
        initial_text=initial,
        max_length=max_length,
        title=title,
        submit_label=submit_label,
        cancel_label=cancel_label,
    )
    window_cls = create_text_entry_window_class()
    window = window_cls(model, output_path=output_path)
    window.resize(1000, 680)
    window.show()

    if created_app:
        app.exec()
    return window.result or model.to_result_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenHTPC Generic Living-Room Text Entry")
    parser.add_argument("--initial", "--initial-text", dest="initial", default="", help="Initial text prefill")
    parser.add_argument("--title", default="OPENHTPC", help="Window title")
    parser.add_argument("--max-length", type=int, default=255, help="Maximum allowed text length")
    parser.add_argument("--submit-label", default="RECHERCHER", help="Submit action button label")
    parser.add_argument("--cancel-label", default="ANNULER", help="Cancel action button label")
    parser.add_argument("--output", default=None, help="Optional output JSON file path")
    parser.add_argument("-platform", default=None, help="Qt platform (e.g. offscreen, wayland)")

    raw_args = list(sys.argv[1:] if argv is None else argv)
    platform_val = None
    if "-platform" in raw_args:
        idx = raw_args.index("-platform")
        if idx + 1 < len(raw_args):
            platform_val = raw_args[idx + 1]
            del raw_args[idx:idx + 2]
        else:
            del raw_args[idx]

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return exc.code

    if args.max_length < 1:
        print("ERROR: max-length must be >= 1", file=sys.stderr)
        return 2

    out_p = Path(args.output).resolve() if args.output else None
    res = run_text_entry(
        initial=args.initial,
        title=args.title,
        max_length=args.max_length,
        submit_label=args.submit_label,
        cancel_label=args.cancel_label,
        output_path=out_p,
        platform_arg=platform_val,
    )
    # Output is already printed in finish(), but ensure printed if finished otherwise
    if not out_p and not res.get("printed"):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
