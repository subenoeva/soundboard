"""List model behind the QML library popup: remote sounds with a name filter."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)

from soundboard.remote import auth, sounds
from soundboard.remote.models import RemoteClient
from soundboard.ui.download_worker import DownloadWorker


class LibraryModel(QAbstractListModel):
    NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    OWNER_ROLE = NAME_ROLE + 1
    SOUND_ID_ROLE = NAME_ROLE + 2

    loadingChanged = Signal()
    errorChanged = Signal()
    filterChanged = Signal()

    def __init__(self, client: RemoteClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._loading = False
        self._error = ""
        self._filter = ""
        self._all: list[tuple[str, str, str]] = []
        self._rows: list[tuple[str, str, str]] = []
        self._active_workers: set[DownloadWorker] = set()

    @Slot()
    def reload(self) -> None:
        if self._loading:
            # Reopening the popup while "Reintentar" is still in flight would race two
            # fetches: the first to land clears the spinner and the slower one then
            # overwrites the rows the user is already looking at.
            return
        self._loading = True
        self.loadingChanged.emit()
        self._error = ""
        self.errorChanged.emit()

        def fetch() -> list[tuple[str, str, str]]:
            available = sounds.list_sounds(self._client)
            owners = auth.display_names(self._client, {s.owner_id for s in available})
            return [(s.id, s.name, owners.get(s.owner_id, s.owner_id))
                    for s in available]

        worker = DownloadWorker(fetch)
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda rows, w=worker: self._on_reload_finished(w, rows)
        )
        worker.signals.failed.connect(
            lambda message, w=worker: self._on_reload_failed(w, message)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_reload_finished(
        self, worker: DownloadWorker, rows: list[tuple[str, str, str]]
    ) -> None:
        self._active_workers.discard(worker)
        self._all = rows
        self._apply_filter()
        self._loading = False
        self.loadingChanged.emit()

    def _on_reload_failed(self, worker: DownloadWorker, message: str) -> None:
        self._active_workers.discard(worker)
        self._error = message
        self.errorChanged.emit()
        self._loading = False
        self.loadingChanged.emit()

    def _apply_filter(self) -> None:
        self.beginResetModel()
        needle = self._filter.lower()
        self._rows = [row for row in self._all if needle in row[1].lower()]
        self.endResetModel()

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> str | None:
        row = index.row()
        if not 0 <= row < len(self._rows):
            return None
        sound_id, name, owner = self._rows[row]
        if role == self.NAME_ROLE:
            return name
        if role == self.OWNER_ROLE:
            return owner
        if role == self.SOUND_ID_ROLE:
            return sound_id
        return None

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        return {
            self.NAME_ROLE: b"name",
            self.OWNER_ROLE: b"owner",
            self.SOUND_ID_ROLE: b"soundId",
        }

    def _get_loading(self) -> bool:
        return self._loading

    def _get_error_text(self) -> str:
        return self._error

    def _get_filter_text(self) -> str:
        return self._filter

    def _set_filter_text(self, value: str) -> None:
        if value == self._filter:
            return
        self._filter = value
        self.filterChanged.emit()
        self._apply_filter()

    loading = Property(bool, _get_loading, notify=loadingChanged)
    errorText = Property(str, _get_error_text, notify=errorChanged)
    filterText = Property(str, _get_filter_text, _set_filter_text, notify=filterChanged)
