from typing import Any

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from soundboard.ui.tray import TrayIcon


def test_tray_menu_actions_call_their_callbacks(qtbot: Any) -> None:
    # `isSystemTrayAvailable()` needs a live QApplication (qtbot's fixture guarantees
    # one) — calling it as a `skipif` decorator argument crashes at collection time,
    # before any fixture has run.
    if not QSystemTrayIcon.isSystemTrayAvailable():
        pytest.skip("no system tray in this environment")

    shown = []
    quit_calls = []
    tray = TrayIcon(on_show=lambda: shown.append(True), on_quit=lambda: quit_calls.append(True))

    actions = tray.contextMenu().actions()
    actions[0].trigger()
    actions[1].trigger()

    assert shown == [True]
    assert quit_calls == [True]
