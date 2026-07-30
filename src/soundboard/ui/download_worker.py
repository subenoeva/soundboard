"""Resolves a sound's PCM (cache hit or network download) off the Qt UI thread."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal


class _DownloadSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(self, resolve: Callable[[], np.ndarray]) -> None:
        super().__init__()
        self._resolve = resolve
        self.signals = _DownloadSignals()

    def run(self) -> None:
        try:
            pcm = self._resolve()
        except Exception as exc:  # background-thread boundary: never crash silently
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(pcm)
