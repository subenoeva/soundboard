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
    QThreadPool,
    Signal,
    Slot,
)

from soundboard.audioio import load_mono_48k
from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui.download_worker import DownloadWorker
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource

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
        self._active_workers: set[DownloadWorker] = set()
        self._hotkey_pressed.connect(self.play)
        for cell in layout.cells:
            if cell.shortcut:
                self._hotkeys.register(
                    cell.shortcut, partial(self._hotkey_pressed.emit, cell.index)
                )

    @Slot(int)
    def play(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        if isinstance(cell.source, LocalSource):
            try:
                pcm = load_mono_48k(cell.source.path)
            except Exception as exc:
                self.toast.emit(f"No se pudo reproducir: {exc}")
                return
            self._track_voice(index, self._engine.play(pcm))
            return
        self._play_remote(index, cell.source)

    def _track_voice(self, index: int, voice_id: int) -> None:
        self._voice_by_cell[index] = voice_id
        self._states[index] = STATE_PLAYING
        self._progress[index] = 0.0
        self._emit_row_changed(index, [self.STATE_ROLE, self.PROGRESS_ROLE])

    def _play_remote(self, index: int, source: RemoteSource) -> None:
        self._states[index] = STATE_LOADING
        self._emit_row_changed(index, [self.STATE_ROLE])

        def resolve() -> np.ndarray:
            sound = sounds.get_sound(self._client, source.id)
            return sounds.resolve_pcm(self._client, self._cache, sound)

        worker = DownloadWorker(resolve)
        # QThreadPool does not keep the Python refcount alive across the thread
        # hop; without this set the worker can be collected before run() ends.
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda pcm, i=index, w=worker: self._on_pcm_ready(i, w, pcm)
        )
        worker.signals.failed.connect(
            lambda message, i=index, w=worker: self._on_pcm_failed(i, w, message)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_pcm_ready(self, index: int, worker: DownloadWorker, pcm: np.ndarray) -> None:
        self._active_workers.discard(worker)
        self._track_voice(index, self._engine.play(pcm))

    def _on_pcm_failed(self, index: int, worker: DownloadWorker, message: str) -> None:
        self._active_workers.discard(worker)
        self._states[index] = STATE_IDLE
        self._emit_row_changed(index, [self.STATE_ROLE])
        self.toast.emit(f"error: {message}")

    def apply_voice_states(self, states: list[tuple[int, float]]) -> None:
        """Called by EngineBridge with the engine's (voice_id, progress) snapshot."""
        progress_by_id = dict(states)
        for cell_index, voice_id in list(self._voice_by_cell.items()):
            if voice_id in progress_by_id:
                self._progress[cell_index] = progress_by_id[voice_id]
                self._emit_row_changed(cell_index, [self.PROGRESS_ROLE])
            else:
                del self._voice_by_cell[cell_index]
                self._states[cell_index] = STATE_IDLE
                self._progress[cell_index] = 0.0
                self._emit_row_changed(cell_index, [self.STATE_ROLE, self.PROGRESS_ROLE])

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
