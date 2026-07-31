"""Every QML component must instantiate standalone under the offscreen platform."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtQml import QQmlComponent, QQmlEngine

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
            "LibraryPopup.qml", "ShortcutPopup.qml", "ColorPopup.qml"} <= names


def test_views_exist() -> None:
    names = {p.name for p in QML_DIR.glob("*.qml")}
    assert {"Main.qml", "LoginView.qml", "DeviceSetupView.qml",
            "BoardView.qml", "Theme.qml"} <= names


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
