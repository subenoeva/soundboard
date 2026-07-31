"""run_gui: client resolution and the full happy-path boot with fakes.

The QWidgets-era flow this file used to cover (LoginDialog / DeviceSettingsDialog /
MainWindow) moved into AppController + Main.qml (see test_controller.py and
test_qml_main.py); only what still applies to the new run_gui survives here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui import app as app_module
from tests.unit.test_controller import FakeStore


def test_run_gui_reports_an_unbuildable_client_instead_of_crashing(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []

    def _raise() -> object:
        raise RuntimeError("SUPABASE_URL no configurada")

    monkeypatch.setattr(app_module, "build_client", _raise)
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: shown.append(text)
    )

    exit_code = app_module.run_gui(
        client=None,
        store=FakeStore(),
        backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 1
    assert shown == ["SUPABASE_URL no configurada"]


def test_run_gui_smoke_without_exec(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "default_layout_path", lambda: tmp_path / "layout.json")
    monkeypatch.setattr(app_module, "_default_cache_dir", lambda: tmp_path / "cache")
    code = app_module.run_gui(
        [], backend=FakeBackend(), client=FakeRemoteClient(), store=FakeStore(),
        hotkeys=FakeHotkeyManager(), exec_app=False,
    )
    assert code == 0


def test_qml_root_resolves_relative_to_the_package_in_a_checkout() -> None:
    assert app_module.qml_root() == Path(app_module.__file__).parent / "qml"


def test_qml_root_resolves_under_meipass_when_bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", "C:/bundle", raising=False)
    assert app_module.qml_root() == Path("C:/bundle") / "soundboard" / "ui" / "qml"
