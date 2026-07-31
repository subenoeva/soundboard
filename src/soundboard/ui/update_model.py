"""View state over the update flow, exposed to QML as ``App.updateModel``.

Kept out of AppController for the same reason GridModel and LibraryModel are: the state
machine is worth testing on its own, and the controller is already at its line budget.

Both the check and the download run on a QRunnable — the check performs two HTTPS
requests and the download moves ~100MB, neither of which may happen on the Qt thread.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, QThreadPool, Signal, Slot

from soundboard.ui.download_worker import DownloadWorker
from soundboard.updater.service import AvailableUpdate, UpdateService


class UpdateModel(QObject):
    stateChanged = Signal()
    progressChanged = Signal()
    toast = Signal(str)
    restartRequested = Signal(str)

    def __init__(self, service: UpdateService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._state = "idle"
        self._progress = 0.0
        self._available: AvailableUpdate | None = None
        self._announce = False
        self._active_workers: set[DownloadWorker] = set()

    @Slot()
    @Slot(bool)
    def check(self, announce: bool = False) -> None:
        """Look for a newer release.

        ``announce`` distinguishes the two callers. The launch check is silent unless it
        finds something: a toast about a failed connection, on every launch someone
        happens to be offline, is noise about a thing they never asked for. The menu
        entry passes True, because there silence would be the failure.
        """
        if self._state in ("checking", "downloading"):
            return
        self._announce = announce
        self._set_state("checking")
        self._run(self._service.check, self._on_checked)

    @Slot()
    def download(self) -> None:
        if self._available is None or self._state == "downloading":
            return
        update = self._available
        self._progress = 0.0
        self.progressChanged.emit()
        self._set_state("downloading")
        self._run(lambda: self._service.apply(update, progress=self._on_progress), self._on_applied)

    @Slot()
    def restart(self) -> None:
        """Ask the controller to relaunch. Deliberately not done here: the engine, the
        poll timer and the global keyboard hook have to come down first, and that stack
        belongs to AppController."""
        if self._state != "ready" or self._available is None:
            return
        self.restartRequested.emit(str(self._available.binary))

    def _run(self, work: object, done: object) -> None:
        worker = DownloadWorker(work)  # type: ignore[arg-type]
        self._active_workers.add(worker)
        # QThreadPool does not keep Python's refcount alive across the thread hop, hence
        # _active_workers; see ui/_worker_dispatch.py for the same pattern.
        worker.signals.finished.connect(
            lambda result, w=worker: self._deliver(w, done, result, None)
        )
        worker.signals.failed.connect(
            lambda message, w=worker: self._deliver(w, done, None, message)
        )
        QThreadPool.globalInstance().start(worker)

    def _deliver(
        self, worker: DownloadWorker, done: object, result: object, error: str | None
    ) -> None:
        self._active_workers.discard(worker)
        done(result, error)  # type: ignore[operator]

    def _on_checked(self, result: object, error: str | None) -> None:
        if error is not None:
            self._set_state("failed" if self._announce else "idle")
            if self._announce:
                self.toast.emit(f"No se pudo comprobar si hay actualizaciones: {error}")
            return
        self._available = result if isinstance(result, AvailableUpdate) else None
        if self._available is None:
            self._set_state("idle")
            if self._announce:
                self.toast.emit("Ya tienes la última versión")
            return
        self._set_state("available")

    def _on_applied(self, result: object, error: str | None) -> None:
        if error is not None:
            self._set_state("failed")
            self.toast.emit(f"No se pudo instalar la actualización: {error}")
            return
        self._set_state("ready")

    def _on_progress(self, downloaded: int, total: int | None) -> None:
        # Runs on the worker thread. Assigning a float and emitting a signal is safe
        # across threads in Qt; anything heavier would have to be queued.
        self._progress = 0.0 if not total else min(downloaded / total, 1.0)
        self.progressChanged.emit()

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    def _get_state(self) -> str:
        return self._state

    def _get_version(self) -> str:
        return self._available.version if self._available is not None else ""

    def _get_progress(self) -> float:
        return self._progress

    def _get_supported(self) -> bool:
        return self._service.is_supported()

    state = Property(str, _get_state, notify=stateChanged)
    version = Property(str, _get_version, notify=stateChanged)
    progress = Property(float, _get_progress, notify=progressChanged)
    supported = Property(bool, _get_supported, constant=True)
