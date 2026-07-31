"""List model behind the QML clip grid: cell contents, runtime state, hotkeys."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui.layout_store import Cell, GridLayout

STATE_EMPTY = "empty"
STATE_IDLE = "idle"
STATE_LOADING = "loading"
STATE_PLAYING = "playing"


class Engine(Protocol):
    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> int: ...
    def stop_all(self) -> None: ...
    def stop(self) -> None: ...


class GridModel(QAbstractListModel):
    NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    SHORTCUT_ROLE = NAME_ROLE + 1
    COLOR_ROLE = NAME_ROLE + 2
    STATE_ROLE = NAME_ROLE + 3
    PROGRESS_ROLE = NAME_ROLE + 4

    toast = Signal(str)
    # pynput delivers hotkeys on its own thread; emitting a signal bounces the
    # call onto the Qt thread (auto connection turns queued cross-thread), so
    # play() and its dataChanged emissions always run where Qt requires them.
    _hotkey_pressed = Signal(int)

    def __init__(
        self,
        engine: Engine,
        client: RemoteClient,
        session: Session,
        cache: SoundCache,
        hotkeys: HotkeyManager,
        layout: GridLayout,
        layout_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._client = client
        self._session = session
        self._cache = cache
        self._hotkeys = hotkeys
        self._layout = layout
        self._layout_path = layout_path
        self._states: dict[int, str] = {}
        self._progress: dict[int, float] = {}
        self._voice_by_cell: dict[int, int] = {}
        self._active_workers: set[QObject] = set()
        self._hotkey_pressed.connect(self.play)
        for cell in layout.cells:
            if cell.shortcut:
                self._hotkeys.register(
                    cell.shortcut, partial(self._hotkey_pressed.emit, cell.index)
                )

    def play(self, index: int) -> None:
        """Filled in by the playback task."""
        return None

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        if parent and parent.isValid():
            return 0
        return self._layout.rows * self._layout.cols

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        i = index.row()
        cell = self._cell_at(i)
        if role == self.NAME_ROLE:
            return cell.name if cell else ""
        if role == self.SHORTCUT_ROLE:
            return (cell.shortcut or "") if cell else ""
        if role == self.COLOR_ROLE:
            return (cell.color or "") if cell else ""
        if role == self.STATE_ROLE:
            return self._states.get(i, STATE_IDLE if cell else STATE_EMPTY)
        if role == self.PROGRESS_ROLE:
            return self._progress.get(i, 0.0)
        return None

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        return {
            self.NAME_ROLE: b"name",
            self.SHORTCUT_ROLE: b"shortcut",
            self.COLOR_ROLE: b"cellColor",
            self.STATE_ROLE: b"cellState",
            self.PROGRESS_ROLE: b"progress",
        }

    def _cell_at(self, index: int) -> Cell | None:
        return next((c for c in self._layout.cells if c.index == index), None)

    def _emit_row_changed(self, index: int, roles: list[int]) -> None:
        model_index = self.index(index)
        self.dataChanged.emit(model_index, model_index, roles)
