"""Every QML component must instantiate standalone under the offscreen platform."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem

QML_DIR = Path(__file__).parents[2] / "src" / "soundboard" / "ui" / "qml"

COMPONENTS = sorted(p for p in (QML_DIR / "components").glob("*.qml"))


def _instantiate(name: str) -> tuple[QQmlComponent, QObject]:
    """Create one component standalone, kept alive for the caller to poke at.

    ``create()`` hands the instance to the QML engine's garbage collector; the
    ownership switch and the returned component (which owns the engine) are what
    stop it from being collected mid-test.
    """
    engine = QQmlEngine()
    component = QQmlComponent(engine, str(QML_DIR / "components" / name))
    engine.setParent(component)
    obj = component.create()
    assert obj is not None, [e.toString() for e in component.errors()]
    QQmlEngine.setObjectOwnership(obj, QQmlEngine.ObjectOwnership.CppOwnership)
    return component, obj


def test_components_exist() -> None:
    names = {p.name for p in COMPONENTS}
    assert {"ClipPad.qml", "HeaderBar.qml", "VUMeter.qml", "Toast.qml",
            "LibraryPopup.qml", "ShortcutPopup.qml", "ColorPopup.qml",
            "UpdateBanner.qml", "EffectBlock.qml", "EffectPalette.qml",
            "ParamPanel.qml", "ParamSlider.qml"} <= names


def test_views_exist() -> None:
    names = {p.name for p in QML_DIR.glob("*.qml")}
    assert {"Main.qml", "LoginView.qml", "DeviceSetupView.qml",
            "BoardView.qml", "GridPage.qml", "EffectsPage.qml", "Theme.qml"} <= names


@pytest.mark.parametrize("qml_file", COMPONENTS, ids=lambda p: p.name)
def test_component_instantiates(qapp: object, qml_file: Path) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine, str(qml_file))
    obj = component.create()
    errors = [e.toString() for e in component.errors()]
    assert obj is not None, errors


def test_vu_meter_holds_the_recent_peak(qapp: object) -> None:
    _component, meter = _instantiate("VUMeter.qml")
    meter.setProperty("level", 0.8)
    meter.setProperty("level", 0.1)
    # The marker stays up where the signal just was; only the decay animation
    # brings it back down, so the eye catches transients the level bar loses.
    assert meter.property("peak") == pytest.approx(0.8)


def test_clip_pad_pulses_when_it_starts_playing(qapp: object) -> None:
    _component, pad = _instantiate("ClipPad.qml")
    pulse = pad.findChild(QObject, "playPulse")
    assert pulse is not None
    assert pulse.property("running") is False

    pad.setProperty("cellState", "playing")

    assert pulse.property("running") is True


def test_update_banner_takes_no_room_until_there_is_an_update(qapp: object) -> None:
    """`visible` is effective visibility and stays False without a window, so the height
    collapse is what this asserts — and it is what actually keeps the grid full-size."""
    _component, banner = _instantiate("UpdateBanner.qml")

    assert banner.property("showing") is False
    assert banner.property("height") == 0

    banner.setProperty("updateState", "available")

    assert banner.property("showing") is True
    assert banner.property("height") > 0

    banner.setProperty("updateState", "idle")

    assert banner.property("height") == 0


def test_update_banner_offers_a_restart_once_the_swap_is_done(qapp: object) -> None:
    _component, banner = _instantiate("UpdateBanner.qml")
    banner.setProperty("version", "0.4.0")
    action = banner.findChild(QObject, "updateAction")
    label = banner.findChild(QObject, "updateLabel")
    assert action is not None and label is not None

    banner.setProperty("updateState", "available")
    assert action.property("text") == "Actualizar"
    assert "0.4.0" in str(label.property("text"))

    banner.setProperty("updateState", "downloading")
    # Clicking again mid-download would start a second one over the same staged file.
    assert action.property("enabled") is False

    banner.setProperty("updateState", "ready")
    assert action.property("text") == "Reiniciar ahora"
    assert action.property("enabled") is True


def test_update_banner_fill_tracks_progress(qapp: object) -> None:
    _component, banner = _instantiate("UpdateBanner.qml")
    banner.setProperty("updateState", "downloading")
    banner.setProperty("width", 200)
    fill = banner.findChild(QObject, "progressFill")
    assert fill is not None

    banner.setProperty("progress", 0.5)
    assert fill.property("width") == pytest.approx(100)

    banner.setProperty("updateState", "ready")
    assert fill.property("width") == 0


def test_header_hides_the_update_check_when_it_cannot_work(qapp: object) -> None:
    _component, header = _instantiate("HeaderBar.qml")
    button = header.findChild(QObject, "checkUpdatesButton")
    assert button is not None

    assert button.property("visible") is False

    header.setProperty("canCheckForUpdates", True)

    assert button.property("visible") is True


def test_clip_pad_wraps_the_shortcut_in_a_badge(qapp: object) -> None:
    _component, pad = _instantiate("ClipPad.qml")
    badge = pad.findChild(QObject, "shortcutBadge")
    assert badge is not None
    assert badge.property("radius") > 0
    # A pad with no shortcut must not show an empty chip.
    assert badge.property("visible") is False

    pad.setProperty("width", 120)
    pad.setProperty("height", 80)
    pad.setProperty("shortcut", "<ctrl>+<alt>+<shift>+F12")

    assert badge.property("visible") is True
    label = pad.findChild(QObject, "shortcutLabel")
    assert label is not None
    assert label.property("text") == "<ctrl>+<alt>+<shift>+F12"
    # Capped to the pad's inner width, which is what makes the label elide rather
    # than spill out of the pad.
    assert badge.property("width") <= 120 - 16


def test_effect_block_offers_a_visible_reorder_button(qapp: object) -> None:
    _component, block = _instantiate("EffectBlock.qml")
    block.setProperty("width", 166)
    drag_handle = block.findChild(QObject, "effectDragHandle")
    reorder_button = block.findChild(QObject, "effectReorderButton")

    assert isinstance(block, QQuickItem)
    assert isinstance(drag_handle, QQuickItem)
    assert isinstance(reorder_button, QQuickItem)
    assert reorder_button.property("visible") is True
    assert reorder_button.property("text") == "✥"
    assert reorder_button.property("implicitContentWidth") <= reorder_button.property(
        "availableWidth"
    )
    handle_origin = drag_handle.mapToItem(reorder_button, QPointF())
    assert handle_origin == QPointF(0, 0)
    assert drag_handle.width() == reorder_button.width()
    assert drag_handle.height() == reorder_button.height()


def test_effect_block_drag_handle_does_not_cover_the_bypass_switch(qapp: object) -> None:
    _component, block = _instantiate("EffectBlock.qml")
    block.setProperty("width", 166)
    drag_handle = block.findChild(QObject, "effectDragHandle")
    bypass = block.findChild(QObject, "effectBypass")

    assert isinstance(block, QQuickItem)
    assert isinstance(drag_handle, QQuickItem)
    assert isinstance(bypass, QQuickItem)
    bypass_left = bypass.mapToItem(block, QPointF()).x()
    handle_right = drag_handle.mapToItem(
        block, QPointF(drag_handle.width(), 0)
    ).x()
    assert handle_right <= bypass_left
