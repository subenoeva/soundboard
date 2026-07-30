"""System tray icon: show/hide the window from the tray, or quit for real."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayIcon(QSystemTrayIcon):
    def __init__(
        self,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(QIcon.fromTheme("audio-volume-high"), parent)
        menu = QMenu()
        show_action = menu.addAction("Mostrar")
        show_action.triggered.connect(on_show)
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(on_quit)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._on_show = on_show

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_show()
