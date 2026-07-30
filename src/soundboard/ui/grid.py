"""The clip grid widget: click to play, drag a file in to assign, right-click to manage."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGridLayout, QMenu, QWidget

from soundboard.ui.clip_button import ClipButton


class ClipGrid(QWidget):
    play_requested = Signal(int)
    file_dropped = Signal(int, str)
    assign_shortcut_requested = Signal(int)
    clear_requested = Signal(int)

    def __init__(self, rows: int, cols: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[ClipButton] = []
        layout = QGridLayout(self)
        for index in range(rows * cols):
            button = ClipButton(index)
            button.clicked.connect(lambda _checked=False, i=index: self.play_requested.emit(i))
            button.file_dropped.connect(self.file_dropped)
            button.customContextMenuRequested.connect(
                lambda _pos, i=index: self._show_context_menu(i)
            )
            layout.addWidget(button, index // cols, index % cols)
            self._buttons.append(button)

    def button_at(self, index: int) -> ClipButton:
        return self._buttons[index]

    def _show_context_menu(self, index: int) -> None:
        menu = QMenu(self)
        assign_action = menu.addAction("Asignar atajo")
        clear_action = menu.addAction("Vaciar celda")
        chosen = menu.exec(QCursor.pos())
        if chosen is assign_action:
            self.assign_shortcut_requested.emit(index)
        elif chosen is clear_action:
            self.clear_requested.emit(index)
