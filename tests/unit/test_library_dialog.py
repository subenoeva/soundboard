from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from PySide6.QtWidgets import QDialog

from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.remote.models import Sound
from soundboard.ui.library_dialog import LibraryDialog


def _add_sound(
    client: FakeRemoteClient, owner_email: str, tmp_path: Path, filename: str, sound_name: str
) -> Sound:
    session = client.sign_in_as_new_user(owner_email)
    client.insert(
        "profiles", {"id": session.user_id, "display_name": owner_email.split("@")[0]}
    )
    path = tmp_path / filename
    sf.write(str(path), np.zeros(480, dtype=np.float32), 48_000)
    return sounds.add_sound(client, session, str(path), name=sound_name)


def test_library_dialog_defers_the_load_until_after_construction(
    qtbot: Any, tmp_path: Path
) -> None:
    """The dialog must be showable before the network round-trip starts (see #3):
    the list is still empty right after __init__, and only gets populated once the
    deferred (QTimer.singleShot(0, ...)) load fires on the next event-loop turn."""
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)

    assert dialog._list.count() == 0

    qtbot.wait(10)

    assert dialog._list.count() == 1


def test_library_dialog_lists_each_sounds_name_and_owner(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    _add_sound(client, "beto@x.com", tmp_path, "b.wav", "applause")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    qtbot.wait(10)

    texts = {dialog._list.item(i).text() for i in range(dialog._list.count())}

    assert texts == {"airhorn — ana", "applause — beto"}


def test_selecting_a_row_and_accepting_exposes_selected_id_and_name(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    sound = _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    qtbot.wait(10)
    dialog._list.setCurrentRow(0)

    assert dialog._ok_button.isEnabled()

    dialog._accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_id == sound.id
    assert dialog.selected_name == "airhorn"


def test_accepting_without_a_selection_does_nothing(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    qtbot.wait(10)

    assert not dialog._ok_button.isEnabled()

    dialog._accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.selected_id is None


def test_ok_button_starts_disabled_and_enables_once_a_row_is_selected(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)

    assert not dialog._ok_button.isEnabled()

    qtbot.wait(10)

    assert not dialog._ok_button.isEnabled()

    dialog._list.setCurrentRow(0)

    assert dialog._ok_button.isEnabled()


def test_empty_library_shows_a_message_and_hides_the_list(qtbot: Any) -> None:
    client = FakeRemoteClient()
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    qtbot.wait(10)

    assert "No hay sonidos compartidos" in dialog._error.text()
    assert dialog._list.isHidden()
    assert not dialog._error.isHidden()
    assert dialog._retry_button.isHidden()


class _FlakyOnceClient(FakeRemoteClient):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_select = False

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if table == "sounds" and self.fail_next_select:
            self.fail_next_select = False
            raise RuntimeError("sin red")
        return super().select(table, filters=filters)


def test_a_failed_load_shows_the_error_and_retry_reloads_it(qtbot: Any, tmp_path: Path) -> None:
    client = _FlakyOnceClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    client.fail_next_select = True

    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    qtbot.wait(10)

    assert "sin red" in dialog._error.text()
    assert dialog._list.isHidden()
    assert not dialog._error.isHidden()
    assert not dialog._retry_button.isHidden()

    dialog._retry_button.click()

    assert dialog._list.count() == 1
    assert not dialog._list.isHidden()
    assert dialog._error.isHidden()
