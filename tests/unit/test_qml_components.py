"""Every QML component must instantiate standalone under the offscreen platform."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML_DIR = Path(__file__).parents[2] / "src" / "soundboard" / "ui" / "qml"

COMPONENTS = sorted(p for p in (QML_DIR / "components").glob("*.qml"))


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
