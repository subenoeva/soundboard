"""GUI entry point: resolves the session, the grid layout and the devices, then runs
the window."""

from __future__ import annotations

import sys
from pathlib import Path

import platformdirs
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from soundboard.audio.backend import AudioBackend
from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.portaudio import PortAudioBackend, find_device
from soundboard.hotkeys import HotkeyManager, PynputHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import auth
from soundboard.remote.client import SessionStore, build_client
from soundboard.remote.models import RemoteClient
from soundboard.ui.device_dialog import DeviceSettingsDialog
from soundboard.ui.layout_store import GridLayout, default_layout_path, load_layout, save_layout
from soundboard.ui.login_dialog import LoginDialog
from soundboard.ui.main_window import MainWindow


def _default_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("soundboard")) / "pcm"


def _start_engine_with_retry(
    backend: AudioBackend, layout: GridLayout, layout_path: Path
) -> AudioEngine | None:
    """Resolve devices and start the engine, reopening the device dialog on failure.

    A saved device name that no longer matches anything (unplugged hardware, a
    renamed cable) or a real PortAudio failure both land here rather than crashing —
    the spec requires a way back into device selection, never a silent exit.
    """
    while True:
        try:
            devices = backend.list_devices()
            microphone = find_device(devices, layout.mic, want_input=True)
            cable = find_device(devices, layout.out, want_input=False)
            engine = AudioEngine(
                backend,
                EngineConfig(
                    blocksize=layout.blocksize,
                    input_device=microphone.index,
                    output_device=cable.index,
                    output_channels=min(2, cable.max_output_channels) or 1,
                ),
            )
            engine.start()
        except Exception as exc:
            QMessageBox.warning(None, "No se pudo iniciar el motor", str(exc))
            dialog = DeviceSettingsDialog(backend, current=layout)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            layout.mic = dialog.selected_mic()
            layout.out = dialog.selected_out()
            layout.rows = dialog.selected_rows()
            layout.cols = dialog.selected_cols()
            save_layout(layout_path, layout)
            continue
        return engine


def run_gui(
    argv: list[str] | None = None,
    *,
    backend: AudioBackend | None = None,
    client: RemoteClient | None = None,
    store: SessionStore | None = None,
    hotkeys: HotkeyManager | None = None,
    exec_app: bool = True,
) -> int:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)

    if client is None:
        try:
            client = build_client()
        except Exception as exc:
            # Double-clicked by a non-technical user: a corrupt settings.json or an exe
            # built without baked-in defaults would otherwise be a raw traceback dialog
            # on Windows and complete silence under a Linux file manager.
            QMessageBox.critical(None, "Configuración inválida", str(exc))
            return 1

    store = store if store is not None else SessionStore()
    backend = backend if backend is not None else PortAudioBackend()
    hotkeys = hotkeys if hotkeys is not None else PynputHotkeyManager()

    if store.load() is None:
        login = LoginDialog(client, store)
        if login.exec() != QDialog.DialogCode.Accepted:
            return 1
        assert login.session is not None
        session = login.session
    else:
        session = auth.require_session(client, store)

    layout_path = default_layout_path()
    layout = load_layout(layout_path)
    if layout is None:
        dialog = DeviceSettingsDialog(backend)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return 1
        layout = GridLayout(
            rows=dialog.selected_rows(),
            cols=dialog.selected_cols(),
            mic=dialog.selected_mic(),
            out=dialog.selected_out(),
            blocksize=256,
        )
        save_layout(layout_path, layout)

    engine = _start_engine_with_retry(backend, layout, layout_path)
    if engine is None:
        return 1

    cache = SoundCache(_default_cache_dir())
    window = MainWindow(engine, client, session, cache, hotkeys, layout, layout_path)
    window.show()

    if not exec_app:
        return 0
    return app.exec()
