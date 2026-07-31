"""GridModel: headless list model over GridLayout, no QML rendering needed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.grid_model import (
    STATE_EMPTY,
    STATE_IDLE,
    GridModel,
)
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource


class FakeEngine:
    def __init__(self) -> None:
        self.played: list[np.ndarray] = []
        self.states: list[tuple[int, float]] = []
        self.stopped = False
        self._next = 0

    def play(self, pcm: np.ndarray, **kwargs: object) -> int:
        self.played.append(pcm)
        self._next += 1
        return self._next

    def stop_all(self) -> None:
        self.stopped = True

    def stop(self) -> None:
        pass


@pytest.fixture
def hotkeys() -> FakeHotkeyManager:
    return FakeHotkeyManager()


def make_model(
    tmp_path: Path, hotkeys: FakeHotkeyManager, cells: list[Cell] | None = None
) -> tuple[GridModel, FakeEngine, GridLayout]:
    engine = FakeEngine()
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("user@example.com")
    layout = GridLayout(rows=2, cols=3, mic="m", out="o", blocksize=256,
                        cells=cells or [])
    model = GridModel(engine, client, session, SoundCache(tmp_path / "cache"),
                      hotkeys, layout, tmp_path / "layout.json")
    return model, engine, layout


def test_row_count_is_rows_times_cols(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, _, _ = make_model(tmp_path, hotkeys)
    assert model.rowCount() == 6


def test_data_for_empty_and_assigned_cells(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    cell = Cell(index=1, source=LocalSource(path="a.wav"), name="airhorn",
                shortcut="<ctrl>+1", color="#e8590c")
    model, _, _ = make_model(tmp_path, hotkeys, cells=[cell])
    empty = model.index(0)
    assigned = model.index(1)
    assert model.data(empty, GridModel.STATE_ROLE) == STATE_EMPTY
    assert model.data(empty, GridModel.NAME_ROLE) == ""
    assert model.data(assigned, GridModel.STATE_ROLE) == STATE_IDLE
    assert model.data(assigned, GridModel.NAME_ROLE) == "airhorn"
    assert model.data(assigned, GridModel.SHORTCUT_ROLE) == "<ctrl>+1"
    assert model.data(assigned, GridModel.COLOR_ROLE) == "#e8590c"
    assert model.data(assigned, GridModel.PROGRESS_ROLE) == 0.0


def test_role_names_are_qml_safe(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, _, _ = make_model(tmp_path, hotkeys)
    names = set(model.roleNames().values())
    assert names == {b"name", b"shortcut", b"cellColor", b"cellState", b"progress"}


def test_saved_shortcuts_are_registered_at_init(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a", shortcut="<ctrl>+1")
    _model, _, _ = make_model(tmp_path, hotkeys, cells=[cell])
    hotkeys.trigger("<ctrl>+1")  # no debe lanzar KeyError
