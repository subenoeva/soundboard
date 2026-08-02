"""Full Main.qml smoke: loads with a real AppController wired to fakes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QMetaObject, QObject
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.app import qml_root
from soundboard.ui.controller import AppController
from soundboard.ui.effects_store import EffectEntry, save_effects
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


def _find_visual_child(item: QQuickItem, name: str) -> QQuickItem | None:
    for child in item.childItems():
        if child.objectName() == name:
            return child
        if found := _find_visual_child(child, name):
            return found
    return None


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
        effects_path=tmp_path / "effects.json",
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


def test_header_log_out_button_is_wired_to_the_controller(
    qapp: QApplication, tmp_path: Path
) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    # `root` must stay referenced for the same reason the engine does (see above):
    # dropping it lets the whole item tree, header included, be collected.
    root = engine.rootObjects()[0]
    header = root.findChild(QObject, "headerBar")
    assert header is not None

    QMetaObject.invokeMethod(header, "logOutClicked")
    qapp.processEvents()

    assert controller.view == "login"  # type: ignore[comparison-overlap]
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_board_offers_sound_and_effect_tabs(qapp: QApplication, tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    root = engine.rootObjects()[0]

    tabs = root.findChild(QObject, "boardTabs")
    sounds_tab = root.findChild(QObject, "soundsTab")
    effects_tab = root.findChild(QObject, "effectsTab")

    assert tabs is not None
    assert tabs.property("count") == 2
    assert sounds_tab is not None and sounds_tab.property("text") == "Sonidos"
    assert effects_tab is not None and effects_tab.property("text") == "Efectos"
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_effect_palette_uses_the_available_width(
    qapp: QApplication, tmp_path: Path
) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    root = engine.rootObjects()[0]
    tabs = root.findChild(QObject, "boardTabs")
    assert tabs is not None
    tabs.setProperty("currentIndex", 1)
    qapp.processEvents()

    palette = root.findChild(QObject, "effectPalette")
    scroller = root.findChild(QObject, "paletteScroller")

    assert palette is not None
    assert scroller is not None and scroller.property("width") > 0
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_selecting_an_effect_lays_out_its_parameter_panel(
    qapp: QApplication, qtbot: Any, tmp_path: Path
) -> None:
    save_effects(tmp_path / "effects.json", [EffectEntry(kind="gain")])
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    root = engine.rootObjects()[0]
    tabs = root.findChild(QObject, "boardTabs")
    rack = root.findChild(QObject, "effectsRack")
    assert tabs is not None and isinstance(rack, QQuickItem)
    tabs.setProperty("currentIndex", 1)
    qapp.processEvents()
    qtbot.waitUntil(lambda: _find_visual_child(rack, "effectBlock") is not None)
    block = _find_visual_child(rack, "effectBlock")
    assert block is not None

    QMetaObject.invokeMethod(block, "selectedRequested")
    qapp.processEvents()
    panel = root.findChild(QObject, "paramPanel")
    parameter_list = root.findChild(QObject, "parameterList")

    assert panel is not None
    assert parameter_list is not None
    assert parameter_list.property("count") == 1
    assert parameter_list.property("width") > 0
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_saved_effect_is_rendered_between_the_fixed_rack_ends(
    qapp: QApplication, qtbot: Any, tmp_path: Path
) -> None:
    save_effects(tmp_path / "effects.json", [EffectEntry(kind="gain")])
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    root = engine.rootObjects()[0]
    tabs = root.findChild(QObject, "boardTabs")
    rack = root.findChild(QObject, "effectsRack")
    assert tabs is not None
    assert rack is not None
    tabs.setProperty("currentIndex", 1)
    qapp.processEvents()

    assert rack.property("count") == 1
    assert rack.property("width") > 0
    assert rack.property("height") > 0

    assert isinstance(rack, QQuickItem)

    def rack_block() -> QQuickItem | None:
        qapp.processEvents()
        return _find_visual_child(rack, "effectBlock")

    qtbot.waitUntil(lambda: rack_block() is not None)

    mic = root.findChild(QObject, "micCard")
    block = rack_block()
    out = root.findChild(QObject, "outCard")

    assert mic is not None
    assert block is not None and block.property("effectLabel") == "Gain"
    assert out is not None
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []
