"""GUI entry point: builds the AppController, loads Main.qml, wires the tray."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import platformdirs
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QMessageBox

from soundboard.audio.backend import AudioBackend
from soundboard.audio.portaudio import PortAudioBackend
from soundboard.hotkeys import HotkeyManager, PynputHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.client import SessionStore, build_client
from soundboard.remote.models import RemoteClient
from soundboard.ui.controller import AppController
from soundboard.ui.engine_factory import Store
from soundboard.ui.layout_store import default_layout_path
from soundboard.ui.tray import TrayIcon

if sys.platform == "win32":
    # PySide6 adds its own package directory to PATH in PySide6/__init__.py, but on
    # some Windows setups that isn't enough for the QML engine's internal DLL loader to
    # resolve a QML plugin's own dependencies — e.g. QtQuick's qtquick2plugin.dll
    # depending on Qt6Quick.dll — failing with "the specified module could not be
    # found" even though the file sits right next to PySide6/__init__.py. Registering
    # the directory via os.add_dll_directory (rather than relying on PATH) fixes it;
    # must run before the first QQmlEngine is constructed. Mirrors the equivalent fix
    # in tests/unit/conftest.py, which only runs under pytest and never touches this
    # production entry point.
    import os

    import PySide6

    _pyside6_dir = Path(PySide6.__file__).resolve().parent
    os.add_dll_directory(str(_pyside6_dir))


def _default_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("soundboard")) / "pcm"


def qml_root() -> Path:
    """Locate qml/ both in a checkout and inside a PyInstaller bundle."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        return Path(bundled) / "soundboard" / "ui" / "qml"
    return Path(__file__).parent / "qml"


def run_gui(
    argv: list[str] | None = None,
    *,
    backend: AudioBackend | None = None,
    client: RemoteClient | None = None,
    store: Store | None = None,
    hotkeys: HotkeyManager | None = None,
    exec_app: bool = True,
) -> int:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)

    if client is None:
        try:
            client = build_client()
        except Exception as exc:
            # Double-clicked by a non-technical user: a corrupt settings.json
            # must be a dialog, not a traceback (or silence under a file manager).
            QMessageBox.critical(None, "Configuración inválida", str(exc))
            return 1

    controller = AppController(
        client=client,
        store=store if store is not None else SessionStore(),
        backend=backend if backend is not None else PortAudioBackend(),
        hotkeys=hotkeys if hotkeys is not None else PynputHotkeyManager(),
        cache=SoundCache(_default_cache_dir()),
        layout_path=default_layout_path(),
    )
    controller.bootstrap()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("App", controller)
    engine.load(str(qml_root() / "Main.qml"))
    if not engine.rootObjects():
        # bootstrap() may already have opened the audio devices and the hotkey hook;
        # bailing out without shutdown() leaves both running until the interpreter dies.
        controller.shutdown()
        QMessageBox.critical(None, "Error de interfaz", "No se pudo cargar la interfaz")
        return 1
    window = cast(QQuickWindow, engine.rootObjects()[0])

    def quit_app() -> None:
        app.quit()

    tray = TrayIcon(on_show=window.show, on_quit=quit_app)
    tray.show()
    app.aboutToQuit.connect(controller.shutdown)

    if not exec_app:
        controller.shutdown()
        return 0
    return app.exec()
