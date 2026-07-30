"""Wires the clip grid, tray icon and hotkeys to the audio engine and remote library."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QWidget,
)

from soundboard.audioio import load_mono_48k
from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.models import RemoteClient
from soundboard.ui.clip_button import ClipButton, ClipState
from soundboard.ui.download_worker import DownloadWorker
from soundboard.ui.grid import ClipGrid
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource, save_layout


class Engine(Protocol):
    def play(self, pcm: np.ndarray, **kwargs: Any) -> None: ...
    def stop_all(self) -> None: ...


def _default_message_box(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


class MainWindow(QMainWindow):
    def __init__(
        self,
        engine: Engine,
        client: RemoteClient,
        cache: SoundCache,
        hotkeys: HotkeyManager,
        layout: GridLayout,
        layout_path: Path,
        message_box: Callable[[QWidget, str, str], None] = _default_message_box,
        prompt_shortcut: Callable[[QWidget, str, str], tuple[str, bool]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Soundboard")
        self._engine = engine
        self._client = client
        self._cache = cache
        self._hotkeys = hotkeys
        self._layout = layout
        self._layout_path = layout_path
        self._message_box = message_box
        self._prompt_shortcut = prompt_shortcut or (
            lambda parent, title, label: QInputDialog.getText(parent, title, label)
        )
        self._pool = QThreadPool.globalInstance()
        self._active_downloads: set[DownloadWorker] = set()

        self._grid = ClipGrid(layout.rows, layout.cols)
        self.setCentralWidget(self._grid)
        self._grid.play_requested.connect(self._play)
        self._grid.file_dropped.connect(self._assign_local_file)
        self._grid.clear_requested.connect(self._clear_cell)
        self._grid.assign_shortcut_requested.connect(self._assign_shortcut)

        toolbar = QToolBar()
        self._stop_all_action = toolbar.addAction("Detener todo")
        self._stop_all_action.triggered.connect(self._engine.stop_all)
        self.addToolBar(toolbar)

        status = QStatusBar()
        self.setStatusBar(status)
        self._metrics_timer = QTimer(self)
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._metrics_timer.start(500)

        for cell in layout.cells:
            self._apply_cell(cell)

    def _apply_cell(self, cell: Cell) -> None:
        self._grid.button_at(cell.index).assign(cell.name, cell.shortcut)
        if cell.shortcut:
            self._hotkeys.register(cell.shortcut, partial(self._play, cell.index))

    def _cell_at(self, index: int) -> Cell | None:
        return next((c for c in self._layout.cells if c.index == index), None)

    def _play(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        button = self._grid.button_at(index)
        if isinstance(cell.source, LocalSource):
            self._engine.play(load_mono_48k(cell.source.path))
            return
        self._play_remote(button, cell.source)

    def _play_remote(self, button: ClipButton, source: RemoteSource) -> None:
        button.set_state(ClipState.LOADING)

        def resolve() -> np.ndarray:
            sound = sounds.get_sound(self._client, source.id)
            return sounds.resolve_pcm(self._client, self._cache, sound)

        worker = DownloadWorker(resolve)
        # QThreadPool doesn't keep Python's refcount alive across the thread hop —
        # without this, the worker (and its bound signals) can be garbage collected
        # before `run()` finishes, silently dropping the finished/failed signal.
        self._active_downloads.add(worker)
        worker.signals.finished.connect(
            lambda pcm, b=button, w=worker: self._on_remote_ready(b, w, pcm)
        )
        worker.signals.failed.connect(
            lambda message, b=button, w=worker: self._on_remote_failed(b, w, message)
        )
        self._pool.start(worker)

    def _on_remote_ready(self, button: ClipButton, worker: DownloadWorker, pcm: np.ndarray) -> None:
        self._active_downloads.discard(worker)
        button.set_state(ClipState.IDLE)
        self._engine.play(pcm)

    def _on_remote_failed(self, button: ClipButton, worker: DownloadWorker, message: str) -> None:
        self._active_downloads.discard(worker)
        button.set_state(ClipState.IDLE)
        self.statusBar().showMessage(f"error: {message}", 5000)

    def _assign_local_file(self, index: int, path: str) -> None:
        try:
            load_mono_48k(path)
        except Exception as exc:
            self._message_box(self, "No se pudo asignar", str(exc))
            return
        name = Path(path).stem
        self._set_cell(Cell(index=index, source=LocalSource(path=path), name=name, shortcut=None))

    def _set_cell(self, cell: Cell) -> None:
        self._layout.cells = [c for c in self._layout.cells if c.index != cell.index] + [cell]
        self._grid.button_at(cell.index).assign(cell.name, cell.shortcut)
        save_layout(self._layout_path, self._layout)

    def _clear_cell(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is not None and cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._layout.cells = [c for c in self._layout.cells if c.index != index]
        self._grid.button_at(index).clear()
        save_layout(self._layout_path, self._layout)

    def _assign_shortcut(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        combo, ok = self._prompt_shortcut(
            self, "Asignar atajo", "Combinación (formato pynput, ej. <ctrl>+<alt>+1):"
        )
        if not ok or not combo:
            return
        try:
            self._hotkeys.register(combo, partial(self._play, index))
        except ValueError as exc:
            self._message_box(self, "Atajo inválido", str(exc))
            return
        if cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._set_cell(Cell(index=cell.index, source=cell.source, name=cell.name, shortcut=combo))

    def _update_metrics(self) -> None:
        metrics = getattr(self._engine, "metrics", None)
        if metrics is not None:
            self.statusBar().showMessage(str(metrics))

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
