from typing import Any

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from soundboard.ui.clip_button import ClipButton, ClipState


def _drop_event(path: str) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    return QDropEvent(
        QPointF(1, 1),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_clip_button_starts_empty(qtbot: Any) -> None:
    button = ClipButton(index=0)
    qtbot.addWidget(button)

    assert button.state is ClipState.EMPTY
    assert "vac" in button.text().lower()


def test_assign_moves_to_idle_and_shows_name_and_shortcut(qtbot: Any) -> None:
    button = ClipButton(index=0)
    qtbot.addWidget(button)

    button.assign("airhorn", "<ctrl>+<alt>+1")

    assert button.state is ClipState.IDLE
    assert "airhorn" in button.text()
    assert "<ctrl>+<alt>+1" in button.text()


def test_loading_disables_the_button_and_playing_re_enables_it(qtbot: Any) -> None:
    button = ClipButton(index=0)
    qtbot.addWidget(button)
    button.assign("airhorn", None)

    button.set_state(ClipState.LOADING)
    assert not button.isEnabled()

    button.set_state(ClipState.PLAYING)
    assert button.isEnabled()


def test_clear_returns_to_empty(qtbot: Any) -> None:
    button = ClipButton(index=0)
    qtbot.addWidget(button)
    button.assign("airhorn", "<ctrl>+1")

    button.clear()

    assert button.state is ClipState.EMPTY
    assert "vac" in button.text().lower()


def test_dropping_a_file_on_an_empty_cell_emits_file_dropped(qtbot: Any) -> None:
    button = ClipButton(index=3)
    qtbot.addWidget(button)
    received = []
    button.file_dropped.connect(lambda index, path: received.append((index, path)))

    button.dropEvent(_drop_event("C:/clips/laugh.wav"))

    assert received == [(3, "C:/clips/laugh.wav")]


def test_dropping_a_file_on_an_occupied_cell_is_ignored(qtbot: Any) -> None:
    button = ClipButton(index=0)
    qtbot.addWidget(button)
    button.assign("airhorn", None)
    received = []
    button.file_dropped.connect(lambda index, path: received.append((index, path)))

    event = _drop_event("C:/clips/laugh.wav")
    button.dragEnterEvent(event)  # type: ignore

    assert not event.isAccepted()
