"""Uploads a locally-dropped file to the shared library, off the Qt UI thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from soundboard.remote.models import Sound


class _UploadSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class UploadWorker(QRunnable):
    def __init__(self, upload: Callable[[], Sound]) -> None:
        super().__init__()
        self._upload = upload
        self.signals = _UploadSignals()

    def run(self) -> None:
        try:
            sound = self._upload()
        except Exception as exc:  # background-thread boundary: never crash silently
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(sound)
