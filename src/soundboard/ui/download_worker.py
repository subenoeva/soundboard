"""Runs a callable off the Qt thread; finished carries its return value."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class _DownloadSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(self, resolve: Callable[[], object]) -> None:
        super().__init__()
        self._resolve = resolve
        self.signals = _DownloadSignals()

    def run(self) -> None:
        try:
            result = self._resolve()
        except Exception as exc:  # background-thread boundary: never crash silently
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(result)
