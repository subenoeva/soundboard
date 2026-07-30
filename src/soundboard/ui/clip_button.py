"""A single cell in the clip grid: idle, loading a remote sound, or playing."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QToolButton, QWidget


class ClipState(Enum):
    EMPTY = auto()
    IDLE = auto()
    LOADING = auto()
    PLAYING = auto()


class ClipButton(QToolButton):
    file_dropped = Signal(int, str)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self._state = ClipState.EMPTY
        self._name = ""
        self._shortcut: str | None = None
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._refresh()

    @property
    def state(self) -> ClipState:
        return self._state

    def assign(self, name: str, shortcut: str | None) -> None:
        self._name = name
        self._shortcut = shortcut
        self._state = ClipState.IDLE
        self._refresh()

    def set_state(self, state: ClipState) -> None:
        self._state = state
        self._refresh()

    def clear(self) -> None:
        self._name = ""
        self._shortcut = None
        self._state = ClipState.EMPTY
        self._refresh()

    def _refresh(self) -> None:
        text = self._name or "(vacío)"
        if self._shortcut:
            text += f"\n[{self._shortcut}]"
        if self._state is ClipState.LOADING:
            text += "\n…"
        self.setText(text)
        self.setEnabled(self._state != ClipState.LOADING)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._state is ClipState.EMPTY and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.file_dropped.emit(self.index, urls[0].toLocalFile())
