"""Blocking login/sign-up dialog, shown when there is no valid Supabase session."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from soundboard.remote import auth
from soundboard.remote.client import SessionStore
from soundboard.remote.models import RemoteClient, Session


class LoginDialog(QDialog):
    def __init__(
        self,
        client: RemoteClient,
        store: SessionStore,
        display_name_prompt: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iniciar sesión")
        self._client = client
        self._store = store
        self._display_name_prompt = display_name_prompt or self._email_local_part
        self.session: Session | None = None

        self._email = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._error = QLabel()
        self._error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Email", self._email)
        form.addRow("Contraseña", self._password)

        login_button = QPushButton("Ingresar")
        login_button.clicked.connect(self._log_in)
        signup_button = QPushButton("Crear cuenta")
        signup_button.clicked.connect(self._sign_up)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(login_button)
        layout.addWidget(signup_button)

    def _email_local_part(self) -> str:
        return self._email.text().split("@")[0]

    def _log_in(self) -> None:
        try:
            self.session = auth.log_in(
                self._client,
                self._store,
                self._email.text(),
                self._password.text(),
                self._display_name_prompt,
            )
        except Exception as exc:  # dialog boundary: show it, keep the dialog open
            self._error.setStyleSheet("color: red")
            self._error.setText(str(exc))
            return
        self.accept()

    def _sign_up(self) -> None:
        try:
            auth.sign_up(self._client, self._email.text(), self._password.text())
        except Exception as exc:  # dialog boundary: show it, keep the dialog open
            self._error.setStyleSheet("color: red")
            self._error.setText(str(exc))
            return
        self._error.setStyleSheet("color: green")
        self._error.setText("cuenta creada — confirmá el email antes de ingresar")
