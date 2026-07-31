from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from soundboard.ui.grid import ClipGrid


def _setup_menu_mock(monkeypatch: Any, action_index: int = 0) -> None:
    """Patch QMenu.__init__ to override exec on each instance.

    Args:
        monkeypatch: pytest's monkeypatch fixture
        action_index: Which action to return (0 for "Asignar atajo", 1 for "Vaciar celda")
    """
    original_init = QMenu.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_init(self, *args, **kwargs)
        # Override exec method on this instance to return the specified action
        # without showing a menu dialog
        self.exec = lambda pos: (
            self.actions()[action_index]
            if self.actions() and len(self.actions()) > action_index
            else None
        )
        return result

    monkeypatch.setattr(QMenu, "__init__", patched_init)


def _setup_menu_mock_capture(monkeypatch: Any, captured: list[Any]) -> None:
    """Patch QMenu.__init__ to capture menu instances without selecting an action.

    Args:
        monkeypatch: pytest's monkeypatch fixture
        captured: List to append captured menu instances to
    """
    original_init = QMenu.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_init(self, *args, **kwargs)
        captured.append(self)
        # Override exec method to return None (no action selected)
        self.exec = lambda pos: None
        return result

    monkeypatch.setattr(QMenu, "__init__", patched_init)


def test_grid_creates_rows_times_cols_buttons(qtbot: Any) -> None:
    grid = ClipGrid(rows=2, cols=3)
    qtbot.addWidget(grid)

    for index in range(6):
        assert grid.button_at(index).index == index


def test_clicking_a_button_emits_play_requested(qtbot: Any) -> None:
    grid = ClipGrid(rows=1, cols=2)
    qtbot.addWidget(grid)
    received: list[int] = []
    grid.play_requested.connect(received.append)

    qtbot.mouseClick(grid.button_at(1), Qt.MouseButton.LeftButton)

    assert received == [1]


def test_dropping_on_a_button_relays_file_dropped_from_the_grid(qtbot: Any) -> None:
    grid = ClipGrid(rows=1, cols=2)
    qtbot.addWidget(grid)
    received: list[tuple[int, str]] = []
    grid.file_dropped.connect(lambda index, path: received.append((index, path)))

    grid.button_at(1).file_dropped.emit(1, "C:/clips/laugh.wav")

    assert received == [(1, "C:/clips/laugh.wav")]


def test_context_menu_assign_shortcut_emits_the_right_signal(qtbot: Any, monkeypatch: Any) -> None:
    _setup_menu_mock(monkeypatch, action_index=0)

    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)
    received: list[int] = []
    grid.assign_shortcut_requested.connect(received.append)

    grid._show_context_menu(0)

    assert received == [0]


def test_context_menu_clear_emits_the_right_signal(qtbot: Any, monkeypatch: Any) -> None:
    _setup_menu_mock(monkeypatch, action_index=1)

    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)
    received: list[int] = []
    grid.clear_requested.connect(received.append)

    grid._show_context_menu(0)

    assert received == [0]


def test_context_menu_offers_assign_from_library_only_when_the_cell_is_empty(
    qtbot: Any, monkeypatch: Any
) -> None:
    captured_menus: list[Any] = []
    _setup_menu_mock_capture(monkeypatch, captured_menus)

    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)

    grid._show_context_menu(0)
    assert [a.text() for a in captured_menus[0].actions()] == [
        "Asignar atajo",
        "Vaciar celda",
        "Asignar desde biblioteca",
    ]

    grid.button_at(0).assign("airhorn", None)
    grid._show_context_menu(0)
    assert [a.text() for a in captured_menus[1].actions()] == [
        "Asignar atajo",
        "Vaciar celda",
    ]


def test_context_menu_assign_from_library_emits_the_right_signal(
    qtbot: Any, monkeypatch: Any
) -> None:
    _setup_menu_mock(monkeypatch, action_index=2)

    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)
    received: list[int] = []
    grid.assign_from_library_requested.connect(received.append)

    grid._show_context_menu(0)

    assert received == [0]
