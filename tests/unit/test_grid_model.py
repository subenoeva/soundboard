"""GridModel: headless list model over GridLayout, no QML rendering needed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import QUrl

from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.grid_model import (
    STATE_EMPTY,
    STATE_IDLE,
    STATE_LOADING,
    STATE_PLAYING,
    GridModel,
)
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource


def make_wav(path: Path) -> Path:
    sf.write(str(path), np.full(480, 0.5, dtype=np.float32), 48_000)
    return path


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


def test_play_local_cell_plays_and_tracks_voice(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: object
) -> None:
    wav = make_wav(tmp_path / "a.wav")
    cell = Cell(index=0, source=LocalSource(path=str(wav)), name="a")
    model, engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.play(0)
    assert len(engine.played) == 1
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_PLAYING


def test_play_empty_cell_is_noop(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, engine, _ = make_model(tmp_path, hotkeys)
    model.play(0)
    assert engine.played == []


def test_play_unreadable_local_file_toasts(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: object
) -> None:
    cell = Cell(index=0, source=LocalSource(path=str(tmp_path / "missing.wav")), name="x")
    model, engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    messages: list[str] = []
    model.toast.connect(messages.append)
    model.play(0)
    assert engine.played == []
    assert messages


def test_apply_voice_states_updates_progress_and_clears_on_end(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    wav = make_wav(tmp_path / "a.wav")
    cell = Cell(index=0, source=LocalSource(path=str(wav)), name="a")
    model, _engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.play(0)  # FakeEngine devuelve voice_id 1
    model.apply_voice_states([(1, 0.4)])
    assert model.data(model.index(0), GridModel.PROGRESS_ROLE) == pytest.approx(0.4)
    model.apply_voice_states([])
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_IDLE
    assert model.data(model.index(0), GridModel.PROGRESS_ROLE) == 0.0


def test_play_remote_cell_loads_then_plays(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: Any
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("user@example.com")
    wav = make_wav(tmp_path / "a.wav")
    sound = sounds.add_sound(client, session, str(wav), name="laugh")
    engine = FakeEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="m", out="o", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id=sound.id), name="laugh")],
    )
    model = GridModel(
        engine, client, session, SoundCache(tmp_path / "cache"), hotkeys, layout,
        tmp_path / "layout.json",
    )

    model.play(0)

    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_LOADING
    qtbot.waitUntil(lambda: len(engine.played) == 1, timeout=2000)
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_PLAYING


def test_play_remote_cell_download_failure_resets_to_idle_and_toasts(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: Any
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("user@example.com")
    engine = FakeEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="m", out="o", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id="missing-id"), name="ghost")],
    )
    model = GridModel(
        engine, client, session, SoundCache(tmp_path / "cache"), hotkeys, layout,
        tmp_path / "layout.json",
    )
    messages: list[str] = []
    model.toast.connect(messages.append)

    model.play(0)

    qtbot.waitUntil(
        lambda: model.data(model.index(0), GridModel.STATE_ROLE) == STATE_IDLE, timeout=2000
    )
    assert engine.played == []
    assert messages


def test_assign_local_valid_file_uploads_and_sets_remote_idle(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: Any
) -> None:
    wav = make_wav(tmp_path / "airhorn.wav")
    model, _engine, layout = make_model(tmp_path, hotkeys)

    # Also exercises the file: URL branch of assign_local's path parsing.
    model.assign_local(0, QUrl.fromLocalFile(str(wav)).toString())

    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_LOADING
    qtbot.waitUntil(
        lambda: model.data(model.index(0), GridModel.STATE_ROLE) == STATE_IDLE, timeout=2000
    )
    assert model.data(model.index(0), GridModel.NAME_ROLE) == "airhorn"
    cell = next(c for c in layout.cells if c.index == 0)
    assert isinstance(cell.source, RemoteSource)


def test_assign_local_invalid_file_toasts_and_stays_empty(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    bogus = tmp_path / "not_audio.txt"
    bogus.write_text("hello")
    model, _engine, _layout = make_model(tmp_path, hotkeys)
    messages: list[str] = []
    model.toast.connect(messages.append)

    model.assign_local(0, str(bogus))

    assert messages
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_EMPTY


def test_assign_local_occupied_cell_is_noop(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    wav = make_wav(tmp_path / "airhorn.wav")
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _engine, _layout = make_model(tmp_path, hotkeys, cells=[cell])

    model.assign_local(0, str(wav))

    assert model.data(model.index(0), GridModel.NAME_ROLE) == "a"
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_IDLE


def test_assign_remote_sets_cell_and_saves(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    model, _, layout = make_model(tmp_path, hotkeys)
    model.assign_remote(2, "sound-id-1", "applause")
    assert model.data(model.index(2), GridModel.NAME_ROLE) == "applause"
    assert (tmp_path / "layout.json").exists()
    assert any(c.index == 2 for c in layout.cells)


def test_assign_remote_refuses_occupied_cell(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.assign_remote(0, "sound-id-1", "applause")
    assert model.data(model.index(0), GridModel.NAME_ROLE) == "a"


def test_clear_cell_unregisters_shortcut_and_empties(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a", shortcut="<ctrl>+1")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.clear_cell(0)
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_EMPTY
    assert layout.cells == []
    with pytest.raises(KeyError):
        hotkeys.trigger("<ctrl>+1")


def test_set_shortcut_registers_and_persists(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.set_shortcut(0, "<ctrl>+2")
    assert layout.cells[0].shortcut == "<ctrl>+2"
    hotkeys.trigger("<ctrl>+2")  # no lanza


def test_set_shortcut_invalid_combo_toasts_and_keeps_cell(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    messages: list[str] = []
    model.toast.connect(messages.append)
    model.set_shortcut(0, "not-a-combo")
    assert messages
    assert layout.cells[0].shortcut is None


def test_set_color_persists_and_clears(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.set_color(0, "#e8590c")
    assert model.data(model.index(0), GridModel.COLOR_ROLE) == "#e8590c"
    model.set_color(0, "")
    assert layout.cells[0].color is None
