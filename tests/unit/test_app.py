from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QDialog

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.remote.client import SessionStore
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui import app as app_module
from soundboard.ui.app import run_gui
from soundboard.ui.layout_store import GridLayout, save_layout
from soundboard.ui.login_dialog import LoginDialog


class _DictKeyringBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def test_run_gui_aborts_when_login_is_cancelled(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(LoginDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    exit_code = run_gui(
        client=FakeRemoteClient(),
        store=SessionStore(backend=_DictKeyringBackend()),
        backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 1


def test_run_gui_happy_path_with_existing_session_and_layout(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)

    layout_path = tmp_path / "ui_layout.json"
    save_layout(
        layout_path,
        GridLayout(rows=1, cols=1, mic="fake microphone", out="fake cable", blocksize=64),
    )
    monkeypatch.setattr(app_module, "default_layout_path", lambda: layout_path)

    exit_code = run_gui(
        client=client,
        store=store,
        backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 0


def _session_and_layout(tmp_path: Path, mic: str) -> tuple[FakeRemoteClient, SessionStore, Path]:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)
    layout_path = tmp_path / "ui_layout.json"
    save_layout(layout_path, GridLayout(rows=1, cols=1, mic=mic, out="fake cable", blocksize=64))
    return client, store, layout_path


def test_run_gui_reopens_the_device_dialog_when_the_saved_device_is_missing(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from soundboard.ui.device_dialog import DeviceSettingsDialog

    client, store, layout_path = _session_and_layout(tmp_path, mic="does-not-exist")
    monkeypatch.setattr(app_module, "default_layout_path", lambda: layout_path)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(DeviceSettingsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DeviceSettingsDialog, "selected_mic", lambda self: "fake microphone")
    monkeypatch.setattr(DeviceSettingsDialog, "selected_out", lambda self: "fake cable")
    monkeypatch.setattr(DeviceSettingsDialog, "selected_rows", lambda self: 1)
    monkeypatch.setattr(DeviceSettingsDialog, "selected_cols", lambda self: 1)

    exit_code = run_gui(
        client=client, store=store, backend=FakeBackend(), hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 0


def test_run_gui_aborts_if_the_device_dialog_is_cancelled_after_a_missing_device(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from soundboard.ui.device_dialog import DeviceSettingsDialog

    client, store, layout_path = _session_and_layout(tmp_path, mic="does-not-exist")
    monkeypatch.setattr(app_module, "default_layout_path", lambda: layout_path)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(DeviceSettingsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    exit_code = run_gui(
        client=client, store=store, backend=FakeBackend(), hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 1
