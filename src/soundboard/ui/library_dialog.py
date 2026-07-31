"""Lists every sound shared to the library so the user can assign one to an empty cell."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from soundboard.remote import auth, sounds
from soundboard.remote.models import RemoteClient, Sound

_EMPTY_LIBRARY_MESSAGE = "No hay sonidos compartidos todavía"


class LibraryDialog(QDialog):
    def __init__(self, client: RemoteClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de sonidos")
        self._client = client
        self.selected_id: str | None = None
        self.selected_name: str | None = None
        self._rows: list[tuple[str, str]] = []

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._update_ok_enabled)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._retry_button = QPushButton("Reintentar")
        self._retry_button.clicked.connect(self._load)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addWidget(self._error)
        layout.addWidget(self._retry_button)
        layout.addWidget(buttons)

        # Defer the first load by one event-loop turn so the dialog is already on
        # screen before the network round-trip starts — otherwise the app appears
        # to freeze with no window visible until it resolves (or times out).
        QTimer.singleShot(0, self._load)

    def _update_ok_enabled(self, row: int) -> None:
        self._ok_button.setEnabled(row >= 0)

    def _load(self) -> None:
        try:
            available = sounds.list_sounds(self._client)
            owners = auth.display_names(self._client, {s.owner_id for s in available})
        except Exception as exc:  # dialog boundary: show it, offer to retry
            self._show_error(str(exc), retry_visible=True)
            return
        self._show_list(available, owners)

    def _show_list(self, available: list[Sound], owners: dict[str, str]) -> None:
        self._list.clear()
        self._rows = [(sound.id, sound.name) for sound in available]
        for sound in available:
            owner_name = owners.get(sound.owner_id, sound.owner_id)
            self._list.addItem(f"{sound.name} — {owner_name}")
        if available:
            self._list.show()
            self._error.hide()
            self._retry_button.hide()
        else:
            # Not an error — nobody has shared anything yet, so retrying would be
            # pointless: reuse the error label for the message but keep the retry
            # button hidden.
            self._show_error(_EMPTY_LIBRARY_MESSAGE, retry_visible=False)

    def _show_error(self, message: str, *, retry_visible: bool) -> None:
        self._list.hide()
        self._error.setText(message)
        self._error.show()
        self._retry_button.setVisible(retry_visible)

    def _accept(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self.selected_id, self.selected_name = self._rows[row]
        self.accept()
