from typing import Any

from PySide6.QtWidgets import QDialog

from soundboard.remote.client import SessionStore
from soundboard.remote.fake_client import FakeRemoteClient
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


def test_login_dialog_logs_in_and_accepts(qtbot: Any) -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = SessionStore(backend=_DictKeyringBackend())
    dialog = LoginDialog(client, store, display_name_prompt=lambda: "Pablo")
    qtbot.addWidget(dialog)
    dialog._email.setText("a@x.com")
    dialog._password.setText("hunter2")

    dialog._log_in()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.session is not None
    assert store.load() is not None


def test_login_dialog_shows_an_error_and_stays_open_on_bad_credentials(qtbot: Any) -> None:
    client = FakeRemoteClient()
    store = SessionStore(backend=_DictKeyringBackend())
    dialog = LoginDialog(client, store)
    qtbot.addWidget(dialog)
    dialog._email.setText("nope@x.com")
    dialog._password.setText("wrong")

    dialog._log_in()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error.text()


def test_login_dialog_sign_up_shows_a_confirmation_message(qtbot: Any) -> None:
    client = FakeRemoteClient()
    store = SessionStore(backend=_DictKeyringBackend())
    dialog = LoginDialog(client, store)
    qtbot.addWidget(dialog)
    dialog._email.setText("new@x.com")
    dialog._password.setText("hunter2")

    dialog._sign_up()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "confirm" in dialog._error.text().lower()
