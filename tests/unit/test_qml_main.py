"""Full Main.qml smoke: loads with a real AppController wired to fakes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.app import qml_root
from soundboard.ui.controller import AppController
from tests.unit.test_controller import FakeEngine, FakeStore


def _load(controller: AppController) -> tuple[QQmlApplicationEngine, list[str]]:
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(
        lambda ws: warnings.extend(w.toString() for w in ws)
    )
    engine.rootContext().setContextProperty("App", controller)
    engine.load(str(qml_root() / "Main.qml"))
    return engine, warnings


def make_controller(tmp_path: Path) -> AppController:
    # FakeRemoteClient.sign_in rejects credentials for an email that was never
    # signed up, so the board-view test below needs the user seeded ahead of
    # time — same pattern test_controller.py uses before calling log_in().
    client = FakeRemoteClient()
    client.sign_up("user@example.com", "password")
    return AppController(
        client=client, store=FakeStore(), backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(), cache=SoundCache(tmp_path / "cache"),
        layout_path=tmp_path / "layout.json",
        engine_factory=lambda layout: FakeEngine(),
    )


def test_main_qml_loads_on_login_view(qapp: QApplication, tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    assert engine.rootObjects(), warnings
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_main_qml_reaches_board_view(qapp: QApplication, tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    # `engine` must stay referenced: an unreferenced QQmlApplicationEngine (and its
    # root objects) is free to be garbage-collected before processEvents() above runs
    # the bindings that would otherwise emit the warnings this test is checking for.
    assert engine.rootObjects()
    assert controller.view == "board"  # type: ignore[comparison-overlap]
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []
